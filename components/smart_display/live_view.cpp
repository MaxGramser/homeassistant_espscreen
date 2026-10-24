// The live view's streams on a P4 (live_view.h says why and what).
//
// Each stream (the full view, a live tile of the page on the glass) is a task of its own with its own buffers and PPA
// client, owned by the main loop: open() makes it, close() and tick() end it. The task reads the stream, decodes each
// picture with the hardware JPEG decoder (one engine for all, its calls are thread safe) and has the PPA bring it to the
// glass: a full view's picture scaled to fill its room and turned as LVGL turns its drawing, straight into the panel's
// frame buffer; a tile's picture first cut or fitted into a canvas of the card's size, where the shade, the corners and
// the name go over it (live_view::compose), and then turned onto the glass. A copy happens with the glass held (glass.h:
// one writer at a time) and only while nobody stopped the stream, so once close() returns nothing of it writes the glass
// any more and LVGL may draw there at once. Buffers live in PSRAM and go when the task has ended (tick()). The panel, its
// frame buffer, the lock and the rooms LVGL keeps out of are the glass's (glass.h, glass_dsi.cpp); the decoder and the
// PPA copies are the engine's (picture_engine.h, picture_engine_p4.cpp). What is here is the stream's own: its task
// and socket, the framing, the canvas of a tile and what goes over it, the loader, the sound, the reports.
#include "live_view.h"
#include "glass.h"
#include "picture_engine.h"
#if defined(USE_LIVE_VIEW) && defined(SCREEN_PICTURES)
#include <atomic>
#include <cerrno>
#include <cstdlib>
#include <sys/socket.h>
#include <unistd.h>

#include "esphome/core/hal.h"
#include "esphome/core/log.h"

#include <esp_err.h>
#include <esp_heap_caps.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/stream_buffer.h>
#include <freertos/task.h>

#include "psram_task.h"
#include "roomy.h"
#ifdef USE_SPEAKER
#include "esphome/components/audio/audio.h"
#include "esphome/components/speaker/speaker.h"
#endif

namespace live_view {

static const char *const TAG = "live";
constexpr size_t CHUNK = 16 * 1024;
constexpr uint32_t STACK_BYTES = 6144;  // a stream task's stack (psram_task.h), its high water logged as it ends
constexpr uint32_t WAIT_MS = 500;  // a read waits this long, so a stop is seen within it
// ---- The glass (glass.h): the panel, its frame buffer, the one-writer lock and the rooms LVGL keeps out of ----
bool available() { return glass::direct(); }
uint32_t misses() { return glass::misses(); }

// ---- The camera's sound: the board's speaker (features/audio.yaml binds it) ----
#ifdef USE_SPEAKER
static esphome::speaker::Speaker *speaker = nullptr;
void bind_speaker(esphome::speaker::Speaker *s) { speaker = s; }
bool has_speaker() { return speaker != nullptr; }
#else
bool has_speaker() { return false; }
#endif

// ---- One stream ----
struct Stream {
  std::string url;
  Rect area;
  Look look;
  uint32_t *name = nullptr;  // the stream's own copy of look.name
  int turn = 0;
  std::atomic<bool> stopping{false}, done{false}, failed{false};
  // Its room on the glass (glass.h): LVGL is kept out of where its picture lies from the first picture on (placed by
  // the task just before it copies one); until then LVGL draws as ever, a spinner turning while the camera comes.
  glass::Room room = -1;
  std::atomic<uint32_t> shown{0}, bytes{0}, decode_us{0}, copy_us{0}, skipped{0};
  // When the way to the first picture went by (ms after start, written once by the task, read after `shown`).
  uint32_t started_at = 0, connected_ms = 0, answered_ms = 0, first_bytes_ms = 0;
  uint32_t live_ms = 0;  // its first live picture (written once by the task, read after `live`)
  picture_engine::Client ppa = nullptr;  // its client of the PPA (the engine's)
  uint8_t *input = nullptr, *picture = nullptr;
  uint16_t *canvas = nullptr;
  size_t input_size = 0, picture_size = 0, canvas_size = 0;
  // The camera's sound (a full view on a board with a speaker): parts the task puts in `sound`, which the main loop
  // hands to the speaker unless `muted`.
  StreamBufferHandle_t sound = nullptr;  // in PSRAM (xStreamBufferCreateWithCaps), as its parts below
  uint8_t *sound_part = nullptr;
  uint8_t *sound_piece = nullptr;  // what the speaker took part of, the rest of it next tick
  size_t piece_left = 0, piece_at = 0;
  std::atomic<bool> muted{false}, heard{false};
  // Until it is live (live_view.h): the picture on the glass is a still (the task turns a tile's loader over it), and a
  // live one was shown. `under` holds the loader's square of the card as composed, its last turn drawn at `turned_at`.
  std::atomic<bool> warming{false}, live{false};
  uint16_t *under = nullptr;
  uint32_t turned_at = 0;
  // The main loop's own: the report of the last REPORT_MS, the first picture, its first live one and sound told, the
  // speaker started.
  bool told_first = false, told_live = false, told_sound = false, speaking = false;
  uint32_t reported_at = 0, reported_shown = 0, reported_bytes = 0, reported_decode = 0, reported_copy = 0;
  psram_task::Task task;  // its task, its stack in PSRAM: the main loop deletes it once done (psram_task.h)
  std::atomic<uint32_t> stack_left{0};  // what of its stack the task never used, in bytes (written before `done`)
};
static Stream *streams[MAX_STREAMS] = {};
static_assert(MAX_STREAMS <= glass::MAX_ROOMS, "every stream has a room on the glass");

static void free_stream(Stream *s) {
  if (s->sound) vStreamBufferDeleteWithCaps(s->sound);
  if (s->sound_part) roomy::release(s->sound_part);
  if (s->sound_piece) roomy::release(s->sound_piece);
  if (s->input) free(s->input);
  if (s->picture) free(s->picture);
  if (s->canvas) free(s->canvas);
  if (s->name) free(s->name);
  if (s->under) free(s->under);
  picture_engine::drop(s->ppa);
  if (s->room >= 0) glass::give_back(s->room);
  delete s;
}

// The engine's copy (picture_engine::blit): the block `bw` x `bh` at bx, by of a picture (`in_w` x `rows`) to x, y of
// another (ow x oh, `out_size` bytes), scaled by `sixteenths` and turned as LVGL turns.
static esp_err_t copy(Stream &s, const void *in, int in_w, int rows, int bx, int by, int bw, int bh, void *out,
                      size_t out_size, int ow, int oh, int x, int y, int sixteenths, int turn) {
  picture_engine::Block block;
  block.in = in, block.in_w = in_w, block.in_rows = rows, block.bx = bx, block.by = by, block.bw = bw, block.bh = bh;
  block.out = out, block.out_size = out_size, block.out_w = ow, block.out_h = oh, block.x = x, block.y = y;
  block.sixteenths = sixteenths, block.turn = turn;
  return static_cast<esp_err_t>(picture_engine::blit(s.ppa, block));
}

// A tile's loader over a still (live_view.h, "Until it is live"): its square of the card as composed kept in `under`,
// and the loader drawn over it as it stands now.
static bool lay_loader(Stream &s) {
  int lx = 0, ly = 0;
  if (!s.under || !loader_spot(s.look, s.area.w, s.area.h, lx, ly)) return false;
  const int cw = s.area.w, size = s.look.loader;
  for (int j = 0; j < size; ++j)
    memcpy(s.under + static_cast<size_t>(j) * size, s.canvas + static_cast<size_t>(ly + j) * cw + lx,
           static_cast<size_t>(size) * 2);
  s.turned_at = esphome::millis();
  draw_loader(s.canvas, cw, lx, ly, s.look, s.turned_at);
  return true;
}
// Its next turn, between the stills: the square as composed again, the loader over it, and that square alone onto the
// glass, every LOADER_STEP_MS while the task waits for the stream's next bytes.
static void turn_loader(Stream &s) {
  const uint32_t now = esphome::millis();
  int lx = 0, ly = 0;
  if (!s.warming || now - s.turned_at < LOADER_STEP_MS || !loader_spot(s.look, s.area.w, s.area.h, lx, ly)) return;
  s.turned_at = now;
  const int cw = s.area.w, ch = s.area.h, size = s.look.loader;
  for (int j = 0; j < size; ++j)
    memcpy(s.canvas + static_cast<size_t>(ly + j) * cw + lx, s.under + static_cast<size_t>(j) * size,
           static_cast<size_t>(size) * 2);
  draw_loader(s.canvas, cw, lx, ly, s.look, now);
  const glass::Panel panel = glass::panel();
  const Rect target = on_panel(Rect{s.area.x + lx, s.area.y + ly, size, size}, s.turn, panel.w, panel.h);
  esp_err_t err = ESP_OK;
  glass::hold();
  if (!s.stopping && glass::armed(s.room))
    err = copy(s, s.canvas, cw, ch, lx, ly, size, size, glass::frame_buffer(), static_cast<size_t>(panel.w) * panel.h * 2,
               panel.w, panel.h, target.x, target.y, 16, s.turn);
  glass::release();
  if (err != ESP_OK) s.warming = false;  // the loader stops where it stands; the pictures go on
}

// One picture of `length` bytes in the stream's input: decoded, laid out, and copied onto the glass. `still`: the
// camera's still from before its stream came, with the loader over it on a tile.
static void show(Stream &s, size_t length, bool still) {
  picture_engine::Still info;
  if (!picture_engine::info(s.input, length, info)) {
    s.skipped++;
    return;
  }
  // The decoder writes whole MCUs (picture_jpeg.h): `stride_w` pixels a row, `rows` of them.
  const int stride_w = info.stride;
  const int rows = static_cast<int>(info.bytes / 2 / info.stride);
  const int w = info.w, h = info.h;
  // Where it goes: a full view's picture as large as fits its room, a tile's into its card.
  int sixteenths = 0;
  Rect where;
  Cut into;
  if (s.look.tile) {
    into = cut(w, h, s.area.w, s.area.h, s.look.contain);
    if (into.ok) where = s.area;
  } else {
    where = fit(w, h, s.area, sixteenths);
  }
  if (where.empty()) {
    if (s.skipped++ == 0) ESP_LOGW(TAG, "a picture of %dx%d does not fit its room (%dx%d)", w, h, s.area.w, s.area.h);
    return;
  }
  const size_t need = info.bytes;
  if (need > s.picture_size) {
    if (s.picture) free(s.picture);
    s.picture = picture_engine::output(need, &s.picture_size);
    if (!s.picture) {
      s.picture_size = 0;
      ESP_LOGW(TAG, "no memory for a picture of %dx%d", w, h);
      s.failed = true;
      s.stopping = true;
      return;
    }
  }
  // The decoder works through the 2D-DMA, as the PPA and the panel's copy of each of LVGL's strips do: it decodes
  // while it holds the glass (glass.h).
  glass::hold();
  if (s.stopping) {
    glass::release();
    return;
  }
  const int64_t t0 = esp_timer_get_time();
  const bool decoded = picture_engine::decode_into(s.input, length, s.picture, s.picture_size);
  const int64_t t1 = esp_timer_get_time();
  glass::release();
  if (!decoded) {
    s.skipped++;
    return;
  }
  if (s.shown == 0)
    ESP_LOGD(TAG, "picture %dx%d decoded in %u us, for %dx%d at %d,%d", w, h, (unsigned) (t1 - t0), where.w, where.h,
             where.x, where.y);
  const glass::Panel panel = glass::panel();
  const size_t glass_size = static_cast<size_t>(panel.w) * panel.h * 2;
  esp_err_t err = ESP_OK;
  bool loading = false;
  if (s.look.tile) {
    // The card: the picture cut or fitted into it, on black where it leaves room, then the shade, corners and name.
    const int cw = s.area.w, ch = s.area.h;
    const size_t canvas_need = (static_cast<size_t>(cw) * ch * 2 + 127) & ~static_cast<size_t>(127);
    if (canvas_need > s.canvas_size) {
      if (s.canvas) free(s.canvas);
      s.canvas = static_cast<uint16_t *>(heap_caps_aligned_calloc(128, 1, canvas_need, MALLOC_CAP_SPIRAM));
      s.canvas_size = s.canvas ? canvas_need : 0;
      if (!s.canvas) {
        ESP_LOGW(TAG, "no memory for a card of %dx%d", cw, ch);
        s.failed = true;
        s.stopping = true;
        return;
      }
    }
    if (!into.covers(cw, ch)) memset(s.canvas, 0, static_cast<size_t>(cw) * ch * 2);
    // Into the card's canvas, not the glass, but through the PPA all the same: with the glass held.
    glass::hold();
    err = copy(s, s.picture, stride_w, rows, into.in_x, into.in_y, into.in_w, into.in_h, s.canvas, s.canvas_size, cw,
               ch, into.out_x, into.out_y, into.sixteenths, 0);
    glass::release();
    if (err == ESP_OK) {
      compose(s.canvas, cw, cw, ch, s.look);
      loading = still && lay_loader(s);
      const Rect target = on_panel(s.area, s.turn, panel.w, panel.h);
      glass::hold();
      if (!s.stopping) {
        glass::place(s.room, s.area);  // from now on LVGL draws nothing here
        err = copy(s, s.canvas, cw, ch, 0, 0, cw, ch, glass::frame_buffer(), glass_size, panel.w, panel.h, target.x,
                   target.y, 16, s.turn);
      }
      glass::release();
    }
  } else {
    // The full view: scaled to fill its room on the way (the app sends the camera's own size where that is smaller).
    const Rect target = on_panel(where, s.turn, panel.w, panel.h);
    glass::hold();
    if (!s.stopping) {
      glass::place(s.room, where);
      err = copy(s, s.picture, stride_w, rows, 0, 0, w, h, glass::frame_buffer(), glass_size, panel.w, panel.h, target.x,
                 target.y, sixteenths, s.turn);
    }
    glass::release();
  }
  if (err != ESP_OK) {
    ESP_LOGW(TAG, "copy to the glass failed: %s", esp_err_to_name(err));
    s.failed = true;
    s.stopping = true;
    return;
  }
  s.decode_us += static_cast<uint32_t>(t1 - t0);
  s.copy_us += static_cast<uint32_t>(esp_timer_get_time() - t1);
  s.warming = loading;
  if (!still && !s.live) {
    s.live_ms = esphome::millis() - s.started_at;
    s.live = true;
  }
  s.shown++;
}

static void stream(Stream &s) {
  const auto address = picture_fetch::split(s.url);
  const int fd = address.ok ? picture_fetch::connect_to(address, WAIT_MS) : -1;
  if (fd < 0) {
    ESP_LOGW(TAG, "no connection to %s:%u", address.host.c_str(), address.port);
    s.failed = true;
    return;
  }
  s.connected_ms = esphome::millis() - s.started_at;
  // HTTP/1.0: the app answers without chunks, and ends the stream by closing it.
  if (!picture_fetch::send_all(fd, "GET " + address.path + " HTTP/1.0\r\nHost: " + address.host + "\r\n\r\n")) {
    ::close(fd);
    s.failed = true;
    return;
  }
  // PSRAM first (roomy.h): recv copies into it and no DMA reads it, and internal RAM is what the Wi-Fi link runs short of.
  auto *chunk = static_cast<uint8_t *>(roomy::allocate(CHUNK));
  if (!chunk) {
    ::close(fd);
    s.failed = true;
    return;
  }
  // A tile with a loader reads in short waits, so its loader turns between the stills.
  if (s.under) {
    timeval step{0, static_cast<suseconds_t>(LOADER_STEP_MS * 1000)};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &step, sizeof(step));
  }
  Reader reader;
  uint32_t heard = esphome::millis();
  while (!s.stopping) {
    const int n = recv(fd, chunk, CHUNK, 0);
    const int error = errno;
    turn_loader(s);
    if (n < 0 && (error == EAGAIN || error == EWOULDBLOCK)) {
      if (esphome::millis() - heard < QUIET_MS) continue;
      ESP_LOGW(TAG, "the stream went quiet");
      s.failed = true;
      break;
    }
    if (n <= 0) {
      ESP_LOGW(TAG, "the stream ended (%d, errno %d)", n, error);
      s.failed = true;
      break;
    }
    heard = esphome::millis();
    if (s.bytes == 0) s.first_bytes_ms = heard - s.started_at;
    s.bytes += n;
    const bool ok = reader.feed(
        chunk, n,
        [&s](size_t length, bool audio) -> uint8_t * {
          if (audio) return s.sound && length <= SOUND_PART ? s.sound_part : nullptr;
          return length <= s.input_size ? s.input : nullptr;
        },
        [&s, &reader](size_t length, bool audio) {
          if (!audio) {
            show(s, length, reader.still());
            return;
          }
          // Sound: into the buffer the main loop plays from; none of it while muted, and none when it is full.
          s.heard = true;
          if (!s.muted) xStreamBufferSend(s.sound, s.sound_part, length, 0);
        });
    if (!ok) {
      ESP_LOGW(TAG, "not a stream of pictures (answer %d)", reader.status());
      s.failed = true;
      break;
    }
    if (!s.answered_ms && reader.status()) s.answered_ms = esphome::millis() - s.started_at;
  }
  ::close(fd);
  roomy::release(chunk);
}

static void task_main(void *arg) {
  auto *s = static_cast<Stream *>(arg);
  stream(*s);
  const bool in_psram = psram_task::in_psram(s->task);  // read before `done`: the main loop frees the stream after it
  s->stack_left.store(uxTaskGetStackHighWaterMark(nullptr), std::memory_order_relaxed);
  s->done.store(true, std::memory_order_release);
  psram_task::finish(in_psram);
}

Handle open(const std::string &url, const Rect &area, const Look &look, bool sound) {
  if (!available() || area.empty()) return -1;
  int slot = -1;
  for (int i = 0; i < MAX_STREAMS && slot < 0; ++i)
    if (!streams[i]) slot = i;
  if (slot < 0) return -1;
  if (!picture_engine::start() || !glass::frame_buffer()) {
    ESP_LOGW(TAG, "cannot stream on this panel");
    return -1;
  }
  auto *s = new Stream();
  s->url = url;
  s->area = area;
  s->look = look;
  s->look.name = nullptr;
  s->turn = glass::turn();
  s->started_at = s->reported_at = esphome::millis();
  s->input = picture_engine::input(look.tile ? TILE_PICTURE : MAX_PICTURE, &s->input_size);
  s->ppa = picture_engine::client();
  bool ok = s->input && s->ppa;
  if (ok && sound && has_speaker()) {
    // The camera's sound between the task and the main loop, in PSRAM: only the task and the speaker's copy read it.
    s->sound = xStreamBufferCreateWithCaps(SOUND_BUFFER, 1, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    s->sound_part = static_cast<uint8_t *>(roomy::allocate(SOUND_PART));
    s->sound_piece = static_cast<uint8_t *>(roomy::allocate(SOUND_PART));
    ok = s->sound && s->sound_part && s->sound_piece;
  }
  // The name as LVGL drew it, the stream's own copy: its owner may draw the card again meanwhile.
  if (ok && look.tile && look.name && look.name_w > 0 && look.name_h > 0) {
    s->name = static_cast<uint32_t *>(heap_caps_malloc(static_cast<size_t>(look.name_w) * look.name_h * 4, MALLOC_CAP_SPIRAM));
    ok = s->name != nullptr;
    if (ok) {
      const int stride = look.name_stride ? look.name_stride : look.name_w;
      for (int y = 0; y < look.name_h; ++y)
        memcpy(s->name + static_cast<size_t>(y) * look.name_w, look.name + static_cast<size_t>(y) * stride,
               static_cast<size_t>(look.name_w) * 4);
      s->look.name = s->name;
      s->look.name_stride = look.name_w;
    }
  }
  if (!ok) {
    ESP_LOGW(TAG, "no memory for another stream");
    free_stream(s);
    return -1;
  }
  // The loader's square of the card, kept under it while it turns; without the memory the tile simply has none.
  int lx = 0, ly = 0;
  if (loader_spot(look, area.w, area.h, lx, ly))
    s->under = static_cast<uint16_t *>(
        heap_caps_malloc(static_cast<size_t>(look.loader) * look.loader * 2, MALLOC_CAP_SPIRAM));
  s->room = glass::reserve(area);
  if (s->room < 0) {
    free_stream(s);
    return -1;
  }
  streams[slot] = s;
  if (!psram_task::start(s->task, task_main, "live_view", STACK_BYTES, s, 5, 1)) {
    streams[slot] = nullptr;
    free_stream(s);
    return -1;
  }
  glass::watch();
  ESP_LOGI(TAG, "stream %d into %dx%d at %d,%d%s, turned %d, PPA bursts of %d bytes", slot, area.w, area.h, area.x, area.y,
           look.tile ? (look.contain ? " (a tile, whole picture)" : " (a tile)") : "", s->turn, glass::PPA_BURST_BYTES);
  return slot;
}

void mute(Handle handle, bool muted) {
  if (handle < 0 || handle >= MAX_STREAMS || !streams[handle]) return;
  streams[handle]->muted = muted;
  if (muted && streams[handle]->sound) xStreamBufferReset(streams[handle]->sound);
}

// The main loop hands a stream's sound to the speaker: it starts once a part of a second waits (so it does not stutter
// at its first gap) and stops with the stream or when muted.
static void speak(Stream &s, bool on) {
#ifdef USE_SPEAKER
  if (!speaker || !s.sound) return;
  if (!on) {
    if (s.speaking) speaker->stop();
    s.speaking = false;
    s.piece_left = 0;
    return;
  }
  if (!s.speaking) {
    if (xStreamBufferBytesAvailable(s.sound) < SOUND_RATE * 2 * 150 / 1000) return;
    speaker->set_audio_stream_info(esphome::audio::AudioStreamInfo(16, 1, SOUND_RATE));
    speaker->start();
    s.speaking = true;
  }
  for (int rounds = 0; rounds < 8; ++rounds) {
    if (s.piece_left == 0) {
      s.piece_left = xStreamBufferReceive(s.sound, s.sound_piece, SOUND_PART, 0);
      s.piece_at = 0;
      if (s.piece_left == 0) return;
    }
    const size_t taken = speaker->play(s.sound_piece + s.piece_at, s.piece_left, 0);
    s.piece_at += taken;
    s.piece_left -= taken;
    if (taken == 0) return;  // the speaker's own buffer is full: the rest next tick
  }
#else
  (void) s;
  (void) on;
#endif
}

size_t held_bytes() {
  size_t held = 0;
  for (auto *s : streams)
    if (s && !s->stopping) held += s->input_size + static_cast<size_t>(std::max(0, s->area.w)) * std::max(0, s->area.h) * 2;
  return held;
}

void close(Handle handle) {
  if (handle < 0 || handle >= MAX_STREAMS || !streams[handle]) return;
  Stream &s = *streams[handle];
  s.stopping = true;
  // A copy on its way finishes; none starts after this, and LVGL draws there again (glass::disarm, under the glass).
  glass::disarm(s.room, true);
}

static void report(int slot, Stream &s, uint32_t now, bool last) {
  const uint32_t span = now - s.reported_at;
  if (span == 0) return;
  const uint32_t shown = s.shown, bytes = s.bytes, decode = s.decode_us, copied = s.copy_us;
  const uint32_t frames = shown - s.reported_shown;
  ESP_LOGI(TAG, "%s %d: %.1f pictures/s, %u KB/s, decoding %.1f ms and laying out %.1f ms a picture, %u skipped in all, "
           "the panel ran dry %u times since boot",
           last ? "ended" : "stream", slot, frames * 1000.0f / span, (unsigned) ((bytes - s.reported_bytes) / span),
           frames ? (decode - s.reported_decode) / 1000.0f / frames : 0.0f,
           frames ? (copied - s.reported_copy) / 1000.0f / frames : 0.0f, (unsigned) s.skipped, (unsigned) glass::misses());
  s.reported_at = now;
  s.reported_shown = shown;
  s.reported_bytes = bytes;
  s.reported_decode = decode;
  s.reported_copy = copied;
}

void tick(const std::function<void(Handle, Event)> &tell) {
  const uint32_t now = esphome::millis();
  const int turn = glass::turn();
  glass::tick();
  for (int slot = 0; slot < MAX_STREAMS; ++slot) {
    Stream *s = streams[slot];
    if (!s) continue;
    if (s->done.load(std::memory_order_acquire)) {
      const bool in_psram = psram_task::in_psram(s->task);
      psram_task::reap(s->task);  // its task deleted (a stack in PSRAM) before anything of the stream is freed
      speak(*s, false);
      report(slot, *s, now, true);
      ESP_LOGI(TAG, "ended %d: its task's stack was in %s, %u of %u bytes of it never used", slot,
               in_psram ? "PSRAM" : "internal RAM", (unsigned) s->stack_left.load(std::memory_order_relaxed),
               (unsigned) STACK_BYTES);
      const bool turned = s->turn != turn, ended = s->stopping && !s->failed;
      glass::disarm(s->room, false);  // its task has ended: nothing of it copies, and LVGL draws the room again
      streams[slot] = nullptr;
      // A full view's stream gone for good: LVGL draws the whole glass once more, now that its task decodes and copies
      // nothing. Now and then the view's top bar, the back key and the name, stayed over the page after the camera
      // closed while the picture's room below it was drawn again, until something else drew there (2026-10-15, a P4
      // board). The redraw at closing comes while the task may still be busy with its last picture, and its first strip
      // is that bar; this one comes after. The whole glass, as the view covered all of it.
      if (!s->look.tile) glass::redraw_all();
      free_stream(s);
      tell(slot, turned ? Event::TURNED : ended ? Event::ENDED : Event::FAILED);
      continue;
    }
    // Its picture lies elsewhere now, or at another size: LVGL draws where it lay again (but where it lies now).
    glass::follow(s->room);
    // The glass turned (a setting): this stream's place is gone; its owner asks again for its new shape.
    if (s->turn != turn && !s->stopping) close(slot);
    speak(*s, !s->stopping && !s->muted);
    if (!s->told_sound && s->heard) {
      s->told_sound = true;
      tell(slot, Event::SOUND);
    }
    if (now - s->reported_at >= REPORT_MS) report(slot, *s, now, false);
    if (!s->told_first && s->shown > 0) {
      s->told_first = true;
      ESP_LOGI(TAG, "stream %d: first picture on the glass %u ms after it started (connected after %u, the app "
               "answered after %u, its first bytes after %u)", slot, (unsigned) (now - s->started_at),
               (unsigned) s->connected_ms, (unsigned) s->answered_ms, (unsigned) s->first_bytes_ms);
      tell(slot, Event::FIRST);
    }
    if (s->told_first && !s->told_live && s->live.load()) {
      s->told_live = true;
      ESP_LOGI(TAG, "stream %d: live %u ms after it started", slot, (unsigned) s->live_ms);
      tell(slot, Event::LIVE);
    }
  }
}

}  // namespace live_view
#endif
