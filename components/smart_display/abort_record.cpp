// What an abort said (abort_record.h says why): panic_abort wrapped, its details kept across the reset.
#include "abort_record.h"
#include "esphome/core/defines.h"
#ifdef USE_ESP32
#include <cstdint>

#include <string>

#include "esphome/core/log.h"
#include "loop_record.h"
#include <esp_attr.h>
#include <esp_memory_utils.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <esp_private/freertos_debug.h>

namespace abort_record {

namespace {

constexpr const char *TAG = "abort_record";
constexpr uint32_t MAGIC = 0x41425254;  // "ABRT"

struct Record {
  uint32_t magic;
  char text[TEXT];
  char task[16];      // the task that aborted
  uint32_t count;     // how many of `at` hold an address
  uint32_t at[MOST];  // the words of its stack that point at code, newest first: the calls that led to the abort
};
__NOINIT_ATTR Record record;
Record taken{};
bool had = false;

}  // namespace

void take() {
  if (record.magic != MAGIC) return;
  taken = record;
  taken.text[TEXT - 1] = '\0';
  had = true;
  record.magic = 0;
}

void report() {
  if (!had) return;
  ESP_LOGE(TAG, "*** ABORT ON PREVIOUS BOOT *** (in task %s)", taken.task);
  ESP_LOGE(TAG, "  Details: %s", taken.text);
  const uint32_t count = taken.count > static_cast<uint32_t>(MOST) ? MOST : taken.count;
  std::string all;
  for (uint32_t i = 0; i < count; ++i) {
    ESP_LOGE(TAG, "  AT%u: 0x%08X", (unsigned) i, (unsigned) taken.at[i]);
    char hex[12];
    snprintf(hex, sizeof hex, " 0x%08X", (unsigned) taken.at[i]);
    all += hex;
  }
  if (count) ESP_LOGE(TAG, "  Use: addr2line -pfiaC -e firmware.elf%s", all.c_str());
}

}  // namespace abort_record

extern "C" {
void __real_panic_abort(const char *details);
// In IRAM and byte by byte: an abort can come with the flash cache off, where nothing in flash may be read.
void IRAM_ATTR __attribute__((noreturn)) __wrap_panic_abort(const char *details) {
  int i = 0;
  for (; details != nullptr && details[i] != '\0' && i < abort_record::TEXT - 1; ++i)
    abort_record::record.text[i] = details[i];
  abort_record::record.text[i] = '\0';
  // The aborting task's own stack from here up, its code addresses kept (loop_record's scan): an assert's own frames
  // first, then whoever called what failed. Read only where the task's snapshot says its stack is.
  abort_record::record.count = 0;
  abort_record::record.task[0] = '\0';
  TaskHandle_t self = xTaskGetCurrentTaskHandle();
  TaskSnapshot_t snapshot;
  if (self != nullptr && vTaskGetSnapshot(self, &snapshot) == pdTRUE && snapshot.pxEndOfStack != nullptr) {
    const auto *from = static_cast<const uint32_t *>(__builtin_frame_address(0));
    const auto *end = reinterpret_cast<const uint32_t *>(snapshot.pxEndOfStack);
    if (from < end)
      abort_record::record.count = loop_record::scan(from, end, abort_record::record.at, abort_record::MOST,
                                                     [](uint32_t w) { return esp_ptr_executable(reinterpret_cast<const void *>(w)); });
    const char *name = pcTaskGetName(self);
    int n = 0;
    for (; name != nullptr && name[n] != '\0' && n < 15; ++n) abort_record::record.task[n] = name[n];
    abort_record::record.task[n] = '\0';
  }
  abort_record::record.magic = abort_record::MAGIC;
  __real_panic_abort(details);
  __builtin_unreachable();
}
}
#else
namespace abort_record {
void take() {}
void report() {}
}  // namespace abort_record
#endif
