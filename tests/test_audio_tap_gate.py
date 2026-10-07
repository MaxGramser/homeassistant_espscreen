"""Execute the actual board hook with both speaker-ownership configurations."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class TapSoundGate(unittest.TestCase):
    def test_wake_capture_allows_aec_taps_but_conversations_and_tests_do_not(self):
        root = Path(__file__).resolve().parents[1]
        yaml = (root / 'packages/hardware/wavesharep4-audio/hardware.yaml').read_text()
        hook = 'settings_screen::tile_sound = [] {' + yaml.split(
            'settings_screen::tile_sound = [] {', 1)[1].split('    };', 1)[0] + '};'
        source = r'''
#include <cassert>
struct Endpoint {
  bool running = false;
  int calls = 0;
  bool is_running() const { return running; }
  bool is_stopped() const { return !running; }
  void execute() { ++calls; }
} panel_microphone, panel_speaker, panel_tap_sound;
#define id(x) (x)
namespace settings_screen {
  int tap_sound = 1, speaker_volume = 50;
  bool conversation = false, testing = false;
  bool (*voice_active)() = [] { return conversation; };
  bool (*audio_busy)() = [] { return testing; };
  void (*tile_sound)();
}
int main() {
  HOOK
  using namespace settings_screen;
  tile_sound(); assert(panel_tap_sound.calls == 1);
  panel_microphone.running = true;
  tile_sound();
#ifdef USE_ESP_AUDIO_STACK
  assert(panel_tap_sound.calls == 2);
#else
  assert(panel_tap_sound.calls == 1);
#endif
  panel_microphone.running = false;
  for (bool *busy : {&conversation, &testing, &panel_speaker.running, &panel_tap_sound.running}) {
    *busy = true;
    const int before = panel_tap_sound.calls;
    tile_sound(); assert(panel_tap_sound.calls == before);
    *busy = false;
  }
  const int before = panel_tap_sound.calls;
  tap_sound = 0; tile_sound(); assert(panel_tap_sound.calls == before);
  tap_sound = 1; speaker_volume = 0; tile_sound(); assert(panel_tap_sound.calls == before);
}
'''.replace('HOOK', hook).replace('#include <cassert>', '#include <cassert>\n#include <initializer_list>')
        with tempfile.TemporaryDirectory() as directory:
            cpp = Path(directory) / 'tap.cpp'
            cpp.write_text(source)
            for aec in (False, True):
                with self.subTest(aec=aec):
                    binary = Path(directory) / ('aec' if aec else 'i2s')
                    command = [os.environ.get('CXX', 'clang++'), '-std=c++17',
                               '-DUSE_SCREEN_DEVICE_VOICE', '-DUSE_SCREEN_AUDIO_TEST']
                    if aec:
                        command.append('-DUSE_ESP_AUDIO_STACK')
                    subprocess.run([*command, str(cpp), '-o', str(binary)], check=True, capture_output=True)
                    subprocess.run([str(binary)], check=True, capture_output=True)
