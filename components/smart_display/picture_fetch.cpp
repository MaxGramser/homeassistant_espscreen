// A picture downloaded beside the main loop: the task and its socket (picture_fetch.h says why and what).
//
// One task per download, made when a load starts and gone when it ends; the main loop never waits for it. The task
// talks to the add-on over a plain socket (lwIP on the ESP32, the system's on a host render): a GET, the answer's head,
// then the BMP's bytes straight into the pixels LVGL draws. Everything the main loop reads of a slot it reads in tick(),
// after the task has written `state` DONE (release/acquire), and everything the task reads was written before the
// task was made. The picture's buffer is written in place when the size is the one on the glass (a camera's next
// frame, as online_image did it), and into a new one otherwise, which tick() swaps in: a widget that drew the old one
// is told about the new size by the slot's `done`, as it always was.
//
// A slot that keeps no picture (direct, a board without PSRAM) hands its rows over in bands instead: the task fills a
// band, says it is ready and waits; tick() draws it on the main loop, where the glass is written, and gives it back.
// One band is all the picture this side ever holds.
#include "picture_fetch.h"
// Only a board with pictures builds this (SCREEN_PICTURES, packages/features/camera.yaml; SCREEN_PICTURES_DIRECT,
// camera-view.yaml): the other boards keep their flash.
#if defined(SCREEN_PICTURES) || defined(SCREEN_PICTURES_DIRECT)
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
#else
#include <chrono>
#include <thread>
#endif

namespace picture_fetch {
static const char *const TAG = "picture";
constexpr uint32_t CONNECT_MS = 4000;   // as ESPHome's http_request timeout was
constexpr uint32_t RECV_MS = 4000;      // a chunk that does not come in this long ends the download
constexpr uint32_t WHOLE_MS = 30000;    // and a picture that takes longer than this altogether
constexpr size_t CHUNK = 8192;          // what one recv takes at most
constexpr size_t DIRECT_CHUNK = 2048;   // and on a board that draws in bands, where every KB inside the chip counts
constexpr uint32_t BAND_MS = 4000;      // a band the main loop does not take in this long ends the download
constexpr size_t HEAD_MAX = 4096;       // an answer's head larger than this is no picture
constexpr uint32_t STACK_BYTES = 6144;  // the task's stack: a socket, the head, a row of the picture (on the heap)

enum State : int { IDLE = 0, LOADING = 1, DONE = 2 };
// A band on its way to the glass: the task makes it READY, tick() takes it (DRAWING) and gives it back (NONE). The task
// frees the band only from NONE, so the main loop never draws from memory that went.
enum BandState : int { NONE = 0, READY = 1, DRAWING = 2 };

struct Slot {
  explicit Slot(const char *n) : name(n) {}
  const char *name;
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
  bool ok = false, cached = false;
  int status = 0;
  size_t received = 0;
  uint16_t *fresh = nullptr;      // a buffer of a new size, or null when the task wrote in place
  size_t fresh_bytes = 0;
  int fresh_w = 0, fresh_h = 0;
  std::string fresh_etag;
  // Rows straight to the glass (direct): no picture is kept.
  Draw draw;
  size_t band_bytes = 0;
  int rounding = 1;
  std::atomic<int> band_state{NONE};
  std::atomic<bool> refused{false};  // `draw` said this picture is not one for this glass
  int band_w = 0, band_h = 0, band_top = 0, band_rows = 0;
  uint16_t *band_pixels = nullptr;
};
static Slot slots[3] = {Slot("camera"), Slot("alert"), Slot("live")};
Slot &full() { return slots[0]; }
Slot &thumb() { return slots[1]; }
Slot &live() { return slots[2]; }

static uint16_t *allocate(size_t bytes) {
#ifdef USE_ESP32
  void *p = heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  if (!p) p = heap_caps_malloc(bytes, MALLOC_CAP_8BIT);
  return static_cast<uint16_t *>(p);
#else
  return static_cast<uint16_t *>(std::malloc(bytes));
#endif
}
static void *allocate_chunk(size_t bytes) {
#ifdef USE_ESP32
  void *p = heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  return p ? p : heap_caps_malloc(bytes, MALLOC_CAP_8BIT);
#else
  return std::malloc(bytes);
#endif
}
static void release_memory(void *p) {
#ifdef USE_ESP32
  heap_caps_free(p);
#else
  std::free(p);
#endif
}
static void pause_briefly() {
#ifdef USE_ESP32
  vTaskDelay(1);
#else
  std::this_thread::sleep_for(std::chrono::milliseconds(1));
#endif
}
// The task's side of a band: ready for the main loop, and back when it is on the glass. False when the download is to
// end: cancelled, refused by `draw`, or a main loop that does not come for it.
static bool hand_over(Slot &slot, const Band &band) {
  slot.band_w = band.width;
  slot.band_h = band.height;
  slot.band_top = band.top;
  slot.band_rows = band.rows;
  slot.band_pixels = band.pixels;
  slot.band_state.store(READY, std::memory_order_release);
  const uint32_t since = esphome::millis();
  while (slot.band_state.load(std::memory_order_acquire) != NONE) {
    const bool give_up = slot.cancel.load(std::memory_order_relaxed) || esphome::millis() - since > BAND_MS;
    int ready = READY;
    // Taken back only while the main loop has not started on it; a band being drawn is waited for.
    if (give_up && slot.band_state.compare_exchange_strong(ready, NONE)) {
      if (!slot.cancel.load(std::memory_order_relaxed)) ESP_LOGW(TAG, "%s: the glass did not take the picture", slot.name);
      return false;
    }
    pause_briefly();
  }
  return !slot.refused.load(std::memory_order_acquire);
}

// ---- the task ----
static int connect_to(const Address &a) {
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
  timeval chunk{static_cast<time_t>(RECV_MS / 1000), static_cast<suseconds_t>((RECV_MS % 1000) * 1000)};
  setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &chunk, sizeof(chunk));
  setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &chunk, sizeof(chunk));
  return fd;
}
static bool send_all(int fd, const std::string &text) {
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
  const int fd = connect_to(a);
  if (fd < 0) { ESP_LOGW(TAG, "%s: no connection to %s:%u", slot.name, a.host.c_str(), a.port); return; }
  std::string request = "GET " + a.path + " HTTP/1.1\r\nHost: " + a.host + ":" + std::to_string(a.port) +
                        "\r\nAccept: image/bmp,*/*;q=0.8\r\nConnection: close\r\n";
  if (!slot.task_etag.empty()) request += "If-None-Match: " + slot.task_etag + "\r\n";
  request += "\r\n";
  if (!send_all(fd, request)) { ESP_LOGW(TAG, "%s: the request did not go out", slot.name); close(fd); return; }

  const bool in_bands = static_cast<bool>(slot.draw);
  const size_t chunk_bytes = in_bands ? DIRECT_CHUNK : CHUNK;
  auto *chunk = static_cast<uint8_t *>(allocate_chunk(chunk_bytes));
  if (!chunk) { ESP_LOGW(TAG, "%s: no memory for the download", slot.name); close(fd); return; }
  std::string head;
  Head answer;
  size_t body = 0;
  Band band;
  const Bmp *shape = nullptr;  // the decoder's own, once it is made
  Decoder::Rows rows;
  if (in_bands) {
    rows.place = [&](int y) { return band.place(y); };
    rows.placed = [&](int y) { return !band.full(y) || hand_over(slot, band); };
  }
  Decoder decoder([&](int width, int height) -> uint16_t * {
    if (in_bands) {
      // A band of as many rows as fit; the picture itself is never held.
      const int fit = Band::rows_in(slot.band_bytes, width, slot.rounding);
      if (fit <= 0 || width % slot.rounding || height % slot.rounding) {
        ESP_LOGW(TAG, "%s: %dx%d is no picture for this glass", slot.name, width, height);
        return nullptr;
      }
      const int band_rows = std::min(fit, height);
      auto *pixels = allocate(static_cast<size_t>(width) * band_rows * 2);
      if (!pixels) { ESP_LOGW(TAG, "%s: no memory for a band of %dx%d", slot.name, width, band_rows); return nullptr; }
      band.start(pixels, width, height, band_rows, shape && shape->top_down);
      return pixels;
    }
    const size_t needed = static_cast<size_t>(width) * height * 2;
    if (slot.pixels && slot.bytes == needed) return slot.pixels;  // in place, the size on the glass
    slot.fresh = allocate(needed);
    if (!slot.fresh) { ESP_LOGW(TAG, "%s: no memory for %dx%d", slot.name, width, height); return nullptr; }
    slot.fresh_bytes = needed;
    slot.fresh_w = width;
    slot.fresh_h = height;
    return slot.fresh;
  }, rows);
  shape = &decoder.bmp();
  bool closed = false, failed = false;
  while (!closed && !failed && !slot.cancel.load(std::memory_order_relaxed)) {
    if (esphome::millis() - slot.started > WHOLE_MS) { ESP_LOGW(TAG, "%s: took too long", slot.name); failed = true; break; }
    const auto n = recv(fd, chunk, chunk_bytes, 0);
    if (n < 0) {
      if (errno == EINTR) continue;
      ESP_LOGW(TAG, "%s: the download stopped (%d)", slot.name, errno);
      failed = true;
      break;
    }
    if (n == 0) { closed = true; break; }
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
    if (size && !decoder.feed(data, size)) { ESP_LOGW(TAG, "%s: not a picture this screen shows", slot.name); failed = true; break; }
    if (decoder.done() || (answer.has_length && body >= answer.content_length)) break;
  }
  close(fd);
  release_memory(chunk);
  if (band.pixels) release_memory(band.pixels);  // no band is out: hand_over came back
  if (!slot.cached && !failed && decoder.done()) slot.ok = true;
  else if (!slot.cached && !failed && !slot.cancel.load(std::memory_order_relaxed))
    ESP_LOGW(TAG, "%s: the picture ended early (%d of %d rows)", slot.name, decoder.rows(), decoder.bmp().height);
}

static void task_main(void *arg) {
  auto &slot = *static_cast<Slot *>(arg);
  download(slot);
#ifdef USE_ESP32
  ESP_LOGD(TAG, "%s: task stack left %u", slot.name, (unsigned) uxTaskGetStackHighWaterMark(nullptr));
#endif
  slot.state.store(DONE, std::memory_order_release);
#ifdef USE_ESP32
  vTaskDelete(nullptr);
#endif
}

static void start(Slot &slot) {
  slot.cancel.store(false);
  slot.free_after = false;
  slot.ok = slot.cached = false;
  slot.status = 0;
  slot.received = 0;
  slot.fresh = nullptr;
  slot.fresh_bytes = 0;
  slot.fresh_w = slot.fresh_h = 0;
  slot.fresh_etag.clear();
  slot.band_state.store(NONE);
  slot.refused.store(false);
  slot.task_url = slot.url;
  slot.task_etag = slot.etag;
  slot.started = esphome::millis();
  slot.state.store(LOADING, std::memory_order_release);
#ifdef USE_ESP32
  if (xTaskCreate(task_main, "picture", STACK_BYTES, &slot, 1, nullptr) != pdPASS) {
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
  ESP_LOGD(TAG, "%s: loading %s", slot.name, url.c_str());
  start(slot);
}

static void forget_picture(Slot &slot) {
  if (slot.pixels) release_memory(slot.pixels);
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

lv_image_dsc_t *source(Slot &slot) { return &slot.dsc; }

static void take_over(Slot &slot) {
  const bool cancelled = slot.cancel.load();
  if (slot.fresh && !slot.ok) {
    // A picture that did not come whole: the one on the glass stays.
    release_memory(slot.fresh);
    slot.fresh = nullptr;
  }
  if (slot.fresh) {
    if (slot.pixels) release_memory(slot.pixels);
    slot.pixels = slot.fresh;
    slot.bytes = slot.fresh_bytes;
    slot.fresh = nullptr;
    slot.dsc.header.w = static_cast<uint32_t>(slot.fresh_w);
    slot.dsc.header.h = static_cast<uint32_t>(slot.fresh_h);
    slot.dsc.header.stride = static_cast<uint32_t>(slot.fresh_w) * 2;
    slot.dsc.header.cf = LV_COLOR_FORMAT_RGB565;
#ifdef LV_IMAGE_HEADER_MAGIC
    slot.dsc.header.magic = LV_IMAGE_HEADER_MAGIC;
#endif
    slot.dsc.data_size = slot.bytes;
    slot.dsc.data = reinterpret_cast<const uint8_t *>(slot.pixels);
  }
  if (slot.ok && !slot.cached) slot.etag = slot.fresh_etag;
  if (slot.ok)
    ESP_LOGI(TAG, "%s: %s, %u bytes in %u ms%s", slot.name, slot.cached ? "unchanged" : "loaded", (unsigned) slot.received,
             (unsigned) (esphome::millis() - slot.started), cancelled ? " (no longer wanted)" : "");
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

void direct(Slot &slot, Draw draw, size_t band_bytes, int rounding) {
  slot.draw = std::move(draw);
  slot.band_bytes = band_bytes;
  slot.rounding = rounding > 0 ? rounding : 1;
}

// A band the task has ready goes to the glass here, on the main loop; a download no longer wanted draws nothing more.
static void draw_band(Slot &slot) {
  int ready = READY;
  if (!slot.band_state.compare_exchange_strong(ready, DRAWING)) return;
  if (!slot.cancel.load() && slot.draw &&
      !slot.draw(slot.band_w, slot.band_h, slot.band_top, slot.band_rows, slot.band_pixels))
    slot.refused.store(true, std::memory_order_release);
  slot.band_state.store(NONE, std::memory_order_release);
}

void tick() {
  for (auto &slot : slots) {
    if (slot.draw) draw_band(slot);
    if (slot.state.load(std::memory_order_acquire) == DONE) take_over(slot);
  }
}
}  // namespace picture_fetch
#endif
