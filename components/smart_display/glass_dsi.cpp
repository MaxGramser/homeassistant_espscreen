// The glass of an ESP32-P4's MIPI-DSI panel (glass.h says what and why; glass_core.cpp has what every panel kind shares):
// the panel ESPHome's display made, picked up as ESP-IDF makes it, its frame buffer, the panel's underrun counter and the
// PPA bursts of every client.
#include "glass.h"
#include "picture_engine.h"
#if defined(GLASS_DSI) && defined(SCREEN_PICTURES)
#include <driver/ppa.h>
#include "lvgl.h"  // LV_COLOR_16_SWAP, LVGL's byte order for this display
#include <esp_lcd_mipi_dsi.h>
#include <esp_attr.h>
#include <atomic>
#include <cstdio>
#include "esphome/core/hal.h"  // millis
#include "esphome/core/log.h"
// The DSI bridge's own registers, for its underrun flag (misses below); ESP-IDF keeps the chip's registers here.
#if __has_include(<soc/mipi_dsi_bridge_struct.h>)
#include <soc/mipi_dsi_bridge_struct.h>
#include <soc/mipi_dsi_host_struct.h>
#define GLASS_COUNTS_MISSES 1
#endif
// The DMA that feeds the panel, for its own restart (refresh_hold below).
#if defined(GLASS_COUNTS_MISSES) && __has_include(<hal/dw_gdma_ll.h>) && !defined(GLASS_NO_REFRESH_HOLD)
#include <hal/dw_gdma_ll.h>
#include <soc/reg_base.h>
#include <esp_attr.h>
#include <esp_rom_sys.h>
#include <esp_system.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#define GLASS_HOLDS_REFRESH 1
#endif

namespace glass {

// ---- The panel ESPHome's display made (the wrap of esp_lcd_new_panel_dpi at the end of this file) ----
static esp_lcd_panel_handle_t panel_handle = nullptr;
static Panel panel_facts;
static void *buffer = nullptr;

static void panel_made(esp_lcd_panel_handle_t made, const esp_lcd_dpi_panel_config_t *config) {
  panel_handle = made;
  panel_facts.swapped = LV_COLOR_16_SWAP;
  panel_facts.w = config->video_timing.h_size;
  panel_facts.h = config->video_timing.v_size;
  // ESPHome names the frame buffer's format in either field, by ESP-IDF version.
  panel_facts.rgb565 = config->in_color_format == LCD_COLOR_FMT_RGB565 ||
                       (config->in_color_format == 0 && config->pixel_format == LCD_COLOR_PIXEL_FORMAT_RGB565);
}
Panel panel() { return panel_facts; }
bool direct() { return panel_handle != nullptr && panel_facts.rgb565 && bound(); }
void *frame_buffer() {
  if (!buffer && panel_handle && esp_lcd_dpi_panel_get_frame_buffer(panel_handle, 1, &buffer) != ESP_OK) buffer = nullptr;
  return buffer;
}

// ---- The panel's share of the memory bus ----
// ESP-IDF only logs an underrun from its interrupt, on the UART and for every frame. Here its interrupt is turned off,
// so the bridge's underrun flag stays up, and the panel's own callback at the end of each frame reads and clears it:
// each frame of blue counted where it happened (the panel watch, glass.h), so a tester's log says whether a change
// helped and nobody has to watch the glass for it.
//
// The flag has a mask the count must take off. The bridge raises its underrun flag only when the panel runs dry past a
// line of the frame (dpi_misc_config.fifo_underrun_discard_vcnt: "the underrun interrupt mask, when underrun occurs
// and line cnt is less than this field"), and ESP-IDF sets that line to the panel's width (esp_lcd_panel_dpi.c,
// mipi_dsi_brg_ll_set_underrun_discard_count(h_size)): 800 of the 1280 lines of a Guition 10.1 or a reTerminal D1001.
// An underrun in the first 800 lines, which blues most of the glass (the bridge discards the rest of the frame and the
// panel shows its colour for no data), raised no flag; one in the last 480 lines, which blues the bottom, did. So
// until 2026-10-29 the count saw the blue over the lower tiles (39 to 53 a minute on a D1001 with the encoder's strip
// in PSRAM, docs/PLATFORM_PLAN.md 4.4a) and never the whole-glass flash a slider drag or a log line brought on the
// same board, and read "the D1001 counts none" (espressif/esp-idf #19188 and jtenniswood/espcontrol #2118 saw the
// same flash with the flag silent). With the mask at 0 every underrun counts; what the panel shows does not change.
//
// The frame callback is ESP-IDF's on_vsync, which ESPHome's display leaves free (it takes on_color_trans_done only):
// the bridge's VSYNC interrupt on rev3 silicon, the end of the panel's DMA of each frame before it (esp_lcd_panel_dpi.c,
// "a fake vsync end"). Added to whatever the display registers (the wrap at the end of this file); a display that
// registers its own on_vsync keeps it, called after this one.
#ifdef GLASS_COUNTS_MISSES
// A flash as it began, written by the callback, read on the main loop.
struct Began {
  Holder holder;
  bool flushing;
};
static constexpr uint32_t BEGAN_KEPT = 8;
static Began began[BEGAN_KEPT];
static std::atomic<uint32_t> frames{0}, dry_frames{0}, flashes{0}, host_errors{0}, host_bits{0};
static bool dry_before = false;              // the frame before ran dry too: the same flash
static std::atomic<bool> watching{false};    // the mask off and the flag clear (once, on the main loop)
static esp_lcd_dpi_panel_vsync_cb_t display_vsync = nullptr;  // the display's own, when it registers one

static std::atomic<bool> refresh_held{false};  // the DMA restarts itself (refresh_hold): the frames are read elsewhere

// One frame of the panel: what the bridge and the DSI host say about it.
static IRAM_ATTR void frame_seen() {
  frames.fetch_add(1, std::memory_order_relaxed);
  const bool dry = MIPI_DSI_BRIDGE.int_raw.underrun_int_raw;
  if (dry) {
    MIPI_DSI_BRIDGE.int_clr.underrun_int_clr = 1;
    dry_frames.fetch_add(1, std::memory_order_relaxed);
    if (!dry_before) {
      const uint32_t n = flashes.load(std::memory_order_relaxed);
      began[n % BEGAN_KEPT] = {holder_now(), flushing_now()};
      flashes.store(n + 1, std::memory_order_release);
    }
  }
  dry_before = dry;
  // The DSI host's own errors (the link to the panel: timeouts, ECC and CRC, its payload FIFO), cleared by the read.
  const uint32_t st0 = MIPI_DSI_HOST.int_st0.val, st1 = MIPI_DSI_HOST.int_st1.val;
  if (st0 | st1) {
    host_errors.fetch_add(1, std::memory_order_relaxed);
    host_bits.fetch_or(st1 | (st0 ? 1u << 31 : 0u), std::memory_order_relaxed);
  }
}

static IRAM_ATTR bool frame_done(esp_lcd_panel_handle_t panel, esp_lcd_dpi_panel_event_data_t *data, void *ctx) {
  if (watching.load(std::memory_order_relaxed) && !refresh_held.load(std::memory_order_relaxed)) frame_seen();
  return display_vsync ? display_vsync(panel, data, ctx) : false;
}

// ---- The panel's DMA restarts itself ----
// ESP-IDF sends each frame as one DW-GDMA transfer and starts the next one from that transfer's end-of-frame interrupt
// (esp_lcd_panel_dpi.c, mipi_dsi_dma_trans_done_cb). The vertical blanking is all the time that interrupt has: 0.59 ms
// on a reTerminal D1001 at 70 MHz. An interrupt that comes later misses the frame, the panel gets nothing for a whole
// refresh and shows its colour for no data, blue, and the bridge raises no underrun flag: the DMA was never asked for
// anything. Back-to-back cache write-backs on the two cores (esp_cache_msync, up to 0.6 ms with the interrupts off per
// chunk, on a spinlock the other core waits for with its own off), a slow interrupt beside it or any long critical
// section are enough. A bare firmware on a D1001 proved it with a camera on the glass (2026-11-08): every frame missed
// (33 ms between restarts instead of 17) was a blue flash and nothing else was, 0 flags; none on the other core.
// So the channel is put in the DMA's auto-reload mode: it repeats its one block, the whole frame buffer, in hardware,
// and no interrupt stands between two frames (10 ms with the interrupts off: not one flash). The switch is made once,
// at the end of a frame, in its blanking. The frame callback no longer comes on a chip whose only "vsync" was that
// interrupt, so the frames are read from the DMA's address every 5 ms (frame_seen).
#ifdef GLASS_HOLDS_REFRESH
static RTC_NOINIT_ATTR uint32_t hold_failed;  // kept over the restart below
static constexpr uint32_t HOLD_FAILED = 0x484F4C44;
static int held_channel = -1;
static uint32_t held_sar = 0;

static void refresh_poll(void *) {
  const uint32_t sar = DW_GDMA.ch[held_channel].sar0.sar0;
  if (sar < held_sar) frame_seen();
  held_sar = sar;
}

static int panel_channel() {
  for (int i = 0; i < DW_GDMA_LL_CHANNELS_PER_GROUP; i++)
    if ((DW_GDMA.chen0.val & (1u << i)) && DW_GDMA.ch[i].dar0.dar0 == MIPI_DSI_BRG_MEM_BASE) return i;
  return -1;
}

static void refresh_hold() {
  if (hold_failed == HOLD_FAILED) {
    ESP_LOGW("glass", "the panel's DMA keeps the driver's restart: the last try to change it failed");
    return;
  }
  const int ch = panel_channel();
  void *fb = frame_buffer();
  const size_t bytes = (size_t) panel_facts.w * panel_facts.h * 2;
  if (ch < 0 || !fb || !panel_facts.rgb565) return;
  volatile dmac_channel_reg_t &c = DW_GDMA.ch[ch];
  if (c.cfg0.src_multblk_type != DW_GDMA_BLOCK_TRANSFER_LIST || c.cfg0.dst_multblk_type != DW_GDMA_BLOCK_TRANSFER_LIST ||
      ((size_t) c.block_ts0.block_ts + 1) * 8 != bytes) {
    ESP_LOGW("glass", "the panel's DMA is not set up as expected: it keeps the driver's restart");
    return;
  }
  // The DMA may read the frame buffer through another view of the same memory (only the top of its address differs, on
  // a revision 3 chip): what counts is how far into the frame it is, and the address it reads through is the one to reload.
  const uint32_t reading = c.sar0.sar0;
  const uint32_t base = reading - ((reading - (uint32_t) fb) & 0x0FFFFFFF);
  const auto sent = [&]() { return (uint32_t) c.sar0.sar0 - base; };
  const auto wait = [](auto done) {
    const int64_t from = esp_timer_get_time();
    while (!done())
      if (esp_timer_get_time() - from > 100000) return false;
    return true;
  };
  // In the middle of a frame the end-of-frame interrupt is taken away, so the channel stops at the end of this frame.
  static portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
  if (!wait([&]() { const uint32_t s = sent(); return s >= bytes / 5 && s <= bytes * 2 / 3; })) {
    ESP_LOGW("glass", "the panel's DMA does not move through its frame buffer as expected: it keeps the driver's restart");
    return;
  }
  const uint32_t signals = c.int_sig_ena0.val;
  dw_gdma_ll_channel_enable_intr_propagation(&DW_GDMA, ch, UINT32_MAX, false);
  // The interrupts go off only for the last tenth of the frame and the blanking.
  const bool near_end = wait([&]() { return sent() >= bytes * 9 / 10 || !(DW_GDMA.chen0.val & (1u << ch)); });
  bool stopped = false;
  portENTER_CRITICAL(&lock);
  if (near_end) {
    const int64_t from = esp_timer_get_time();
    while ((DW_GDMA.chen0.val & (1u << ch)) && esp_timer_get_time() - from < 50000) {}
    stopped = !(DW_GDMA.chen0.val & (1u << ch));
  }
  if (stopped) {
    dw_gdma_ll_channel_clear_intr(&DW_GDMA, ch, UINT32_MAX);
    dw_gdma_ll_channel_set_src_multi_block_type(&DW_GDMA, ch, DW_GDMA_BLOCK_TRANSFER_RELOAD);
    dw_gdma_ll_channel_set_dst_multi_block_type(&DW_GDMA, ch, DW_GDMA_BLOCK_TRANSFER_RELOAD);
    dw_gdma_ll_channel_set_src_addr(&DW_GDMA, ch, base);
    dw_gdma_ll_channel_set_dst_addr(&DW_GDMA, ch, MIPI_DSI_BRG_MEM_BASE);
    dw_gdma_ll_channel_set_block_markers(&DW_GDMA, ch, false, false, false);
    dw_gdma_ll_channel_enable(&DW_GDMA, ch, true);
  } else if (DW_GDMA.chen0.val & (1u << ch)) {
    c.int_sig_ena0.val = signals;  // it never stopped: the driver goes on as before
  }
  portEXIT_CRITICAL(&lock);
  bool running = false;
  if (stopped) {
    esp_rom_delay_us(50000);
    const uint32_t a = c.sar0.sar0;
    esp_rom_delay_us(3000);
    running = (DW_GDMA.chen0.val & (1u << ch)) && a != c.sar0.sar0;
    if (!running) {
      // A panel without a DMA stays blue until a restart; the next start leaves the driver's way alone.
      ESP_LOGE("glass", "the panel's DMA did not keep running on its own: restarting without it");
      hold_failed = HOLD_FAILED;
      esp_restart();
    }
  }
  if (!running) return;
  held_channel = ch;
  held_sar = c.sar0.sar0;
  refresh_held.store(true, std::memory_order_relaxed);
  esp_timer_create_args_t args{};
  args.callback = refresh_poll;
  args.name = "glass_frames";
  esp_timer_handle_t timer = nullptr;
  if (esp_timer_create(&args, &timer) == ESP_OK) esp_timer_start_periodic(timer, 5000);
  ESP_LOGI("glass", "the panel's DMA restarts itself (channel %d)", ch);
}
#else
static void refresh_hold() {}
#endif

// What the runtime notes for the watch: the log's lines (any task) and the finger (the main loop).
static std::atomic<uint32_t> log_lines{0};
static bool finger = false;
void note_log_line() { log_lines.fetch_add(1, std::memory_order_relaxed); }
void note_finger(bool down) { finger = down; }

// The minute's flashes, noted on the main loop as they come.
struct Flash {
  uint32_t at_ms;
  Began began;
  bool finger;
  uint32_t log_lines;  // in the second or two before
};
static constexpr int MINUTE_KEPT = 6;
static Flash minute[MINUTE_KEPT];
static uint32_t minute_from = 0, minute_flashes = 0, minute_frames_from = 0, minute_dry_from = 0, minute_host_from = 0,
                minute_lines_from = 0, flashes_seen = 0, lines_mark = 0, lines_mark_at = 0;
static std::string said = "quiet";  // until the first minute is over

static const char *held_by(const Began &b) {
  switch (b.holder) {
    case LVGL: return b.flushing ? "LVGL flushing" : "LVGL drawing";
    case STREAM: return "a stream";
    case OTHER: return "another writer";
    default: return b.flushing ? "LVGL flushing" : "nobody";
  }
}

static void say_minute(uint32_t now) {
  const uint32_t f = frames.load(std::memory_order_relaxed), d = dry_frames.load(std::memory_order_relaxed),
                 h = host_errors.load(std::memory_order_relaxed), l = log_lines.load(std::memory_order_relaxed);
  if (minute_flashes == 0 && d == minute_dry_from && h == minute_host_from) {
    // With the frames, so a quiet minute also says the watch saw the panel at all (about 3600 at 60 Hz).
    said = "quiet, " + std::to_string(f - minute_frames_from) + " frames";
  } else {
    char line[256];
    int n = snprintf(line, sizeof line, "%u flashes, %u of %u frames dry", (unsigned) minute_flashes,
                     (unsigned) (d - minute_dry_from), (unsigned) (f - minute_frames_from));
    for (uint32_t i = 0; i < minute_flashes && i < MINUTE_KEPT && n < (int) sizeof line - 1; ++i) {
      const Flash &x = minute[i];
      n += snprintf(line + n, sizeof line - n, "; +%.1f s %s%s, %u log", (x.at_ms - minute_from) / 1000.0f,
                    held_by(x.began), x.finger ? ", finger" : "", (unsigned) x.log_lines);
    }
    if (minute_flashes > MINUTE_KEPT && n < (int) sizeof line - 1) n += snprintf(line + n, sizeof line - n, "; ...");
    if (n < (int) sizeof line - 1)
      snprintf(line + n, sizeof line - n, "; %u log lines; DSI host errors %u (0x%08x)", (unsigned) (l - minute_lines_from),
               (unsigned) (h - minute_host_from), (unsigned) host_bits.load(std::memory_order_relaxed));
    said = line;
    ESP_LOGW("glass", "panel watch, the last minute: %s", line);
  }
  minute_from = now;
  minute_flashes = 0;
  minute_frames_from = f;
  minute_dry_from = d;
  minute_host_from = h;
  minute_lines_from = l;
}

static void watch_tick() {
  const uint32_t now = esphome::millis();
  if (!watching.load(std::memory_order_relaxed)) {
    MIPI_DSI_BRIDGE.int_ena.underrun_int_ena = 0;
    MIPI_DSI_BRIDGE.dpi_misc_config.fifo_underrun_discard_vcnt = 0;
    MIPI_DSI_BRIDGE.dpi_config_update.dpi_config_update = 1;
    MIPI_DSI_BRIDGE.int_clr.underrun_int_clr = 1;
    minute_from = lines_mark_at = now;
    watching.store(true, std::memory_order_relaxed);
    refresh_hold();
    return;
  }
  const uint32_t lines = log_lines.load(std::memory_order_relaxed);
  if (now - lines_mark_at >= 1000) {
    lines_mark = lines;
    lines_mark_at = now;
  }
  const uint32_t n = flashes.load(std::memory_order_acquire);
  for (; flashes_seen != n; ++flashes_seen) {
    if (minute_flashes < MINUTE_KEPT)
      minute[minute_flashes] = {now, began[flashes_seen % BEGAN_KEPT], finger, lines - lines_mark};
    ++minute_flashes;
  }
  if (now - minute_from >= 60000) say_minute(now);
}
#else
static void watch_tick() {}
void note_log_line() {}
void note_finger(bool) {}
static std::string said;
static std::atomic<uint32_t> dry_frames{0};
#endif
void tick() {
  if (direct()) watch_tick();
}
uint32_t misses() { return dry_frames.load(std::memory_order_relaxed); }
std::string watch_said() { return said; }

}  // namespace glass

// ESP-IDF makes the DPI panel for ESPHome's display (mipi_dsi, or the repo's mipi_dsi_v3 copy): its handle and its
// size are picked up here as they are made (-Wl,--wrap=esp_lcd_new_panel_dpi, smart_display/__init__.py on a P4).
extern "C" esp_err_t __real_esp_lcd_new_panel_dpi(esp_lcd_dsi_bus_handle_t bus, const esp_lcd_dpi_panel_config_t *config,
                                                   esp_lcd_panel_handle_t *made);
extern "C" esp_err_t __wrap_esp_lcd_new_panel_dpi(esp_lcd_dsi_bus_handle_t bus, const esp_lcd_dpi_panel_config_t *config,
                                                   esp_lcd_panel_handle_t *made) {
  const esp_err_t err = __real_esp_lcd_new_panel_dpi(bus, config, made);
  if (err == ESP_OK && made && config) glass::panel_made(*made, config);
  return err;
}
// The display registers its callbacks (ESPHome's mipi_dsi: on_color_trans_done); the panel watch's frame callback goes
// with them (-Wl,--wrap=esp_lcd_dpi_panel_register_event_callbacks, engine_build.py), the display's own on_vsync after it.
extern "C" esp_err_t __real_esp_lcd_dpi_panel_register_event_callbacks(esp_lcd_panel_handle_t panel,
                                                                      const esp_lcd_dpi_panel_event_callbacks_t *cbs,
                                                                      void *user_ctx);
extern "C" esp_err_t __wrap_esp_lcd_dpi_panel_register_event_callbacks(esp_lcd_panel_handle_t panel,
                                                                      const esp_lcd_dpi_panel_event_callbacks_t *cbs,
                                                                      void *user_ctx) {
#ifdef GLASS_COUNTS_MISSES
  if (cbs) {
    esp_lcd_dpi_panel_event_callbacks_t own = *cbs;
    if (own.on_vsync != glass::frame_done) glass::display_vsync = own.on_vsync;
    own.on_vsync = glass::frame_done;
    return __real_esp_lcd_dpi_panel_register_event_callbacks(panel, &own, user_ctx);
  }
#endif
  return __real_esp_lcd_dpi_panel_register_event_callbacks(panel, cbs, user_ctx);
}
// Every PPA client on this screen, ESPHome's for LVGL's turned flushes included, moves in the engine's burst, so
// the panel's DMA gets its turn on the bus ("The panel's share of the memory bus", glass.h). The streams' own clients
// ask for it already; a client that asks for less keeps its own.
static_assert(picture_engine::limits().burst_bytes == 64, "the burst below is the engine's");
extern "C" esp_err_t __real_ppa_register_client(const ppa_client_config_t *config, ppa_client_handle_t *ret_client);
extern "C" esp_err_t __wrap_ppa_register_client(const ppa_client_config_t *config, ppa_client_handle_t *ret_client) {
  if (!config) return __real_ppa_register_client(config, ret_client);
  ppa_client_config_t own = *config;
  // A zeroed config means ESP-IDF's default, the longest burst.
  if (own.data_burst_length == 0 || own.data_burst_length > PPA_DATA_BURST_LENGTH_64) own.data_burst_length = PPA_DATA_BURST_LENGTH_64;
  return __real_ppa_register_client(&own, ret_client);
}
#endif
