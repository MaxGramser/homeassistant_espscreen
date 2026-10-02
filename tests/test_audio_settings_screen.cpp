#define SETTINGS_SCREEN_TEST
#define USE_SCREEN_AUDIO
#define USE_SCREEN_AUDIO_TEST
#include "screen_text_en.h"
#include "../components/smart_display/settings_screen.h"
#include <cassert>

using namespace settings_screen;
static int applied = 0, stored = 0, reported = 0, mode = 0, taps = 0;
static bool running = false;
static std::string status;
static const Row &named(uint16_t label) {
  for (const auto &row : audio_rows) if (row.label == label) return row;
  assert(false);
  return audio_rows[0];
}
int main() {
  assert(PAGE_COUNT == 6 && pages[4].title == screen_text::txt::settings_this_screen);
  assert(set("speaker_volume", 50) == SetResult::unknown);
  audio_available = true;
  apply_audio = [] { ++applied; };
  store = [] { ++stored; };
  report = [](const char *, int32_t) { ++reported; };
  assert(set("speaker_volume", 140) == SetResult::changed && speaker_volume == 100);
  assert(applied == 1 && stored == 1 && reported == 1);
  assert(set("speaker_volume", 100) == SetResult::same && applied == 1);
  assert(set("speaker_volume", -10) == SetResult::changed && speaker_volume == 0);
  assert(set("microphone_alc", 0) == SetResult::changed && microphone_alc == 0);
  assert(set("microphone_gain", 36) == SetResult::unknown);
  assert(set("microphone_digital_gain", 12) == SetResult::unknown);
  tile_sound = [] { ++taps; };
  feedback(); assert(taps == 1);
  apply_wake_word = [] {};
  assert(set("wake_word", 99) == SetResult::changed && wake_word == 3);
  test_audio = [](int value) { mode = value; };
  audio_test_mode = [] { return mode; };
  audio_test_running = [] { return running; };
  audio_status = [] { return status; };
  const auto &mic = named(screen_text::txt::settings_test_microphone);
  const auto &speaker = named(screen_text::txt::settings_test_speaker);
  assert(mic.confirm == NO_TEXT && !mic.active());
  mic.run(); running = true; status = "Recording (4s)";
  assert(mode == 1 && mic.active() && !speaker.active());
  assert(row_text(mic) == status && row_text(speaker) == "Test speaker");
  status = "Playing recording";
  assert(row_text(mic) == status && pages[5].busy());
  pages[5].stop(); running = false; status.clear();
  assert(mode == 0 && !mic.active() && !pages[5].busy());
  assert(row_text(mic) == "Test microphone");
}
