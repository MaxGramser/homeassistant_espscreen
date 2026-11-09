// The panel's DMA repeats the frame buffer by itself (glass_dsi_refresh.h says what this file knows).
//
// ESP-IDF sends each frame as one DW-GDMA transfer and starts the next one from that transfer's end-of-frame interrupt
// (esp_lcd_panel_dpi.c, mipi_dsi_dma_trans_done_cb). The vertical blanking is all the time that interrupt has: 0.59 ms
// on a reTerminal D1001 at 70 MHz. An interrupt that comes later misses the frame, the panel gets nothing for a whole
// refresh and shows its colour for no data, blue, and the bridge raises no underrun flag: the DMA was never asked for
// anything. Back-to-back cache write-backs on the two cores (esp_cache_msync, up to 0.6 ms with the interrupts off per
// chunk, on a spinlock the other core waits for with its own off), a slow interrupt beside it or any long critical
// section are enough. A bare firmware on a D1001 proved it with a camera on the glass (2026-11-08): every frame missed
// (33 ms between restarts instead of 17) was a blue flash and nothing else was, 0 flags; none on the other core.
//
// So the channel is put in the DMA's auto-reload mode: it repeats its one block, the whole frame buffer, in hardware,
// and no interrupt stands between two frames (10 ms with the interrupts off: not one flash). ESP-IDF's DMA driver has no
// call that changes a running channel's block type, so the switch itself is made with its low-level functions. The
// channel is the one ESP-IDF creates for the DSI bridge (the wrap of dw_gdma_new_channel below).
#include "glass_dsi_refresh.h"

#include "esphome/core/defines.h"  // GLASS_DSI: the header above has no ESPHome in it
#if defined(GLASS_DSI) && defined(SCREEN_PICTURES)
#include <esp_private/dw_gdma.h>
#include <cstdint>

#if __has_include(<hal/dw_gdma_ll.h>) && !defined(GLASS_NO_REFRESH_HOLD)
#include <esp_attr.h>
#include <esp_rom_sys.h>
#include <esp_system.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <hal/dw_gdma_ll.h>
#include <soc/reg_base.h>
#include "esphome/core/log.h"
#define GLASS_HOLDS_REFRESH 1
#endif

static dw_gdma_channel_handle_t panel_channel = nullptr;

// The channel that feeds the DSI bridge, as ESP-IDF creates it (-Wl,--wrap=dw_gdma_new_channel, engine_build.py).
extern "C" esp_err_t __real_dw_gdma_new_channel(const dw_gdma_channel_alloc_config_t *config, dw_gdma_channel_handle_t *ret);
extern "C" esp_err_t __wrap_dw_gdma_new_channel(const dw_gdma_channel_alloc_config_t *config, dw_gdma_channel_handle_t *ret) {
  const esp_err_t err = __real_dw_gdma_new_channel(config, ret);
  if (err == ESP_OK && config->dst.role == DW_GDMA_ROLE_PERIPH_DSI) panel_channel = *ret;
  return err;
}

namespace glass {

#ifdef GLASS_HOLDS_REFRESH
namespace {

constexpr const char *TAG = "glass";
constexpr uint32_t HOLD_FAILED = 0x484F4C44;
constexpr int64_t FRAME_WAIT_US = 100000;   // more than any panel's frame
constexpr int64_t BLANKING_WAIT_US = 50000;
constexpr uint32_t FRAME_POLL_US = 5000;    // shorter than any panel's frame

RTC_NOINIT_ATTR uint32_t hold_failed;  // kept over the restart below

volatile dmac_channel_reg_t *channel_regs = nullptr;
FrameSeen on_frame = nullptr;
uint32_t last_address = 0;

// The address goes back to the start of the buffer once a frame.
void poll_frames(void *) {
  const uint32_t address = channel_regs->sar0.sar0;
  if (address < last_address) on_frame();
  last_address = address;
}

bool enabled(int ch) { return DW_GDMA.chen0.val & (1u << ch); }

template<typename Done> bool wait_for(Done done) {
  const int64_t from = esp_timer_get_time();
  while (!done())
    if (esp_timer_get_time() - from > FRAME_WAIT_US) return false;
  return true;
}

// In the middle of a frame the end-of-frame interrupt is taken away, so the channel stops at the end of this frame, and
// is started again in auto-reload in that frame's blanking. True when it was restarted.
bool switch_to_reload(int ch, uint32_t base, size_t bytes) {
  volatile dmac_channel_reg_t &c = DW_GDMA.ch[ch];
  const auto sent = [&]() { return (uint32_t) c.sar0.sar0 - base; };
  if (!wait_for([&]() { const uint32_t s = sent(); return s >= bytes / 5 && s <= bytes * 2 / 3; })) {
    ESP_LOGW(TAG, "the panel's DMA does not move through its frame buffer as expected: it keeps the driver's restart");
    return false;
  }
  const uint32_t signals = c.int_sig_ena0.val;
  dw_gdma_ll_channel_enable_intr_propagation(&DW_GDMA, ch, UINT32_MAX, false);
  // The interrupts go off only for the last tenth of the frame and the blanking.
  const bool near_end = wait_for([&]() { return sent() >= bytes * 9 / 10 || !enabled(ch); });
  static portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
  bool stopped = false;
  portENTER_CRITICAL(&lock);
  if (near_end) {
    const int64_t from = esp_timer_get_time();
    while (enabled(ch) && esp_timer_get_time() - from < BLANKING_WAIT_US) {}
    stopped = !enabled(ch);
  }
  if (stopped) {
    dw_gdma_ll_channel_clear_intr(&DW_GDMA, ch, UINT32_MAX);
    dw_gdma_ll_channel_set_src_multi_block_type(&DW_GDMA, ch, DW_GDMA_BLOCK_TRANSFER_RELOAD);
    dw_gdma_ll_channel_set_dst_multi_block_type(&DW_GDMA, ch, DW_GDMA_BLOCK_TRANSFER_RELOAD);
    dw_gdma_ll_channel_set_src_addr(&DW_GDMA, ch, base);
    dw_gdma_ll_channel_set_dst_addr(&DW_GDMA, ch, MIPI_DSI_BRG_MEM_BASE);
    dw_gdma_ll_channel_set_block_markers(&DW_GDMA, ch, false, false, false);
    dw_gdma_ll_channel_enable(&DW_GDMA, ch, true);
  } else if (enabled(ch)) {
    c.int_sig_ena0.val = signals;  // it never stopped: the driver goes on as before
  }
  portEXIT_CRITICAL(&lock);
  return stopped;
}

bool keeps_running(int ch) {
  esp_rom_delay_us(50000);
  const uint32_t address = DW_GDMA.ch[ch].sar0.sar0;
  esp_rom_delay_us(3000);
  return enabled(ch) && address != DW_GDMA.ch[ch].sar0.sar0;
}

}  // namespace

bool hold_refresh(void *frame_buffer, size_t bytes, FrameSeen frame_seen) {
  if (hold_failed == HOLD_FAILED) {
    ESP_LOGW(TAG, "the panel's DMA keeps the driver's restart: the last try to change it failed");
    return false;
  }
  int ch = -1;
  if (!panel_channel || dw_gdma_channel_get_id(panel_channel, &ch) != ESP_OK) return false;
  volatile dmac_channel_reg_t &c = DW_GDMA.ch[ch];
  if (c.cfg0.src_multblk_type != DW_GDMA_BLOCK_TRANSFER_LIST || c.cfg0.dst_multblk_type != DW_GDMA_BLOCK_TRANSFER_LIST ||
      ((size_t) c.block_ts0.block_ts + 1) * 8 != bytes) {
    ESP_LOGW(TAG, "the panel's DMA is not set up as expected: it keeps the driver's restart");
    return false;
  }
  // The DMA may read the frame buffer through another view of the same memory (only the top of its address differs, on
  // a revision 3 chip): what counts is how far into the frame it is, and the address it reads through is the one to reload.
  const uint32_t reading = c.sar0.sar0;
  const uint32_t base = reading - ((reading - (uint32_t) frame_buffer) & 0x0FFFFFFF);
  if (!switch_to_reload(ch, base, bytes)) return false;
  if (!keeps_running(ch)) {
    // A panel without a DMA stays blue until a restart; the next start leaves the driver's way alone.
    ESP_LOGE(TAG, "the panel's DMA did not keep running on its own: restarting without it");
    hold_failed = HOLD_FAILED;
    esp_restart();
  }
  channel_regs = &c;
  on_frame = frame_seen;
  last_address = c.sar0.sar0;
  esp_timer_create_args_t args{};
  args.callback = poll_frames;
  args.name = "glass_frames";
  esp_timer_handle_t timer = nullptr;
  if (esp_timer_create(&args, &timer) == ESP_OK) esp_timer_start_periodic(timer, FRAME_POLL_US);
  ESP_LOGI(TAG, "the panel's DMA restarts itself (channel %d)", ch);
  return true;
}
#else
bool hold_refresh(void *, size_t, FrameSeen) { return false; }
#endif

}  // namespace glass
#endif
