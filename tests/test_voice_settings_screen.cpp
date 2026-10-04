#define SETTINGS_SCREEN_TEST
#define USE_SCREEN_AUDIO
#define USE_SCREEN_DEVICE_VOICE
#include "screen_text_en.h"
#include "../components/smart_display/settings_screen.h"
#include <cassert>

using namespace settings_screen;
static bool running = false;
static std::string status;
int main() {
  audio_available = true;
  apply_voice_wake = [] {};
  apply_wake_word = [] {};
  assert(!wake_word_enabled);
  assert(set("wake_word_enabled", 1) == SetResult::changed);
  assert(wake_word_enabled);
  assert(set("wake_word", 20) == SetResult::changed && wake_word == 3);
  assert(set("wake_word_enabled", 0) == SetResult::changed);
  voice_start = [] { running = true; };
  voice_stop = [] { running = false; };
  voice_active = [] { return running; };
  voice_status = [] { return status; };
  const auto &start = audio_rows[0], &stop = audio_rows[1];
  assert(row_text(start) == "Start voice" && start.enabled() && !stop.enabled());
  assert(start.shown() && stop.shown());
  start.run(); status = "Listening";
  assert(!start.enabled() && start.active() && stop.enabled());
  assert(row_text(start) == status);
  stop.run(); status.clear();
  assert(start.enabled() && !start.active() && !stop.enabled());
  assert(row_text(start) == "Start voice");
}
