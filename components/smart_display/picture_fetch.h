#pragma once
// A picture downloaded beside the main loop (firmware 0.49.0+). ESP Screen Manager serves every picture a screen shows
// (a camera full screen, an alert's snapshot, the live pictures of a page, a cover, a page of a library) as an
// uncompressed BMP on its own port; this fetches one in a task of its own and turns it into the RGB565 pixels LVGL
// draws, while touch, drawing and Home Assistant keep the main loop to themselves.
//
// Before, ESPHome's online_image downloaded in the main loop, a chunk of 16 KB a turn, and every chunk waited for the
// network: on a 4-inch panel at about 200 KB/s a page of album covers held the loop for most of two to three seconds.
// A finger on the glass meanwhile landed late or nowhere (GitHub, 2026-10-05: "the whole screen stood still until the
// covers were in"). The download now runs where waiting costs nothing, and the main loop only takes the finished
// picture over (tick), the way the add-on's answers come in.
//
// Three pictures, as before: the full view (also a cover and a page of covers), the alert's frame and the page's strip
// (Slot). Each keeps the ETag of its link, so an unchanged picture answers 304 and costs no bytes; a new link forgets
// it. One download a slot at a time: a load while one runs waits for it (a cancelled one ends soon, at the next chunk).
//
// What online_image did for us, this keeps, so a screen behaves as before in every case that mattered: the ETag of the
// last picture goes out as If-None-Match and a 304 reports the picture unchanged; a link that does not connect, an
// answer that is not 200, a body that is no BMP or breaks off, a chunk that does not come within four seconds and a
// picture that takes over thirty all end as a failure the card's own retry handles (camera_view::Feed); the BMP is
// decoded as it streams, so no copy of the file is kept, and the pixels of a camera's next frame land in the buffer of
// the last; a picture of another size gets a new buffer, swapped in on the main loop. It decodes every BMP the add-on
// writes (Pillow: 24-bit, or 8-bit on a palette, BITMAPINFOHEADER, bottom-up) and the other plain forms too (16 and 32
// bits, BI_BITFIELDS masks, top-down), where online_image took 8 and 24 bits only. What it leaves out on purpose, since
// the add-on never sends it over the LAN: HTTPS, redirects and chunked transfer encoding.
//
// The link, the answer's head and the BMP are parsed here, free of sockets, LVGL and ESPHome, so
// tests/test_picture_fetch.cpp checks them on a PC; picture_fetch.cpp has the task and the sockets (BSD sockets on the
// ESP32's lwIP and on the host renders alike).
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <functional>
#include <string>
#include <vector>

namespace picture_fetch {

// ---- the link: http://host[:port]/path, nothing else (plain HTTP on the LAN, as the add-on serves it) ----
struct Address {
  std::string host, path;
  uint16_t port = 80;
  bool ok = false;
};
inline Address split(const std::string &url) {
  Address a;
  const std::string scheme = "http://";
  if (url.compare(0, scheme.size(), scheme) != 0) return a;
  const size_t start = scheme.size();
  const size_t slash = url.find('/', start);
  std::string authority = url.substr(start, slash == std::string::npos ? std::string::npos : slash - start);
  a.path = slash == std::string::npos ? "/" : url.substr(slash);
  const size_t colon = authority.rfind(':');
  if (colon != std::string::npos) {
    const std::string digits = authority.substr(colon + 1);
    if (digits.empty() || digits.size() > 5) return a;
    unsigned port = 0;
    for (char c : digits) {
      if (c < '0' || c > '9') return a;
      port = port * 10 + (c - '0');
    }
    if (port == 0 || port > 65535) return a;
    a.port = static_cast<uint16_t>(port);
    authority.resize(colon);
  }
  a.host = authority;
  a.ok = !a.host.empty() && a.host.find_first_of(" @/\\") == std::string::npos;
  return a;
}

// ---- the answer's head: the status line and the headers, up to the blank line ----
struct Head {
  bool complete = false;   // the blank line was seen; `length` bytes belong to the head
  size_t length = 0;
  int status = 0;
  bool has_length = false;
  size_t content_length = 0;
  std::string etag;
};
inline bool same_ignoring_case(const char *a, const char *b, size_t n) {
  for (size_t i = 0; i < n; ++i) {
    char x = a[i], y = b[i];
    if (x >= 'A' && x <= 'Z') x += 32;
    if (y >= 'A' && y <= 'Z') y += 32;
    if (x != y) return false;
  }
  return true;
}
inline Head parse_head(const char *data, size_t size) {
  Head h;
  // The end of the head: CRLF CRLF (or LF LF from a lenient server).
  size_t end = std::string::npos, skip = 0;
  for (size_t i = 0; i + 1 < size; ++i) {
    if (data[i] == '\n' && data[i + 1] == '\n') { end = i; skip = 2; break; }
    if (i + 3 < size && data[i] == '\r' && data[i + 1] == '\n' && data[i + 2] == '\r' && data[i + 3] == '\n') { end = i; skip = 4; break; }
  }
  if (end == std::string::npos) return h;
  h.complete = true;
  h.length = end + skip;
  // Line by line.
  size_t pos = 0;
  bool first = true;
  while (pos < end) {
    size_t nl = pos;
    while (nl < end && data[nl] != '\n') ++nl;
    size_t stop = nl;
    if (stop > pos && data[stop - 1] == '\r') --stop;
    const char *line = data + pos;
    const size_t len = stop - pos;
    if (first) {
      first = false;
      // HTTP/1.1 200 OK
      size_t sp = 0;
      while (sp < len && line[sp] != ' ') ++sp;
      int status = 0;
      for (size_t i = sp + 1; i < len && line[i] >= '0' && line[i] <= '9'; ++i) status = status * 10 + (line[i] - '0');
      h.status = status;
    } else {
      size_t colon = 0;
      while (colon < len && line[colon] != ':') ++colon;
      if (colon < len) {
        size_t v = colon + 1;
        while (v < len && (line[v] == ' ' || line[v] == '\t')) ++v;
        size_t ve = len;
        while (ve > v && (line[ve - 1] == ' ' || line[ve - 1] == '\t')) --ve;
        if (colon == 14 && same_ignoring_case(line, "content-length", 14)) {
          size_t n = 0;
          bool digits = v < ve;
          for (size_t i = v; i < ve; ++i) {
            if (line[i] < '0' || line[i] > '9') { digits = false; break; }
            n = n * 10 + (line[i] - '0');
          }
          if (digits) { h.has_length = true; h.content_length = n; }
        } else if (colon == 4 && same_ignoring_case(line, "etag", 4)) {
          h.etag.assign(line + v, ve - v);
        }
      }
    }
    pos = nl + 1;
  }
  return h;
}

// ---- the BMP: what the add-on writes (Pillow: 24-bit, or 8-bit on a palette, BITMAPINFOHEADER, bottom-up) and the
// other plain forms, so a picture from elsewhere still shows ----
constexpr size_t BMP_HEAD = 54;        // the file header and a BITMAPINFOHEADER
constexpr int MAX_SIDE = 4096;         // more than any glass; a wrong header stops here
struct Bmp {
  bool ok = false;
  int width = 0, height = 0;           // height as drawn (positive)
  bool top_down = false;
  int bpp = 0;
  uint32_t compression = 0;            // 0 BI_RGB, 3 BI_BITFIELDS
  size_t dib_size = 0, data_offset = 0;
  unsigned colors = 0;                 // palette entries (8-bit)
  size_t row_bytes = 0;                // a row in the file, padded to four bytes
  uint32_t masks[3] = {0, 0, 0};       // BI_BITFIELDS: red, green, blue
  size_t palette_offset() const { return 14 + dib_size; }
  size_t palette_bytes() const { return bpp <= 8 ? colors * 4 : 0; }
  // What the head must hold before the rows: the palette or the masks come before the pixel data.
  size_t prefix() const { return data_offset; }
};
inline uint32_t le32(const uint8_t *p) { return uint32_t(p[0]) | uint32_t(p[1]) << 8 | uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24; }
inline uint16_t le16(const uint8_t *p) { return uint16_t(p[0] | p[1] << 8); }
// Parses the file header and the info header (`size` >= BMP_HEAD); the masks are read when `size` reaches them.
inline Bmp parse_bmp(const uint8_t *data, size_t size) {
  Bmp b;
  if (size < BMP_HEAD || data[0] != 'B' || data[1] != 'M') return b;
  b.data_offset = le32(data + 10);
  b.dib_size = le32(data + 14);
  if (b.dib_size < 40) return b;
  const int32_t w = static_cast<int32_t>(le32(data + 18)), h = static_cast<int32_t>(le32(data + 22));
  b.bpp = le16(data + 28);
  b.compression = le32(data + 30);
  b.colors = le32(data + 46);
  if (w <= 0 || w > MAX_SIDE || h == 0 || h > MAX_SIDE || h < -MAX_SIDE) return b;
  b.width = w;
  b.top_down = h < 0;
  b.height = h < 0 ? -h : h;
  if (b.bpp == 8) {
    if (b.colors == 0 || b.colors > 256) b.colors = 256;
  } else if (b.bpp == 16 || b.bpp == 24 || b.bpp == 32) {
    b.colors = 0;
  } else {
    return b;
  }
  if (b.compression == 3) {
    if (b.bpp != 16 && b.bpp != 32) return b;
    // The masks follow a 40-byte header; a larger header (V4, V5) holds them at the same place.
    if (size < BMP_HEAD + 12) return b;
    for (int i = 0; i < 3; ++i) b.masks[i] = le32(data + BMP_HEAD + 4 * i);
  } else if (b.compression != 0) {
    return b;
  }
  b.row_bytes = ((static_cast<size_t>(b.width) * b.bpp + 31) / 32) * 4;
  if (b.data_offset < b.palette_offset() + b.palette_bytes() + (b.compression == 3 ? 12 : 0)) return b;
  b.ok = true;
  return b;
}
inline uint16_t rgb565(uint8_t r, uint8_t g, uint8_t bl) {
  return static_cast<uint16_t>((r & 0xF8) << 8 | (g & 0xFC) << 3 | bl >> 3);
}
// One channel out of a masked pixel, scaled to 8 bits.
inline uint8_t channel(uint32_t pixel, uint32_t mask) {
  if (!mask) return 0;
  int shift = 0;
  while (!((mask >> shift) & 1)) ++shift;
  uint32_t m = mask >> shift;
  int bits = 0;
  while ((m >> bits) & 1) ++bits;
  const uint32_t value = (pixel & mask) >> shift;
  return bits >= 8 ? static_cast<uint8_t>(value >> (bits - 8)) : static_cast<uint8_t>(value * 255 / ((1u << bits) - 1));
}
// One row of the file into `out` (width pixels, RGB565 in the chip's own byte order, as LVGL reads it).
// `palette` is the file's palette (BGRX, four bytes an entry) for 8 bits a pixel.
inline void convert_row(const Bmp &b, const uint8_t *palette, const uint8_t *row, uint16_t *out) {
  const int w = b.width;
  switch (b.bpp) {
    case 8:
      for (int x = 0; x < w; ++x) {
        const unsigned i = row[x] < b.colors ? row[x] : 0;
        const uint8_t *e = palette + 4 * i;
        out[x] = rgb565(e[2], e[1], e[0]);
      }
      break;
    case 24:
      for (int x = 0; x < w; ++x) { const uint8_t *p = row + 3 * x; out[x] = rgb565(p[2], p[1], p[0]); }
      break;
    case 32:
      if (b.compression == 3) {
        for (int x = 0; x < w; ++x) { const uint32_t p = le32(row + 4 * x); out[x] = rgb565(channel(p, b.masks[0]), channel(p, b.masks[1]), channel(p, b.masks[2])); }
      } else {
        for (int x = 0; x < w; ++x) { const uint8_t *p = row + 4 * x; out[x] = rgb565(p[2], p[1], p[0]); }
      }
      break;
    case 16:
      if (b.compression == 3) {
        if (b.masks[0] == 0xF800 && b.masks[1] == 0x07E0 && b.masks[2] == 0x001F) {
          for (int x = 0; x < w; ++x) out[x] = le16(row + 2 * x);
        } else {
          for (int x = 0; x < w; ++x) { const uint32_t p = le16(row + 2 * x); out[x] = rgb565(channel(p, b.masks[0]), channel(p, b.masks[1]), channel(p, b.masks[2])); }
        }
      } else {
        // BI_RGB 16 bits: 5-5-5.
        for (int x = 0; x < w; ++x) { const uint16_t p = le16(row + 2 * x); out[x] = rgb565(channel(p, 0x7C00), channel(p, 0x03E0), channel(p, 0x001F)); }
      }
      break;
    default:
      std::memset(out, 0, sizeof(uint16_t) * w);
  }
}

// ---- the download as a run of bytes: feeds the decoder from any source, the socket or a test ----
// Takes the bytes of the BMP as they come and fills `pixels` (width * height RGB565) once the head is known: `ready`
// is called with the picture's size and must give the buffer (or null to stop). `done` tells whether the whole
// picture came.
class Decoder {
 public:
  using Ready = std::function<uint16_t *(int width, int height)>;
  explicit Decoder(Ready ready) : ready_(std::move(ready)) {}
  // False on a picture this cannot show (a wrong head, no buffer); then nothing more is taken.
  bool feed(const uint8_t *data, size_t size) {
    if (failed_) return false;
    size_t pos = 0;
    while (pos < size) {
      if (!headed_) {
        // The head in three steps: the two headers, the masks when the picture has them, then everything up to the
        // rows (the palette); never a byte more, the rows start right after.
        const size_t want = bmp_.ok ? bmp_.prefix() : masks_ ? BMP_HEAD + 12 : BMP_HEAD;
        const size_t take = std::min(size - pos, want - head_.size());
        head_.append(reinterpret_cast<const char *>(data + pos), take);
        pos += take;
        if (head_.size() < want) return true;
        const auto *head = reinterpret_cast<const uint8_t *>(head_.data());
        if (!bmp_.ok) {
          bmp_ = parse_bmp(head, head_.size());
          if (!bmp_.ok) {
            if (!masks_ && head[0] == 'B' && head[1] == 'M' && le32(head + 30) == 3) { masks_ = true; continue; }
            return fail();
          }
          if (bmp_.prefix() > 64 * 1024) return fail();
          continue;
        }
        pixels_ = ready_ ? ready_(bmp_.width, bmp_.height) : nullptr;
        if (!pixels_) return fail();
        headed_ = true;
        row_.resize(bmp_.row_bytes);
        row_fill_ = 0;
      }
      if (rows_done_ >= bmp_.height) return true;  // the rest of the file (nothing the add-on sends) is ignored
      const size_t take = std::min(size - pos, bmp_.row_bytes - row_fill_);
      std::memcpy(row_.data() + row_fill_, data + pos, take);
      row_fill_ += take;
      pos += take;
      if (row_fill_ == bmp_.row_bytes) {
        const int y = bmp_.top_down ? rows_done_ : bmp_.height - 1 - rows_done_;
        convert_row(bmp_, reinterpret_cast<const uint8_t *>(head_.data()) + bmp_.palette_offset(), row_.data(),
                    pixels_ + static_cast<size_t>(y) * bmp_.width);
        ++rows_done_;
        row_fill_ = 0;
      }
    }
    return true;
  }
  bool done() const { return headed_ && rows_done_ >= bmp_.height; }
  bool failed() const { return failed_; }
  const Bmp &bmp() const { return bmp_; }
  int rows() const { return rows_done_; }

 private:
  bool fail() { failed_ = true; return false; }
  Ready ready_;
  std::string head_;
  std::vector<uint8_t> row_;
  size_t row_fill_ = 0;
  Bmp bmp_;
  bool headed_ = false, failed_ = false, masks_ = false;
  uint16_t *pixels_ = nullptr;
  int rows_done_ = 0;
};

// ---- what the rest of the firmware sees (picture_fetch.cpp) ----
// A slot is one of the board's pictures: the camera full screen (also the cover and the library's page), the alert's
// frame and the live strip. Its `done` is bound once at boot (the hooks in packages/features/camera.yaml) and called on
// the main loop, from tick(), when a load ends: `ok` with the picture in source(), or `cached` when the add-on answered
// 304 and the picture there is still the right one.
struct Slot;
using Done = std::function<void(bool ok, bool cached)>;
Slot &full();
Slot &thumb();
Slot &live();
void bind(Slot &slot, Done done);
// Starts the download of `url` (a new link forgets the ETag of the last). While one runs, this one waits for its end:
// a load that was released (cancelled) ends at its next chunk.
void load(Slot &slot, const std::string &url);
// Frees the picture; a download on its way is cancelled and reports nothing.
void release(Slot &slot);
bool loading(const Slot &slot);
// Hands finished downloads to their `done`, on the main loop (every 50 ms, packages/features/camera.yaml).
void tick();
}  // namespace picture_fetch

#ifdef SCREEN_PICTURES
#include "lvgl.h"
namespace picture_fetch {
// The picture LVGL draws: RGB565, `data` null while the slot holds none. The same descriptor for every load, as
// ESPHome's online_image kept one: a card that shows it keeps its pointer.
lv_image_dsc_t *source(Slot &slot);
}  // namespace picture_fetch
#endif
