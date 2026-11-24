// moved.h: whether the board itself moved, from its accelerometer and gyroscope (Wake when moved).
// Readings ten times a second, as the board file reads them, in g and degrees a second as ESPHome's `motion` reports.
// The shapes below are made, after the LSM6DS3TR-C's datasheet noise. Recordings of a reTerminal D1001 (t ms, ax, ay,
// az g, gx, gy, gz degrees a second) go in tests/data/moved_*.csv and are replayed when present; none are measured yet.
#include "components/smart_display/moved.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
using namespace moved;

namespace {

struct Reading {
  float a[3];
  float g[3];
};

// Feeds one reading of all six axes; true when the detector said the board moved.
bool feed(Detector &d, uint32_t t, const Reading &r) {
  bool said = false;
  for (uint8_t i = 0; i < 3; i++) said |= d.feel(ACCELERATION, i, r.a[i], t);
  for (uint8_t i = 0; i < 3; i++) said |= d.feel(TURNING, i, r.g[i], t);
  return said;
}

// A cheap repeatable noise in [-1, 1].
float noise(uint32_t &seed) {
  seed = seed * 1664525u + 1013904223u;
  return ((seed >> 8) & 0xFFFF) / 32767.5f - 1.0f;
}

// Lying on a table, tilted back, with a gyroscope that reads a few degrees a second at rest and drifts.
Reading still(uint32_t t, uint32_t &seed) {
  float drift = 0.5f * std::sin(t / 20000.0f);
  return Reading{{0.17f + 0.004f * noise(seed), -0.02f + 0.004f * noise(seed), 0.985f + 0.004f * noise(seed)},
                 {-3.2f + drift + 0.8f * noise(seed), 1.9f + 0.8f * noise(seed), 0.6f + 0.8f * noise(seed)}};
}

// Count the times the board "moved" over `ms` milliseconds of readings made by `make`.
template<typename F> int count(Detector &d, uint32_t from, uint32_t ms, F make) {
  int n = 0;
  for (uint32_t t = from; t < from + ms; t += 100)
    if (feed(d, t, make(t))) n++;
  return n;
}

// Replays a recording, if there is one; returns how many times it said moved, or -1 without the file.
int replay(const char *path) {
  FILE *f = std::fopen(path, "r");
  if (!f) return -1;
  Detector d;
  char line[256];
  int n = 0;
  while (std::fgets(line, sizeof line, f)) {
    unsigned t;
    Reading r;
    if (std::sscanf(line, "%u,%f,%f,%f,%f,%f,%f", &t, &r.a[0], &r.a[1], &r.a[2], &r.g[0], &r.g[1], &r.g[2]) == 7 &&
        feed(d, t, r))
      n++;
  }
  std::fclose(f);
  return n;
}

}  // namespace

int main() {
  uint32_t seed = 7;

  // Lying still for ten minutes, gyroscope offset and drift included: never moved.
  {
    Detector d;
    assert(count(d, 0, 600000, [&](uint32_t t) { return still(t, seed); }) == 0);
  }

  // Picked up: a turn of 30 degrees a second about x for half a second, and the hand's lift of a tenth of a g.
  {
    Detector d;
    assert(count(d, 0, 10000, [&](uint32_t t) { return still(t, seed); }) == 0);
    int n = count(d, 10000, 600, [&](uint32_t t) {
      Reading r = still(t, seed);
      r.g[0] += 30.0f;
      r.a[2] += 0.1f;
      return r;
    });
    assert(n == 1 && "one pick-up is one wake");
  }

  // A slow tilt: 10 degrees over two seconds, 5 degrees a second, too slow for the gyroscope's threshold alone; the
  // accelerometer sees gravity move across its axes.
  {
    Detector d;
    count(d, 0, 10000, [&](uint32_t t) { return still(t, seed); });
    const float pi = 3.14159265f;
    int n = count(d, 10000, 2000, [&](uint32_t t) {
      float deg = 10.0f * (t - 10000) / 2000.0f;
      float rad = (10.0f + deg) * pi / 180.0f;
      Reading r = still(t, seed);
      r.a[0] = std::sin(rad);
      r.a[2] = std::cos(rad);
      r.g[1] += 4.0f;  // under TURNING_DPS: only the accelerometer may say it
      return r;
    });
    assert(n >= 1);
  }

  // A bump of the table: one reading 0.08 g off, then still. A knock is a wake, by design.
  {
    Detector d;
    count(d, 0, 10000, [&](uint32_t t) { return still(t, seed); });
    Reading r = still(10000, seed);
    r.a[2] += 0.08f;
    assert(feed(d, 10000, r));
    assert(d.last_kind() == ACCELERATION && d.last_axis() == 2);
    assert(count(d, 10100, 20000, [&](uint32_t t) { return still(t, seed); }) == 0);
  }

  // Being carried around for ten seconds: once every REPEAT_MS at most.
  {
    Detector d;
    count(d, 0, 5000, [&](uint32_t t) { return still(t, seed); });
    int n = count(d, 5000, 10000, [&](uint32_t t) {
      Reading r = still(t, seed);
      r.g[2] += 40.0f * std::sin(t / 300.0f);
      return r;
    });
    assert(n >= 4 && n <= (int) (10000 / REPEAT_MS) + 1);
  }

  // The old rule's mistake: half a g between two readings is a lot of movement, not a little.
  {
    Detector d;
    count(d, 0, 5000, [&](uint32_t t) { return still(t, seed); });
    Reading r = still(5000, seed);
    r.a[0] += 0.5f;
    assert(feed(d, 5000, r));
  }

  // A missing reading (NAN) and a wrapping millisecond counter are no movement.
  {
    Detector d;
    assert(!d.feel(TURNING, 0, NAN, 0));
    uint32_t t0 = UINT32_MAX - 3000;
    for (uint32_t i = 0; i < 100; i++) assert(!feed(d, t0 + i * 100, still(i * 100, seed)));
  }

  // Recordings of a real reTerminal D1001: lying still says nothing, each pick-up says it moved.
  int rest = replay("tests/data/moved_d1001_rest.csv");
  if (rest >= 0) assert(rest == 0);
  int lifts = replay("tests/data/moved_d1001_pickups.csv");
  if (lifts >= 0) assert(lifts >= 1);
  std::printf("moved ok (recordings: rest %d, pick-ups %d)\n", rest, lifts);
}
