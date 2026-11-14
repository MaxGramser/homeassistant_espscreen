// The talk uplink's task (talk_uplink.h, docs/CALLS.md).
#include "talk_uplink.h"

#if defined(USE_MICROPHONE) && defined(USE_LIVE_VIEW)
#include <cstring>
#include <memory>
#include <atomic>
#include <esp_heap_caps.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/stream_buffer.h>
#include <lwip/sockets.h>
#include <netinet/in.h>
#include <netinet/tcp.h>

#include "esphome/components/microphone/microphone_source.h"
#include "esphome/core/hal.h"
#include "esphome/core/log.h"
#include "picture_fetch.h"
#include "psram_task.h"
#include "roomy.h"

namespace talk_uplink {

static const char *const TAG = "talk";
// Below the wake word as every stream (docs/ARCHITECTURE.md, "Nothing of ours runs above the voice").
constexpr UBaseType_t TASK_PRIORITY = 2;
constexpr uint32_t TASK_STACK = 8192;
constexpr int TASK_CORE = 1;

namespace {
esphome::microphone::Microphone *microphone = nullptr;
// One source for the screen's whole life: ESPHome adds its callback to the microphone and has no way to take it off.
esphome::microphone::MicrophoneSource *source = nullptr;

struct Run {
  std::string host, path;
  uint16_t port = 0;
  StreamBufferHandle_t buffer = nullptr;
  StaticStreamBuffer_t *control = nullptr;
  uint8_t *storage = nullptr;
  psram_task::Task task;
  std::atomic<bool> stopping{false}, done{false};
};
Run *run = nullptr;
std::atomic<State> now{State::OFF};
std::atomic<float> shown_bar{0.0f};
std::atomic<uint32_t> last_voice{0};
std::atomic<bool> muted_now{false};

// The microphone's task: a whole part or none.
void on_samples(const std::vector<uint8_t> &data) {
  Run *r = run;
  if (!r || r->stopping.load(std::memory_order_relaxed) || !r->buffer || data.empty()) return;
  const size_t whole = data.size() & ~static_cast<size_t>(1);
  if (xStreamBufferSpacesAvailable(r->buffer) >= whole) xStreamBufferSend(r->buffer, data.data(), whole, 0);
}

void free_run(Run *r) {
  if (r->buffer) vStreamBufferDelete(r->buffer);
  if (r->control) heap_caps_free(r->control);
  if (r->storage) roomy::release(r->storage);
  delete r;
}

bool send_frame(int fd, const uint8_t *data, size_t length) {
  char head[12];
  const int n = chunk_head(head, sizeof head, length);
  // One write for the chunk and its framing, so a part leaves in one segment.
  uint8_t out[PART + sizeof head + 2];
  std::memcpy(out, head, n);
  std::memcpy(out + n, data, length);
  std::memcpy(out + n + length, "\r\n", 2);
  size_t sent = 0;
  const size_t total = n + length + 2;
  while (sent < total) {
    const int w = send(fd, out + sent, total - sent, 0);
    if (w <= 0) return false;
    sent += w;
  }
  return true;
}

void task_main(void *arg) {
  auto *r = static_cast<Run *>(arg);
  bool in_psram = psram_task::in_psram(r->task);
  picture_fetch::Address address;
  address.ok = true;
  address.host = r->host;
  address.port = r->port;
  address.path = r->path;
  State ended = State::FAILED;
  const int fd = picture_fetch::connect_to(address, 5000);
  if (fd < 0) {
    ESP_LOGW(TAG, "no connection to %s:%u", r->host.c_str(), r->port);
  } else {
    int yes = 1;
    setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &yes, sizeof yes);
    timeval send_wait{2, 0};
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &send_wait, sizeof send_wait);
    timeval read_wait{0, 200 * 1000};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &read_wait, sizeof read_wait);
    if (picture_fetch::send_all(fd, request_head(r->host, r->path))) {
      // The add-on's answer comes once the session to the camera stands.
      char head[256];
      size_t have = 0;
      const uint32_t since = esphome::millis();
      int status = 0;
      while (!r->stopping.load() && esphome::millis() - since < ANSWER_MS) {
        const int n = recv(fd, head + have, sizeof head - have - 1, 0);
        if (n > 0) {
          have += n;
          const auto h = picture_fetch::parse_head(head, have);
          if (h.complete) { status = h.status; break; }
          if (have >= sizeof head - 1) break;
        } else if (n == 0 || (errno != EAGAIN && errno != EWOULDBLOCK)) {
          break;
        }
        // Meanwhile the microphone's parts go by: nobody hears them yet.
        xStreamBufferReset(r->buffer);
      }
      if (status == 200) {
        xStreamBufferReset(r->buffer);
        now.store(State::LIVE);
        ESP_LOGI(TAG, "live after %u ms", (unsigned) (esphome::millis() - since));
        auto *part = static_cast<uint8_t *>(roomy::allocate(PART));
        uint32_t heard = esphome::millis(), sent = 0;
        float smooth = 0.0f;
        while (part && !r->stopping.load()) {
          const size_t got = xStreamBufferReceive(r->buffer, part, PART, pdMS_TO_TICKS(100));
          if (got < 2) continue;
          const size_t whole = got & ~static_cast<size_t>(1);
          if (muted_now.load(std::memory_order_relaxed)) std::memset(part, 0, whole);
          if (!send_frame(fd, part, whole)) {
            ESP_LOGW(TAG, "the add-on went away (errno %d)", errno);
            break;
          }
          ++sent;
          const float db = level_db(reinterpret_cast<const int16_t *>(part), whole / 2);
          smooth = std::max(bar_of(db), smooth * 0.8f);
          shown_bar.store(smooth, std::memory_order_relaxed);
          if (db > VOICE_DB) {
            heard = esphome::millis();
            last_voice.store(heard, std::memory_order_relaxed);
          }
        }
        if (part) roomy::release(part);
        ESP_LOGI(TAG, "ended: %u parts sent", (unsigned) sent);
        (void) heard;
        send(fd, "0\r\n\r\n", 5, 0);
        ended = State::OFF;
      } else if (status == 409) {
        ESP_LOGW(TAG, "someone else is talking to this camera");
        ended = State::BUSY;
      } else if (status) {
        ESP_LOGW(TAG, "the add-on said %d", status);
      } else {
        ESP_LOGW(TAG, "no answer from the add-on");
      }
    }
    ::close(fd);
  }
  now.store(r->stopping.load() ? State::OFF : ended);
  r->done.store(true);
  psram_task::finish(in_psram);
}
}  // namespace

void bind_microphone(esphome::microphone::Microphone *m) {
  microphone = m;
  if (!m) return;
  source = new esphome::microphone::MicrophoneSource(m, 16, GAIN, false);
  source->add_channel(0);
  source->add_data_callback(on_samples);
}

bool available() { return microphone != nullptr; }

State state() {
  // A run that ended by itself is reaped here, on the main loop, as its task may not delete itself.
  if (run && run->done.load()) {
    if (source) source->stop();
    psram_task::reap(run->task);
    free_run(run);
    run = nullptr;
  }
  return now.load();
}

bool start(const std::string &url) {
  state();  // the last run's end, if any
  if (!microphone || !source || run) return false;
  const auto address = picture_fetch::split(url);
  if (!address.ok) return false;
  auto *r = new Run;
  r->host = address.host;
  r->port = address.port;
  r->path = address.path;
  r->control = static_cast<StaticStreamBuffer_t *>(
      heap_caps_malloc(sizeof(StaticStreamBuffer_t), MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
  r->storage = static_cast<uint8_t *>(roomy::allocate(BUFFER + 1));
  if (r->control && r->storage) r->buffer = xStreamBufferCreateStatic(BUFFER + 1, 1, r->storage, r->control);
  if (!r->buffer) {
    free_run(r);
    return false;
  }
  now.store(State::CONNECTING);
  last_voice.store(esphome::millis());
  shown_bar.store(0.0f);
  run = r;
  if (!psram_task::start(r->task, task_main, "talk", TASK_STACK, r, TASK_PRIORITY, TASK_CORE)) {
    run = nullptr;
    free_run(r);
    now.store(State::FAILED);
    return false;
  }
  source->start();
  const auto info = source->get_audio_stream_info();
  ESP_LOGI(TAG, "the microphone gives %u Hz, %u bits, %u channels", (unsigned) info.get_sample_rate(), (unsigned) info.get_bits_per_sample(), (unsigned) info.get_channels());
  return true;
}

void stop() {
  if (!run) return;
  run->stopping.store(true);
  // state() frees it on the main loop once its task said it is done.
}

void set_muted(bool muted) { muted_now.store(muted, std::memory_order_relaxed); }

float bar() { return shown_bar.load(std::memory_order_relaxed); }
uint32_t voice_at() { return last_voice.load(std::memory_order_relaxed); }

}  // namespace talk_uplink
#endif
