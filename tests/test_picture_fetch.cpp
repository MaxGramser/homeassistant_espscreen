#include "screen_text_en.h"
// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_picture_fetch.cpp -o /tmp/test_picture_fetch && /tmp/test_picture_fetch
// The parts of a picture's download that a PC can check (picture_fetch.h): the link, the answer's head, the BMP as the
// add-on writes it (Pillow: 24-bit, or 8-bit on a palette, bottom-up) and the decoder that takes it in any chunks.
#include "../components/smart_display/picture_fetch.h"
#include <cassert>
#include <cstring>
#include <vector>

using namespace picture_fetch;

static void put32(std::vector<uint8_t> &v, size_t at, uint32_t x) { for (int i = 0; i < 4; ++i) v[at + i] = (x >> (8 * i)) & 255; }
static void put16(std::vector<uint8_t> &v, size_t at, uint16_t x) { v[at] = x & 255; v[at + 1] = x >> 8; }

// A BMP the way Pillow saves one: BITMAPINFOHEADER, BI_RGB, rows padded to four bytes, bottom-up unless `top_down`.
// `pixels` row by row from the top, RGB; 8 bits a pixel take a palette of the picture's own colours.
static std::vector<uint8_t> make_bmp(int w, int h, int bpp, const std::vector<uint32_t> &rgb, bool top_down = false, uint32_t compression = 0) {
  std::vector<uint32_t> palette;
  if (bpp == 8) for (uint32_t c : rgb) { bool had = false; for (uint32_t p : palette) had |= p == c; if (!had) palette.push_back(c); }
  const size_t row_bytes = ((size_t(w) * bpp + 31) / 32) * 4;
  const size_t masks = compression == 3 ? 12 : 0;
  const size_t offset = 54 + masks + (bpp == 8 ? 256 * 4 : 0);
  std::vector<uint8_t> f(offset + row_bytes * h, 0);
  f[0] = 'B'; f[1] = 'M';
  put32(f, 2, f.size());
  put32(f, 10, offset);
  put32(f, 14, 40);
  put32(f, 18, w);
  put32(f, 22, top_down ? uint32_t(-h) : uint32_t(h));
  put16(f, 26, 1);
  put16(f, 28, bpp);
  put32(f, 30, compression);
  put32(f, 46, bpp == 8 ? 256 : 0);
  if (compression == 3) { put32(f, 54, 0xF800); put32(f, 58, 0x07E0); put32(f, 62, 0x001F); }
  if (bpp == 8) for (size_t i = 0; i < palette.size(); ++i) { f[54 + 4 * i] = palette[i] & 255; f[55 + 4 * i] = (palette[i] >> 8) & 255; f[56 + 4 * i] = palette[i] >> 16; }
  for (int y = 0; y < h; ++y) {
    const int file_row = top_down ? y : h - 1 - y;
    uint8_t *row = f.data() + offset + row_bytes * file_row;
    for (int x = 0; x < w; ++x) {
      const uint32_t c = rgb[y * w + x];
      if (bpp == 24) { row[3 * x] = c & 255; row[3 * x + 1] = (c >> 8) & 255; row[3 * x + 2] = c >> 16; }
      else if (bpp == 16) { const uint16_t p = rgb565(c >> 16, (c >> 8) & 255, c & 255); row[2 * x] = p & 255; row[2 * x + 1] = p >> 8; }
      else { for (size_t i = 0; i < palette.size(); ++i) if (palette[i] == c) row[x] = static_cast<uint8_t>(i); }
    }
  }
  return f;
}
static uint16_t expect(uint32_t rgb) { return rgb565(rgb >> 16, (rgb >> 8) & 255, rgb & 255); }

// Feeds the file in pieces of `step` bytes and returns the pixels the decoder made.
static std::vector<uint16_t> decode(const std::vector<uint8_t> &file, size_t step, bool *failed = nullptr, int *w = nullptr, int *h = nullptr) {
  std::vector<uint16_t> pixels;
  Decoder d([&](int width, int height) { pixels.assign(size_t(width) * height, 0xBEEF); if (w) *w = width; if (h) *h = height; return pixels.data(); });
  for (size_t at = 0; at < file.size(); at += step)
    if (!d.feed(file.data() + at, std::min(step, file.size() - at))) break;
  if (failed) *failed = d.failed();
  if (!d.done()) pixels.clear();
  return pixels;
}

int main() {
  // ---- the link ----
  Address a = split("http://192.168.1.20:8098/camera/abcdefghijklmnopqrstuvwx.bmp");
  assert(a.ok && a.host == "192.168.1.20" && a.port == 8098 && a.path == "/camera/abcdefghijklmnopqrstuvwx.bmp");
  a = split("http://homeassistant.local/x.bmp");
  assert(a.ok && a.host == "homeassistant.local" && a.port == 80 && a.path == "/x.bmp");
  assert(split("http://host:8098").path == "/");
  assert(!split("https://192.168.1.20:8098/x.bmp").ok);  // plain HTTP on the LAN only
  assert(!split("http://:8098/x.bmp").ok && !split("http://host:0/x").ok && !split("http://host:70000/x").ok && !split("ftp://h/x").ok);
  assert(!split("http://host:80a/x").ok);

  // ---- the answer's head ----
  const std::string ok200 = "HTTP/1.1 200 OK\r\nContent-Type: image/bmp\r\nContent-Length: 1234\r\nETag: \"abc\"\r\nCache-Control: no-cache\r\n\r\nBM..";
  Head hd = parse_head(ok200.data(), ok200.size());
  assert(hd.complete && hd.status == 200 && hd.has_length && hd.content_length == 1234 && hd.etag == "\"abc\"");
  assert(hd.length == ok200.size() - 4);
  hd = parse_head(ok200.data(), 20);
  assert(!hd.complete);
  const std::string not_modified = "HTTP/1.1 304 Not Modified\r\netag: \"abc\"\r\n\r\n";
  hd = parse_head(not_modified.data(), not_modified.size());
  assert(hd.complete && hd.status == 304 && !hd.has_length && hd.etag == "\"abc\"" && hd.length == not_modified.size());
  const std::string lenient = "HTTP/1.0 404 Not Found\nContent-Length: 0\n\n";
  hd = parse_head(lenient.data(), lenient.size());
  assert(hd.complete && hd.status == 404 && hd.has_length && hd.content_length == 0);

  // ---- a 24-bit BMP, the add-on's full picture ----
  const std::vector<uint32_t> rgb{0xFF0000, 0x00FF00, 0x0000FF, 0x123456, 0xFFFFFF, 0x000000};
  std::vector<uint8_t> file = make_bmp(3, 2, 24, rgb);
  Bmp b = parse_bmp(file.data(), file.size());
  assert(b.ok && b.width == 3 && b.height == 2 && !b.top_down && b.bpp == 24 && b.row_bytes == 12 && b.data_offset == 54 && b.palette_bytes() == 0);
  for (size_t step : {1, 7, 54, 55, 1000}) {
    int w = 0, h = 0;
    bool failed = true;
    auto px = decode(file, step, &failed, &w, &h);
    assert(!failed && w == 3 && h == 2 && px.size() == 6);
    for (size_t i = 0; i < 6; ++i) assert(px[i] == expect(rgb[i]));
  }
  // ---- 8-bit on a palette, the add-on's compact picture ----
  file = make_bmp(3, 2, 8, rgb);
  b = parse_bmp(file.data(), file.size());
  assert(b.ok && b.bpp == 8 && b.colors == 256 && b.row_bytes == 4 && b.data_offset == 1078 && b.palette_offset() == 54 && b.palette_bytes() == 1024);
  for (size_t step : {1, 3, 1077, 1078, 1079, 5000}) {
    auto px = decode(file, step);
    assert(px.size() == 6);
    for (size_t i = 0; i < 6; ++i) assert(px[i] == expect(rgb[i]));
  }
  // ---- top-down, and 16-bit 5-6-5 with masks ----
  file = make_bmp(3, 2, 24, rgb, true);
  assert(parse_bmp(file.data(), file.size()).top_down);
  auto px = decode(file, 5);
  assert(px.size() == 6);
  for (size_t i = 0; i < 6; ++i) assert(px[i] == expect(rgb[i]));
  file = make_bmp(3, 2, 16, rgb, false, 3);
  b = parse_bmp(file.data(), 54);
  assert(!b.ok);  // the masks lie past the first 54 bytes
  b = parse_bmp(file.data(), file.size());
  assert(b.ok && b.bpp == 16 && b.compression == 3 && b.masks[0] == 0xF800 && b.data_offset == 66);
  for (size_t step : {1, 60, 66, 70, 500}) {
    px = decode(file, step);
    assert(px.size() == 6);
    for (size_t i = 0; i < 6; ++i) assert(px[i] == expect(rgb[i]));
  }
  // The masks of a picture that uses them, a channel at a time.
  assert(channel(0xF800, 0xF800) == 255 && channel(0x0000, 0xF800) == 0 && channel(0x07E0, 0x07E0) == 255 && channel(0x0400, 0x07E0) == 129);

  // ---- what stops a download ----
  bool failed = false;
  std::vector<uint8_t> bad = make_bmp(3, 2, 24, rgb);
  bad[0] = 'X';
  decode(bad, 10, &failed);
  assert(failed);
  bad = make_bmp(3, 2, 24, rgb);
  put16(bad, 28, 4);  // 4 bits a pixel: not a form the add-on writes
  decode(bad, 10, &failed);
  assert(failed);
  bad = make_bmp(3, 2, 24, rgb);
  put32(bad, 30, 1);  // RLE
  decode(bad, 10, &failed);
  assert(failed);
  bad = make_bmp(3, 2, 24, rgb);
  put32(bad, 18, 5000);  // wider than any glass
  decode(bad, 10, &failed);
  assert(failed);
  // A file cut off halfway is not done; the rows that came are in place, the rest untouched.
  file = make_bmp(3, 2, 24, rgb);
  {
    std::vector<uint16_t> pixels;
    Decoder d([&](int w, int h) { pixels.assign(size_t(w) * h, 0xBEEF); return pixels.data(); });
    assert(d.feed(file.data(), 54 + 12) && !d.done() && d.rows() == 1);
    assert(pixels[3] == expect(rgb[3]) && pixels[0] == 0xBEEF);  // bottom-up: the first file row is the last on the glass
    assert(d.feed(file.data() + 66, file.size() - 66) && d.done());
  }
  // No buffer: the decoder stops and takes nothing more.
  {
    Decoder d([](int, int) -> uint16_t * { return nullptr; });
    assert(!d.feed(file.data(), file.size()) && d.failed());
    assert(!d.feed(file.data(), 1));
  }
  // Bytes past the last row (nothing the add-on sends) are ignored, not an error.
  {
    std::vector<uint8_t> longer = file;
    longer.insert(longer.end(), 100, 0);
    px = decode(longer, 17);
    assert(px.size() == 6 && px[0] == expect(rgb[0]));
  }
  return 0;
}
