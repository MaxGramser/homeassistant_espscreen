// What asks the internal RAM for room (heap_watch.h says why): the lowest since boot and the allocations that failed,
// kept across a reset and logged with the config dump.
#include "heap_watch.h"
#include "glass.h"
#include "esphome/core/defines.h"
#ifdef USE_ESP32
#include <cstring>

#include "esphome/core/log.h"
#include <esp_attr.h>
#include <esp_heap_caps.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

namespace heap_watch {

namespace {

constexpr const char *TAG = "heap_watch";
constexpr uint32_t MAGIC = 0x48454150;  // "HEAP"

struct Record {
  uint32_t magic;
  uint32_t lowest, lowest_at;  // the least internal RAM free this boot, and when (ms since boot)
  uint32_t failures;           // allocations that found no room this boot
  uint32_t fell_back, fell_back_size;  // the encoder's first asks (falls_back), and the last one's size
  // The last of them.
  uint32_t size, caps, free_then, at;
  char task[16];
  char function[32];
};
__NOINIT_ATTR Record record;
Record previous{};
bool had_previous = false;
LowWater water;
uint32_t logged_failures = 0, logged_fell_back = 0, checked_at = 0, counted_at = 0;
uint32_t internal_total = 0;  // all the internal RAM there is, read once at boot
constexpr uint32_t COUNT_MS = 5 * 60 * 1000;  // how often the tasks and the two heaps are logged: a leak shows as a trend

uint32_t internal_free() { return heap_caps_get_free_size(MALLOC_CAP_INTERNAL); }
uint32_t internal_lowest() { return heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL); }

void copy(char *to, size_t room, const char *from) {
  size_t i = 0;
  for (; from != nullptr && from[i] != '\0' && i + 1 < room; ++i) to[i] = from[i];
  to[i] = '\0';
}

// ESP-IDF calls this in the task whose allocation failed: no logging and no allocation here.
void failed(size_t size, uint32_t caps, const char *function) {
  if (falls_back(static_cast<uint32_t>(size), caps, internal_total)) {
    record.fell_back++;
    record.fell_back_size = static_cast<uint32_t>(size);
    return;
  }
  record.failures++;
  record.size = size;
  record.caps = caps;
  record.free_then = internal_free();
  record.at = static_cast<uint32_t>(esp_timer_get_time() / 1000);
  copy(record.task, sizeof record.task, pcTaskGetName(nullptr));
  copy(record.function, sizeof record.function, function);
}

// One failure: as the previous boot's record (an error line the report keeps), or as it happens.
void log_failure(const Record &r, bool previous_boot) {
  if (previous_boot) {
    ESP_LOGE(TAG, "  Failed: %u allocations; the last %u bytes (caps 0x%X) in %s, task %s, %u bytes internal free, "
             "%u s after boot", (unsigned) r.failures, (unsigned) r.size, (unsigned) r.caps, r.function, r.task,
             (unsigned) r.free_then, (unsigned) (r.at / 1000));
  } else {
    ESP_LOGW(TAG, "An allocation of %u bytes (caps 0x%X) found no room: in %s, task %s, %u bytes internal free (%u "
             "failed since boot)", (unsigned) r.size, (unsigned) r.caps, r.function, r.task, (unsigned) r.free_then,
             (unsigned) r.failures);
  }
}

}  // namespace

void setup() {
  if (record.magic == MAGIC) {
    previous = record;
    previous.task[sizeof previous.task - 1] = '\0';
    previous.function[sizeof previous.function - 1] = '\0';
    had_previous = true;
  }
  record = Record{};
  record.lowest = internal_lowest();
  record.magic = MAGIC;
  internal_total = static_cast<uint32_t>(heap_caps_get_total_size(MALLOC_CAP_INTERNAL));
  water.due(record.lowest, STEP);
  heap_caps_register_failed_alloc_callback(failed);
}

void tick(uint32_t now) {
  if (now - checked_at < EVERY_MS) return;
  checked_at = now;
  const uint32_t lowest = internal_lowest();
  if (lowest < record.lowest) {
    record.lowest = lowest;
    record.lowest_at = now;
  }
  if (water.due(lowest, STEP))
    ESP_LOGW(TAG, "Internal RAM at its lowest since boot: %u bytes free (%u free now)", (unsigned) lowest,
             (unsigned) internal_free());
  if (now - counted_at >= COUNT_MS) {
    counted_at = now;
    // The panel's dry runs beside the memory: PSRAM is one bus with the panel's frame buffer, and a buffer moved there
    // can starve the panel (blue frames), which every measurement of memory should see (docs/CAMERA.md).
    ESP_LOGI(TAG, "%u tasks; internal RAM %u bytes free (%u at the lowest), PSRAM %u free; the panel ran dry %u times since boot",
             (unsigned) uxTaskGetNumberOfTasks(), (unsigned) internal_free(), (unsigned) record.lowest,
             (unsigned) heap_caps_get_free_size(MALLOC_CAP_SPIRAM), (unsigned) glass::misses());
  }
  const uint32_t fell_back = record.fell_back;
  if (fell_back != logged_fell_back) {
    logged_fell_back = fell_back;
    ESP_LOGI(TAG, "An ask of %u bytes for internal RAM fell back to PSRAM, as the H.264 encoder's reference frame does",
             (unsigned) record.fell_back_size);
  }
  const uint32_t failures = record.failures;
  if (failures != logged_failures) {
    logged_failures = failures;
    const Record last = record;
    log_failure(last, false);
  }
}

void dump() {
  if (had_previous) {
    ESP_LOGE(TAG, "*** INTERNAL RAM ON PREVIOUS BOOT ***");
    ESP_LOGE(TAG, "  Lowest: %u bytes free, %u s after boot", (unsigned) previous.lowest,
             (unsigned) (previous.lowest_at / 1000));
    if (previous.failures != 0) log_failure(previous, true);
  }
  // INFO, not CONFIG: the screens log at INFO, where ESPHome compiles every ESP_LOGCONFIG out.
  ESP_LOGI(TAG, "Internal RAM: %u bytes free, %u at the lowest since boot (%u s after it), %u failed allocations, %u "
                "fell back to PSRAM", (unsigned) internal_free(), (unsigned) record.lowest,
                (unsigned) (record.lowest_at / 1000), (unsigned) record.failures, (unsigned) record.fell_back);
}

}  // namespace heap_watch
#else
namespace heap_watch {
void setup() {}
void tick(uint32_t) {}
void dump() {}
}  // namespace heap_watch
#endif
