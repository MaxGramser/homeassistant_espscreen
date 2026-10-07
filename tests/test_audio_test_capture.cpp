#include "../components/smart_display/audio_test_capture.h"
#include <cassert>

int main() {
  audio_test::Capture capture;
  // No buffer, or a stopped test, never writes. Only complete stereo frames count.
  const uint8_t stereo[] = {0x34, 0x12, 0x78, 0x56, 0x00, 0x80, 0xff, 0x7f};
  capture.push(stereo, sizeof(stereo));
  assert(capture.size() == 0);
  int16_t guarded[] = {11, 0, 0, 22};
  capture.begin(guarded + 1, 2);
  capture.push(stereo, 3);
  assert(capture.size() == 0 && capture.active());
  capture.push(stereo, sizeof(stereo));
  assert(capture.size() == 2 && !capture.active());
  assert(guarded[0] == 11 && guarded[3] == 22);
  assert(guarded[1] == 0x1234 && guarded[2] == -32768);
  capture.push(stereo, sizeof(stereo));
  assert(capture.size() == 2);
  capture.begin(guarded + 1, 2);
  capture.push(stereo, 4);
  capture.stop();
  capture.push(stereo, 4);
  assert(capture.size() == 1);
  capture.discard();
  assert(capture.data() == nullptr && capture.size() == 0 && !capture.active());
  // A caller cannot raise the five-second ceiling by allocating a larger buffer.
  static int16_t large[audio_test::Capture::MAX_SAMPLES + 1]{};
  large[audio_test::Capture::MAX_SAMPLES] = 123;
  capture.begin(large, audio_test::Capture::MAX_SAMPLES + 1);
  for (size_t i = 0; i < audio_test::Capture::MAX_SAMPLES + 1; ++i) capture.push(stereo, 4);
  assert(capture.size() == audio_test::Capture::MAX_SAMPLES);
  assert(large[audio_test::Capture::MAX_SAMPLES] == 123 && !capture.active());
  // AEC produces mono: preserve every sample at 16 kHz, without halving duration.
  capture.begin(guarded + 1, 2, 1);
  capture.push(stereo, 1);
  assert(capture.size() == 0);
  capture.push(stereo, sizeof(stereo));
  assert(capture.size() == 2 && !capture.active());
  assert(guarded[0] == 11 && guarded[3] == 22);
  assert(guarded[1] == 0x1234 && guarded[2] == 0x5678);
  capture.begin(guarded + 1, 2, 0);
  capture.push(stereo, sizeof(stereo));
  assert(capture.size() == 0 && !capture.active());
}
