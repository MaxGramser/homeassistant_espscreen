#pragma once
#include "generated/image/bmp_decoder.h"

namespace preview_images {
constexpr size_t MAX_BYTES = 20u * 1024 * 1024;
inline unsigned next_id = 0;
struct Download {
  unsigned id = 0;
  std::string url;
  bool pending = false;
  std::vector<uint8_t> bytes;
  esphome::runtime_image::RuntimeImage image;
  void load(const std::string &value) { id = ++next_id; url = value; pending = true; }
  void release() { id = 0; pending = false; bytes.clear(); image.release(); }
  bool decode() {
    // The manager supplies bounded, uncompressed BMPs. Reject truncated or
    // malformed headers before handing bytes to ESPHome's streaming decoder.
    if (bytes.size() < 54 || bytes[0] != 'B' || bytes[1] != 'M') return false;
    const auto u32 = [&](size_t p) { return esphome::encode_uint32(bytes[p+3], bytes[p+2], bytes[p+1], bytes[p]); };
    const auto w = u32(18), h = u32(22), offset = u32(10), dib = u32(14);
    const auto bpp = esphome::encode_uint16(bytes[29], bytes[28]);
    if (!w || !h || w > 2560 || h > 2560 || dib != 40 || u32(30) != 0 || (bpp != 8 && bpp != 24)) return false;
    const size_t stride = ((size_t(w) * bpp + 31) / 32) * 4;
    const auto colors = u32(46) ? u32(46) : 256;
    if (offset < 54 || (bpp == 8 && (colors > 256 || offset < 54 + colors * 4)) ||
        offset + stride * h != bytes.size()) return false;
    esphome::runtime_image::BmpDecoder decoder(&image);
    decoder.prepare(bytes.size());
    const int used = decoder.decode(bytes.data(), bytes.size());
    return used == int(bytes.size()) && decoder.is_finished();
  }
};
inline std::array<Download, 3> downloads;
inline std::string outgoing;
inline Download *find(unsigned id) {
  for (auto &download : downloads) if (id && download.id == id) return &download;
  return nullptr;
}
inline void bind() {
  auto hooks = [](size_t index) {
    return runtime_tiles::ImageHooks{
      [index](const std::string &url) { downloads[index].load(url); },
      [index] { downloads[index].release(); },
      [index] { return &downloads[index].image.descriptor; }};
  };
  runtime_tiles::camera_full = hooks(0);
  runtime_tiles::camera_thumb = hooks(1);
  runtime_tiles::camera_live = hooks(2);
  runtime_tiles::pictures.budget = 1536u << 10;
}
}

extern "C" {
const char *preview_next_image() {
  for (auto &download : preview_images::downloads) if (download.pending) {
    download.pending = false;
    JsonDocument packet;
    packet["id"] = download.id; packet["url"] = download.url;
    preview_images::outgoing.clear(); serializeJson(packet, preview_images::outgoing);
    return preview_images::outgoing.c_str();
  }
  return "";
}
uint8_t *preview_image_buffer(unsigned id, size_t size) {
  auto *download = preview_images::find(id);
  if (!download || size < 54 || size > preview_images::MAX_BYTES) return nullptr;
  download->bytes.resize(size);
  return download->bytes.data();
}
int preview_image_ready(unsigned id, int success) {
  auto *download = preview_images::find(id);
  if (!download) return 0;  // The firmware released this image while HTTP was in flight.
  const size_t channel = download - preview_images::downloads.data();
  const bool decoded = success && download->decode();
  std::vector<uint8_t>().swap(download->bytes);
  // The one route every picture goes (picture_loader.h): the download ends in its slot, the store keeps it.
  const auto slot = channel == 2 ? picture_loader::Slot::LIVE : channel == 1 ? picture_loader::Slot::THUMB : picture_loader::Slot::FULL;
  runtime_tiles::picture_done(slot, decoded, false);
  return decoded ? 1 : 0;
}
}
