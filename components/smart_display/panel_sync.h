#pragma once
// A panel's tearing signal (packages/features/panel-sync.yaml): a panel with its own memory, such as a QSPI AMOLED,
// shows that memory while it is written. LVGL sends a frame in strips of its draw buffer, so a picture that moves (a
// radar's beam, a page sliding in) would show half the old frame and half the new one, a diagonal edge in steps. The
// panel pulses its TE line as it starts showing a frame from its first row (the RM690B0's TEON, mode 0); the first strip
// of every frame waits for that pulse, so the writing starts behind the panel's own scan and keeps ahead of it.
//
// A pulse that never comes (TE not wired, or a panel that does not send it) stops the waiting after MISSES frames in a
// row, so a screen without the signal draws as fast as before. REPORT_MS after the start the log says how it went, late
// enough for a log that connects after the screen started to see it.
#include "lvgl.h"

#include <cstdint>

#if __has_include(<driver/gpio.h>) && __has_include(<esp_timer.h>)
#include <driver/gpio.h>
#include <esp_attr.h>
#include <esp_rom_sys.h>
#include <esp_timer.h>
#include "esphome/core/log.h"
#define PANEL_SYNC_ON_CHIP 1
#endif

namespace panel_sync {
// How long the first strip of a frame waits at most: a little more than one frame of a 60 Hz panel.
constexpr int64_t WAIT_US = 20000;
// Frames in a row without a pulse before the screen stops waiting for one.
constexpr int MISSES = 10;
constexpr uint32_t REPORT_MS = 30000;

inline volatile uint32_t pulses = 0;
inline bool armed = false, on = false;
inline int missed = 0;
inline uint32_t synced = 0;

#ifdef PANEL_SYNC_ON_CHIP
static void IRAM_ATTR on_pulse(void *) { pulses = pulses + 1; }

// Until the next pulse, or WAIT_US; false when none came.
inline bool wait() {
  const uint32_t seen = pulses;
  const int64_t until = esp_timer_get_time() + WAIT_US;
  while (pulses == seen) {
    if (esp_timer_get_time() >= until) return false;
    esp_rom_delay_us(10);
  }
  return true;
}

inline void flush_start(lv_event_t *) {
  if (!on || !armed) return;
  armed = false;
  if (wait()) {
    missed = 0;
    ++synced;
    return;
  }
  if (++missed < MISSES) return;
  on = false;
  ESP_LOGW("panel_sync", "No tearing signal in %d frames: the screen draws without waiting for it", MISSES);
}

// Called at boot with the GPIO the panel's TE line is on.
inline void start(int pin) {
  lv_display_t *display = lv_display_get_default();
  if (!display || pin < 0) return;
  gpio_config_t io{};
  io.pin_bit_mask = 1ULL << pin;
  io.mode = GPIO_MODE_INPUT;
  io.pull_up_en = GPIO_PULLUP_DISABLE;
  io.pull_down_en = GPIO_PULLDOWN_ENABLE;
  io.intr_type = GPIO_INTR_POSEDGE;
  if (gpio_config(&io) != ESP_OK) return;
  // ESPHome installs the shared service for its own interrupt pins (the touch panel's); otherwise this does.
  const esp_err_t service = gpio_install_isr_service(0);
  if (service != ESP_OK && service != ESP_ERR_INVALID_STATE) return;
  if (gpio_isr_handler_add((gpio_num_t) pin, on_pulse, nullptr) != ESP_OK) return;
  lv_display_add_event_cb(display, [](lv_event_t *) { armed = true; }, LV_EVENT_REFR_START, nullptr);
  lv_display_add_event_cb(display, flush_start, LV_EVENT_FLUSH_START, nullptr);
  lv_timer_t *report = lv_timer_create([](lv_timer_t *) {
    if (on) ESP_LOGI("panel_sync", "%u frames waited for the panel's tearing signal, none of the last ones in vain", (unsigned) synced);
    else ESP_LOGW("panel_sync", "The tearing signal stopped coming after %u frames: the screen draws without it", (unsigned) synced);
  }, REPORT_MS, nullptr);
  lv_timer_set_repeat_count(report, 1);
  on = true;
  ESP_LOGI("panel_sync", "Each frame waits for the panel's tearing signal on GPIO%d", pin);
}
#else
// The browser preview and the host renders have no panel to wait for.
inline void start(int) {}
#endif
}  // namespace panel_sync
