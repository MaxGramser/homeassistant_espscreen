#pragma once
// The buzzer as a sound output: samples in, the buzzer's pin out (docs/SECOND_CHIP.md, "The sound").
//
// The pin (GPIO19) switches the buzzer's coil, so it has two levels and no volume of its own. This drives it with a
// pulse 64 000 times a second whose width is the sample: the coil evens the pulses out and moves with the sound, as a
// class D amplifier's speaker does. A stream of any rate is brought to that rate here.
//
// A coil that rests in the middle of its swing carries current all the time, so the middle is only held while there
// is sound: it comes up in 16 ms before the first loud sample, slowly enough to be silent, and goes down the same way
// after a quarter of a second of quiet. At rest the pin is low and the buzzer takes nothing.
//
// What it does not know: where the samples come from (main.cpp: the screen's serial line or the USB port).
#include <cstdint>

namespace sound_out {

// The samples it holds at most: two seconds of 16 kHz, so a screen that draws for half a second leaves no gap.
constexpr uint32_t ROOM = 32768;

void setup();
// A new sound at `rate` samples a second. What still played stops, without a click.
void begin(uint32_t rate);
// Samples of the sound that began (16 bits, little endian, as they come off the line). Returns how many it took: all,
// unless a sender ignored the room it was told.
uint32_t push(const uint8_t *bytes, uint32_t samples);
// The sound is over: `now` stops it at once, otherwise what is held plays out first.
void end(bool now);
// What every sample is multiplied by: 32768 is as it came, 0 is silence.
void volume(uint16_t gain);

bool open();      // a sound began and has not ended
bool ending();    // it ended, and what is held still plays
uint32_t taken();   // samples taken in since begin()
uint32_t played();  // samples played (or let go at a stop) since begin()
uint32_t dry();     // times the sound ran out while it was open, since the start

}  // namespace sound_out
