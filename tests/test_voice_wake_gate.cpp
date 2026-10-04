#include "../components/smart_display/voice_wake_gate.h"
#include <cassert>
using voice_wake::Gate;

int main() {
  Gate g;
  assert(g.step(1000, false, true, true, false, false) == Gate::NONE); // opt-in
  g.configure(true, 0);
  assert(g.step(1001, false, true, true, false, false) == Gate::START_WAKE);
  assert(!g.ready());
  assert(g.step(1010, true, false, true, false, false) == Gate::NONE);
  assert(g.ready());
  g.request(1200); // detector callback, no network session before the handoff
  assert(g.step(1201, true, false, true, false, false) == Gate::STOP_WAKE);
  assert(g.step(1210, false, false, true, false, false) == Gate::STOP_WAKE);
  assert(g.step(1220, false, true, true, false, false) == Gate::STOP_WAKE);
  assert(g.step(1221, false, true, true, false, false) == Gate::START_VOICE);
  assert(!g.pending());
  assert(g.step(2300, false, false, true, true, false) == Gate::NONE);
  assert(g.step(5000, false, true, false, true, false) == Gate::NONE); // speaking
  assert(g.step(6000, false, true, true, true, false) == Gate::NONE);
  assert(g.step(6999, false, true, true, false, false) == Gate::NONE);
  assert(g.step(7000, false, true, true, false, false) == Gate::START_WAKE);

  // Disabling while ESPHome's start is still queued must not transfer ownership.
  g.configure(false, 0);
  g.request(7100);
  assert(g.step(7100, false, true, true, false, false) == Gate::STOP_WAKE);
  assert(g.step(7110, true, false, true, false, false) == Gate::STOP_WAKE);
  assert(g.step(7120, false, true, true, false, false) == Gate::STOP_WAKE);
  g.cancel();
  assert(g.step(8200, false, true, true, false, false) == Gate::NONE);
  assert(!g.pending());

  // Changing a model releases the detector before starting it with the new choice.
  g.configure(true, 1);
  assert(g.step(8300, false, true, true, false, false) == Gate::START_WAKE);
  g.step(8310, true, false, true, false, false);
  g.configure(true, 2);
  assert(g.step(8400, true, false, true, false, false) == Gate::STOP_WAKE);
  g.step(8410, false, true, true, false, false);
  assert(g.step(9410, false, true, true, false, false) == Gate::START_WAKE);
  g.step(9420, true, false, true, false, false);
  g.request(9500);
  assert(g.step(9501, true, false, true, false, true) == Gate::STOP_WAKE); // mute cancels
  assert(!g.pending());
  g.step(9510, false, true, true, false, true);
  assert(g.step(20000, false, true, true, false, true) == Gate::NONE);

  Gate broken;
  broken.configure(true, 0);
  assert(broken.step(1000, false, true, true, false, false) == Gate::START_WAKE);
  assert(broken.step(4000, false, true, true, false, false) & Gate::FAILED);
  assert(broken.failed());
  assert(broken.step(10000, false, true, true, false, false) == Gate::NONE); // no retry loop
  broken.request(11000); // manual Start still works if the detector failed
  assert(broken.step(11000, false, true, true, false, false) == Gate::START_VOICE);

  Gate stuck;
  stuck.request(1000);
  assert(stuck.step(6000, true, false, true, false, false) & Gate::FAILED);
  assert(!stuck.pending());
}
