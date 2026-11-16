// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_doorbell_ring.cpp -o /tmp/test_doorbell_ring && /tmp/test_doorbell_ring
// A ring on the glass (components/smart_display/doorbell_ring.h, which module_doorbell.cpp asks): how long it stays, what a
// ring does to the view's chime and sound, and which keys the view has.
#include "../components/smart_display/doorbell_ring.h"
#include <cassert>
#include <cstdio>

using namespace doorbell_ring;

// The op's `t`: a minute without one, and never shorter than ten seconds nor longer than ten minutes.
static void test_timeout() {
  assert(untouched_ms(0) == 60000);
  assert(untouched_ms(45) == 45000);
  assert(untouched_ms(5) == 10000 && untouched_ms(10) == 10000);
  assert(untouched_ms(600) == 600000 && untouched_ms(9999) == 600000);
  assert(TIMEOUT_MIN_S < TIMEOUT_S && TIMEOUT_S < TIMEOUT_MAX_S);
}

// A new ring opens a view with its sound on, off for a quiet ring; it chimes unless its automation said `chime: false`.
static void test_a_new_ring() {
  const Ring loud = ring(false, false, true);
  assert(!loud.again && loud.chime && loud.sets_sound && !loud.muted);
  const Ring quiet = ring(false, true, true);
  assert(quiet.sets_sound && quiet.muted && quiet.chime);
  const Ring silent = ring(false, false, false);
  assert(!silent.chime && silent.sets_sound && !silent.muted);
}

// Ringing again while its view shows: the chime again (unless the automation says none), and the sound stays as the
// person at the screen left it, also when this ring says quiet.
static void test_ringing_again() {
  const Ring again = ring(true, true, true);
  assert(again.again && again.chime && !again.sets_sound);
  assert(!ring(true, false, false).chime);
}

// Door when the ring has one, Talk only where the screen has a microphone, a way to send its voice and the app gave it a
// place to send it to, Sound where it has a speaker.
static void test_keys() {
  const Keys all = keys(true, true, true, true, true);
  assert(all.door && all.talk && all.sound && all.count() == 3);
  assert(!keys(true, false, true, true, true).talk);
  assert(!keys(true, true, false, true, true).talk);
  assert(!keys(true, true, true, false, true).talk);
  const Keys bare = keys(false, false, false, false, false);
  assert(!bare.door && !bare.talk && !bare.sound && bare.count() == 0);
  const Keys sound = keys(false, true, true, false, true);
  assert(!sound.door && !sound.talk && sound.sound && sound.count() == 1);
}

int main() {
  test_timeout();
  test_a_new_ring();
  test_ringing_again();
  test_keys();
  std::puts("doorbell ring: its timeout, its chime and sound, its keys");
  return 0;
}
