// A picture downloaded beside the main loop: the task and its socket (picture_fetch.h says why and what).
//
// One task per download, made when a load starts and gone when it ends; the main loop never waits for it. The task
// talks to the add-on over a plain socket (lwIP on the ESP32, the system's on a host render): a GET, the answer's head,
// then the BMP's bytes straight into the pixels LVGL draws. Everything the main loop reads of a slot it reads in tick(),
// after the task has written `state` DONE (release/acquire), and everything the task reads was written before the
// task was made. The picture's buffer is written in place when the size is the one on the glass (a camera's next
// frame, as online_image did it), and into a new one otherwise, which tick() swaps in: a widget that drew the old one
// is told about the new size by the slot's `done`, as it always was.
#include "picture_fetch.h"
#include "picture_engine.h"
// Only a board with pictures builds this (SCREEN_PICTURES, packages/features/camera.yaml): the CYD keeps its flash.
#ifdef SCREEN_PICTURES
#include "esphome/core/hal.h"
#include "esphome/core/log.h"
#include <atomic>
#include <cerrno>
#include <cstdlib>
#include <arpa/inet.h>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>
#ifdef USE_ESP32
#include <esp_heap_caps.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include "psram_task.h"
#else
#include <thread>
#endif

namespace picture_fetch {
static const char *const TAG = "picture";
constexpr uint32_t CONNECT_MS = 4000;   // as ESPHome's http_request timeout was
constexpr uint32_t RECV_MS = 4000;      // a chunk that does not come in this long ends the download
constexpr uint32_t WHOLE_MS = 30000;    // and a picture that takes longer than this altogether
constexpr size_t CHUNK = 8192;          // what one recv takes at most
constexpr size_t HEAD_MAX = 4096;       // an answer's head larger than this is no picture
constexpr uint32_t SLOW_MS = 2000;      // a picture that took longer says where the time went
// The task's stack: a socket, the head, a row of a BMP, and on a P4 the decode of a whole JPEG (the hardware decoder's
// driver and the PPA's, picture_engine_p4.cpp). 6 KB from the days of BMP alone left 61 bytes unused on a reTerminal
// D1001 (2026-10-24, a cover of 1.5 KB), and the stack's canary turns an overflow into a restart; 10 KB, in PSRAM
// (psram_task.h), costs no internal RAM. The least a task ever left is logged (task_main).
constexpr uint32_t STACK_BYTES = 10240;

enum State : int { IDLE = 0, LOADING = 1, DONE = 2 };

struct Slot {
  explicit Slot(const char *n) : name(n) {}
  const char *name;
#ifdef USE_ESP32
  psram_task::Task task;  // the download's task, its stack in PSRAM: tick deletes it once done (psram_task.h)
#endif
  Done done;
  std::string url, etag;   // the link on the glass (or on its way) and the ETag the add-on gave for it
  // The picture LVGL draws.
  lv_image_dsc_t dsc{};
  uint16_t *pixels = nullptr;
  size_t bytes = 0;
  // The download: the main loop's side.
  std::atomic<int> state{IDLE};
  std::atomic<bool> cancel{false};
  bool free_after = false;        // released while loading: the picture goes once the task has ended
  bool has_pending = false;       // a load asked for while one ran: it follows
  std::string pending;
  // What the task was given, and what it gives back (written before `state` becomes DONE).
  std::string task_url, task_etag;
  uint32_t started = 0;
  // Its way, in ms after `started`: connected, its first bytes, all of it, and decoded (a JPEG, in the glass's turn).
  uint32_t connected_ms = 0, first_ms = 0, body_ms = 0, decoded_ms = 0;
  uint32_t waited_ms = 0, held_ms = 0;  // of the decoding: its wait for the glass, then its hold of it
  bool ok = false, cached = false;
  int status = 0;
  size_t received = 0;
  uint16_t *fresh = nullptr;      // a buffer of a new size, or null when the task wrote in place
  size_t fresh_bytes = 0;
  int fresh_w = 0, fresh_h = 0, fresh_stride = 0;  // stride: pixels a row (a JPEG's are whole MCUs)
  std::string fresh_etag;
};
static Slot slots[3] = {Slot("camera"), Slot("alert"), Slot("live")};
Slot &full() { return slots[0]; }
Slot &thumb() { return slots[1]; }
Slot &live() { return slots[2]; }

// Pixels and the read buffer take PSRAM first (roomy.h): only this file's code reads them, never a DMA.

// ---- the task ----
int connect_to(const Address &a, uint32_t wait_ms) {
  addrinfo hints{};
  hints.ai_family = AF_INET;
  hints.ai_socktype = SOCK_STREAM;
  addrinfo *found = nullptr;
  const std::string port = std::to_string(a.port);
  if (getaddrinfo(a.host.c_str(), port.c_str(), &hints, &found) != 0 || !found) return -1;
  int fd = socket(found->ai_family, found->ai_socktype, found->ai_protocol);
  if (fd < 0) { freeaddrinfo(found); return -1; }
  const int flags = fcntl(fd, F_GETFL, 0);
  fcntl(fd, F_SETFL, flags | O_NONBLOCK);
  int r = connect(fd, found->ai_addr, found->ai_addrlen);
  freeaddrinfo(found);
  if (r < 0 && errno != EINPROGRESS) { close(fd); return -1; }
  if (r < 0) {
    fd_set writable;
    FD_ZERO(&writable);
    FD_SET(fd, &writable);
    timeval wait{static_cast<time_t>(CONNECT_MS / 1000), static_cast<suseconds_t>((CONNECT_MS % 1000) * 1000)};
    if (select(fd + 1, nullptr, &writable, nullptr, &wait) <= 0) { close(fd); return -1; }
    int error = 0;
    socklen_t len = sizeof(error);
    if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &error, &len) < 0 || error != 0) { close(fd); return -1; }
  }
  fcntl(fd, F_SETFL, flags);
  timeval chunk{static_cast<time_t>(wait_ms / 1000), static_cast<suseconds_t>((wait_ms % 1000) * 1000)};
  setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &chunk, sizeof(chunk));
  setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &chunk, sizeof(chunk));
  return fd;
}
bool send_all(int fd, const std::string &text) {
  size_t sent = 0;
  while (sent < text.size()) {
    const auto n = send(fd, text.data() + sent, text.size() - sent, 0);
    if (n <= 0) return false;
    sent += static_cast<size_t>(n);
  }
  return true;
}

// The whole download; `slot.ok`/`slot.cached` tell how it went.
static void download(Slot &slot) {
  const Address a = split(slot.task_url);
  if (!a.ok) { ESP_LOGW(TAG, "%s: not a link: %s", slot.name, slot.task_url.c_str()); return; }
  const int fd = connect_to(a, RECV_MS);
  if (fd < 0) { ESP_LOGW(TAG, "%s: no connection to %s:%u", slot.name, a.host.c_str(), a.port); return; }
  slot.connected_ms = esphome::millis() - slot.started;
  // A P4 takes JPEG as well (picture_engine::JPEG); the app answers with the format the question named first.
  std::string request = "GET " + a.path + " HTTP/1.1\r\nHost: " + a.host + ":" + std::to_string(a.port) +
                        (picture_engine::JPEG ? "\r\nAccept: image/jpeg,image/bmp,*/*;q=0.8" : "\r\nAccept: image/bmp,*/*;q=0.8") +
                        "\r\nConnection: close\r\n";
  if (!slot.task_etag.empty()) request += "If-None-Match: " + slot.task_etag + "\r\n";
  request += "\r\n";
  if (!send_all(fd, request)) { ESP_LOGW(TAG, "%s: the request did not go out", slot.name); close(fd); return; }

  auto *chunk = static_cast<uint8_t *>(roomy::allocate(CHUNK));
  if (!chunk) { ESP_LOGW(TAG, "%s: no memory for the download", slot.name); close(fd); return; }
  roomy::Text head;
  head.reserve(1024);
  Head answer;
  size_t body = 0;
  Decoder decoder([&](int width, int height) -> uint16_t * {
    const size_t needed = static_cast<size_t>(width) * height * 2;
    // In place, the size on the glass (rows without the padding a JPEG's whole MCUs leave).
    if (slot.pixels && slot.bytes == needed && slot.dsc.header.stride == static_cast<uint32_t>(width) * 2) return slot.pixels;
    slot.fresh = static_cast<uint16_t *>(roomy::allocate(needed));
    if (!slot.fresh) { ESP_LOGW(TAG, "%s: no memory for %dx%d", slot.name, width, height); return nullptr; }
    slot.fresh_bytes = needed;
    slot.fresh_w = width;
    slot.fresh_h = height;
    slot.fresh_stride = width;
    return slot.fresh;
  });
  // A JPEG (a P4): gathered whole, then decoded at once in hardware (picture_engine::decode). 0 before the first byte
  // of the body says which, 1 a BMP, 2 a JPEG.
  Gather jpeg;
  int kind = 0;
  bool closed = false, failed = false;
  while (!closed && !failed && !slot.cancel.load(std::memory_order_relaxed)) {
    if (esphome::millis() - slot.started > WHOLE_MS) { ESP_LOGW(TAG, "%s: took too long", slot.name); failed = true; break; }
    const auto n = recv(fd, chunk, CHUNK, 0);
    if (n < 0) {
      if (errno == EINTR) continue;
      ESP_LOGW(TAG, "%s: the download stopped (%d)", slot.name, errno);
      failed = true;
      break;
    }
    if (n == 0) { closed = true; break; }
    if (slot.received == 0) slot.first_ms = esphome::millis() - slot.started;
    slot.received += static_cast<size_t>(n);
    const uint8_t *data = chunk;
    size_t size = static_cast<size_t>(n);
    if (!answer.complete) {
      head.append(reinterpret_cast<const char *>(data), size);
      answer = parse_head(head.data(), head.size());
      if (!answer.complete) {
        if (head.size() > HEAD_MAX) { ESP_LOGW(TAG, "%s: no picture in the answer", slot.name); failed = true; }
        continue;
      }
      slot.status = answer.status;
      if (answer.status == 304) { slot.cached = true; slot.ok = true; break; }
      if (answer.status != 200) { ESP_LOGW(TAG, "%s: HTTP %d", slot.name, answer.status); failed = true; break; }
      slot.fresh_etag = answer.etag;
      data = reinterpret_cast<const uint8_t *>(head.data()) + answer.length;
      size = head.size() - answer.length;
    }
    body += size;
    if (size && kind == 0) {
      kind = picture_engine::JPEG && picture_jpeg::is_jpeg(data, size) ? 2 : 1;
      if (kind == 2 && !jpeg.start(answer.has_length, answer.content_length, picture_engine::input)) {
        ESP_LOGW(TAG, "%s: a JPEG of %u bytes this screen cannot take", slot.name, (unsigned) answer.content_length);
        failed = true;
        break;
      }
    }
    if (kind == 2) {
      jpeg.feed(data, size);
      if (jpeg.done()) break;
      continue;
    }
    if (size && !decoder.feed(data, size)) { ESP_LOGW(TAG, "%s: not a picture this screen shows", slot.name); failed = true; break; }
    if (decoder.done() || (answer.has_length && body >= answer.content_length)) break;
  }
  close(fd);
  roomy::release(chunk);
  slot.body_ms = slot.decoded_ms = esphome::millis() - slot.started;
  if (kind == 2 && !slot.cached && !failed && jpeg.done()) {
    // The whole JPEG: decoded into a buffer of its own, which tick() swaps in as it does a BMP of a new size.
    picture_engine::Still still;
    uint8_t *pixels = picture_engine::decode(jpeg.buffer, jpeg.have, still);
    slot.decoded_ms = esphome::millis() - slot.started;
    slot.waited_ms = still.waited_ms;
    slot.held_ms = still.held_ms;
    // Shown at its own size (the rows and columns past it, made to fill whole MCUs, lie unseen in the stride), with
    // its places' corners exact again (jpeg_notes).
    picture_jpeg::JpegNotes notes;
    if (pixels && picture_jpeg::jpeg_notes(jpeg.buffer, jpeg.have, notes)) {
      if (notes.width <= still.w && notes.height <= still.h) {
        still.w = notes.width;
        still.h = notes.height;
      }
      for (const auto &corner : notes.corners)
        picture_jpeg::mask_corners(reinterpret_cast<uint16_t *>(pixels), still.stride, still.w, still.h, corner);
    }
    if (pixels) {
      slot.fresh = reinterpret_cast<uint16_t *>(pixels);
      slot.fresh_bytes = still.bytes;
      slot.fresh_w = still.w;
      slot.fresh_h = still.h;
      slot.fresh_stride = still.stride;
      slot.ok = true;
    } else {
      ESP_LOGW(TAG, "%s: the JPEG could not be decoded", slot.name);
    }
  } else if (kind == 2 && !slot.cached && !failed && !slot.cancel.load(std::memory_order_relaxed)) {
    ESP_LOGW(TAG, "%s: the JPEG ended early (%u of %u bytes)", slot.name, (unsigned) jpeg.have, (unsigned) jpeg.want);
  } else if (kind != 2 && !slot.cached && !failed && decoder.done()) {
    slot.ok = true;
  } else if (kind != 2 && !slot.cached && !failed && !slot.cancel.load(std::memory_order_relaxed)) {
    ESP_LOGW(TAG, "%s: the picture ended early (%d of %d rows)", slot.name, decoder.rows(), decoder.bmp().height);
  }
  if (jpeg.buffer) roomy::release(jpeg.buffer);
}

static void task_main(void *arg) {
  auto &slot = *static_cast<Slot *>(arg);
  download(slot);
#ifdef USE_ESP32
  // The least of the stack any download left unused, logged as it falls: the margin STACK_BYTES really has.
  static std::atomic<unsigned> least{~0u};
  const unsigned stack_left = uxTaskGetStackHighWaterMark(nullptr);
  unsigned was = least.load(std::memory_order_relaxed);
  while (stack_left < was && !least.compare_exchange_weak(was, stack_left, std::memory_order_relaxed)) {}
  if (stack_left < was && stack_left < 2048)
    ESP_LOGW(TAG, "%s: a download left %u of the task's %u bytes of stack unused, the least so far", slot.name, stack_left,
             (unsigned) STACK_BYTES);
  else if (stack_left < was)
    ESP_LOGI(TAG, "%s: a download left %u of the task's %u bytes of stack unused, the least so far", slot.name, stack_left,
             (unsigned) STACK_BYTES);
#endif
#ifdef USE_ESP32
  const bool in_psram = psram_task::in_psram(slot.task);  // read before DONE: the slot's next download follows it
#endif
  slot.state.store(DONE, std::memory_order_release);
#ifdef USE_ESP32
  psram_task::finish(in_psram);
#endif
}

static void start(Slot &slot) {
  slot.cancel.store(false);
  slot.free_after = false;
  slot.ok = slot.cached = false;
  slot.status = 0;
  slot.received = 0;
  slot.connected_ms = slot.first_ms = slot.body_ms = slot.decoded_ms = slot.waited_ms = slot.held_ms = 0;
  slot.fresh = nullptr;
  slot.fresh_bytes = 0;
  slot.fresh_w = slot.fresh_h = slot.fresh_stride = 0;
  slot.fresh_etag.clear();
  slot.task_url = slot.url;
  slot.task_etag = slot.etag;
  slot.started = esphome::millis();
  slot.state.store(LOADING, std::memory_order_release);
#ifdef USE_ESP32
  if (!psram_task::start(slot.task, task_main, "picture", STACK_BYTES, &slot, 1, tskNO_AFFINITY)) {
    ESP_LOGW(TAG, "%s: no task for the download", slot.name);
    slot.state.store(DONE, std::memory_order_release);  // tick reports the failure
  }
#else
  std::thread(task_main, &slot).detach();
#endif
}

// ---- the main loop's side ----
void bind(Slot &slot, Done done) { slot.done = std::move(done); }
bool loading(const Slot &slot) { return slot.state.load(std::memory_order_acquire) != IDLE; }

void load(Slot &slot, const std::string &url) {
  if (slot.state.load(std::memory_order_acquire) != IDLE) {
    // One at a time: this one follows the one on its way (a cancelled one ends at its next chunk).
    slot.pending = url;
    slot.has_pending = true;
    return;
  }
  if (url != slot.url) { slot.url = url; slot.etag.clear(); }  // a new link: the ETag was the old one's
  if (picture_engine::JPEG) picture_engine::ready();  // the decoder for a JPEG, made on the main loop
  ESP_LOGD(TAG, "%s: loading %s", slot.name, url.c_str());
  start(slot);
}

static void forget_picture(Slot &slot) {
  if (slot.pixels) roomy::release(slot.pixels);
  slot.pixels = nullptr;
  slot.bytes = 0;
  slot.dsc.data = nullptr;
  slot.dsc.data_size = 0;
  slot.dsc.header.w = slot.dsc.header.h = 0;
  slot.etag.clear();  // without the picture, "unchanged" would be an answer without one
}

void release(Slot &slot) {
  if (slot.state.load(std::memory_order_acquire) != IDLE) {
    slot.cancel.store(true);
    slot.free_after = true;
    slot.has_pending = false;
    return;
  }
  forget_picture(slot);
}

void hand_over(Slot &slot) {
  slot.pixels = nullptr;
  slot.bytes = 0;
  slot.dsc.data = nullptr;
  slot.dsc.data_size = 0;
  slot.dsc.header.w = slot.dsc.header.h = 0;
}

lv_image_dsc_t *source(Slot &slot) { return &slot.dsc; }

static void take_over(Slot &slot) {
  const bool cancelled = slot.cancel.load();
  if (slot.fresh && !slot.ok) {
    // A picture that did not come whole: the one on the glass stays.
    roomy::release(slot.fresh);
    slot.fresh = nullptr;
  }
  if (slot.fresh) {
    if (slot.pixels) roomy::release(slot.pixels);
    slot.pixels = slot.fresh;
    slot.bytes = slot.fresh_bytes;
    slot.fresh = nullptr;
    slot.dsc.header.w = static_cast<uint32_t>(slot.fresh_w);
    slot.dsc.header.h = static_cast<uint32_t>(slot.fresh_h);
    slot.dsc.header.stride = static_cast<uint32_t>(slot.fresh_stride) * 2;
    slot.dsc.header.cf = LV_COLOR_FORMAT_RGB565;
#ifdef LV_IMAGE_HEADER_MAGIC
    slot.dsc.header.magic = LV_IMAGE_HEADER_MAGIC;
#endif
    slot.dsc.data_size = slot.bytes;
    slot.dsc.data = reinterpret_cast<const uint8_t *>(slot.pixels);
  }
  if (slot.ok && !slot.cached) slot.etag = slot.fresh_etag;
  const uint32_t took = esphome::millis() - slot.started;
  // A JPEG is decoded once it is all here (a BMP row by row as it comes): its decode is what lies past the body.
  if (slot.ok && slot.decoded_ms > slot.body_ms)
    ESP_LOGI(TAG, "%s: loaded, %u bytes in %u ms, of which %u decoding a JPEG of %dx%d%s", slot.name,
             (unsigned) slot.received, (unsigned) took, (unsigned) (slot.decoded_ms - slot.body_ms), slot.fresh_w,
             slot.fresh_h, cancelled ? " (no longer wanted)" : "");
  else if (slot.ok)
    ESP_LOGI(TAG, "%s: %s, %u bytes in %u ms%s", slot.name, slot.cached ? "unchanged" : "loaded", (unsigned) slot.received,
             (unsigned) took, cancelled ? " (no longer wanted)" : "");
  if (took > SLOW_MS)
    ESP_LOGW(TAG, "%s: %u ms: connected after %u, its first bytes after %u, all of it after %u, decoded after %u (%u ms "
             "waiting for the glass, %u ms holding it)", slot.name, (unsigned) took, (unsigned) slot.connected_ms,
             (unsigned) slot.first_ms, (unsigned) slot.body_ms, (unsigned) slot.decoded_ms, (unsigned) slot.waited_ms,
             (unsigned) slot.held_ms);
  slot.state.store(IDLE, std::memory_order_release);
  if (cancelled) {
    slot.cancel.store(false);
    if (slot.free_after) forget_picture(slot);
    slot.free_after = false;
  } else if (slot.done) {
    slot.done(slot.ok, slot.cached);
  }
  if (slot.has_pending && slot.state.load() == IDLE) {
    slot.has_pending = false;
    load(slot, slot.pending);
  }
}

void tick() {
  for (auto &slot : slots)
    if (slot.state.load(std::memory_order_acquire) == DONE) {
#ifdef USE_ESP32
      psram_task::reap(slot.task);  // its task deleted (a stack in PSRAM) before the slot's next download makes one
#endif
      take_over(slot);
    }
}
}  // namespace picture_fetch
#endif
