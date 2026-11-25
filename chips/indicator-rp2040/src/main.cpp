// Tessera's firmware for the second chip of a SenseCAP Indicator, its RP2040 (docs/SECOND_CHIP.md).
//
// The chip drives the buzzer. The screen (the ESP32-S3) sends it sound over their serial line and this plays it
// (sound_out.h), so the buzzer does what a speaker does on other boards: a doorbell's chime, an alert's sound, a
// plugin's alarm. The same frames come in over the USB port, where a computer asks which firmware this is and can play
// a sound without the screen; Tessera's New screen does that after it wrote this file to the chip.
//
// Whoever began the sound that plays gets its STATUS, 50 times a second, on the line it came in on. Nothing is sent
// unasked: Seeed's own firmware for the ESP32-S3 would not know what to do with it.
//
// Opening the USB port at 1200 baud restarts the chip as the drive RPI-RP2 (the Pico SDK's doing), which is how a
// newer file gets on without the button inside the case.
#include <cstdio>

#include "chip_protocol.h"
#include "hardware/irq.h"
#include "hardware/uart.h"
#include "hardware/watchdog.h"
#include "pico/binary_info.h"
#include "pico/rand.h"
#include "pico/stdio_usb.h"
#include "pico/stdlib.h"
#include "sound_out.h"

namespace {

using namespace chip_protocol;

// The serial line to the ESP32-S3 (its GPIO19 and GPIO20), as Seeed wired it.
constexpr uint LINE_TX = 16, LINE_RX = 17;
constexpr uint32_t STATUS_EVERY_US = 20000;

// What came over the serial line and waits for the main loop: 8 KB, 90 ms of it at full speed.
constexpr uint32_t WAITING = 8192;
uint8_t waiting[WAITING];
volatile uint32_t wait_head = 0, wait_tail = 0;

void __isr line_bytes() {
  while (uart_is_readable(uart0)) {
    const uint8_t byte = static_cast<uint8_t>(uart_getc(uart0));
    if (wait_head - wait_tail < WAITING) {
      waiting[wait_head % WAITING] = byte;
      wait_head = wait_head + 1;
    }
  }
}

struct Line {
  Reader reader;
  void (*write)(const uint8_t *, size_t);
};

void line_write(const uint8_t *bytes, size_t length) { uart_write_blocking(uart0, bytes, length); }
void usb_write(const uint8_t *bytes, size_t length) {
  if (!stdio_usb_connected()) return;
  stdio_put_string(reinterpret_cast<const char *>(bytes), static_cast<int>(length), false, false);
  stdio_flush();
}

// Drawn once at the start: whoever asks twice and gets another number knows the chip restarted in between, and that
// it forgot the volume it was told.
uint16_t started = 0;

Line serial{{}, line_write}, usb{{}, usb_write};
// Whose sound plays, and its number.
Line *owner = nullptr;
uint8_t stream = 0;
bool told_idle = true;

void send(Line &to, uint8_t type, const uint8_t *payload, size_t length) {
  static uint8_t wire[WIRE_MOST];
  const size_t n = frame(type, payload, length, wire);
  if (n) to.write(wire, n);
}

void send_status() {
  if (owner == nullptr) return;
  uint8_t p[10];
  p[0] = stream;
  p[1] = !sound_out::open() ? STATE_IDLE : sound_out::ending() ? STATE_ENDING : STATE_PLAYING;
  put32(p + 2, sound_out::taken());
  put32(p + 6, sound_out::played());
  send(*owner, STATUS, p, sizeof p);
  told_idle = p[1] == STATE_IDLE;
}

// The chip's own sound, for whoever wants to hear that the buzzer works (TRY): two notes that die away, the higher
// first, at the two pitches this buzzer is loudest (3020 and 2540 Hz). Each is a resonator, y = 2 cos(w) y1 - y2, which
// needs no sine at run time.
void play_own_sound() {
  constexpr uint32_t RATE = 16000, NOTE = 7200;  // 0.45 s a note
  // 2 cos(w) and sin(w) in 2.14 fixed point, w = 2 pi f / RATE.
  constexpr int32_t NOTES[2][2] = {{12302, 15186}, {17775, 13764}};
  static uint8_t some[512];
  sound_out::begin(RATE);
  for (const auto &note : NOTES) {
    int32_t y1 = note[1], y2 = 0, loud = 30000;
    for (uint32_t i = 0; i < NOTE;) {
      uint32_t n = 0;
      for (; n < sizeof some / 2 && i < NOTE; ++n, ++i) {
        const int32_t sample = (y1 * loud) >> 14;
        put16(some + 2 * n, static_cast<uint16_t>(static_cast<int16_t>(sample > 32767 ? 32767 : sample < -32767 ? -32767 : sample)));
        const int32_t y0 = ((note[0] * y1) >> 14) - y2;
        y2 = y1;
        y1 = y0;
        loud -= loud >> 11;
      }
      sound_out::push(some, n);
    }
  }
  sound_out::end(false);
}

void handle(Line &from) {
  const Reader &r = from.reader;
  const uint8_t *p = r.payload();
  switch (r.type()) {
    case HELLO: {
      uint8_t back[9] = {VERSION, CHIP_VERSION_MAJOR, CHIP_VERSION_MINOR, CHIP_VERSION_PATCH, WHAT_SOUND, 0, 0, 0, 0};
      put16(back + 5, static_cast<uint16_t>(sound_out::ROOM > 0xFFFF ? 0xFFFF : sound_out::ROOM));
      put16(back + 7, started);
      send(from, HELLO_BACK, back, sizeof back);
      break;
    }
    case BEGIN:
      if (r.size() < 3) break;
      stream = p[0];
      owner = &from;
      sound_out::begin(u16(p + 1));
      send_status();
      break;
    case AUDIO:
      if (r.size() < 3 || owner != &from || p[0] != stream) break;
      sound_out::push(p + 1, static_cast<uint32_t>((r.size() - 1) / 2));
      break;
    case END:
      if (r.size() < 2 || owner != &from || p[0] != stream) break;
      sound_out::end(p[1] != 0);
      break;
    case VOLUME:
      if (r.size() >= 2) sound_out::volume(u16(p));
      break;
    case TRY:
      stream = 0xFF;
      owner = &from;
      play_own_sound();
      send_status();
      break;
    default:
      break;
  }
}

}  // namespace

int main() {
  bi_decl(bi_program_description("Tessera: the buzzer of a SenseCAP Indicator as a sound output"));
  bi_decl(bi_1pin_with_name(19, "Buzzer"));
  bi_decl(bi_2pins_with_func(LINE_TX, LINE_RX, GPIO_FUNC_UART));

  stdio_usb_init();
  stdio_set_translate_crlf(&stdio_usb, false);

  uart_init(uart0, BAUD);
  gpio_set_function(LINE_TX, GPIO_FUNC_UART);
  gpio_set_function(LINE_RX, GPIO_FUNC_UART);
  uart_set_format(uart0, 8, 1, UART_PARITY_NONE);
  uart_set_hw_flow(uart0, false, false);
  uart_set_fifo_enabled(uart0, true);
  irq_set_exclusive_handler(UART0_IRQ, line_bytes);
  irq_set_priority(UART0_IRQ, PICO_HIGHEST_IRQ_PRIORITY);
  irq_set_enabled(UART0_IRQ, true);
  uart_set_irq_enables(uart0, true, false);

  started = static_cast<uint16_t>(get_rand_32());
  sound_out::setup();
  // A program that hangs must not leave the buzzer's coil switched on.
  watchdog_enable(2000, true);

  absolute_time_t next_status = make_timeout_time_us(STATUS_EVERY_US);
  for (;;) {
    watchdog_update();
    while (wait_tail != wait_head) {
      const uint8_t byte = waiting[wait_tail % WAITING];
      wait_tail = wait_tail + 1;
      if (serial.reader.feed(byte)) handle(serial);
    }
    static char some[256];
    const int got = stdio_get_until(some, sizeof some, get_absolute_time());
    for (int i = 0; i < got; ++i)
      if (usb.reader.feed(static_cast<uint8_t>(some[i]))) handle(usb);
    if (time_reached(next_status)) {
      next_status = make_timeout_time_us(STATUS_EVERY_US);
      // While a sound is open, and once more when it is over.
      if (sound_out::open() || !told_idle) send_status();
    }
  }
}
