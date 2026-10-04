#define SETTINGS_SCREEN_TEST
#define USE_SCREEN_AUDIO
#include "screen_text_en.h"
#include "../components/smart_display/settings_screen.h"
#include <cassert>
int main() {
  using namespace settings_screen;
  static_assert(PAGE_COUNT == 6);
  static_assert(std::size(audio_rows) == 4);
  audio_available = true;
  assert(set("wake_word", 1) == SetResult::unknown);
  assert(set("speaker_volume", 75) == SetResult::changed && speaker_volume == 75);
  for (const auto &row : audio_rows) assert(row.kind != Kind::action);
}
