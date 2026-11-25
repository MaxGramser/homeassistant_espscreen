// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_chip_protocol.cpp -o /tmp/test_chip_protocol && /tmp/test_chip_protocol
// The words between a screen and its second chip (chip_protocol.h): a frame comes out of the reader as it went in,
// whatever bytes it holds; a damaged or overlong one is dropped and the next one still reads; and the screen never
// sends more sound than the chip has room for.
#include "../components/chip_link/chip_protocol.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>

using namespace chip_protocol;

static std::vector<uint8_t> wire_of(uint8_t type, const std::vector<uint8_t> &payload) {
  std::vector<uint8_t> wire(WIRE_MOST);
  const size_t n = frame(type, payload.data(), payload.size(), wire.data());
  wire.resize(n);
  return wire;
}

// Feeds the bytes and returns how many frames stood ready; the last one's type and payload stay in `r`.
static int feed(Reader &r, const std::vector<uint8_t> &bytes) {
  int ready = 0;
  for (uint8_t b : bytes) ready += r.feed(b) ? 1 : 0;
  return ready;
}

int main() {
  {  // The check is CRC-16/CCITT-FALSE: "123456789" gives 0x29B1.
    assert(crc16(reinterpret_cast<const uint8_t *>("123456789"), 9) == 0x29B1);
  }
  {  // A frame holds no zero but its last byte, and reads back as it was: empty, with zeros, with 254 and more in a row.
    for (size_t length : {size_t{0}, size_t{1}, size_t{5}, size_t{253}, size_t{254}, size_t{255}, size_t{600}, MOST - 1}) {
      for (int fill = 0; fill < 3; ++fill) {
        std::vector<uint8_t> payload(length);
        for (size_t i = 0; i < length; ++i) payload[i] = fill == 0 ? 0 : fill == 1 ? 0x55 : static_cast<uint8_t>(i * 7 + 1);
        const auto wire = wire_of(AUDIO, payload);
        assert(!wire.empty() && wire.size() <= WIRE_MOST && wire.back() == 0);
        for (size_t i = 0; i + 1 < wire.size(); ++i) assert(wire[i] != 0);
        Reader r;
        assert(feed(r, wire) == 1);
        assert(r.type() == AUDIO && r.size() == length);
        assert(length == 0 || std::memcmp(r.payload(), payload.data(), length) == 0);
      }
    }
  }
  {  // A payload that does not fit makes no frame.
    std::vector<uint8_t> big(MOST), out(WIRE_MOST);
    assert(frame(AUDIO, big.data(), big.size(), out.data()) == 0);
  }
  {  // Two frames back to back are two frames; a zero between them is nothing.
    auto wire = wire_of(HELLO, {});
    const auto second = wire_of(VOLUME, {0x00, 0x80});
    wire.push_back(0);
    wire.insert(wire.end(), second.begin(), second.end());
    Reader r;
    assert(feed(r, wire) == 2);
    assert(r.type() == VOLUME && r.size() == 2 && u16(r.payload()) == 0x8000);
  }
  {  // A byte that changed on the way: the frame is dropped and counted, and the next one reads.
    auto bad = wire_of(BEGIN, {1, 0x80, 0x3e});
    bad[2] ^= 0x10;
    Reader r;
    assert(feed(r, bad) == 0 && r.bad() == 1);
    assert(feed(r, wire_of(BEGIN, {1, 0x80, 0x3e})) == 1 && r.size() == 3 && u16(r.payload() + 1) == 16000);
  }
  {  // A reader that starts in the middle of a frame, or gets noise, finds its place at the next zero.
    const auto whole = wire_of(STATUS, {1, 1, 0, 0, 0, 0, 0, 0, 0, 0});
    std::vector<uint8_t> tail(whole.begin() + 4, whole.end());
    Reader r;
    assert(feed(r, tail) == 0);
    assert(feed(r, whole) == 1 && r.type() == STATUS && r.size() == 10);
    std::vector<uint8_t> noise(3000, 0xAA);  // longer than any frame of ours
    noise.push_back(0);
    assert(feed(r, noise) == 0);
    assert(feed(r, whole) == 1);
  }
  {  // Seeed's own packets (no check, types from 0xA0) are never taken for ours.
    const uint8_t seeed[] = {0xB2, 0x00, 0x00, 0xC8, 0x43};  // a CO2 reading of its factory firmware
    std::vector<uint8_t> wire(16);
    const size_t n = cobs_encode(seeed, sizeof seeed, wire.data());
    wire.resize(n);
    wire.push_back(0);
    Reader r;
    assert(feed(r, wire) == 0);
  }
  {  // The numbers travel little endian.
    uint8_t p[4];
    put32(p, 0x12345678);
    assert(p[0] == 0x78 && p[3] == 0x12 && u32(p) == 0x12345678);
    put16(p, 0xBEEF);
    assert(u16(p) == 0xBEEF);
  }
  {  // The screen may send what the chip has room for, less what is on its way or waiting there, and never below zero.
    assert(may_send(32768, 0, 0) == 32768);
    assert(may_send(32768, 30000, 1000) == 3768);
    assert(may_send(32768, 40000, 7232) == 0);
    assert(may_send(32768, 50000, 1000) == 0);
    // The counters wrap after 2^32 samples; the difference still holds.
    assert(may_send(32768, 5, 0xFFFFFFF0u) == 32768 - 21);
  }
  std::puts("test_chip_protocol: ok");
  return 0;
}
