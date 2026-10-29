// The PPA guard on a P4 screen (ppa_guard.h says why): every scale-rotate-mirror call of the firmware comes through
// here, ESPHome's LVGL flush of a turned glass, a stream's copy of its picture (live_view.cpp) and a plugin's camera
// alike, through the linker's wrap of ppa_do_scale_rotate_mirror (smart_display/__init__.py adds it with the other
// wraps on a P4). A call the engine takes whole goes straight on; one it would stall on goes in the pieces the plan
// gives, one after the other, each as blocking as the call was. Every call is noted in the trace (ppa_trace.h) on its
// way in and on its way back.
#include "ppa_guard.h"
#include "ppa_trace.h"
#include "glass.h"
#include "esphome/core/defines.h"  // PICTURE_ENGINE_P4: the header above has no ESPHome in it
#ifdef PICTURE_ENGINE_P4
#include <atomic>
#include <cstdio>
#include <cstring>
#include <driver/ppa.h>
#include <hal/ppa_ll.h>
#include <esp_attr.h>
#include <esp_system.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include "esphome/core/log.h"

namespace {

constexpr const char *TAG = "ppa_guard";
constexpr uint32_t TOLD_AT_MOST = 8;  // log lines per boot about blocks that went in pieces; the rest are counted
uint32_t guarded = 0, given_up = 0;

ppa_guard::Scale as_scale(float scale) {
  // As the driver splits its float (ppa_srm.c): the whole part, and the fraction in sixteenths rounded down.
  ppa_guard::Scale s;
  s.whole = static_cast<uint32_t>(scale);
  s.frag = static_cast<uint32_t>(scale * ppa_guard::FRAG_MAX) & (ppa_guard::FRAG_MAX - 1);
  return s;
}

// The output's bits per pixel, and the width of a transaction unit for it: 32 pixels for the wide formats, else 64
// (ppa_srm.c, "Hardware bug workaround"). 0 for a format the guard does not know, which then goes as it is.
uint32_t depth_of(ppa_srm_color_mode_t cm, uint32_t &unit_w) {
  unit_w = 64;
  switch (cm) {
    case PPA_SRM_COLOR_MODE_RGB565:
      return 16;
    case PPA_SRM_COLOR_MODE_RGB888:
      unit_w = 32;
      return 24;
    case PPA_SRM_COLOR_MODE_ARGB8888:
      unit_w = 32;
      return 32;
    case PPA_SRM_COLOR_MODE_YUV420:
      return 12;
    case PPA_SRM_COLOR_MODE_YUV444:
      return 24;
    default:  // GRAY8 and whatever a later ESP-IDF adds: as it is
      return 0;
  }
}

// ---- The trace (ppa_trace.h) ----
using ppa_trace::ASKED;
using ppa_trace::BACK;
using ppa_trace::Call;
using ppa_trace::FAILED;
constexpr uint32_t TRACE_CALLS = ppa_trace::CALLS;
constexpr uint32_t TRACE_MAGIC = 0x50504154;  // "PPAT"
struct Ring {
  uint32_t magic;
  Call calls[TRACE_CALLS];
};
__NOINIT_ATTR Ring ring;  // where a reset leaves it
Ring kept;                // the last boot's, taken over at boot
bool had = false;
std::atomic<uint32_t> next_seq{1};

uint32_t note(const ppa_srm_oper_config_t *config) {
  if (ring.magic != TRACE_MAGIC) {
    memset(&ring, 0, sizeof ring);
    ring.magic = TRACE_MAGIC;
  }
  const uint32_t seq = next_seq.fetch_add(1, std::memory_order_relaxed);
  Call &call = ring.calls[seq % TRACE_CALLS];
  call.seq = seq;
  call.at_ms = static_cast<uint32_t>(esp_timer_get_time() / 1000);
  call.w = static_cast<uint16_t>(config->in.block_w);
  call.h = static_cast<uint16_t>(config->in.block_h);
  call.out_x = static_cast<uint16_t>(config->out.block_offset_x);
  call.out_y = static_cast<uint16_t>(config->out.block_offset_y);
  call.angle = static_cast<uint8_t>(config->rotation_angle);
  call.pieces = 0;
  __atomic_store_n(&call.state, ASKED, __ATOMIC_RELEASE);  // the watch reads the call whole once it says asked
  strncpy(call.task, pcTaskGetName(nullptr), sizeof call.task - 1);
  call.task[sizeof call.task - 1] = 0;
  return seq;
}

void came_back(uint32_t seq, int pieces, esp_err_t err) {
  Call &call = ring.calls[seq % TRACE_CALLS];
  if (call.seq != seq) return;  // the ring went round meanwhile
  call.pieces = static_cast<int8_t>(pieces);
  __atomic_store_n(&call.state, err == ESP_OK ? BACK : FAILED, __ATOMIC_RELEASE);
}

// The watch (ppa_trace.h): each second, in a task of its own, outside every task that may wait for the engine, a call
// still out after NEVER_MS aborts the boot with its name, and with the state of ESP-IDF's esp_timer task, where the
// watch ran before and stood still on a Tab5 (ppa_trace.h). No log and no heap on that way: the words go into a buffer
// of their own, and abort_record keeps them.
constexpr uint32_t WATCH_STACK = 3072;  // snprintf's own frames are most of it
// Above the main loop and the streams' tasks (glass::WRITER_PRIORITY, 5), below Wi-Fi's and esp_hosted's: it runs once
// a second for a moment, and never waits for the engine.
constexpr UBaseType_t WATCH_PRIORITY = 10;
TaskHandle_t watch = nullptr;
TaskHandle_t timer_task = nullptr;
char never_details[128];
void look() {
  if (ring.magic != TRACE_MAGIC) return;
  const uint32_t now = static_cast<uint32_t>(esp_timer_get_time() / 1000);
  const Call *call = ppa_trace::never_back(ring.calls, TRACE_CALLS, now);
  if (!call) return;
  static const char *const STATE[] = {"running", "ready", "blocked", "suspended", "deleted"};
  const int state = timer_task ? static_cast<int>(eTaskGetState(timer_task)) : -1;
  snprintf(never_details, sizeof never_details,
           "PPA copy never finished: %ux%u turned %u to %u,%u by %s, %u ms; esp_timer %s", (unsigned) call->w,
           (unsigned) call->h, (unsigned) call->angle * 90, (unsigned) call->out_x, (unsigned) call->out_y, call->task,
           (unsigned) (now - call->at_ms), state >= 0 && state < 5 ? STATE[state] : "?");
  esp_system_abort(never_details);
}
void watch_main(void *) {
  for (;;) {
    vTaskDelay(pdMS_TO_TICKS(1000));
    look();
  }
}
void start_watch() {
  if (watch) return;
  timer_task = xTaskGetHandle("esp_timer");
  xTaskCreatePinnedToCore(watch_main, "ppa_watch", WATCH_STACK, nullptr, WATCH_PRIORITY, &watch, 0);
}

}  // namespace

namespace ppa_trace {
void take() {
  start_watch();
  if (ring.magic != TRACE_MAGIC) return;
  kept = ring;
  had = true;
  ring.magic = 0;
}
void report() {
  if (!had) return;
  uint32_t newest = 0;
  for (const Call &call : kept.calls) newest = call.seq > newest ? call.seq : newest;
  ESP_LOGW(TAG, "The last PPA calls of the previous boot, the newest last:");
  for (uint32_t seq = newest >= TRACE_CALLS ? newest - TRACE_CALLS + 1 : 1; seq <= newest && seq > 0; ++seq) {
    const Call &call = kept.calls[seq % TRACE_CALLS];
    if (call.seq != seq || call.state < ASKED || call.state > FAILED) continue;
    static const char *const STATE[] = {"", "NEVER CAME BACK", "came back", "failed"};
    ESP_LOGW(TAG, "  #%u at %u ms, %s: %ux%u turned %u to %u,%u, %d piece(s), %s", (unsigned) call.seq,
             (unsigned) call.at_ms, call.task, (unsigned) call.w, (unsigned) call.h, (unsigned) call.angle * 90,
             (unsigned) call.out_x, (unsigned) call.out_y, (int) call.pieces, STATE[call.state]);
  }
}
}  // namespace ppa_trace

extern "C" esp_err_t __real_ppa_do_scale_rotate_mirror(ppa_client_handle_t client, const ppa_srm_oper_config_t *config);

// The call as the guard makes it: `pieces` the plan it went in (1 whole, 0 as it was).
static esp_err_t copy_guarded(ppa_client_handle_t client, const ppa_srm_oper_config_t *config, int &pieces) {
  pieces = 0;
  // A call that does not wait cannot be made to wait for its pieces, and a mirrored block lands elsewhere than the plan
  // places it: both go as they are (nothing on this screen asks for either).
  if (config->mode != PPA_TRANS_MODE_BLOCKING || config->mirror_x || config->mirror_y)
    return __real_ppa_do_scale_rotate_mirror(client, config);
  ppa_guard::Block block;
  block.w = config->in.block_w;
  block.h = config->in.block_h;
  block.angle = static_cast<ppa_guard::Angle>(config->rotation_angle);
  block.sx = as_scale(config->scale_x);
  block.sy = as_scale(config->scale_y);
  block.depth = depth_of(config->out.srm_cm, block.unit_w);
  // The macro block as the driver counts it (ppa_srm.c): 16 rows on a build for revision 1, the register's on
  // revision 3.
  block.mb = ppa_ll_srm_get_mb_size(PPA_LL_GET_HW) == PPA_LL_SRM_MB_SIZE_16_16 ? 16 : 32;
  if (block.depth == 0) return __real_ppa_do_scale_rotate_mirror(client, config);
  ppa_guard::Piece plan[ppa_guard::MAX_PIECES];
  const int n = ppa_guard::plan(block, plan);
  pieces = n;
  if (n == 1) return __real_ppa_do_scale_rotate_mirror(client, config);
  if (n == 0) {
    if (given_up++ == 0)
      ESP_LOGW(TAG, "a turned copy of %ux%u may hang the 2D-DMA (DIG-734) and has no safe pieces; copied as it is",
               (unsigned) block.w, (unsigned) block.h);
    return __real_ppa_do_scale_rotate_mirror(client, config);
  }
  if (guarded++ < TOLD_AT_MOST)
    ESP_LOGI(TAG, "a turned copy of %ux%u would hang the 2D-DMA (DIG-734): copied in %d pieces", (unsigned) block.w,
             (unsigned) block.h, n);
  for (int i = 0; i < n; ++i) {
    ppa_srm_oper_config_t own = *config;
    own.in.block_offset_x = config->in.block_offset_x + plan[i].in_x;
    own.in.block_offset_y = config->in.block_offset_y + plan[i].in_y;
    own.in.block_w = plan[i].in_w;
    own.in.block_h = plan[i].in_h;
    own.out.block_offset_x = config->out.block_offset_x + plan[i].out_x;
    own.out.block_offset_y = config->out.block_offset_y + plan[i].out_y;
    const esp_err_t err = __real_ppa_do_scale_rotate_mirror(client, &own);
    if (err != ESP_OK) return err;
  }
  return ESP_OK;
}

extern "C" esp_err_t __wrap_ppa_do_scale_rotate_mirror(ppa_client_handle_t client, const ppa_srm_oper_config_t *config) {
  if (!config) return __real_ppa_do_scale_rotate_mirror(client, config);
  const uint32_t seq = note(config);
  int pieces = 0;
  const int64_t from = esp_timer_get_time();
  const esp_err_t err = copy_guarded(client, config, pieces);
  glass::engine_took(static_cast<uint32_t>(esp_timer_get_time() - from));  // LVGL's turn of a flush (glass.h, Held)
  came_back(seq, pieces, err);
  return err;
}
#else
namespace ppa_trace {
void take() {}
void report() {}
}  // namespace ppa_trace
#endif
