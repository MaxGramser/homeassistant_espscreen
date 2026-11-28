#pragma once
// The JPEG a screen takes (docs/PICTURES.md, "Formats"; docs/PICTURE_ARCHITECTURE.md, section 3.7): one profile, shared
// with ESP Screen Manager's picture_paint.py, which makes every such JPEG, and tests/test_camera.py keeps the two sides
// equal. A baseline JPEG sampled 4:2:0, made whole MCUs of MCU pixels each way (the ESP32-P4's hardware decoder refuses a
// picture whose sides do not divide), its last row and column carried on; its own size, the one it is shown at, and the
// rounded corners of its flat places travel in an APP15 segment right after its start (NOTES_MARK). JPEG rings where a
// corner's edge meets its ground (white flecks on a light page around a dark cover), so the screen sets what lies wholly
// outside each arc back to the ground once it has decoded the picture (mask_corners), exactly as a BMP has it.
//
// The decoder writes whole MCUs too: a decoded picture's rows are as wide as the picture rounded up to 16 (4:2:0 and
// 4:2:2) or 8 pixels, and there are as many rows as its height rounded up to 16 (4:2:0) or 8 (decoded_width,
// decoded_height), the stride every reader of a decoded JPEG counts with.
//
// Pure, free of ESP-IDF, LVGL and sockets: tests/test_picture_jpeg.cpp checks it on a PC.
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <vector>

namespace picture_jpeg {
// The app pads a JPEG to whole MCUs of this many pixels each way (picture_paint.MCU).
constexpr int MCU = 16;
// The APP15 segment's mark (picture_paint.JPEG_SIZE), and the most corners the app writes into it (picture_paint.MAX_CORNERS).
constexpr char NOTES_MARK[] = "TSSR";
constexpr int MAX_CORNERS = 64;

// A JPEG, told by its first two bytes (the start of image marker).
inline bool is_jpeg(const uint8_t *data, size_t size) { return size >= 2 && data[0] == 0xFF && data[1] == 0xD8; }

// How a JPEG's chroma is sampled, as far as the decoder's whole MCUs are concerned: 4:2:0 (MCUs of 16 x 16), 4:2:2
// (16 x 8), anything else (8 x 8: 4:4:4, grey).
enum class Sampling : uint8_t { OTHER, YUV422, YUV420 };
// A decoded picture's rows are this wide (pixels), and there are this many of them: the picture's size rounded up to
// the MCU of its sampling.
inline int decoded_width(int width, Sampling sampling) {
  const int mcu = sampling == Sampling::OTHER ? 8 : 16;
  return (width + mcu - 1) & ~(mcu - 1);
}
inline int decoded_height(int height, Sampling sampling) {
  const int mcu = sampling == Sampling::YUV420 ? 16 : 8;
  return (height + mcu - 1) & ~(mcu - 1);
}

// What the app says along with a JPEG (picture_paint.encode: an APP15 segment right after its start, NOTES_MARK): the size it
// is shown at, since every JPEG is made whole MCUs (a multiple of 16 each way, the P4's decoder takes no other), and the
// rounded corners of its flat places. JPEG rings where a corner's edge meets its ground (white flecks on a light page
// around a dark cover), so each corner is made exact again after decoding (mask_corners). False without the segment:
// the JPEG's own size holds, and it has no corners to mend.
struct Corner {
  int x = 0, y = 0, w = 0, h = 0, radius = 0;
  uint16_t ground = 0;  // RGB565, as the pixels are
};
struct JpegNotes {
  int width = 0, height = 0;
  std::vector<Corner> corners;
};
inline bool jpeg_notes(const uint8_t *data, size_t size, JpegNotes &notes) {
  if (size < 15 || data[2] != 0xFF || data[3] != 0xEF || std::memcmp(data + 6, NOTES_MARK, 4) != 0) return false;
  const size_t end = 4 + ((static_cast<size_t>(data[4]) << 8) | data[5]);  // the segment ends here
  if (end < 15 || end > size) return false;
  const auto u16 = [&](size_t at) { return (static_cast<int>(data[at]) << 8) | data[at + 1]; };
  notes.width = u16(10);
  notes.height = u16(12);
  notes.corners.clear();
  for (size_t i = 0, at = 15; i < data[14] && at + 11 <= end; ++i, at += 11) {
    Corner c;
    c.x = u16(at), c.y = u16(at + 2), c.w = u16(at + 4), c.h = u16(at + 6), c.radius = data[at + 8];
    c.ground = static_cast<uint16_t>(u16(at + 9));
    notes.corners.push_back(c);
  }
  return notes.width > 0 && notes.height > 0;
}
// Every pixel of `c`'s four corners that lies wholly outside its arc (past its soft edge, half a pixel wide) back to its
// ground, in pixels of `stride` a row and `width` x `height` shown. The soft edge itself stays as the app painted it.
inline void mask_corners(uint16_t *pixels, int stride, int width, int height, const Corner &c) {
  const int r = std::min(c.radius, std::min(c.w, c.h) / 2);
  if (!pixels || r <= 0) return;
  const float edge = r + 0.5f;
  for (int dy = 0; dy < r; ++dy) {
    const float across = r - dy - 0.5f;  // the row's distance from the arc's centre
    const int out = std::max(0, std::min(r, static_cast<int>(std::ceil(r - std::sqrt(edge * edge - across * across) - 0.5f))));
    for (const int y : {c.y + dy, c.y + c.h - 1 - dy}) {
      if (y < 0 || y >= height) continue;
      for (int i = 0; i < out; ++i)
        for (const int x : {c.x + i, c.x + c.w - 1 - i})
          if (x >= 0 && x < width) pixels[static_cast<size_t>(y) * stride + x] = c.ground;
    }
  }
}
}  // namespace picture_jpeg
