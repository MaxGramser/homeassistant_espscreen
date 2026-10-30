// The live view's streams on a P4 (live_view.h says why and what).
//
// Each stream (the full view, a live tile of the page on the glass) is a task of its own with its own buffers and PPA
// client, owned by the main loop: open() makes it, close() and tick() end it. Two halves make it:
//
// - Where its pictures come from, its Source: the app's link asked for each picture (a live tile), the app's stream of
//   pictures and sound (the full view, and a tile of an app before asking), or the screen's own camera's frames (a tile
//   of it, plugin API 0.22). Each runs on the stream's task until the stream stops.
// - What every stream does with a picture, shared: decoded with the hardware JPEG decoder, laid out (a full view's
//   scaled to fill its room; a tile's card, corners, shade and name, laid over it as one overlay made once,
//   live_view::Overlay) and copied onto the glass with the PPA, turned as LVGL turns its drawing where the app did not
//   turn the picture so already (X-Turn); a live tile kept to its pace (pace), a busy screen's tile to a share of it
//   (the governor, pressure.h).
//
// A copy happens with the glass held (glass.h: one writer at a time, and one user of the 2D-DMA) and only while nobody
// stopped the stream, so once close() returns nothing of it writes the glass any more and LVGL may draw there at once.
// A stream's task runs below the voice and holds the glass at the writers' priority (take_glass). Buffers live in PSRAM
// and go when the task has ended (tick()). The panel, its frame buffer, the lock and the rooms LVGL keeps out of are the
// glass's (glass.h, glass_dsi.cpp); the decoder and the PPA copies are the engine's (picture_engine.h).
#include "live_view.h"
#include "glass.h"
#include "picture_engine.h"
#include "hw.h"
#include "pressure.h"
#if defined(USE_LIVE_VIEW) && defined(SCREEN_PICTURES)
#include <algorithm>
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

#include "audio_owner.h"
#include "psram_task.h"
#include "roomy.h"
#ifdef USE_SPEAKER
#include "esphome/components/audio/audio.h"
#include "esphome/components/speaker/speaker.h"
#endif

namespace live_view {

static const char *const TAG = "live";
constexpr size_t CHUNK = 16 * 1024;
// A live tile's pause (pace): a read and a picture longer than this say nothing of its pace (a camera that paused).
constexpr int64_t PACE_GAP_US = 2000000;
// A picture of a stream this much later on its way than the quickest is a frame behind (read_stream, Wait).
constexpr uint32_t STALE_MS = 150;
constexpr uint32_t PAUSE_STEP_MS = 20;
constexpr uint32_t STACK_BYTES = 6144;  // a stream task's stack (psram_task.h), its high water logged as it ends
constexpr unsigned STREAM_PRIORITY = 2;  // below the wake word's inference (3), above the main loop (1): take_glass
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

// How long the parts of a stream waited on their way, from the app's X-Made: the app's clock and this one differ by a
// constant (and a drift of milliseconds an hour), so the least difference seen is the way at its quickest and what lies
// over it the wait. Kept by the stream's task, read by the main loop for its report.
struct Wait {
  bool seen = false;
  int32_t quickest = 0;
  std::atomic<uint32_t> count{0}, total_ms{0}, most_ms{0};
  uint32_t reported_count = 0, reported_total = 0;
  // A part that left the app at `made` came now: its wait, which is also counted.
  uint32_t add(uint32_t made) {
    const int32_t gap = static_cast<int32_t>(static_cast<uint32_t>(esp_timer_get_time() / 1000) - made);
    if (!seen || gap < quickest) {
      quickest = gap;
      seen = true;
    }
    const uint32_t waited = static_cast<uint32_t>(gap - quickest);
    count++;
    total_ms += waited;
    if (waited > most_ms) most_ms = waited;
    return waited;
  }
};

struct Stream;
// Where a stream's pictures come from (the file's head): run on the stream's task until it stops; false when this
// source cannot serve it, and the next one takes over (a tile's ask_each on an app before it: read_stream).
struct Source {
  const char *what;
  bool (*run)(Stream &s);
  const Source *otherwise;
};

// ---- One stream ----
// One overlay of a tile (live_view.h, Overlay) made for pictures that lie `lies` degrees turned (-1: not made): its shade,
// and its marks' segments and pixels, in PSRAM.
struct MadeOverlay {
  int lies = -1;
  uint8_t *shade = nullptr, *alpha = nullptr;
  OverlaySegment *segments = nullptr;
  uint16_t *color = nullptr;
  Overlay over;
  void clear() {
    for (void *part : {static_cast<void *>(shade), static_cast<void *>(segments), static_cast<void *>(alpha),
                       static_cast<void *>(color)})
      if (part) free(part);
    *this = MadeOverlay{};
  }
};

struct Stream {
  const Source *source = nullptr;
  std::string url;
  Rect area;
  Look look;
  uint32_t *name = nullptr;   // the stream's own copy of look.name
  uint32_t *badge = nullptr;  // and of look.badge
  int turn = 0;
  std::atomic<bool> stopping{false}, done{false}, failed{false};
  // Its room on the glass (glass.h): LVGL is kept out of where its picture lies from the first picture on (placed by
  // the task just before it copies one); until then LVGL draws as ever, a spinner turning while the camera comes.
  glass::Room room = -1;
  std::atomic<uint32_t> shown{0}, bytes{0}, decode_us{0}, copy_us{0}, skipped{0};
  // Time a picture waited for the glass (glass::hold) while it was laid out, inside copy_us; and of a tile's lay-out, the
  // PPA's copy into its card and onto the glass (each under the glass) and the composing between them.
  std::atomic<uint32_t> wait_us{0}, into_us{0}, compose_us{0}, onto_us{0};
  // A live tile pauses after a picture instead of reading on: to keep to its share (tile_gap_us), and on a busy screen (the
  // governor's LIVE_TILES, pressure.h) to half or a quarter of that or of its own pace, whichever is slower. It reads
  // nothing meanwhile, so the app sends fewer (it makes the next picture once the last one left its host) and the
  // Wi-Fi rests too. Leaving pictures out undecoded saved nothing, as the tile only read the next one sooner (a
  // reTerminal D1001, 2026-10-28: 6.5 pictures a second shown either way, twice the bytes). Its pace (what a read and a
  // picture took, smoothed) and when it last went on reading; the pauses for a busy screen and their time; and the time
  // recv waited for the app.
  uint32_t pace_us = 0;
  int64_t free_at = 0;
  std::atomic<uint32_t> pauses{0}, paused_us{0}, net_us{0};
  std::atomic<uint32_t> passed{0};  // pictures of a stream passed for a newer one (read_stream)
  int64_t view_at = 0;               // a full view's last picture shown, for the engine's view_pps
  // How long its pictures and its sound waited on their way (X-Made: Wait).
  Wait picture_wait, sound_wait;
  // When the way to the first picture went by (ms after start, written once by the task, read after `shown`).
  uint32_t started_at = 0, connected_ms = 0, answered_ms = 0, first_bytes_ms = 0;
  uint32_t live_ms = 0;  // its first live picture (written once by the task, read after `live`)
  picture_engine::Client ppa = nullptr;  // its client of the PPA (the engine's)
  uint8_t *input = nullptr, *picture = nullptr;
  uint16_t *canvas = nullptr;
  size_t input_size = 0, picture_size = 0, canvas_size = 0;
  // What a tile lays over each picture (MadeOverlay), made at its first picture for the way its pictures lie (X-Turn);
  // and the same with the mark of a squeezed tile, made the first time the governor squeezes the live tiles.
  // `onto_turn`: what the PPA still turns on a picture's way onto the glass, for the report.
  MadeOverlay plain, squeezed;
  std::atomic<int> onto_turn{0};
  // The camera's sound (a full view on a board with a speaker): parts the task puts in `sound`, which the main loop
  // hands to the speaker unless `muted`.
  // Its storage in PSRAM, its control (with the spinlock its critical sections take) inside the chip: made static over
  // memory of the stream's own (sound_control, sound_storage), never with xStreamBufferCreateWithCaps. ESP-IDF 5.5.5's
  // vStreamBufferDeleteWithCaps deletes a stream buffer as a queue (vSemaphoreDelete), reads a byte past the control
  // as the queue's "statically allocated" flag and, when that byte is 0, frees the control twice (espressif/esp-idf
  // #18855, on release/v5.5 after 5.5.5). A test build that moved this buffer to PSRAM with the WithCaps pair restarted
  // a reTerminal D1001 that way at the close of a camera with sound (2026-10-25, tlsf_free "block already marked as
  // free"); no release ever built it so, the buffer was an ordinary xStreamBufferCreate before.
  StreamBufferHandle_t sound = nullptr;
  StaticStreamBuffer_t *sound_control = nullptr;
  uint8_t *sound_storage = nullptr;
  uint8_t *sound_part = nullptr;
  uint8_t *sound_piece = nullptr;  // what the speaker took part of, the rest of it next tick
  size_t piece_left = 0, piece_at = 0;
  // Whole samples only (s16le, two bytes each): parts of an odd length cut to even (the task) and writes the speaker
  // took an odd number of bytes of (the main loop), counted for the stream's last line, which should say none.
  std::atomic<uint32_t> odd_parts{0};
  std::atomic<uint32_t> full_parts{0};  // parts left out because the buffer had no room for all of it
  uint32_t odd_taken = 0;
  uint32_t caught_up = 0, caught_up_bytes = 0;  // the times the main loop left the oldest out (SOUND_HIGH), and how much
  // The buffer ran dry while speaking: the speaker gets nothing until SOUND_LOW waits again, as at the start, instead of
  // each part as it trickles in (which played as snippets out of joint, 2026-10-29). Counted for the stream's line.
  bool dry = false;
  uint32_t ran_dry = 0;
  std::atomic<bool> muted{false}, heard{false};
  // The speaker is someone else's for now (audio_owner.h: a voice session or a doorbell took it): the sound is held back
  // as when muted, and plays again once the owner gives the speaker back. Set on the main loop, read by the task.
  std::atomic<bool> yielded{false};
  audio_owner::Role sound_role = audio_owner::Role::CAMERA_SOUND;  // the role its sound claimed (open), released with it
  audio_owner::Side claimed = audio_owner::Side::OUT;              // and the sides, while `claims`
  bool claims = false;
  // Until it is live (live_view.h): the picture on the glass is a still (the task turns a tile's loader over it), and a
  // live one was shown. `under` holds the loader's square of the card as composed, its last turn drawn at `turned_at`.
  std::atomic<bool> warming{false}, live{false};
  uint16_t *under = nullptr;
  uint32_t turned_at = 0;
  // The main loop's own: the report of the last REPORT_MS, the first picture, its first live one and sound told, the
  // speaker started.
  bool told_first = false, told_live = false, told_sound = false, speaking = false;
  uint32_t reported_at = 0, reported_shown = 0, reported_bytes = 0, reported_decode = 0, reported_copy = 0,
           reported_wait = 0, reported_net = 0, reported_into = 0, reported_compose = 0, reported_onto = 0,
           reported_passed = 0, reported_pauses = 0, reported_paused = 0;
  psram_task::Task task;  // its task, its stack in PSRAM: the main loop deletes it once done (psram_task.h)
  // A tile of the screen's own camera (take_frames): its card's canvas filled from a camera frame on the camera's task
  // (own_frame), then `own_full` until its own task laid it onto the glass; and when it takes the next.
  std::atomic<bool> own_full{false};
  int64_t own_next = 0;
  std::atomic<uint32_t> stack_left{0};  // what of its stack the task never used, in bytes (written before `done`)
};
static Stream *streams[MAX_STREAMS] = {};
static_assert(MAX_STREAMS <= glass::MAX_ROOMS, "every stream has a room on the glass");
// The live tiles streaming, a camera's or the screen's own: counted as they open and as they are reaped, on the main
// loop, and read by every tile's pace (tile_pps).
static std::atomic<int> tiles_open{0};
// What one tile waits between pictures: the engine's budget shared among the tiles streaming (picture_engine::tile_pps),
// on a busy screen half or a quarter of that (the governor's LIVE_TILES, pressure.h).
static int64_t tile_gap_us() {
  const int pps = picture_engine::tile_pps(picture_engine::limits().tile_budget_pps,
                                           tiles_open.load(std::memory_order_relaxed), hw::LIVE_TILE_PPS);
  return 1000000 / pps;
}

static void free_stream(Stream *s) {
  if (s->sound) vStreamBufferDelete(s->sound);  // static: frees nothing, its memory is the stream's own below
  if (s->sound_control) heap_caps_free(s->sound_control);
  if (s->sound_storage) roomy::release(s->sound_storage);
  if (s->sound_part) roomy::release(s->sound_part);
  if (s->sound_piece) roomy::release(s->sound_piece);
  if (s->input) free(s->input);
  if (s->picture) free(s->picture);
  if (s->canvas) free(s->canvas);
  s->plain.clear();
  s->squeezed.clear();
  if (s->name) free(s->name);
  if (s->badge) free(s->badge);
  if (s->under) free(s->under);
  picture_engine::drop(s->ppa);
  if (s->room >= 0) glass::give_back(s->room);
  delete s;
}

// The engine's copy (picture_engine::blit): the block `bw` x `bh` at bx, by of a picture (`in_w` x `rows`) to x, y of
// another (ow x oh, `out_size` bytes), at the engine's `scale` (picture_engine::fit, cut) and turned as LVGL turns.
static esp_err_t copy(Stream &s, const void *in, int in_w, int rows, int bx, int by, int bw, int bh, void *out,
                      size_t out_size, int ow, int oh, int x, int y, int scale, int turn) {
  picture_engine::Block block;
  block.in = in, block.in_w = in_w, block.in_rows = rows, block.bx = bx, block.by = by, block.bw = bw, block.bh = bh;
  block.out = out, block.out_size = out_size, block.out_w = ow, block.out_h = oh, block.x = x, block.y = y;
  block.scale = scale, block.turn = turn;
  block.swap = out == glass::frame_buffer() && glass::panel().swapped;
  return static_cast<esp_err_t>(picture_engine::blit(s.ppa, block));
}

// One overlay of a tile (live_view.h) for pictures that lie turned `lies`, with the squeezed mark or without: made on
// the stream's task, once. False without the memory for it.
static bool make_overlay(Stream &s, MadeOverlay &made, int lies, bool badge) {
  const int64_t from = esp_timer_get_time();
  const int w = s.area.w, h = s.area.h;
  made.clear();
  Overlay o{turned_w(w, h, lies), turned_h(w, h, lies)};
  made.shade = static_cast<uint8_t *>(heap_caps_malloc(std::max(w, h), MALLOC_CAP_SPIRAM));
  if (!made.shade) return false;
  o.shade_count = overlay_shade(s.look, w, h, lies, made.shade, o.shade_by_column, o.shade_from);
  size_t pixels = 0;
  o.count = overlay_marks(s.look, w, h, lies, nullptr, pixels, nullptr, nullptr, badge);
  made.segments = static_cast<OverlaySegment *>(
      heap_caps_malloc(sizeof(OverlaySegment) * std::max(o.count, 1), MALLOC_CAP_SPIRAM));
  made.alpha = static_cast<uint8_t *>(heap_caps_malloc(std::max<size_t>(pixels, 1), MALLOC_CAP_SPIRAM));
  made.color = static_cast<uint16_t *>(heap_caps_malloc(std::max<size_t>(pixels, 1) * 2, MALLOC_CAP_SPIRAM));
  if (!made.segments || !made.alpha || !made.color) {
    made.clear();
    return false;
  }
  overlay_marks(s.look, w, h, lies, made.segments, pixels, made.alpha, made.color, badge);
  o.shade = made.shade, o.segments = made.segments, o.alpha = made.alpha, o.color = made.color;
  made.over = o;
  made.lies = lies;
  ESP_LOGI(TAG, "its card's overlay%s for pictures turned %d: a shade of %d %s, %d marks of %u pixels, made in %u ms",
           badge ? " with the squeezed mark" : "", lies, o.shade_count, o.shade_by_column ? "columns" : "rows", o.count,
           (unsigned) pixels, (unsigned) ((esp_timer_get_time() - from) / 1000));
  return true;
}
// A tile's overlay for pictures that lie turned `lies`: made at its first picture, again only if its pictures came to
// lie otherwise. False without the memory for it.
static bool overlay_for(Stream &s, int lies) {
  return s.plain.lies == lies || make_overlay(s, s.plain, lies, false);
}
// What a picture gets laid over it now: with the squeezed mark while the governor squeezes the live tiles (pressure.h),
// made the first time it does; the plain one at rest, for a card without the mark, or when its memory is not there
// (the mark then stays off for this stream).
static const Overlay &overlay_now(Stream &s) {
  if (!s.look.badge || pressure::level_of(pressure::LIVE_TILES) == 0) return s.plain.over;
  if (s.squeezed.lies != s.plain.lies && !make_overlay(s, s.squeezed, s.plain.lies, true)) {
    s.look.badge = nullptr;
    return s.plain.over;
  }
  return s.squeezed.over;
}

// A tile's loader square: where it lies in the card's canvas, as the pictures lie (s.plain.lies), and on the glass.
static bool loader_square(const Stream &s, Rect &in_canvas, Rect &on_glass) {
  int lx = 0, ly = 0;
  if (s.plain.lies < 0 || !loader_spot(s.look, s.area.w, s.area.h, lx, ly)) return false;
  const int size = s.look.loader;
  in_canvas = in_turned(Rect{lx, ly, size, size}, s.plain.lies, s.area.w, s.area.h);
  const glass::Panel panel = glass::panel();
  on_glass = on_panel(Rect{s.area.x + lx, s.area.y + ly, size, size}, s.turn, panel.w, panel.h);
  return true;
}

// A tile's loader over a still (live_view.h, "Until it is live"): its square of the card as composed kept in `under`,
// and the loader drawn over it as it stands now.
static bool lay_loader(Stream &s) {
  Rect at, unused;
  if (!s.under || !loader_square(s, at, unused)) return false;
  const int cw = s.plain.over.w, size = s.look.loader;
  for (int j = 0; j < size; ++j)
    memcpy(s.under + static_cast<size_t>(j) * size, s.canvas + static_cast<size_t>(at.y + j) * cw + at.x,
           static_cast<size_t>(size) * 2);
  s.turned_at = esphome::millis();
  draw_loader(s.canvas, cw, at.x, at.y, s.look, s.turned_at);
  return true;
}
// Its next turn, between the stills: the square as composed again, the loader over it, and that square alone onto the
// glass, every LOADER_STEP_MS while the task waits for the stream's next bytes.
// A stream's task runs below the voice assistant's wake word (STREAM_PRIORITY), and asks for and holds the glass at
// glass::WRITER_PRIORITY, in turn with the other streams and a still's download (picture_engine::decode), then goes back:
// composing a picture and reading the app run below the voice. At WRITER_PRIORITY throughout, four tiles' composing (30
// ms of wall clock a picture on a reTerminal D1001) and the screen's own video (priority 4) left the wake word's
// inference (ESPHome's micro_wake_word, priority 3) behind 644 times in an hour at rest (2026-10-28).
static uint32_t take_glass() {
  vTaskPrioritySet(nullptr, glass::WRITER_PRIORITY);
  return glass::hold_counted();
}
static void give_glass() {
  glass::release();
  vTaskPrioritySet(nullptr, STREAM_PRIORITY);
}

static void turn_loader(Stream &s) {
  const uint32_t now = esphome::millis();
  Rect at, target;
  if (!s.warming || now - s.turned_at < LOADER_STEP_MS || !loader_square(s, at, target)) return;
  s.turned_at = now;
  const int cw = s.plain.over.w, ch = s.plain.over.h, size = s.look.loader;
  for (int j = 0; j < size; ++j)
    memcpy(s.canvas + static_cast<size_t>(at.y + j) * cw + at.x, s.under + static_cast<size_t>(j) * size,
           static_cast<size_t>(size) * 2);
  draw_loader(s.canvas, cw, at.x, at.y, s.look, now);
  const glass::Panel panel = glass::panel();
  esp_err_t err = ESP_OK;
  take_glass();
  if (!s.stopping && glass::armed(s.room))
    err = copy(s, s.canvas, cw, ch, at.x, at.y, size, size, glass::frame_buffer(),
               static_cast<size_t>(panel.w) * panel.h * 2, panel.w, panel.h, target.x, target.y, picture_engine::AS_IS,
               turn_between(s.plain.lies, s.turn));
  give_glass();
  if (err != ESP_OK) s.warming = false;  // the loader stops where it stands; the pictures go on
}

// The glass held for a copy of the lay-out, and how long that waited for it (another stream's copy, LVGL's flush).
static void hold_timed(Stream &s) { s.wait_us += take_glass(); }

// One picture of `length` bytes at `data`: decoded, laid out, and copied onto the glass. `still`: the camera's still
// from before its stream came, with the loader over it on a tile. `turn`: how the app turned the picture for a turned
// glass (X-Turn, the hello's picture_turn): a tile lays its card over it as it lies, and the PPA turns only what is left
// between the picture and the glass, nothing on a glass the app turned it for.
static void show(Stream &s, const uint8_t *data, size_t length, bool still, int turn) {
  picture_engine::Still info;
  if (!picture_engine::info(data, length, info)) {
    s.skipped++;
    return;
  }
  // The decoder writes whole MCUs (picture_jpeg.h): `stride_w` pixels a row, `rows` of them.
  const int stride_w = info.stride;
  const int rows = static_cast<int>(info.bytes / 2 / info.stride);
  const int w = info.w, h = info.h;
  // Where it goes: a full view's picture as large as fits its room, worked out on the picture upright; a tile's into its
  // card, the card as the picture lies.
  int scale = 0;
  Rect where;
  picture_engine::Cut into;
  const int lies = turn;
  const int cw = turned_w(s.area.w, s.area.h, lies), ch = turned_h(s.area.w, s.area.h, lies);
  if (s.look.tile) {
    into = picture_engine::cut(w, h, cw, ch, s.look.contain);
    if (into.ok) where = s.area;
  } else {
    const picture_engine::Fit f =
        picture_engine::fit(turned_w(w, h, lies), turned_h(w, h, lies), s.area.x, s.area.y, s.area.w, s.area.h);
    if (!f.empty()) where = Rect{f.x, f.y, f.w, f.h};
    scale = f.scale;
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
  // A P4's decoder works through the 2D-DMA, as the PPA and the panel's copy of each of LVGL's strips do: it decodes
  // while it holds the glass (glass.h). Its wait counts in the glass's report, not in the stream's own. An S3's decodes
  // with the CPU, and holds nothing (picture_engine::Limits::decode_on_glass).
  const bool on_glass = picture_engine::limits().decode_on_glass;
  if (on_glass) take_glass();
  if (s.stopping) {
    if (on_glass) give_glass();
    return;
  }
  const int64_t t0 = esp_timer_get_time();
  const bool decoded = picture_engine::decode_into(data, length, s.picture, s.picture_size);
  const int64_t t1 = esp_timer_get_time();
  if (on_glass) give_glass();
  if (!decoded) {
    s.skipped++;
    return;
  }
  if (s.shown == 0)
    ESP_LOGI(TAG, "picture %dx%d (decoded %d wide) in %u us, for %dx%d at %d,%d, scale %d", w, h, stride_w,
             (unsigned) (t1 - t0), where.w, where.h, where.x, where.y, s.look.tile ? into.scale : scale);
  const glass::Panel panel = glass::panel();
  const size_t glass_size = static_cast<size_t>(panel.w) * panel.h * 2;
  esp_err_t err = ESP_OK;
  bool loading = false;
  if (s.look.tile && !overlay_for(s, lies)) {
    ESP_LOGW(TAG, "no memory for the overlay of a card of %dx%d", s.area.w, s.area.h);
    s.failed = true;
    s.stopping = true;
    return;
  }
  const int onto = turn_between(lies, s.turn);
  s.onto_turn = onto;
  // A live tile's picture the app sent at the card's own size (it makes them for the card, a few pixels over): the card
  // is composed in the decoded picture where it lies, and the PPA copies it once, onto the glass. Through the card's
  // canvas the PPA worked twice under the glass, and four tiles waited their turn for it: on a reTerminal D1001 18 ms
  // into the canvas and 18.5 onto the glass a picture, with 20 ms composing between, so each tile waited 60 to 80 ms
  // for the others (2026-10-28). A still keeps the canvas, which its loader turns over.
  if (s.look.tile && !still && into.ok && into.scale == picture_engine::AS_IS && into.covers(cw, ch) &&
      into.in_w == cw && into.in_h == ch) {
    int64_t from = esp_timer_get_time();
    uint16_t *card = reinterpret_cast<uint16_t *>(s.picture) + static_cast<size_t>(into.in_y) * stride_w + into.in_x;
    lay_overlay(card, stride_w, overlay_now(s));
    const Rect target = on_panel(s.area, s.turn, panel.w, panel.h);
    s.compose_us += static_cast<uint32_t>(esp_timer_get_time() - from);
    hold_timed(s);
    from = esp_timer_get_time();
    if (!s.stopping) {
      glass::place(s.room, s.area);  // from now on LVGL draws nothing here
      err = copy(s, s.picture, stride_w, rows, into.in_x, into.in_y, cw, ch, glass::frame_buffer(), glass_size, panel.w,
                 panel.h, target.x, target.y, picture_engine::AS_IS, onto);
    }
    give_glass();
    s.onto_us += static_cast<uint32_t>(esp_timer_get_time() - from);
  } else if (s.look.tile) {
    // The card: the picture cut or fitted into it, on black where it leaves room, then the shade, corners and name.
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
    hold_timed(s);
    int64_t from = esp_timer_get_time();
    err = copy(s, s.picture, stride_w, rows, into.in_x, into.in_y, into.in_w, into.in_h, s.canvas, s.canvas_size, cw,
               ch, into.out_x, into.out_y, into.scale, 0);
    give_glass();
    int64_t to = esp_timer_get_time();
    s.into_us += static_cast<uint32_t>(to - from);
    if (err == ESP_OK) {
      lay_overlay(s.canvas, cw, overlay_now(s));
      loading = still && lay_loader(s);
      from = esp_timer_get_time();
      s.compose_us += static_cast<uint32_t>(from - to);
      const Rect target = on_panel(s.area, s.turn, panel.w, panel.h);
      hold_timed(s);
      from = esp_timer_get_time();
      if (!s.stopping) {
        glass::place(s.room, s.area);  // from now on LVGL draws nothing here
        err = copy(s, s.canvas, cw, ch, 0, 0, cw, ch, glass::frame_buffer(), glass_size, panel.w, panel.h, target.x,
                   target.y, picture_engine::AS_IS, onto);
      }
      give_glass();
      s.onto_us += static_cast<uint32_t>(esp_timer_get_time() - from);
    }
  } else {
    // The full view: scaled to fill its room on the way (the app sends the camera's own size where that is smaller).
    const Rect target = on_panel(where, s.turn, panel.w, panel.h);
    hold_timed(s);
    if (!s.stopping) {
      glass::place(s.room, where);
      err = copy(s, s.picture, stride_w, rows, 0, 0, w, h, glass::frame_buffer(), glass_size, panel.w, panel.h, target.x,
                 target.y, scale, onto);
    }
    give_glass();
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

// After a live tile's picture: its pace kept and the pause it owes, to its share of the engine's budget or to a busy
// screen's share of that (Stream, pace_us). Each 20 ms it looks again whether the pressure eased or the stream stops; it reads nothing
// meanwhile.
static void pace(Stream &s) {
  const int64_t now = esp_timer_get_time();
  // What the read and this picture took since the task last went on reading, as the next will take about as long.
  const int64_t took = s.free_at ? now - s.free_at : 0;
  if (took > 0 && took < PACE_GAP_US)
    s.pace_us = s.pace_us ? static_cast<uint32_t>((3 * static_cast<int64_t>(s.pace_us) + took) / 4)
                          : static_cast<uint32_t>(took);
  const int64_t base = std::max<int64_t>(s.pace_us, tile_gap_us());
  const bool busy = pressure::level_of(pressure::LIVE_TILES) > 0;
  if (busy) s.pauses++;
  for (;;) {
    const uint8_t level = pressure::level_of(pressure::LIVE_TILES);
    if (s.stopping || esp_timer_get_time() + took >= now + (base << level)) break;
    vTaskDelay(pdMS_TO_TICKS(PAUSE_STEP_MS));
  }
  s.free_at = esp_timer_get_time();
  if (busy) s.paused_us += static_cast<uint32_t>(s.free_at - now);
}

// ---- The sources ----
// A live tile asks the app for each picture (its link's .jpg, live_stream.py pull): one at a time over a kept connection,
// when its pace says, so nothing waits on the way and the app sends only what the tile shows. An ask with nothing newer
// within the app's wait answers 204, and the tile asks again. False when the app has no such link (an app before it
// answers 404 at the first ask).
static bool ask_each(Stream &s) {
  const auto address = picture_fetch::split(s.url);
  const std::string path = address.ok ? pull_path(address.path) : "";
  if (path.empty()) return false;
  const int fd = picture_fetch::connect_to(address, WAIT_MS);
  if (fd < 0) {
    ESP_LOGW(TAG, "no connection to %s:%u", address.host.c_str(), address.port);
    s.failed = true;
    return true;
  }
  s.connected_ms = esphome::millis() - s.started_at;
  auto *chunk = static_cast<uint8_t *>(roomy::allocate(CHUNK));
  if (!chunk) {
    ::close(fd);
    s.failed = true;
    return true;
  }
  if (s.under) {  // a tile with a loader waits in short steps, so its loader turns between the stills
    timeval step{0, static_cast<suseconds_t>(LOADER_STEP_MS * 1000)};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &step, sizeof(step));
  }
  const std::string ask = "GET " + path + " HTTP/1.1\r\nHost: " + address.host + "\r\n\r\n";
  const size_t most = picture_engine::limits().tile_picture_bytes;
  bool supported = true, first = true;
  std::string head;
  while (!s.stopping) {
    if (!picture_fetch::send_all(fd, ask)) {
      ESP_LOGW(TAG, "the app's link closed");
      s.failed = true;
      break;
    }
    // The answer: its head, then Content-Length bytes of picture (none for 204). The app sends nothing unasked, so what
    // one read brings past the head is this picture's.
    head.clear();
    size_t length = 0, got = 0;
    picture_fetch::Head h;
    uint32_t heard = esphome::millis();
    bool broken = false;
    while (!s.stopping) {
      const int64_t asked = esp_timer_get_time();
      const int n = recv(fd, chunk, CHUNK, 0);
      const int error = errno;
      s.net_us += static_cast<uint32_t>(esp_timer_get_time() - asked);
      turn_loader(s);
      if (n < 0 && (error == EAGAIN || error == EWOULDBLOCK)) {
        if (esphome::millis() - heard < QUIET_MS) continue;
        ESP_LOGW(TAG, "the app went quiet");
        broken = true;
        break;
      }
      if (n <= 0) {
        ESP_LOGW(TAG, "the app's link ended (%d, errno %d)", n, error);
        broken = true;
        break;
      }
      heard = esphome::millis();
      if (s.bytes == 0) s.first_bytes_ms = heard - s.started_at;
      s.bytes += n;
      size_t at = 0;
      if (!h.complete) {
        head.append(reinterpret_cast<const char *>(chunk), n);
        h = picture_fetch::parse_head(head.data(), head.size());
        if (!h.complete) {
          if (head.size() >= MAX_HEAD) broken = true;
          if (broken) break;
          continue;
        }
        if (!s.answered_ms) s.answered_ms = heard - s.started_at;
        if (h.status == 404 && first) {
          supported = false;
          break;
        }
        if (h.status == 204) break;
        if (h.status != 200 || !h.has_length || h.content_length == 0 || h.content_length > most ||
            h.content_length > s.input_size) {
          ESP_LOGW(TAG, "not a picture (answer %d, %u bytes)", h.status, (unsigned) h.content_length);
          broken = true;
          break;
        }
        length = h.content_length;
        at = n - (head.size() - h.length);  // where this read's picture bytes begin
      }
      const size_t take = std::min(static_cast<size_t>(n) - at, length - got);
      memcpy(s.input + got, chunk + at, take);
      got += take;
      if (got == length) break;
    }
    first = false;
    if (broken) {
      s.failed = true;
      break;
    }
    if (!supported || s.stopping) break;
    if (h.status == 204 || got != length || length == 0) continue;
    if (h.has_made) s.picture_wait.add(h.made);
    show(s, s.input, length, h.still, h.turn);
    if (!h.still) pace(s);
  }
  ::close(fd);
  roomy::release(chunk);
  if (!supported) ESP_LOGI(TAG, "the app sends this tile as a stream (it answers no ask for a picture)");
  return supported;
}

// The screen's own camera on a tile of its own (live_view.h, own_frame).
// The open tiles of it, which the camera's task reads under own_lock while it fills one's canvas; the main loop takes a
// tile out under it before it frees the stream. The camera's task never waits for it: a frame it cannot take goes by.
static Stream *own_tiles[MAX_STREAMS] = {};
static SemaphoreHandle_t own_lock = nullptr;
static std::atomic<bool> offered{false};
static std::atomic<int> own_open{0};

void own_offer() { offered.store(true, std::memory_order_release); }
bool own_offered() { return offered.load(std::memory_order_acquire) && available(); }
bool own_wanted() { return own_open.load(std::memory_order_relaxed) > 0; }

static void own_add(Stream *s) {
  if (!own_lock) own_lock = xSemaphoreCreateMutex();
  xSemaphoreTake(own_lock, portMAX_DELAY);
  for (auto &slot : own_tiles)
    if (!slot) {
      slot = s;
      break;
    }
  xSemaphoreGive(own_lock);
  own_open.fetch_add(1, std::memory_order_relaxed);
}
static void own_remove(Stream *s) {
  if (!own_lock) return;
  xSemaphoreTake(own_lock, portMAX_DELAY);
  for (auto &slot : own_tiles)
    if (slot == s) {
      slot = nullptr;
      own_open.fetch_sub(1, std::memory_order_relaxed);
    }
  xSemaphoreGive(own_lock);
}

void own_frame(const uint8_t *data, int width, int height, bool yuv420) {
  if (!data || width <= 0 || height <= 0 || !own_wanted() || !own_lock) return;
  if (xSemaphoreTake(own_lock, 0) != pdTRUE) return;
  const int64_t now = esp_timer_get_time();
  for (Stream *s : own_tiles) {
    if (!s || s->stopping || s->own_full.load(std::memory_order_acquire) || now < s->own_next || !s->canvas) continue;
    const int cw = s->area.w, ch = s->area.h;
    picture_engine::Cut into = picture_engine::cut(width, height, cw, ch, s->look.contain);
    if (!into.ok) continue;
    if (yuv420) {  // the PPA reads YUV420 in pairs of pixels and rows
      into.in_x &= ~1;
      into.in_y &= ~1;
      into.in_w &= ~1;
      into.in_h &= ~1;
    }
    if (!glass::try_hold()) continue;  // the glass is busy: this frame goes by, the next one comes
    if (!into.covers(cw, ch)) memset(s->canvas, 0, static_cast<size_t>(cw) * ch * 2);
    picture_engine::Block block;
    block.in = data, block.in_w = width, block.in_rows = height, block.bx = into.in_x, block.by = into.in_y;
    block.bw = into.in_w, block.bh = into.in_h, block.out = s->canvas, block.out_size = s->canvas_size;
    block.out_w = cw, block.out_h = ch, block.x = into.out_x, block.y = into.out_y, block.scale = into.scale;
    block.yuv420 = yuv420;
    const int64_t from = esp_timer_get_time();
    const int err = picture_engine::blit(s->ppa, block);
    glass::release();
    s->into_us += static_cast<uint32_t>(esp_timer_get_time() - from);
    if (err != 0) {
      s->skipped++;
      continue;
    }
    // Its next frame after its pace: its share of the budget, a busy screen's tile half or a quarter of that.
    s->own_next = now + (tile_gap_us() << pressure::level_of(pressure::LIVE_TILES));
    s->own_full.store(true, std::memory_order_release);
    xTaskNotifyGive(s->task.handle);
  }
  xSemaphoreGive(own_lock);
}

// The tile's own task: its card laid over the frame the camera's task copied in, and laid onto the glass. The frames
// come upright, so this is the one live tile whose pictures the PPA still turns onto a turned glass, once a picture
// (docs/PLATFORM_PLAN.md 4.12).
static bool take_frames(Stream &s) {
  s.connected_ms = s.answered_ms = s.first_bytes_ms = esphome::millis() - s.started_at;
  const glass::Panel panel = glass::panel();
  const size_t glass_size = static_cast<size_t>(panel.w) * panel.h * 2;
  const int cw = s.area.w, ch = s.area.h;
  if (!overlay_for(s, 0)) {
    ESP_LOGW(TAG, "no memory for the overlay of a card of %dx%d", cw, ch);
    s.failed = true;
    return true;
  }
  s.onto_turn = s.turn;
  while (!s.stopping) {
    if (!ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(WAIT_MS)) || !s.own_full.load(std::memory_order_acquire)) continue;
    const int64_t t0 = esp_timer_get_time();
    lay_overlay(s.canvas, cw, overlay_now(s));
    const int64_t t1 = esp_timer_get_time();
    s.compose_us += static_cast<uint32_t>(t1 - t0);
    const Rect target = on_panel(s.area, s.turn, panel.w, panel.h);
    hold_timed(s);
    const int64_t t2 = esp_timer_get_time();
    esp_err_t err = ESP_OK;
    if (!s.stopping) {
      glass::place(s.room, s.area);  // from now on LVGL draws nothing here
      err = copy(s, s.canvas, cw, ch, 0, 0, cw, ch, glass::frame_buffer(), glass_size, panel.w, panel.h, target.x,
                 target.y, picture_engine::AS_IS, s.turn);
    }
    give_glass();
    s.onto_us += static_cast<uint32_t>(esp_timer_get_time() - t2);
    s.copy_us += static_cast<uint32_t>(esp_timer_get_time() - t0);
    s.own_full.store(false, std::memory_order_release);
    if (err != ESP_OK) {
      ESP_LOGW(TAG, "copy to the glass failed: %s", esp_err_to_name(err));
      s.failed = true;
      break;
    }
    s.warming = false;
    if (!s.live) {
      s.live_ms = esphome::millis() - s.started_at;
      s.live = true;
    }
    s.shown++;
  }
  return true;
}

// The app's stream: plain HTTP/1.0, then parts, pictures and (a full view's) sound as they come (Reader). The sound is
// the clock: a picture more than a frame later on its way than the quickest, with more bytes already waiting, is passed
// for the newer one behind it, and the sound that came with it plays on.
static bool read_stream(Stream &s) {
  const auto address = picture_fetch::split(s.url);
  const int fd = address.ok ? picture_fetch::connect_to(address, WAIT_MS) : -1;
  if (fd < 0) {
    ESP_LOGW(TAG, "no connection to %s:%u", address.host.c_str(), address.port);
    s.failed = true;
    return true;
  }
  s.connected_ms = esphome::millis() - s.started_at;
  // HTTP/1.0: the app answers without chunks, and ends the stream by closing it.
  if (!picture_fetch::send_all(fd, "GET " + address.path + " HTTP/1.0\r\nHost: " + address.host + "\r\n\r\n")) {
    ::close(fd);
    s.failed = true;
    return true;
  }
  // PSRAM first (roomy.h): recv copies into it and no DMA reads it, and internal RAM is what the Wi-Fi link runs short of.
  auto *chunk = static_cast<uint8_t *>(roomy::allocate(CHUNK));
  if (!chunk) {
    ::close(fd);
    s.failed = true;
    return true;
  }
  // A tile with a loader reads in short waits, so its loader turns between the stills.
  if (s.under) {
    timeval step{0, static_cast<suseconds_t>(LOADER_STEP_MS * 1000)};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &step, sizeof(step));
  }
  const picture_engine::Limits most = picture_engine::limits();
  Reader reader(s.look.tile ? most.tile_picture_bytes : most.picture_bytes);
  uint32_t heard = esphome::millis();
  while (!s.stopping) {
    const int64_t asked = esp_timer_get_time();
    const int n = recv(fd, chunk, CHUNK, 0);
    const int error = errno;
    s.net_us += static_cast<uint32_t>(esp_timer_get_time() - asked);
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
        [&s, &reader, fd](size_t length, bool audio) {
          if (!audio) {
            // A frame behind, with a newer picture on its way: passed.
            if (reader.has_made() && s.picture_wait.add(reader.made()) > STALE_MS && !reader.still()) {
              uint8_t next = 0;
              if (recv(fd, &next, 1, MSG_PEEK | MSG_DONTWAIT) > 0) {
                s.passed++;
                return;
              }
            }
            // A full view on an engine that decodes so many a second at most: one that comes sooner is passed.
            const uint8_t most = picture_engine::limits().view_pps;
            if (!s.look.tile && most && !reader.still()) {
              const int64_t now = esp_timer_get_time();
              if (s.view_at && now - s.view_at < 1000000 / most) {
                s.passed++;
                return;
              }
              s.view_at = now;
            }
            show(s, s.input, length, reader.still(), reader.turn());
            return;
          }
          // Sound: into the buffer the main loop plays from; none of it while muted. Whole samples only, so the buffer,
          // every piece read from it and every write to the speaker stay on a sample's first byte: a speaker one byte
          // off plays seconds of full-scale noise (a ring on a reTerminal D1001, 2026-10-25), until another odd write
          // puts it right by chance. So a part goes in whole or not at all, never cut to the room left.
          s.heard = true;
          if (reader.has_made()) s.sound_wait.add(reader.made());
          if (length & 1) s.odd_parts.fetch_add(1, std::memory_order_relaxed);
          if (s.muted || s.yielded) return;
          const size_t whole = length & ~static_cast<size_t>(1);
          // Only this task sends, so the room it saw is there when it sends (the main loop only takes out or empties).
          if (xStreamBufferSpacesAvailable(s.sound) >= whole)
            xStreamBufferSend(s.sound, s.sound_part, whole, 0);
          else
            s.full_parts.fetch_add(1, std::memory_order_relaxed);
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
  return true;
}

static const Source STREAM{"the app's stream", read_stream, nullptr};
static const Source ASK_EACH{"a picture at a time from the app", ask_each, &STREAM};
static const Source OWN_CAMERA{"the screen's own camera", take_frames, nullptr};

static void task_main(void *arg) {
  auto *s = static_cast<Stream *>(arg);
  // A source that cannot serve the stream hands it on (a tile on an app before asking: the app's stream).
  for (const Source *source = s->source; source && !source->run(*s); source = source->otherwise)
    s->source = source->otherwise;
  const bool in_psram = psram_task::in_psram(s->task);  // read before `done`: the main loop frees the stream after it
  s->stack_left.store(uxTaskGetStackHighWaterMark(nullptr), std::memory_order_relaxed);
  s->done.store(true, std::memory_order_release);
  psram_task::finish(in_psram);
}

bool full_view() { return available() && picture_engine::limits().picture_bytes > 0; }

// The live tiles on the glass now, for the governor's heard rule (pressure::live_tiles): the tile streams, not a view.
static void count_tiles() {
  uint8_t n = 0;
  for (auto *s : streams)
    if (s && !s->stopping && s->look.tile) ++n;
  pressure::live_tiles.store(n, std::memory_order_relaxed);
}

static_assert(picture_engine::limits().streams <= MAX_STREAMS, "the engine's streams have their slots");
// What a stream's connection takes of the chip's internal RAM, its Wi-Fi and lwIP buffers (about 11 KB on a Guition
// 4848S040, 2026-10-28), and what stays free whatever streams: docs/ARCHITECTURE.md, "Internal RAM never below 32 KB at
// rest". A screen whose pages already took it closer keeps its stills.
constexpr size_t STREAM_INTERNAL_BYTES = 11 * 1024;
constexpr size_t INTERNAL_FLOOR_BYTES = 32 * 1024;

static int held() {
  int n = 0;
  for (auto *s : streams)
    if (s) ++n;
  return n;
}
bool room_for_another() { return held() < picture_engine::limits().streams; }
bool beside() { return picture_engine::limits().streams > 1; }

Handle open(const std::string &url, const Rect &area, const Look &look, bool sound, audio_owner::Role role) {
  if (!available() || area.empty() || (!look.tile && !full_view())) return -1;
  // Every stream counts, of every kind, and one still ending too: its task holds its connection until it is gone. A
  // full view beside a live tile that had not ended took a tester's S3 down (2026-10-30).
  if (!room_for_another()) {
    ESP_LOGW(TAG, "no room for another stream: %d at once on this screen", picture_engine::limits().streams);
    return -1;
  }
  if (!is_own(url)) {
    const size_t internal = heap_caps_get_free_size(MALLOC_CAP_INTERNAL);
    if (internal < STREAM_INTERNAL_BYTES + INTERNAL_FLOOR_BYTES) {
      ESP_LOGW(TAG, "internal RAM %u KB: too little for a stream's connection (%u KB with %u KB left), the stills stay",
               (unsigned) (internal / 1024), (unsigned) (STREAM_INTERNAL_BYTES / 1024),
               (unsigned) (INTERNAL_FLOOR_BYTES / 1024));
      return -1;
    }
  }
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
  s->source = is_own(url) ? &OWN_CAMERA : look.tile ? &ASK_EACH : &STREAM;
  const bool own = s->source == &OWN_CAMERA;
  if (own) {
    // The card's canvas the camera's frames are copied into: no input, no decoded picture.
    s->canvas_size = (static_cast<size_t>(area.w) * area.h * 2 + 127) & ~static_cast<size_t>(127);
    s->canvas = static_cast<uint16_t *>(heap_caps_aligned_calloc(128, 1, s->canvas_size, MALLOC_CAP_SPIRAM));
    if (!s->canvas) s->canvas_size = 0;
  } else {
    s->input = picture_engine::input(look.tile ? picture_engine::limits().tile_picture_bytes
                                               : picture_engine::limits().picture_bytes,
                                     &s->input_size);
  }
  s->ppa = picture_engine::client();
  bool ok = (own ? s->canvas != nullptr : s->input != nullptr) && s->ppa;
  if (ok && sound && has_speaker()) {
    // The camera's sound between the task and the main loop: its storage in PSRAM (only the task and the speaker's copy
    // read it), its control inside the chip (see Stream::sound).
    s->sound_control = static_cast<StaticStreamBuffer_t *>(
        heap_caps_malloc(sizeof(StaticStreamBuffer_t), MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
    // A static stream buffer holds a byte less than its storage (FreeRTOS keeps one free; xStreamBufferCreate adds it
    // itself): one more, so it holds SOUND_BUFFER, an even count of bytes.
    s->sound_storage = static_cast<uint8_t *>(roomy::allocate(SOUND_BUFFER + 1));
    if (s->sound_control && s->sound_storage)
      s->sound = xStreamBufferCreateStatic(SOUND_BUFFER + 1, 1, s->sound_storage, s->sound_control);
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
  // The squeezed mark the same way; without the memory for it the tile simply goes without.
  s->look.badge = nullptr;
  if (ok && look.tile && look.badge && look.badge_w > 0 && look.badge_h > 0) {
    s->badge = static_cast<uint32_t *>(
        heap_caps_malloc(static_cast<size_t>(look.badge_w) * look.badge_h * 4, MALLOC_CAP_SPIRAM));
    if (s->badge) {
      const int stride = look.badge_stride ? look.badge_stride : look.badge_w;
      for (int y = 0; y < look.badge_h; ++y)
        memcpy(s->badge + static_cast<size_t>(y) * look.badge_w, look.badge + static_cast<size_t>(y) * stride,
               static_cast<size_t>(look.badge_w) * 4);
      s->look.badge = s->badge;
      s->look.badge_stride = look.badge_w;
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
  if (!psram_task::start(s->task, task_main, "live_view", STACK_BYTES, s, STREAM_PRIORITY,
                          picture_engine::limits().stream_core)) {
    streams[slot] = nullptr;
    free_stream(s);
    return -1;
  }
  count_tiles();
  if (own) own_add(s);
  if (look.tile) tiles_open.fetch_add(1, std::memory_order_relaxed);
  if (s->sound || role == audio_owner::Role::DOORBELL) {
    // The camera's sound claims the speaker (audio_owner.h) in the role its opener gave: as CAMERA_SOUND music pauses
    // for it, and a voice session or a doorbell takes it and gives it back, since the camera stays open; as DOORBELL
    // (the view a ring opened) nothing takes it, and the ring takes the microphone too, sound or not: the wake word
    // rests while someone is at the door (and the talk, section 5 of PLATFORM_PLAN.md, will speak into it). Given back in
    // tick when the stream ends: a ring whose stream ends while its view stays (stills after its third break) lets the
    // wake word listen again under the open ring, until module_doorbell holds the claim for as long as the ring is up
    // (PLATFORM_PLAN.md 3.4).
    s->sound_role = role;
    s->claimed = role == audio_owner::Role::DOORBELL ? audio_owner::Side::BOTH : audio_owner::Side::OUT;
    s->claims = true;
    audio_owner::Claim claim;
    claim.role = role;
    claim.id = static_cast<uint32_t>(slot);
    claim.lost = [slot]() {
      Stream *t = streams[slot];
      if (!t || !t->sound) return;
      t->yielded = true;
      xStreamBufferReset(t->sound);  // as mute() does: what waited is stale by the time the speaker is back
    };
    claim.regained = [slot]() {
      if (Stream *t = streams[slot]) t->yielded = false;
    };
    audio_owner::the().claim(s->claimed, claim);
  }
  glass::watch();
  ESP_LOGI(TAG, "stream %d into %dx%d at %d,%d%s from %s, turned %d, PPA bursts of %d bytes", slot, area.w, area.h,
           area.x, area.y, look.tile ? (look.contain ? " (a tile, whole picture)" : " (a tile)") : "", s->source->what,
           s->turn, picture_engine::limits().burst_bytes);
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
    if (xStreamBufferBytesAvailable(s.sound) < SOUND_LOW) return;
    speaker->set_audio_stream_info(esphome::audio::AudioStreamInfo(16, 1, SOUND_RATE));
    speaker->start();
    s.speaking = true;
    s.dry = false;
  }
  if (s.dry) {
    if (xStreamBufferBytesAvailable(s.sound) < SOUND_LOW) return;  // a new run-up first, as at the start
    s.dry = false;
  }
  // Behind the picture (a burst after a hiccup in the stream): the oldest goes, down to SOUND_LOW, the rest of the piece
  // the speaker had not taken first. Every tick, whatever the speaker takes, so a speaker that is full does not hold it
  // back until the buffer runs full. Whole samples: the buffer holds only those, both marks are even, and a piece goes
  // only from a sample's first byte.
  const size_t held = xStreamBufferBytesAvailable(s.sound);
  if (held > SOUND_HIGH && (s.piece_at & 1) == 0) {
    ++s.caught_up;
    s.caught_up_bytes += s.piece_left;
    s.piece_left = 0;
    for (size_t drop = held - SOUND_LOW; drop > 0;) {
      const size_t n = xStreamBufferReceive(s.sound, s.sound_piece, std::min(drop, SOUND_PART), 0);
      if (n == 0) break;
      s.caught_up_bytes += n;
      drop -= n;
    }
  }
  for (int rounds = 0; rounds < 8; ++rounds) {
    if (s.piece_left == 0) {
      s.piece_left = xStreamBufferReceive(s.sound, s.sound_piece, SOUND_PART, 0);
      s.piece_at = 0;
      if (s.piece_left == 0) {
        if (rounds == 0) {  // nothing waited at all: the buffer ran dry
          s.dry = true;
          ++s.ran_dry;
        }
        return;
      }
    }
    // Every piece is whole samples (the task writes only those); a write the speaker took an odd number of bytes of goes
    // on from the very next byte, the other half of that sample first, so its count is even again.
    const size_t taken = speaker->play(s.sound_piece + s.piece_at, s.piece_left, 0);
    if (taken & 1) ++s.odd_taken;
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
    if (s && !s->stopping)
      held += s->input_size +
              static_cast<size_t>(std::max(0, s->area.w)) * std::max(0, s->area.h) * 2;
  return held;
}

void close(Handle handle) {
  if (handle < 0 || handle >= MAX_STREAMS || !streams[handle]) return;
  Stream &s = *streams[handle];
  s.stopping = true;
  // A copy on its way finishes; none starts after this, and LVGL draws there again (glass::disarm, under the glass).
  glass::disarm(s.room, true);
}

bool ending() {
  for (Stream *s : streams)
    if (s && s->stopping.load(std::memory_order_relaxed)) return true;
  return false;
}

static void report(int slot, Stream &s, uint32_t now, bool last) {
  const uint32_t span = now - s.reported_at;
  if (span == 0) return;
  const uint32_t shown = s.shown, bytes = s.bytes, decode = s.decode_us, copied = s.copy_us, waited = s.wait_us;
  const uint32_t pauses = s.pauses, paused = s.paused_us, net = s.net_us, passed = s.passed;
  const uint32_t frames = shown - s.reported_shown;
  // Laying out is the picture's copies and composing; the wait for the glass inside it is said apart.
  const uint32_t wait = waited - s.reported_wait, lay = copied - s.reported_copy;
  ESP_LOGI(TAG, "%s %d: %.1f pictures/s, %u KB/s, waiting %.1f ms for the app, decoding %.1f ms, waiting %.1f ms for the "
           "glass and laying out %.1f ms a picture, %u skipped in all%s, the panel ran dry %u times since boot",
           last ? "ended" : "stream", slot, frames * 1000.0f / span, (unsigned) ((bytes - s.reported_bytes) / span),
           frames ? (net - s.reported_net) / 1000.0f / frames : 0.0f,
           frames ? (decode - s.reported_decode) / 1000.0f / frames : 0.0f, frames ? wait / 1000.0f / frames : 0.0f,
           frames ? (lay > wait ? lay - wait : 0) / 1000.0f / frames : 0.0f, (unsigned) s.skipped,
           pauses != s.reported_pauses ? ", paused for a busy screen" : "", (unsigned) glass::misses());
  const uint32_t into = s.into_us, composed = s.compose_us, onto = s.onto_us;
  if (frames && s.look.tile)
    ESP_LOGI(TAG, "%s %d: of laying out, %.1f ms a picture into its card, %.1f ms composing and %.1f ms onto the glass, "
             "turned %d on the way", last ? "ended" : "stream", slot, (into - s.reported_into) / 1000.0f / frames,
             (composed - s.reported_compose) / 1000.0f / frames, (onto - s.reported_onto) / 1000.0f / frames,
             s.onto_turn.load());
  s.reported_into = into;
  s.reported_compose = composed;
  s.reported_onto = onto;
  Wait &pw = s.picture_wait, &sw = s.sound_wait;
  const uint32_t pictures = pw.count, picture_total = pw.total_ms, sounds = sw.count, sound_total = sw.total_ms;
  if (pictures != pw.reported_count)
    ESP_LOGI(TAG, "%s %d: its pictures waited %.0f ms on their way (at most %u) over the quickest; %u older ones passed "
             "for a newer", last ? "ended" : "stream", slot,
             static_cast<float>(picture_total - pw.reported_total) / static_cast<float>(pictures - pw.reported_count),
             (unsigned) pw.most_ms.exchange(0), (unsigned) (passed - s.reported_passed));
  if (sounds != sw.reported_count)
    ESP_LOGI(TAG, "%s %d: its sound waited %.0f ms on its way (at most %u) over the quickest, %u pieces; ran dry %u times, "
             "caught up %u times since the start", last ? "ended" : "stream",
             slot, static_cast<float>(sound_total - sw.reported_total) / static_cast<float>(sounds - sw.reported_count),
             (unsigned) sw.most_ms.exchange(0), (unsigned) (sounds - sw.reported_count), (unsigned) s.ran_dry,
             (unsigned) s.caught_up);
  s.reported_passed = passed;
  pw.reported_count = pictures;
  pw.reported_total = picture_total;
  sw.reported_count = sounds;
  sw.reported_total = sound_total;
  if (pauses != s.reported_pauses)
    ESP_LOGI(TAG, "%s %d: paused %u times for a busy screen since the last report, %.1f s in all, its pace %.0f ms",
             last ? "ended" : "stream", slot, (unsigned) (pauses - s.reported_pauses),
             (paused - s.reported_paused) / 1e6f, s.pace_us / 1000.0f);
  s.reported_wait = waited;
  s.reported_pauses = pauses;
  s.reported_paused = paused;
  s.reported_net = net;
  s.reported_at = now;
  s.reported_shown = shown;
  s.reported_bytes = bytes;
  s.reported_decode = decode;
  s.reported_copy = copied;
}

// Who kept the streams waiting for the glass these 10 s (glass.h, Held), while any stream is open.
static void report_glass(uint32_t now) {
  static uint32_t reported_at = 0;
  if (now - reported_at < REPORT_MS) return;
  const uint32_t span = reported_at ? now - reported_at : REPORT_MS;
  reported_at = now;
  const glass::Held h = glass::held_since();
  const uint32_t drawing = h.refresh_us > h.flush_us ? h.refresh_us - h.flush_us : 0;
  const uint32_t copying = h.flush_us > h.turn_us ? h.flush_us - h.turn_us : 0;
  ESP_LOGI(TAG, "glass: in %u ms LVGL refreshed %u times and flushed %u, holding the glass %.1f ms in all (at most %.1f): "
           "drawing %.1f ms, turning on the PPA %.1f ms (at most %.1f), copying to the panel %.1f ms (a flush at most "
           "%.1f); the streams waited %u times, %.1f ms behind LVGL (at most %.1f), %.1f ms behind another stream "
           "(at most %.1f) and %.1f ms behind another writer (at most %.1f)",
           (unsigned) span, (unsigned) h.refreshes, (unsigned) h.flushes, h.refresh_us / 1000.0f,
           h.refresh_most_us / 1000.0f, drawing / 1000.0f, h.turn_us / 1000.0f, h.turn_most_us / 1000.0f,
           copying / 1000.0f, h.flush_most_us / 1000.0f, (unsigned) h.waits, h.behind_lvgl_us / 1000.0f,
           h.behind_lvgl_most_us / 1000.0f, h.behind_stream_us / 1000.0f, h.behind_stream_most_us / 1000.0f,
           h.behind_other_us / 1000.0f, h.behind_other_most_us / 1000.0f);
}

void tick(const std::function<void(Handle, Event)> &tell) {
  const uint32_t now = esphome::millis();
  const int turn = glass::turn();
  glass::tick();
  bool any = false;
  for (int slot = 0; slot < MAX_STREAMS; ++slot) any = any || streams[slot] != nullptr;
  if (any) report_glass(now);
  for (int slot = 0; slot < MAX_STREAMS; ++slot) {
    Stream *s = streams[slot];
    if (!s) continue;
    if (s->done.load(std::memory_order_acquire)) {
      const bool in_psram = psram_task::in_psram(s->task);
      if (s->source == &OWN_CAMERA) own_remove(s);  // the camera's task copies into it no more
      if (s->look.tile) tiles_open.fetch_sub(1, std::memory_order_relaxed);
      psram_task::reap(s->task);  // its task deleted (a stack in PSRAM) before anything of the stream is freed
      speak(*s, false);
      report(slot, *s, now, true);
      ESP_LOGI(TAG, "ended %d: its task's stack was in %s, %u of %u bytes of it never used", slot,
               in_psram ? "PSRAM" : "internal RAM", (unsigned) s->stack_left.load(std::memory_order_relaxed),
               (unsigned) STACK_BYTES);
      if (s->sound)
        ESP_LOGI(TAG, "ended %d: its sound caught up with the picture %u times (%u bytes of the oldest left out), had %u "
                 "parts left out for a full buffer, %u parts of an odd length and %u odd writes to the speaker", slot,
                 (unsigned) s->caught_up, (unsigned) s->caught_up_bytes,
                 (unsigned) s->full_parts.load(std::memory_order_relaxed),
                 (unsigned) s->odd_parts.load(std::memory_order_relaxed), (unsigned) s->odd_taken);
      const bool turned = s->turn != turn, ended = s->stopping && !s->failed;
      glass::disarm(s->room, false);  // its task has ended: nothing of it copies, and LVGL draws the room again
      streams[slot] = nullptr;
      count_tiles();
      // A full view's stream gone for good: LVGL draws the whole glass once more, now that its task decodes and copies
      // nothing. Now and then the view's top bar, the back key and the name, stayed over the page after the camera
      // closed while the picture's room below it was drawn again, until something else drew there (2026-10-15, a P4
      // board). The redraw at closing comes while the task may still be busy with its last picture, and its first strip
      // is that bar; this one comes after. The whole glass, as the view covered all of it.
      if (!s->look.tile) glass::redraw_all();
      if (s->claims) audio_owner::the().release(s->claimed, s->sound_role, static_cast<uint32_t>(slot));
      free_stream(s);
      tell(slot, turned ? Event::TURNED : ended ? Event::ENDED : Event::FAILED);
      continue;
    }
    // Its picture lies elsewhere now, or at another size: LVGL draws where it lay again (but where it lies now).
    glass::follow(s->room);
    // The glass turned (a setting): this stream's place is gone; its owner asks again for its new shape.
    if (s->turn != turn && !s->stopping) close(slot);
    speak(*s, !s->stopping && !s->muted && !s->yielded);
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
