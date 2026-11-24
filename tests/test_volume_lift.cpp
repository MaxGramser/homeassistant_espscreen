// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_volume_lift.cpp -o /tmp/test_volume_lift && /tmp/test_volume_lift
// A sound louder than the screen (volume_lift.h): a call's ring and a plugin's alarm lift the speaker, and the screen's
// own volume comes back when the last one comes down, whatever order they come and go in; a lift never lowers the
// speaker, a person's change while it is up is kept, and an update takes every lift down.
#include "../components/smart_display/volume_lift.h"
#include <cassert>
#include <cmath>
#include <cstdio>

using volume_lift::Lifts;

struct Speaker {
  float volume = 0.5f;
  int sets = 0;
};

static Lifts bound(Speaker &s) {
  Lifts l;
  l.bind([&s]() { return s.volume; }, [&s](float v) { s.volume = v; ++s.sets; });
  return l;
}
static bool near(float a, float b) { return std::fabs(a - b) < 1e-4f; }

int main() {
  constexpr uintptr_t RING = 1, ALARM = 0x3fc90000, OTHER = 0x3fc90100;
  {  // Unbound (a board without a speaker): every lift says no.
    Lifts l;
    assert(!l.lift(RING, 1.0f));
    l.drop(RING);
    assert(!l.any());
  }
  {  // One lift up and down: the screen's volume comes back.
    Speaker s;
    Lifts l = bound(s);
    assert(l.lift(ALARM, 0.9f) && near(s.volume, 0.9f));
    assert(l.lift(ALARM, 0.8f) && near(s.volume, 0.8f));  // again: another level of the same lift
    l.drop(ALARM);
    assert(near(s.volume, 0.5f) && !l.any());
    l.drop(ALARM);  // a second restore changes nothing
    assert(near(s.volume, 0.5f));
  }
  {  // Never quieter: a screen turned up stays up, and nothing is written.
    Speaker s;
    s.volume = 0.95f;
    Lifts l = bound(s);
    assert(l.lift(ALARM, 0.6f) && near(s.volume, 0.95f) && s.sets == 0);
    l.drop(ALARM);
    assert(near(s.volume, 0.95f) && s.sets == 0);
  }
  {  // An alarm, then a call rings, then the alarm stops, then the call: the old volume comes back, never a lift's.
    Speaker s;
    Lifts l = bound(s);
    l.lift(ALARM, 0.8f);
    l.lift(RING, 1.0f);
    assert(near(s.volume, 1.0f));
    l.drop(ALARM);
    assert(near(s.volume, 1.0f));  // the ring still rings at the top
    l.drop(RING);
    assert(near(s.volume, 0.5f));
    // The other order: the ring comes down first and the alarm keeps its own level.
    l.lift(ALARM, 0.8f);
    l.lift(RING, 1.0f);
    l.drop(RING);
    assert(near(s.volume, 0.8f));
    l.drop(ALARM);
    assert(near(s.volume, 0.5f));
  }
  {  // Someone moves the volume while it rings: theirs stays, also after the lift.
    Speaker s;
    Lifts l = bound(s);
    l.lift(ALARM, 0.9f);
    s.volume = 0.3f;  // Home Assistant's slider
    l.drop(ALARM);
    assert(near(s.volume, 0.3f));
    // With two up: the one left keeps lifting over the new volume, and the last puts back the new one.
    l.lift(ALARM, 0.9f);
    l.lift(OTHER, 0.7f);
    s.volume = 0.4f;
    l.drop(OTHER);
    assert(near(s.volume, 0.9f));
    l.drop(ALARM);
    assert(near(s.volume, 0.4f));
  }
  {  // An update takes every lift down at once; at most MOST lifts are up.
    Speaker s;
    Lifts l = bound(s);
    for (uintptr_t i = 1; i <= Lifts::MOST; ++i) assert(l.lift(i, 0.6f + 0.05f * i));
    assert(!l.lift(99, 1.0f));
    l.drop_all();
    assert(near(s.volume, 0.5f) && !l.any());
  }
  {  // A plugin asks in the screen's own volume: the media player's 0 to 100 % on the DAC.
    volume_lift::low() = 0.2f;
    volume_lift::high() = 0.8f;
    assert(near(volume_lift::on_dac(0.0f), 0.2f) && near(volume_lift::on_dac(1.0f), 0.8f));
    assert(near(volume_lift::on_dac(0.5f), 0.5f) && near(volume_lift::on_dac(2.0f), 0.8f));
  }
  std::puts("volume_lift: ok");
  return 0;
}
