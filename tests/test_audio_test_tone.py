"""The real test-tone producer must survive a small speaker buffer and short writes."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml


class AudioTestTone(unittest.TestCase):
    def test_complete_tone_under_backpressure_and_bounded_failure(self):
        root = Path(__file__).resolve().parents[1]
        config = yaml.load((root / 'packages/features/audio-hardware-test.yaml').read_text(), Loader=yaml.BaseLoader)
        run = next(s for s in config['script'] if s['id'] == 'audio_test_run')
        branches = next(s['if'] for s in run['then'] if 'if' in s)['then']
        tone = next(s['if'] for s in branches
                    if s.get('if', {}).get('condition', {}).get('lambda') == 'return test == 2;')
        body = next(s['if'] for s in tone['then'] if 'if' in s)['then']
        loop = next(s['while'] for s in body if 'while' in s)
        failure = next(s['lambda'] for s in body if 'lambda' in s and '9600' in s['lambda'])
        source = r'''
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <vector>
#define id(x) (x)
#define ESP_LOGW(...) do {} while (0)
size_t audio_test_play_offset = 0;
uint32_t audio_test_play_started = 0, now = 0;
int audio_test_result = 0;
uint32_t millis() { return now; }
struct Speaker {
  size_t capacity = 3200, queued = 0, calls = 0;
  bool partial = false, blocked = false;
  std::vector<uint8_t> accepted;
  size_t play(const uint8_t *data, size_t length, int) {
    ++calls;
    if (blocked || calls % 7 == 0) return 0;
    size_t count = length;
    if (partial) count = std::min({length, capacity - queued, size_t(510)}) & ~size_t(1);
    else if (length > capacity - queued) return 0;
    accepted.insert(accepted.end(), data, data + count);
    queued += count;
    return count;
  }
} panel_speaker;
bool more() { CONDITION }
void pump() { PRODUCER }
void check_result() { FAILURE }
void reset(bool partial = false, bool blocked = false) {
  panel_speaker = Speaker{};
  panel_speaker.partial = partial;
  panel_speaker.blocked = blocked;
  audio_test_play_offset = 0;
  audio_test_play_started = now = 0;
  audio_test_result = 0;
}
void run() {
  while (more()) {
    pump();
    panel_speaker.queued -= std::min(size_t(320), panel_speaker.queued);
    now += 10;
    assert(now <= 2000);
  }
  check_result();
}
int main() {
  // Reproduce why the old, ignored one-shot write produced no sound.
  std::array<uint8_t, 19200> old_tone{};
  assert(panel_speaker.play(old_tone.data(), old_tone.size(), 0) == 0);
  assert(panel_speaker.accepted.empty());

  reset();
  run();
  assert(audio_test_result == 0 && audio_test_play_offset == 9600);
  const auto complete = panel_speaker.accepted;
  assert(complete.size() == 19200);
  assert(std::any_of(complete.begin(), complete.end(), [](uint8_t b) { return b != 0; }));
  assert(now >= 500 && now < 2000);

  reset(true);
  run();
  assert(audio_test_result == 0 && audio_test_play_offset == 9600);
  // Retries and partial writes must not skip, duplicate or restart tone samples.
  assert(panel_speaker.accepted == complete);

  reset(false, true);
  run();
  assert(audio_test_play_offset == 0 && panel_speaker.accepted.empty());
  assert(now == 2000 && audio_test_result == 3);
}
'''.replace('CONDITION', loop['condition']['lambda']).replace(
            'PRODUCER', loop['then'][0]['lambda']).replace('FAILURE', failure)
        with tempfile.TemporaryDirectory() as directory:
            cpp = Path(directory) / 'tone.cpp'
            binary = Path(directory) / 'tone'
            cpp.write_text(source)
            subprocess.run([os.environ.get('CXX', 'clang++'), '-std=c++17', str(cpp), '-o', str(binary)],
                           check=True, capture_output=True)
            subprocess.run([str(binary)], check=True, capture_output=True)
