#include "screen_text_en.h"
#include "components/smart_display/runtime_model.h"
#include "components/smart_display/screen_input.h"
#include <cassert>

int main() {
  screen_input::TouchGuard guard;
  guard.begin(0); guard.consume();
  assert(!guard.accept(100,1)); assert(!guard.accept_slider(100,1));
  guard.begin(200); assert(guard.accept(300,1));

  // A tile keeps the fingerprint of its last state message, not the message itself.
  auto rev=[](const char *state){ return runtime_tiles::state_revision(state,""); };
  runtime_tiles::Tile t;
  t.entity="light.lamp";
  t.revision=rev("off"); t.begin(100);
  // Nothing is drawn in the first 400 ms, so a command Home Assistant confirms in 350 ms looks instant. A second
  // finger is ignored from the first moment all the same.
  assert(t.waiting(200)); assert(!t.loading(200));
  assert(t.loading(500));
  t.observe(rev("off")); assert(!t.confirmed);
  t.observe(rev("on")); assert(t.confirmed);
  assert(!t.waiting(500)); assert(!t.loading(500));

  // Without a state the wait runs to three seconds, not six.
  t.begin(2000); t.observe(rev("on"));
  assert(t.waiting(4999)); assert(t.loading(2400)); assert(!t.loading(2399));
  assert(!t.waiting(5000)); assert(!t.loading(5000));

  // "It worked" without a new state (a stop on a cover that already stands still) ends the wait 800 ms later.
  t.begin(2000); t.observe(rev("on")); t.answered_at=2600;
  assert(t.waiting(3399)); assert(!t.waiting(3400)); assert(!t.loading(3400));
  t.begin(2000); assert(t.answered_at==0);

  // A tap that opens a card draws no sheet at all, and the clock wrapping around changes nothing.
  t.begin(100,true);
  assert(!t.waiting(200)); assert(!t.loading(1099));
  t.begin(0xFFFFFFF0); t.observe(rev("on"));
  assert(t.waiting(20)); assert(!t.loading(20)); assert(t.loading(0xFFFFFFF0+400));

  // A switch changes state with identical attributes. That still confirms at once, and within the first 400 ms
  // nothing was drawn anyway.
  runtime_tiles::Tile sw;
  sw.entity="switch.printer";
  sw.revision=runtime_tiles::state_revision("off","{}"); sw.begin(100);
  assert(!sw.loading(249));
  sw.observe(runtime_tiles::state_revision("on","{}"));
  assert(!sw.waiting(250)); assert(!sw.loading(500));
  sw.begin(300); sw.observe(runtime_tiles::state_revision("on","{}"));
  assert(sw.waiting(1000)); // Repeated identical data is not confirmation.
  assert(!sw.waiting(3300));

  // On / off, a mode, play or pause: what a finger changed shows through a wish (optimistic.h, tests/test_optimistic.cpp),
  // which keeps the Hue room of #159 too: a message that still says the word from before the tap is no answer.

  // A slider the finger let go stays put while the light fades towards it (firmware 0.2.60+).
  runtime_tiles::Tile group;
  group.entity="light.living_room"; group.received=true; group.state="on"; group.brightness=51; group.revision=rev("on");
  group.hold_slider(1000,204); group.begin(1000);
  assert(group.brightness==204); assert(group.slider_holding(1200));
  // The fade reports 80, 128, 180: each keeps the sent value in front, and each keeps the hold alive.
  for (float step : {80.0f, 128.0f, 180.0f}) {
    group.brightness=step; group.observe(rev("on")); group.slider_reported(1500+(int)step*10);
    assert(group.brightness==204); assert(group.slider_holding(1500+(int)step*10+1400));
  }
  // Within 3 % of the target the hold ends and the reported value shows.
  group.brightness=200; group.slider_reported(4000);
  assert(!std::isfinite(group.slider_sent)); assert(group.brightness==200);
  // A fan that only knows 33/66/100 reports 66 once and then stays quiet: after 1.5 s the slider follows it.
  runtime_tiles::Tile fan;
  fan.entity="fan.attic"; fan.received=true; fan.state="on"; fan.percentage=33; fan.revision=rev("on");
  fan.hold_slider(1000,50); fan.begin(1000);
  fan.percentage=66; fan.observe(rev("on")); fan.slider_reported(1400);
  assert(fan.percentage==50); assert(fan.slider_holding(2800)); assert(!fan.slider_holding(2900));
  fan.release_slider(); assert(fan.percentage==66); assert(!std::isfinite(fan.slider_sent));
  // No report at all: the hold ends with the wait, and what was there before comes back.
  runtime_tiles::Tile lone;
  lone.entity="light.lone"; lone.received=true; lone.state="on"; lone.brightness=100; lone.revision=rev("on");
  lone.hold_slider(1000,200); lone.begin(1000);
  assert(lone.slider_holding(3999)); assert(!lone.slider_holding(4000));
  lone.release_slider(); assert(lone.brightness==100);
  // "It worked" without a state (the value was already there) keeps it until the cap.
  lone.hold_slider(5000,200); lone.begin(5000); lone.answered_at=5400;
  assert(lone.slider_holding(9000)); assert(!lone.slider_holding(13000));
  // A slider on an off light: the light goes on through a wish (docs/OPTIMISTIC.md), which keeps "on" in front while
  // the hold keeps the value; without a wait of the tile's own the hold lasts the wait.
  runtime_tiles::Tile dark;
  dark.entity="light.dark"; dark.received=true; dark.state="off"; dark.brightness=NAN; dark.revision=rev("off");
  dark.hold_slider(1000,128);
  assert(dark.state=="off"); assert(dark.brightness==128);
  assert(dark.slider_holding(1000+runtime_tiles::Tile::BUSY_CAP-1));
  assert(!dark.slider_holding(1000+runtime_tiles::Tile::BUSY_CAP));
  // Home Assistant reporting it off (the wish lost) ends the hold.
  dark.state="off"; dark.brightness=NAN; dark.observe(rev("off")); dark.slider_reported(1500);
  assert(!std::isfinite(dark.slider_sent)); assert(!std::isfinite(dark.brightness));
  // A refusal puts the reported value back.
  dark.state="on"; dark.brightness=40; dark.hold_slider(2000,128); dark.begin(2000);
  dark.refused_at=2500; assert(!dark.slider_holding(2600)); dark.release_slider(); assert(dark.brightness==40);
  // A cover's position slider follows the blind as it moves: no hold.
  runtime_tiles::Tile blind;
  blind.entity="cover.blind"; blind.received=true; blind.state="open"; blind.position=20;
  blind.hold_slider(1000,80); assert(!std::isfinite(blind.slider_sent)); assert(blind.position==20);

  // The fingerprint follows state and attributes, and the streaming writer (what receive() hands to
  // ArduinoJson) gives the same value as hashing the joined text.
  assert(runtime_tiles::state_revision("on","{\"brightness\":255}")!=runtime_tiles::state_revision("on","{\"brightness\":254}"));
  assert(runtime_tiles::state_revision("on","{}")!=runtime_tiles::state_revision("off","{}"));
  assert(runtime_tiles::state_revision("o","n{}")!=runtime_tiles::state_revision("on","{}"));
  runtime_tiles::Fingerprint f; f.add("on"); f.write('\n');
  const char json[]="{\"a\":1}"; f.write(reinterpret_cast<const uint8_t*>(json),sizeof(json)-1);
  assert(f.value==runtime_tiles::state_revision("on","{\"a\":1}"));
}
