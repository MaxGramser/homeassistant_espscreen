#pragma once
// The words a screen and a board's second chip speak over their serial line (docs/SECOND_CHIP.md): the frames, their
// check and what each one means. The SenseCAP Indicator's RP2040 is the first such chip: it drives the buzzer, and the
// ESP32-S3 sends it the sound to play.
//
// Both ends build this one file: the screen's side (chip_link.cpp, ESPHome) and the chip's own firmware
// (chips/indicator-rp2040, the Pico SDK). The same frames travel over the chip's USB port, which is how a computer
// asks which firmware it runs and plays a sound on it without the screen.
//
// A frame is a type, its payload and a CRC-16 of the two, COBS-encoded and closed with a zero byte, so a zero never
// occurs inside one and a reader that lost its place finds the next frame at the next zero. Seeed's factory firmware
// frames its own packets the same way (PacketSerial) without the check and with types from 0xA0; ours stay below it,
// so the two can never be taken for each other.
//
// What it does not know: the serial port, the sound, or what plays it. tests/test_chip_protocol.cpp proves it.
#include <cstddef>
#include <cstdint>

namespace chip_protocol {

constexpr uint8_t VERSION = 1;
// The line between the two chips: 8N1, no flow control. A sound of 16 kHz is 32 000 bytes a second, a third of it.
constexpr uint32_t BAUD = 921600;
// A frame's type and payload together, at most.
constexpr size_t MOST = 1024;
// The same on the wire: the check, COBS's one byte in 254 and the closing zero.
constexpr size_t WIRE_MOST = MOST + 2 + (MOST + 2) / 254 + 2;
// The samples of sound in one AUDIO frame at most (16 bits each, after the stream's number).
constexpr size_t AUDIO_MOST = (MOST - 2) / 2;

enum Type : uint8_t {
  // To the chip.
  HELLO = 0x01,   // nothing: who are you? The chip answers HELLO_BACK on the line it was asked on.
  BEGIN = 0x10,   // stream u8, rate u16: a sound starts, at this many samples a second; what was left of another goes
  AUDIO = 0x11,   // stream u8, then samples (16 bits, little endian, mono) of the stream that began
  END = 0x12,     // stream u8, now u8: the sound is over. now 0 plays what is buffered first, 1 stops at once
  VOLUME = 0x13,  // gain u16: what every sample is multiplied by, 32768 is as it came, 0 is silence
  TRY = 0x14,     // nothing: the chip plays a short sound of its own, two notes, so someone hears that it works
  // From the chip.
  HELLO_BACK = 0x81,  // protocol u8, major u8, minor u8, patch u8, what u8 (WHAT_*), room u16 (samples it buffers),
                      // start u16: a number the chip drew when it started, so a chip that restarted is told apart
  STATUS = 0x90,      // stream u8, state u8 (STATE_*), taken u32, played u32: samples of the stream, taken in and played
  LOG = 0xF0,         // text, for whoever listens on the USB port
};

// What a chip can do, a bit each, in its HELLO_BACK.
constexpr uint8_t WHAT_SOUND = 0x01;

enum State : uint8_t {
  STATE_IDLE = 0,     // no stream
  STATE_PLAYING = 1,  // a stream is open
  STATE_ENDING = 2,   // END came, and what was buffered still plays
};

// CRC-16/CCITT-FALSE, over the type and the payload.
inline uint16_t crc16(const uint8_t *data, size_t length, uint16_t crc = 0xFFFF) {
  for (size_t i = 0; i < length; ++i) {
    crc ^= static_cast<uint16_t>(data[i]) << 8;
    for (int bit = 0; bit < 8; ++bit) crc = (crc & 0x8000) ? static_cast<uint16_t>((crc << 1) ^ 0x1021) : static_cast<uint16_t>(crc << 1);
  }
  return crc;
}

// COBS, a byte at a time: `out` needs a byte more than it is given, and one more for every 254.
struct CobsWriter {
  uint8_t *out;
  size_t write = 1, code_at = 0;
  uint8_t code = 1;
  void put(uint8_t byte) {
    if (byte == 0) {
      out[code_at] = code;
      code_at = write++;
      code = 1;
      return;
    }
    out[write++] = byte;
    if (++code == 0xFF) {
      out[code_at] = code;
      code_at = write++;
      code = 1;
    }
  }
  // Closes the last run and returns the bytes written, without a closing zero.
  size_t done() {
    out[code_at] = code;
    return write;
  }
};

inline size_t cobs_encode(const uint8_t *in, size_t length, uint8_t *out) {
  CobsWriter w{out};
  for (size_t i = 0; i < length; ++i) w.put(in[i]);
  return w.done();
}

// The reverse, of a frame without its closing zero; `out` may be `in`. Returns the bytes, or 0 for what is no COBS.
inline size_t cobs_decode(const uint8_t *in, size_t length, uint8_t *out) {
  size_t read = 0, write = 0;
  while (read < length) {
    const uint8_t code = in[read++];
    if (code == 0 || read + code - 1 > length) return 0;
    for (uint8_t i = 1; i < code; ++i) out[write++] = in[read++];
    if (code != 0xFF && read < length) out[write++] = 0;
  }
  return write;
}

// A whole frame for the wire, closing zero included: `out` needs WIRE_MOST bytes. Returns its length, or 0 when the
// payload is too long.
inline size_t frame(uint8_t type, const uint8_t *payload, size_t length, uint8_t *out) {
  if (length + 1 > MOST) return 0;
  const uint16_t crc = crc16(payload, length, crc16(&type, 1));
  CobsWriter w{out};
  w.put(type);
  for (size_t i = 0; i < length; ++i) w.put(payload[i]);
  w.put(static_cast<uint8_t>(crc >> 8));
  w.put(static_cast<uint8_t>(crc));
  const size_t wire = w.done();
  out[wire] = 0;
  return wire + 1;
}

// The bytes of a line, one at a time, into frames. feed() says true when a whole, checked frame stands ready; it stays
// until the next byte.
class Reader {
 public:
  bool feed(uint8_t byte) {
    if (byte != 0) {
      if (fill_ < sizeof buffer_) buffer_[fill_++] = byte;
      else lost_ = true;  // longer than any frame of ours: skip to the next zero
      return false;
    }
    const size_t wire = fill_;
    const bool lost = lost_;
    fill_ = 0;
    lost_ = false;
    if (lost || wire < 4) return false;  // a frame holds at least COBS's byte, a type and the check
    const size_t plain = cobs_decode(buffer_, wire, buffer_);
    if (plain < 3 || crc16(buffer_, plain - 2) != static_cast<uint16_t>((buffer_[plain - 2] << 8) | buffer_[plain - 1])) {
      ++bad_;
      return false;
    }
    size_ = plain - 3;
    return true;
  }
  uint8_t type() const { return buffer_[0]; }
  const uint8_t *payload() const { return buffer_ + 1; }
  size_t size() const { return size_; }
  // Frames that came damaged, since the start.
  uint32_t bad() const { return bad_; }

 private:
  uint8_t buffer_[WIRE_MOST];
  size_t fill_ = 0, size_ = 0;
  uint32_t bad_ = 0;
  bool lost_ = false;
};

inline uint16_t u16(const uint8_t *p) { return static_cast<uint16_t>(p[0] | (p[1] << 8)); }
inline uint32_t u32(const uint8_t *p) { return static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) | (static_cast<uint32_t>(p[2]) << 16) | (static_cast<uint32_t>(p[3]) << 24); }
inline void put16(uint8_t *p, uint16_t v) {
  p[0] = static_cast<uint8_t>(v);
  p[1] = static_cast<uint8_t>(v >> 8);
}
inline void put32(uint8_t *p, uint32_t v) {
  put16(p, static_cast<uint16_t>(v));
  put16(p + 2, static_cast<uint16_t>(v >> 16));
}

// How many samples the screen may still send: the chip's room, less what is on its way or waiting there.
constexpr uint32_t may_send(uint32_t room, uint32_t sent, uint32_t played) {
  return sent - played >= room ? 0 : room - (sent - played);
}

}  // namespace chip_protocol
