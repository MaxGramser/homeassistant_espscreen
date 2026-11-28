#pragma once
// A task whose stack lies in PSRAM, ended by the main loop. A FreeRTOS task's stack is internal RAM unless it asks
// otherwise, and the stream and download tasks of a screen (live_view.cpp, picture_fetch.cpp) asked nothing: 6 KB each,
// beside the Wi-Fi link's buffers that run a P4 short of internal RAM (heap_watch.h). PSRAM does for them, as it does
// for Screen camera's video server. ESP-IDF allows a stack there on every chip but the ESP32
// (CONFIG_FREERTOS_TASK_CREATE_ALLOW_EXT_MEM defaults to y elsewhere; without it xPortcheckValidStackMem would assert),
// on two conditions:
// - such a task never writes the flash itself (NVS, OTA, spi_flash): where the flash cache is turned off for a write the
//   PSRAM is out of reach, and its own stack with it (ESP-IDF, "Support for External RAM", restrictions). The P4 screens
//   execute from PSRAM (CONFIG_SPIRAM_XIP_FROM_PSRAM), which keeps it in reach while the flash is written, so on them
//   this is a precaution; the streams and downloads only read sockets, decode and log, and anything that keeps a
//   setting goes through the main loop.
// - it is not deleted from itself: ESP-IDF's vTaskDeleteWithCaps(NULL) makes a cleanup task for it and aborts when there
//   is no room for one, which is when internal RAM runs short (freertos/esp_additions/idf_additions.c).
// So the task says it is done and suspends itself (finish), and the main loop deletes it (reap): vTaskDeleteWithCaps
// suspends it in turn and waits until it is the current task on no core before it frees the stack and the TCB, so a
// task still on its way into its suspension is safe to delete (idf_additions.c, prvTaskDeleteWithCaps). Without PSRAM,
// or with none of it free, the task is an ordinary one and deletes itself, as before.
#include <atomic>
#include <cstdint>
#ifdef USE_ESP32
#include <esp_heap_caps.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/idf_additions.h>
#endif

namespace psram_task {

#ifdef USE_ESP32
struct Task {
  TaskHandle_t handle = nullptr;
  // Written before the task is made, so the task reads it right however soon it runs (a stream task outranks the main
  // loop and can end at once, a link refused); read by the task once, before it says it is done.
  std::atomic<bool> in_psram{false};
};

// Starts `fn(arg)` on `core` (or tskNO_AFFINITY): its stack in PSRAM where there is room, else inside the chip. The
// last task on `task` must be reaped before.
inline bool start(Task &task, TaskFunction_t fn, const char *name, uint32_t stack, void *arg, UBaseType_t priority,
                  BaseType_t core) {
  task.handle = nullptr;
  task.in_psram.store(true, std::memory_order_release);
  if (xTaskCreatePinnedToCoreWithCaps(fn, name, stack, arg, priority, &task.handle, core,
                                      MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT) == pdPASS)
    return true;
  // Nothing ran: the flag can still change.
  task.handle = nullptr;
  task.in_psram.store(false, std::memory_order_release);
  return xTaskCreatePinnedToCore(fn, name, stack, arg, priority, &task.handle, core) == pdPASS;
}

// What the task reads of itself before it says it is done (its owner may be freed or restarted after that).
inline bool in_psram(const Task &task) { return task.in_psram.load(std::memory_order_acquire); }

// The task's last call: an ordinary task deletes itself, one in PSRAM suspends itself until reap.
[[noreturn]] inline void finish(bool in_psram) {
  if (!in_psram) vTaskDelete(nullptr);
  for (;;) vTaskSuspend(nullptr);
}

// On the main loop, after the task said it is done: deletes it if its stack is in PSRAM (an ordinary one deleted
// itself). Before its owner is freed or its next task is started.
inline void reap(Task &task) {
  if (task.in_psram.load(std::memory_order_acquire) && task.handle != nullptr) vTaskDeleteWithCaps(task.handle);
  task.handle = nullptr;
  task.in_psram.store(false, std::memory_order_release);
}
#endif

}  // namespace psram_task
