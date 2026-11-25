// The buzzer as a sound output (sound_out.h): the pulse, the block of widths the DMA hands it, and the samples in
// between.
//
// Two DMA channels take turns: each hands the PWM one block of pulse widths, a width per pulse, and starts the other
// when it is through. The interrupt of the one that finished fills its block again, so the pulse never waits for the
// program. Everything the interrupt reads is written by the main loop with that interrupt held off for a moment.
#include "sound_out.h"

#include "hardware/clocks.h"
#include "hardware/dma.h"
#include "hardware/gpio.h"
#include "hardware/irq.h"
#include "hardware/pwm.h"
#include "pico/stdlib.h"

namespace sound_out {
namespace {

constexpr uint BUZZER_PIN = 19;
// The pulse counts 0 to TOP: 125 MHz / 1953 is 64 004 pulses a second, far above what anyone hears, with eleven bits
// of width.
constexpr uint32_t TOP = 1952;
constexpr int32_t MID = (TOP + 1) / 2;
constexpr uint32_t BLOCK = 256;  // widths per block: 4 ms
constexpr uint32_t MASK = ROOM - 1;
// The middle comes up and goes down over this many pulses (16 ms), along a curve without a corner.
constexpr uint32_t RAMP = 1024;
// A sample this near to zero is quiet, and this many quiet pulses (a quarter of a second) let the middle go.
constexpr int32_t QUIET = 48;
constexpr uint32_t HOLD = 16000;
// A sound that is stopped fades over this many pulses (4 ms) instead of breaking off.
constexpr int32_t FADE = 256;

enum Middle : uint8_t { DOWN, RISING, UP, FALLING };

uint32_t block[2][BLOCK];
uint16_t curve[RAMP + 1];
int16_t ring[ROOM];
int channel[2];
uint slice, shift;

// The ring: the main loop writes at head, the interrupt reads at tail.
volatile uint32_t head = 0, tail = 0;
volatile uint32_t taken_ = 0, played_ = 0, dry_ = 0;
volatile bool open_ = false, ending_ = false, cut_ = false;
volatile uint32_t step = 0x4000;  // input samples per pulse, 16.16
volatile int32_t gain = 0;        // a sample times this, shifted down 19, is its width around the middle

// The interrupt's own.
uint32_t phase = 0, ramp = 0, quiet = HOLD;
int32_t s0 = 0, s1 = 0, rest = 0, fade = FADE;
Middle middle = DOWN;
bool was_dry = false;

inline void next_sample() {
  s0 = s1;
  if (tail != head) {
    s1 = ring[tail & MASK];
    tail = tail + 1;
    played_ = played_ + 1;
    was_dry = false;
    return;
  }
  s1 = 0;
  if (ending_) {
    ending_ = false;
    open_ = false;
  } else if (open_ && !was_dry) {
    was_dry = true;
    dry_ = dry_ + 1;
  }
}

void __time_critical_func(fill)(uint32_t *out) {
  for (uint32_t i = 0; i < BLOCK; ++i) {
    int32_t sample = 0;
    if (middle == RISING) {
      // The sound waits while the middle comes up.
      if (++ramp >= RAMP) middle = UP;
    } else {
      phase += step;
      while (phase >= 0x10000) {
        phase -= 0x10000;
        next_sample();
      }
      sample = s0 + (((s1 - s0) * static_cast<int32_t>(phase >> 1)) >> 15);
      if (cut_) {
        sample = (sample * fade) >> 8;
        if (--fade <= 0) {
          // Faded out: what is held goes, and the sound is over.
          played_ = played_ + (head - tail);
          tail = head;
          s0 = s1 = 0;
          fade = FADE;
          cut_ = false;
          ending_ = false;
          open_ = false;
        }
      }
      if (s1 > QUIET || s1 < -QUIET) quiet = 0;
      else if (quiet < HOLD) ++quiet;
      if (middle == DOWN) {
        if (quiet == 0) middle = RISING;
        sample = 0;
      } else if (middle == UP) {
        if (quiet >= HOLD) middle = FALLING;
      } else {  // FALLING
        if (quiet == 0) middle = RISING;
        else if (ramp == 0) middle = DOWN;
        else --ramp;
      }
    }
    if (middle == DOWN) {
      rest = 0;
      out[i] = 0;
      continue;
    }
    // The sample as a width, with what the last width left out carried into this one.
    const int32_t wide = sample * gain + rest;
    const int32_t width = wide >> 19;
    rest = wide - (width << 19);
    int32_t level = static_cast<int32_t>(curve[ramp]) + width;
    if (level < 0) level = 0;
    else if (level > static_cast<int32_t>(TOP)) level = TOP;
    out[i] = static_cast<uint32_t>(level) << shift;
  }
}

void __isr __time_critical_func(block_done)() {
  for (int i = 0; i < 2; ++i) {
    if (!dma_channel_get_irq0_status(channel[i])) continue;
    dma_channel_acknowledge_irq0(channel[i]);
    // Back to the start of its block; the other channel starts it when it is through.
    dma_channel_set_read_addr(channel[i], block[i], false);
    fill(block[i]);
  }
}

// Holds the interrupt off while the main loop changes what it reads; the pulse goes on from the other block.
struct Hold {
  Hold() { irq_set_enabled(DMA_IRQ_0, false); }
  ~Hold() { irq_set_enabled(DMA_IRQ_0, true); }
};

}  // namespace

void setup() {
  // 3t^2 - 2t^3: level at both ends, so the middle starts and stops moving without a click.
  for (uint32_t i = 0; i <= RAMP; ++i) {
    const uint64_t t = (static_cast<uint64_t>(i) << 16) / RAMP;
    const uint64_t smooth = (3 * t * t - ((2 * t * t * t) >> 16)) >> 16;
    curve[i] = static_cast<uint16_t>((smooth * MID) >> 16);
  }
  volume(32768);

  gpio_set_function(BUZZER_PIN, GPIO_FUNC_PWM);
  slice = pwm_gpio_to_slice_num(BUZZER_PIN);
  shift = pwm_gpio_to_channel(BUZZER_PIN) == PWM_CHAN_B ? 16 : 0;
  pwm_config pulse = pwm_get_default_config();
  pwm_config_set_clkdiv_int(&pulse, 1);
  pwm_config_set_wrap(&pulse, TOP);
  pwm_init(slice, &pulse, false);
  pwm_set_both_levels(slice, 0, 0);

  for (int i = 0; i < 2; ++i) channel[i] = dma_claim_unused_channel(true);
  for (int i = 0; i < 2; ++i) {
    dma_channel_config c = dma_channel_get_default_config(channel[i]);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
    channel_config_set_read_increment(&c, true);
    channel_config_set_write_increment(&c, false);
    channel_config_set_dreq(&c, pwm_get_dreq(slice));
    channel_config_set_chain_to(&c, channel[1 - i]);
    dma_channel_configure(channel[i], &c, &pwm_hw->slice[slice].cc, block[i], BLOCK, false);
    dma_channel_set_irq0_enabled(channel[i], true);
  }
  irq_set_exclusive_handler(DMA_IRQ_0, block_done);
  // Below the serial line's interrupt, which has 32 bytes of room and a byte every 11 microseconds.
  irq_set_priority(DMA_IRQ_0, PICO_LOWEST_IRQ_PRIORITY);
  irq_set_enabled(DMA_IRQ_0, true);
  pwm_set_enabled(slice, true);
  dma_channel_start(channel[0]);
}

void begin(uint32_t rate) {
  if (open_ || tail != head) {
    end(true);
    // The fade is 4 ms and a block another 4.
    for (int i = 0; i < 40 && (cut_ || tail != head); ++i) sleep_ms(1);
  }
  if (rate < 4000) rate = 4000;
  if (rate > 48000) rate = 48000;
  const uint32_t pulses = clock_get_hz(clk_sys) / (TOP + 1);
  Hold hold;
  step = static_cast<uint32_t>((static_cast<uint64_t>(rate) << 16) / pulses);
  head = tail = 0;
  taken_ = played_ = 0;
  was_dry = true;  // nothing has come yet: that is no gap
  cut_ = ending_ = false;
  open_ = true;
}

uint32_t push(const uint8_t *bytes, uint32_t samples) {
  if (!open_ || ending_ || cut_) return 0;
  const uint32_t room = ROOM - (head - tail);
  if (samples > room) samples = room;
  uint32_t at = head;
  for (uint32_t i = 0; i < samples; ++i, ++at)
    ring[at & MASK] = static_cast<int16_t>(bytes[2 * i] | (bytes[2 * i + 1] << 8));
  head = at;
  taken_ = taken_ + samples;
  return samples;
}

void end(bool now) {
  Hold hold;
  if (!open_) return;
  if (now) cut_ = true;
  else ending_ = true;
}

void volume(uint16_t value) {
  const uint32_t v = value > 32768 ? 32768 : value;
  gain = static_cast<int32_t>((v * static_cast<uint32_t>(MID)) >> 11);
}

bool open() { return open_; }
bool ending() { return open_ && (ending_ || cut_); }
uint32_t taken() { return taken_; }
uint32_t played() { return played_; }
uint32_t dry() { return dry_; }

}  // namespace sound_out
