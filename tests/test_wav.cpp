// wav.h and file_fetch::name_of (docs/SCREEN_FILES.md): a ringtone as ESP Screen Manager writes it, and the files a
// screen must refuse.
#include <cassert>
#include <cstdio>
#include <string>
#include <vector>
#include "components/smart_display/file_fetch.h"
#include "components/smart_display/wav.h"

static void put32(std::vector<uint8_t> &v, uint32_t x) { for (int i = 0; i < 4; ++i) v.push_back(uint8_t(x >> (8 * i))); }
static void put16(std::vector<uint8_t> &v, uint16_t x) { v.push_back(uint8_t(x)); v.push_back(uint8_t(x >> 8)); }
static void tag(std::vector<uint8_t> &v, const char *t) { v.insert(v.end(), t, t + 4); }

static std::vector<uint8_t> file(uint16_t kind, uint16_t channels, uint32_t rate, uint16_t bits, size_t samples, bool list_first = false) {
  std::vector<uint8_t> v;
  tag(v, "RIFF");
  put32(v, 0);
  tag(v, "WAVE");
  if (list_first) { tag(v, "LIST"); put32(v, 3); v.push_back('a'); v.push_back('b'); v.push_back('c'); v.push_back(0); }
  tag(v, "fmt ");
  put32(v, 16);
  put16(v, kind);
  put16(v, channels);
  put32(v, rate);
  put32(v, rate * channels * bits / 8);
  put16(v, uint16_t(channels * bits / 8));
  put16(v, bits);
  tag(v, "data");
  put32(v, uint32_t(samples * channels * bits / 8));
  for (size_t i = 0; i < samples * channels * bits / 8; ++i) v.push_back(uint8_t(i));
  return v;
}

int main() {
  // What the add-on sends: 16 kHz, mono, 16 bits.
  auto tone = file(1, 1, 16000, 16, 32000);
  auto s = wav::read(tone.data(), tone.size());
  assert(s.ok && s.rate == 16000 && s.channels == 1 && s.bits == 16 && s.offset == 44 && s.size == 64000);
  // A chunk before `fmt `, padded to an even length, is skipped.
  auto listed = file(1, 1, 16000, 16, 10, true);
  s = wav::read(listed.data(), listed.size());
  assert(s.ok && s.offset == 44 + 12 && s.size == 20);
  // A data chunk that says more than came: what is there, in whole frames.
  auto cut = file(1, 1, 16000, 16, 100);
  cut.resize(cut.size() - 3);
  s = wav::read(cut.data(), cut.size());
  assert(s.ok && s.size == 197 - 1);
  // Not PCM, not a WAV, no samples, a block that does not match.
  auto packed = file(2, 1, 16000, 16, 10);
  assert(!wav::read(packed.data(), packed.size()).ok);
  const uint8_t junk[] = "RIFX....WAVE";
  assert(!wav::read(junk, sizeof junk).ok);
  auto empty = file(1, 1, 16000, 16, 0);
  assert(!wav::read(empty.data(), empty.size()).ok);
  auto odd = file(1, 1, 16000, 16, 10);
  odd[32] = 3;  // the block's size
  assert(!wav::read(odd.data(), odd.size()).ok);
  assert(!wav::read(nullptr, 0).ok);

  // A file's name, as the screen keeps it.
  assert(file_fetch::name_of("http://10.0.0.2:8098/files/ab12.wav") == "ab12");
  assert(file_fetch::name_of("http://10.0.0.2:8098/files/ab12") == "ab12");
  assert(file_fetch::name_of("http://10.0.0.2:8098/camera/ab12.bmp").empty());
  std::puts("test_wav: ok");
  return 0;
}
