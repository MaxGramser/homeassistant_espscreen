// A direct call's server and its task (call_serve.h, docs/CALLS.md "Screen to screen").
#include "esphome/core/defines.h"
#include "picture_engine.h"
#include "call_serve.h"

#ifdef CALL_SERVE
#include <atomic>
#include <cerrno>
#include <esp_heap_caps.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/stream_buffer.h>
#include <freertos/task.h>
#include <lwip/sockets.h>
#include <netinet/in.h>
#include <netinet/tcp.h>

#include "esphome/core/hal.h"
#include "esphome/core/log.h"
#include "glass.h"
#include "psram_task.h"
#include "roomy.h"
#include "talk_uplink.h"

namespace call_serve {

static const char *const TAG = "call_serve";
// Below the wake word as every stream (docs/ARCHITECTURE.md, "Nothing of ours runs above the voice").
constexpr UBaseType_t TASK_PRIORITY = 2;
constexpr uint32_t TASK_STACK = 8192;
constexpr int TASK_CORE = 1;
constexpr size_t MIC_BUFFER = 12800;       // 400 ms between the microphone and the socket, as talk_uplink's
constexpr int QUALITY = 60;
// A picture's state between the camera's task, which fills it, and the server's, which sends it.
enum : int { EMPTY, FILLING, FULL };

namespace {
struct Run {
  std::string token, peer;
  psram_task::Task task;
  std::atomic<bool> stopping{false}, done{false}, viewed{false};
  StreamBufferHandle_t mic = nullptr;
  StaticStreamBuffer_t *control = nullptr;
  uint8_t *storage = nullptr;
  // The picture: RGB565 pixels the encoder reads, the JPEG it writes, and the PPA's client that scales a frame in.
  picture_engine::Client ppa = nullptr;
  uint8_t *pixels = nullptr, *jpeg = nullptr;
  size_t pixels_size = 0, jpeg_size = 0;
  Size size{0, 0};
  std::atomic<int> picture{EMPTY};
  int64_t next_us = 0;
  uint32_t since = 0, pictures = 0, sounds = 0, skipped = 0, encode_us = 0, blit_us = 0;
};
Run *run = nullptr;
// The camera's task reads `run` under this, never waiting; the main loop takes it before a run goes.
SemaphoreHandle_t lock = nullptr;
std::atomic<bool> muted{false}, picture_on{true}, wanted{false};

void free_run(Run *r) {
  if (r->mic) vStreamBufferDelete(r->mic);
  if (r->control) heap_caps_free(r->control);
  if (r->storage) roomy::release(r->storage);
  if (r->pixels) free(r->pixels);
  if (r->jpeg) free(r->jpeg);
  picture_engine::drop(r->ppa);
  delete r;
}

bool send_all(int fd, const void *data, size_t length) {
  const auto *at = static_cast<const uint8_t *>(data);
  while (length) {
    const int n = send(fd, at, length, 0);
    if (n <= 0) return false;
    at += n;
    length -= n;
  }
  return true;
}

// Whether the socket takes more without waiting: a picture is left out rather than held behind a slow link.
bool writable(int fd) {
  fd_set set;
  FD_ZERO(&set);
  FD_SET(fd, &set);
  timeval none{0, 0};
  return select(fd + 1, nullptr, &set, nullptr, &none) > 0;
}

// One who knocks: answered with the stream under the call's token and from the other screen's address, else refused.
int answer_one(Run &r, int listener) {
  sockaddr_in from{};
  socklen_t size = sizeof from;
  const int fd = accept(listener, reinterpret_cast<sockaddr *>(&from), &size);
  if (fd < 0) return -1;
  char address[16] = "";
  inet_ntoa_r(from.sin_addr, address, sizeof address);
  timeval wait{1, 0};
  setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &wait, sizeof wait);
  char request[256];
  size_t have = 0;
  while (have < sizeof request - 1) {
    const int n = recv(fd, request + have, sizeof request - 1 - have, 0);
    if (n <= 0) break;
    have += n;
    request[have] = 0;
    if (strstr(request, "\r\n")) break;
  }
  const bool known = r.peer.empty() || r.peer == address;
  if (!known || !asks_for(request, have, r.token)) {
    ESP_LOGW(TAG, "refused %s", address);
    send(fd, refusal(), strlen(refusal()), 0);
    ::close(fd);
    return -1;
  }
  int yes = 1;
  setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &yes, sizeof yes);
  timeval send_wait{2, 0};
  setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &send_wait, sizeof send_wait);
  if (!send_all(fd, answer(), strlen(answer()))) {
    ::close(fd);
    return -1;
  }
  ESP_LOGI(TAG, "%s watches and listens", address);
  return fd;
}

void task_main(void *arg) {
  auto *r = static_cast<Run *>(arg);
  const bool in_psram = psram_task::in_psram(r->task);
  int listener = socket(AF_INET, SOCK_STREAM, 0), fd = -1;
  sockaddr_in here{};
  here.sin_family = AF_INET;
  here.sin_port = htons(PORT);
  here.sin_addr.s_addr = htonl(INADDR_ANY);
  int yes = 1;
  if (listener >= 0) setsockopt(listener, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof yes);
  if (listener < 0 || bind(listener, reinterpret_cast<sockaddr *>(&here), sizeof here) != 0 || listen(listener, 1) != 0) {
    ESP_LOGW(TAG, "no room to serve the call (errno %d)", errno);
    if (listener >= 0) ::close(listener);
    listener = -1;
  }
  uint8_t part[SOUND_PART];
  size_t held = 0;
  char head[HEAD];
  while (listener >= 0 && !r->stopping.load()) {
    if (fd < 0) {
      // Nobody listens: the microphone's parts go by, and the door is looked at ten times a second.
      xStreamBufferReset(r->mic);
      held = 0;
      fd_set set;
      FD_ZERO(&set);
      FD_SET(listener, &set);
      timeval wait{0, 100 * 1000};
      if (select(listener + 1, &set, nullptr, nullptr, &wait) > 0) fd = answer_one(*r, listener);
      r->viewed.store(fd >= 0);
      wanted.store(fd >= 0 && picture_on.load(), std::memory_order_release);
      continue;
    }
    // The voice first: a whole part of 20 ms, whatever pieces the microphone gave it in.
    held += xStreamBufferReceive(r->mic, part + held, SOUND_PART - held, pdMS_TO_TICKS(40));
    bool gone = false;
    if (held == SOUND_PART) {
      held = 0;
      if (muted.load(std::memory_order_relaxed)) memset(part, 0, sizeof part);
      const size_t n = sound_head(head, sizeof head, SOUND_PART, static_cast<uint32_t>(esp_timer_get_time() / 1000));
      uint8_t out[HEAD + SOUND_PART];
      memcpy(out, head, n);
      memcpy(out + n, part, SOUND_PART);
      gone = !send_all(fd, out, n + SOUND_PART);
      if (!gone) ++r->sounds;
    }
    // Then a picture the camera's task filled: encoded here, sent when the link takes it now.
    wanted.store(picture_on.load(), std::memory_order_release);
    if (!gone && r->picture.load(std::memory_order_acquire) == FULL) {
      if (!writable(fd)) {
        ++r->skipped;
      } else {
        const int64_t from = esp_timer_get_time();
        glass::hold();
        const size_t length = picture_engine::encode(r->pixels, r->pixels_size, r->size.w, r->size.h, QUALITY, r->jpeg, r->jpeg_size);
        glass::release();
        r->encode_us += static_cast<uint32_t>(esp_timer_get_time() - from);
        if (length) {
          const size_t n = picture_head(head, sizeof head, length, static_cast<uint32_t>(esp_timer_get_time() / 1000));
          gone = !send_all(fd, head, n) || !send_all(fd, r->jpeg, length);
          if (!gone) ++r->pictures;
        } else {
          ++r->skipped;
        }
      }
      r->picture.store(EMPTY, std::memory_order_release);
    }
    if (gone) {
      ESP_LOGI(TAG, "the other screen went away (errno %d)", errno);
      ::close(fd);
      fd = -1;
    }
  }
  wanted.store(false, std::memory_order_release);
  r->viewed.store(false);
  if (fd >= 0) ::close(fd);
  if (listener >= 0) ::close(listener);
  const uint32_t seconds = std::max<uint32_t>(1, (esphome::millis() - r->since) / 1000);
  ESP_LOGI(TAG, "ended after %u s: %u pictures (%u left out), %u parts of voice, a picture scaled in %u us and encoded in %u us",
           (unsigned) seconds, (unsigned) r->pictures, (unsigned) r->skipped, (unsigned) r->sounds,
           (unsigned) (r->pictures ? r->blit_us / r->pictures : 0), (unsigned) (r->pictures ? r->encode_us / r->pictures : 0));
  r->done.store(true);
  psram_task::finish(in_psram);
}

// A run that ended is freed here, on the main loop, as its task may not delete itself.
void reap() {
  if (!run || !run->done.load()) return;
  talk_uplink::untap();
  psram_task::reap(run->task);
  if (lock) xSemaphoreTake(lock, portMAX_DELAY);
  Run *r = run;
  run = nullptr;
  if (lock) xSemaphoreGive(lock);
  free_run(r);
}
}  // namespace

bool start(const std::string &token, const std::string &peer) {
  reap();
  if (run) {
    // The same call said again (its camera turned, a held call back): nothing to start.
    if (!run->stopping.load() && run->token == token) return true;
    return false;  // the last one is still ending; the caller asks again
  }
  if (token.empty() || !talk_uplink::available()) return false;
  if (!lock) lock = xSemaphoreCreateMutex();
  auto *r = new Run;
  r->token = token;
  r->peer = peer;
  r->since = esphome::millis();
  r->ppa = picture_engine::client();
  r->control = static_cast<StaticStreamBuffer_t *>(heap_caps_malloc(sizeof(StaticStreamBuffer_t), MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
  r->storage = static_cast<uint8_t *>(roomy::allocate(MIC_BUFFER + 1));
  if (r->control && r->storage) r->mic = xStreamBufferCreateStatic(MIC_BUFFER + 1, 1, r->storage, r->control);
  if (!r->mic) {
    free_run(r);
    return false;
  }
  muted.store(false);
  picture_on.store(true);
  run = r;
  if (!psram_task::start(r->task, task_main, "call_serve", TASK_STACK, r, TASK_PRIORITY, TASK_CORE)) {
    run = nullptr;
    free_run(r);
    return false;
  }
  talk_uplink::tap(r->mic);
  ESP_LOGI(TAG, "serving this call on port %u", (unsigned) PORT);
  return true;
}

void stop() {
  reap();
  if (run) run->stopping.store(true);
  wanted.store(false, std::memory_order_release);
}

bool running() {
  reap();
  return run != nullptr && !run->stopping.load();
}
bool viewed() { return run != nullptr && run->viewed.load(); }
uint32_t started() { return run ? run->since : 0; }
void set_muted(bool m) { muted.store(m, std::memory_order_relaxed); }
void set_picture(bool on) { picture_on.store(on, std::memory_order_release); }
bool wants_picture() { return wanted.load(std::memory_order_acquire); }

void frame(const uint8_t *data, int width, int height, bool yuv420) {
  if (!wanted.load(std::memory_order_acquire) || !lock || !data) return;
  if (xSemaphoreTake(lock, 0) != pdTRUE) return;
  Run *r = run;
  const int64_t now = esp_timer_get_time();
  if (r && !r->stopping.load() && r->ppa && now >= r->next_us && r->picture.load(std::memory_order_acquire) == EMPTY) {
    if (!r->pixels) {
      // The first frame says the size: the buffers of a call's picture are made once for it.
      r->size = picture_size(width, height);
      if (r->size.w) {
        r->pixels = picture_engine::encode_input(static_cast<size_t>(r->size.w) * r->size.h * 2, &r->pixels_size);
        r->jpeg = picture_engine::encode_output(static_cast<size_t>(r->size.w) * r->size.h, &r->jpeg_size);
        if (r->pixels) memset(r->pixels, 0, r->pixels_size);  // what a frame of another shape leaves bare stays black
      }
    }
    picture_engine::Cut into = r->pixels && r->jpeg ? picture_engine::cut(width, height, r->size.w, r->size.h, false) : picture_engine::Cut{};
    if (into.ok) {
      if (yuv420) {  // the PPA reads YUV420 in pairs of pixels and rows
        into.in_x &= ~1;
        into.in_y &= ~1;
        into.in_w &= ~1;
        into.in_h &= ~1;
      }
      if (glass::try_hold()) {  // the glass is busy: this frame goes by, the next one comes
        r->picture.store(FILLING, std::memory_order_release);
        picture_engine::Block block;
        block.in = data, block.in_w = width, block.in_rows = height, block.bx = into.in_x, block.by = into.in_y;
        block.bw = into.in_w, block.bh = into.in_h, block.out = r->pixels, block.out_size = r->pixels_size;
        block.out_w = r->size.w, block.out_h = r->size.h, block.x = into.out_x, block.y = into.out_y, block.scale = into.scale;
        block.yuv420 = yuv420;
        const int64_t from = esp_timer_get_time();
        const int err = picture_engine::blit(r->ppa, block);
        glass::release();
        r->blit_us += static_cast<uint32_t>(esp_timer_get_time() - from);
        r->next_us = now + 1000000 / PICTURES_A_SECOND;
        r->picture.store(err == 0 ? FULL : EMPTY, std::memory_order_release);
      }
    }
  }
  xSemaphoreGive(lock);
}

}  // namespace call_serve
#endif
