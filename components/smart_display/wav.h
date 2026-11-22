#pragma once
// A WAV file's sound: where its samples are and what they are (docs/SCREEN_FILES.md). ESP Screen Manager sends sounds as
// plain RIFF/WAVE with PCM samples, which a browser plays as they are too (the editor's preview of a ringtone). This reads
// the chunks `fmt ` and `data` in any order and skips the rest (LIST and the like), and says no to anything that is not
// PCM: a compressed format, a size that runs past the file, a block that does not match its channels and bits.
//
// Pure: tests/test_wav.cpp checks it on a PC.
#include <cstddef>
#include <cstdint>
#include <cstring>

namespace wav {

struct Sound {
  bool ok = false;
  uint32_t rate = 0;
  uint16_t channels = 0, bits = 0;
  size_t offset = 0, size = 0;  // the samples: `size` bytes from `offset`, whole frames only
};

inline uint32_t le32(const uint8_t *p) { return uint32_t(p[0]) | uint32_t(p[1]) << 8 | uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24; }
inline uint16_t le16(const uint8_t *p) { return uint16_t(p[0] | p[1] << 8); }

inline Sound read(const uint8_t *data, size_t size) {
  Sound s;
  if (!data || size < 12 || std::memcmp(data, "RIFF", 4) != 0 || std::memcmp(data + 8, "WAVE", 4) != 0) return s;
  bool format = false, samples = false;
  size_t at = 12;
  while (at + 8 <= size) {
    const uint8_t *chunk = data + at;
    const size_t length = le32(chunk + 4);
    const size_t body = at + 8;
    if (length > size - body) {
      // A data chunk may say more than came (a writer that never went back to fill in its size): take what is there.
      if (std::memcmp(chunk, "data", 4) != 0) return s;
    }
    if (std::memcmp(chunk, "fmt ", 4) == 0) {
      if (length < 16) return s;
      const uint16_t kind = le16(data + body);
      s.channels = le16(data + body + 2);
      s.rate = le32(data + body + 4);
      const uint16_t block = le16(data + body + 12);
      s.bits = le16(data + body + 14);
      // 1: PCM; 0xFFFE: WAVE_FORMAT_EXTENSIBLE, which a writer may use for PCM too (its sub-format is not read).
      if ((kind != 1 && kind != 0xFFFE) || s.channels == 0 || s.rate == 0 || (s.bits != 8 && s.bits != 16) ||
          block != s.channels * (s.bits / 8))
        return s;
      format = true;
    } else if (std::memcmp(chunk, "data", 4) == 0) {
      s.offset = body;
      s.size = length > size - body ? size - body : length;
      samples = true;
      if (format) break;
    }
    at = body + length + (length & 1);  // chunks are padded to an even length
  }
  if (!format || !samples) return s;
  const size_t frame = static_cast<size_t>(s.channels) * (s.bits / 8);
  s.size -= s.size % frame;
  s.ok = s.size > 0;
  return s;
}

}  // namespace wav
