// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_picture_jpeg.cpp -o /tmp/test_picture_jpeg && /tmp/test_picture_jpeg
// The JPEG a screen takes (picture_jpeg.h): its first bytes, the whole MCUs its decoder writes, what the app says along
// with it (the size it is shown at, its places' corners, in an APP15 segment) and the corners made exact again.
// tests/test_camera.py keeps the numbers equal to picture_paint.py's.
#include "../components/smart_display/picture_jpeg.h"
#include <cassert>
#include <vector>

using namespace picture_jpeg;

int main() {
  // A JPEG by its first two bytes.
  const uint8_t start[] = {0xFF, 0xD8, 0xFF, 0xE0};
  assert(is_jpeg(start, 4) && !is_jpeg(start, 1) && !is_jpeg(reinterpret_cast<const uint8_t *>("BM"), 2));
  // The decoder writes whole MCUs: 16 x 16 for 4:2:0, 16 x 8 for 4:2:2, 8 x 8 otherwise; a picture the app made whole
  // MCUs of MCU comes out at its own size.
  assert(MCU == 16);
  assert(decoded_width(1280, Sampling::YUV420) == 1280 && decoded_height(720, Sampling::YUV420) == 720);
  assert(decoded_width(1281, Sampling::YUV420) == 1296 && decoded_height(721, Sampling::YUV420) == 736);
  assert(decoded_width(1281, Sampling::YUV422) == 1296 && decoded_height(721, Sampling::YUV422) == 728);
  assert(decoded_width(1281, Sampling::OTHER) == 1288 && decoded_height(721, Sampling::OTHER) == 728);
  assert(decoded_width(226, Sampling::YUV420) == 240 && decoded_height(254, Sampling::YUV420) == 256);
  assert(decoded_width(1, Sampling::OTHER) == 8 && decoded_height(16, Sampling::YUV420) == 16);
  // What the app says along with a JPEG: the size it is shown at and its places' corners, in an APP15 segment.
  {
    const uint8_t noted[] = {0xFF, 0xD8, 0xFF, 0xEF, 0x00, 0x18, 'T', 'S', 'S', 'R', 0x00, 0xE2, 0x00, 0xFE, 0x01,
                             0x00, 0x02, 0x00, 0x03, 0x00, 0x28, 0x00, 0x1E, 0x08, 0xE7, 0x3C, 0xFF, 0xE0};
    JpegNotes notes;
    assert(jpeg_notes(noted, sizeof(noted), notes) && notes.width == 226 && notes.height == 254);
    assert(notes.corners.size() == 1 && notes.corners[0].x == 2 && notes.corners[0].y == 3 && notes.corners[0].w == 40 &&
           notes.corners[0].h == 30 && notes.corners[0].radius == 8 && notes.corners[0].ground == 0xE73C);
    const uint8_t plain[] = {0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 'J', 'F', 'I', 'F', 0x00, 0x01, 0x01, 0x00, 0x00, 0x01};
    assert(!jpeg_notes(plain, sizeof(plain), notes));
    assert(!jpeg_notes(noted, 12, notes));
    // A segment that says it is longer than the JPEG: not read.
    std::vector<uint8_t> cut(noted, noted + 20);
    assert(!jpeg_notes(cut.data(), cut.size(), notes));
  }
  // A corner made exact: what lies wholly outside its arc becomes its ground, its soft edge and inside stay.
  {
    const int w = 48, h = 40, stride = 50;
    std::vector<uint16_t> px(static_cast<size_t>(stride) * h, 0x1234);
    Corner c;
    c.x = 2, c.y = 3, c.w = 40, c.h = 30, c.radius = 8, c.ground = 0xE73C;
    mask_corners(px.data(), stride, w, h, c);
    const auto at = [&](int x, int y) { return px[static_cast<size_t>(y) * stride + x]; };
    // Top left: the corner pixel and the first row's first four outside; the fifth is in the soft edge.
    assert(at(2, 3) == 0xE73C && at(5, 3) == 0xE73C && at(6, 3) == 0x1234);
    // The other three corners alike.
    assert(at(41, 3) == 0xE73C && at(2, 32) == 0xE73C && at(41, 32) == 0xE73C && at(38, 3) == 0xE73C && at(37, 3) == 0x1234);
    // The arc's own row and the middle stay; nothing outside the place is touched.
    assert(at(2, 11) == 0x1234 && at(20, 15) == 0x1234 && at(1, 3) == 0x1234 && at(0, 0) == 0x1234 && at(44, 3) == 0x1234);
    // A corner past the picture's edge is cut, not written past it.
    Corner big = c;
    big.x = 30, big.w = 40;
    mask_corners(px.data(), stride, w, h, big);
    assert(at(47, 3) == 0x1234 || at(47, 3) == 0xE73C);
    assert(px[static_cast<size_t>(3) * stride + 49] == 0x1234);  // the stride's padding past `width`
  }
  return 0;
}
