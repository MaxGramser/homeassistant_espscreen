// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_pressure.cpp -o /tmp/test_pressure && /tmp/test_pressure
#include "../components/smart_display/pressure.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>

using namespace pressure;

static void tick_until(Governor &g, uint32_t from, uint32_t to) {
  for (uint32_t t = from; t <= to; t += 250) g.tick(t);
}

// The glass, the voice and the doorbell are never squeezed, whatever the pressure and the finger.
static void test_never_squeezed() {
  Governor g;
  g.touching(true, true, 100);
  for (uint32_t t = 1000; t < 20000; t += 3000) g.signal(GLASS_MISS, t);
  assert(g.step() == MOST);
  for (Work w : {GLASS, VOICE, DOORBELL}) assert(g.level(w) == 0);
}

// From the bottom of the order up: the background, sensing and the camera first, then the camera further and the
// live tiles, then the tiles further.
static void test_steps_in_order() {
  Governor g;
  g.signal(SLOW_LOOP, 1000);
  assert(g.step() == 1 && g.level(BACKGROUND) == 1 && g.level(SENSING) == 1 && g.level(OWN_CAMERA) == 1 &&
         g.level(LIVE_TILES) == 0);
  g.signal(GLASS_MISS, 4000);
  assert(g.step() == 2 && g.level(OWN_CAMERA) == 2 && g.level(LIVE_TILES) == 1);
  g.signal(SLOW_LOOP, 7000);
  assert(g.step() == 3 && g.level(LIVE_TILES) == 2 && g.cause() == SLOW_LOOP);
  g.signal(SLOW_LOOP, 10000);
  assert(g.step() == MOST);
}

// A burst of signs within ESCALATE_GAP_MS is one step (twenty held-up loops in half a second).
static void test_burst_is_one_sign() {
  Governor g;
  for (uint32_t t = 1000; t < 1400; t += 20) g.signal(SLOW_LOOP, t);
  assert(g.step() == 1 && g.signs(SLOW_LOOP) == 20);
}

// The wake word falling behind takes the live tiles at once (FLOOR), a burst of its resets as one sign, and once the
// screen rested down a step a reset brings it back there; the slow climb stays the others'.
static void test_wake_word_takes_the_tiles() {
  Governor g;
  for (uint32_t t = 1000; t < 1400; t += 20) g.signal(WAKE_WORD_RESET, t);
  assert(g.step() == 2 && g.level(LIVE_TILES) == 1 && g.level(OWN_CAMERA) == 2 && g.cause() == WAKE_WORD_RESET);
  tick_until(g, 1400, 1400 + REST_MS);
  assert(g.step() == 1 && g.level(LIVE_TILES) == 0);
  g.signal(WAKE_WORD_RESET, 70000);  // a minute after the last
  assert(g.step() == 2 && g.level(LIVE_TILES) == 1);
  g.signal(WAKE_WORD_RESET, 75000);  // within the window: on up, as any sign
  assert(g.step() == 3 && g.level(LIVE_TILES) == 2);
  for (Work w : {GLASS, VOICE, DOORBELL}) assert(g.level(w) == 0);
}

// Back down one step every REST_MS without a sign, the live tiles first; a sign meanwhile holds the step.
static void test_rest() {
  Governor g;
  g.signal(GLASS_MISS, 1000);
  g.signal(GLASS_MISS, 4000);
  g.signal(GLASS_MISS, 7000);
  tick_until(g, 7000, 7000 + REST_MS - 250);
  assert(g.step() == 3);
  g.tick(7000 + REST_MS);
  assert(g.step() == 2 && g.level(LIVE_TILES) == 1 && g.level(OWN_CAMERA) == 2);
  g.signal(GLASS_MISS, 7000 + REST_MS + 1000);  // within the window of the last sign: up again, and the rest starts over
  assert(g.step() == 3);
  tick_until(g, 18000, 18000 + REST_MS);
  assert(g.step() == 2);
  tick_until(g, 28000, 28000 + REST_MS);
  assert(g.step() == 1 && g.level(LIVE_TILES) == 0);
  // A sign outside the window of the last one, while still on a step, does not climb: it holds the first step.
  g.signal(SLOW_LOOP, 39000);
  assert(g.step() == 1);
  tick_until(g, 39000, 39000 + 2 * REST_MS);
  assert(g.step() == 0 && g.level(BACKGROUND) == 0);
  // A sign long after the last starts at the first step.
  g.signal(SLOW_LOOP, 200000);
  assert(g.step() == 1);
}

// The finger: down steps the camera, sensing and the background down; a drag the live tiles too; a second after it
// lets go, all back at once.
static void test_finger() {
  Governor g;
  g.touching(true, false, 1000);
  assert(g.level(OWN_CAMERA) == 1 && g.level(SENSING) == 1 && g.level(BACKGROUND) == 1 && g.level(LIVE_TILES) == 0);
  g.touching(true, true, 1200);
  assert(g.level(LIVE_TILES) == 1);
  g.touching(false, false, 2000);
  g.tick(2500);
  assert(g.level(LIVE_TILES) == 1 && g.touched());
  g.tick(2000 + LET_GO_MS);
  assert(g.level(LIVE_TILES) == 0 && g.level(OWN_CAMERA) == 0 && !g.touched());
  // With pressure besides, the higher of the two.
  g.signal(GLASS_MISS, 5000);
  g.signal(GLASS_MISS, 8000);
  g.touching(true, false, 8100);
  assert(g.level(OWN_CAMERA) == 2 && g.level(LIVE_TILES) == 1);
}

// While someone hears the microphone, the live tiles stay at a quarter whatever the steps and the finger say; the
// camera, sensing and the background follow the steps as before, and the tiles are free again once nobody hears.
static void test_heard() {
  Governor g;
  g.heard(true);
  // One live tile crowds nothing: the heard rule needs two or more.
  live_tiles.store(1);
  assert(g.level(LIVE_TILES) == 0 && g.level(OWN_CAMERA) == 0);
  live_tiles.store(2);
  assert(g.level(LIVE_TILES) == 2 && g.level(OWN_CAMERA) == 0 && g.level(SENSING) == 0 && g.level(BACKGROUND) == 0);
  for (Work w : {GLASS, VOICE, DOORBELL}) assert(g.level(w) == 0);
  g.signal(SLOW_LOOP, 1000);
  // The screen's own camera is the conversation: whole frames while someone hears it, whatever the step or a finger.
  assert(g.step() == 1 && g.level(LIVE_TILES) == 2 && g.level(OWN_CAMERA) == 0);
  g.touching(true, false, 1100);
  assert(g.level(OWN_CAMERA) == 0 && g.level(SENSING) == 1);
  g.touching(false, false, 1200);
  g.heard(false);
  assert(g.level(LIVE_TILES) == 0 && g.level(OWN_CAMERA) == 1);
}

int main() {
  test_never_squeezed();
  test_steps_in_order();
  test_burst_is_one_sign();
  test_wake_word_takes_the_tiles();
  test_rest();
  test_finger();
  test_heard();
  std::puts("PASS: the governor's order, its steps, a burst as one sign, the rest, the wake word's floor, the finger and "
            "someone hearing the microphone");
  return 0;
}
