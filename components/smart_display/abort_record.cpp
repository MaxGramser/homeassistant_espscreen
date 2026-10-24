// What an abort said (abort_record.h says why): panic_abort wrapped, its details kept across the reset.
#include "abort_record.h"
#include "esphome/core/defines.h"
#ifdef USE_ESP32
#include <cstdint>

#include "esphome/core/log.h"
#include <esp_attr.h>

namespace abort_record {

namespace {

constexpr const char *TAG = "abort_record";
constexpr uint32_t MAGIC = 0x41425254;  // "ABRT"

struct Record {
  uint32_t magic;
  char text[TEXT];
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
  ESP_LOGE(TAG, "*** ABORT ON PREVIOUS BOOT ***");
  ESP_LOGE(TAG, "  Details: %s", taken.text);
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
