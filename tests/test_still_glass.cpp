// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_still_glass.cpp -o /tmp/test_still_glass && /tmp/test_still_glass
// A still glass's sums (still_glass.h): how a time that counts down is shown where a change is a print, and how often
// a picture is fetched again.
#include "../components/smart_display/still_glass.h"
#include <cassert>
#include <cstdio>

using namespace still_glass;

static void a_countdown_in_steps() {
  // Whole minutes while more than one is left, rounded up: the glass never says less than there is.
  assert(counted(300) == 300 && counted(299) == 300 && counted(241) == 300 && counted(240) == 240);
  assert(counted(3601) == 3660 && counted(61) == 120);
  // Inside the last minute, ten seconds at a time.
  assert(counted(60) == 60 && counted(59) == 60 && counted(51) == 60 && counted(50) == 50 && counted(41) == 50);
  assert(counted(10) == 10 && counted(9) == 10 && counted(1) == 10 && counted(0) == 0);
  // It only ever goes down as the time does, and changes at most once in ten seconds.
  uint32_t last = counted(600), changes = 0;
  for (int s = 600; s >= 0; --s) {
    const uint32_t now = counted(static_cast<uint32_t>(s));
    assert(now <= last && now >= static_cast<uint32_t>(s));
    if (now != last) ++changes;
    last = now;
  }
  assert(changes == 9 + 6);  // nine minutes fall away, then six steps of ten seconds
}

static void a_picture_every_ten_seconds_at_most() {
  assert(picture_every(4000) == 10000 && picture_every(10000) == 10000 && picture_every(15000) == 15000);
  // What a lit glass already takes more slowly keeps its own pace.
  assert(picture_every(300000) == 300000);
}

int main() {
  a_countdown_in_steps();
  a_picture_every_ten_seconds_at_most();
  std::puts("still_glass: ok");
  return 0;
}
