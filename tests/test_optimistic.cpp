// The one way a finger's change shows before Home Assistant confirms it (docs/OPTIMISTIC.md).
#include "components/smart_display/optimistic.h"
#include <cassert>

using namespace optimistic;

// A choice tapped, as wish() does it (it sends at once with a tick).
static void tap(Wish &w, const char *entity, Field field, const std::string &shown, const std::string &value, uint32_t now) {
  want(w, entity, entity, field, shown, value, now);
}

int main() {
  // A tap: the wish shows at once and goes out at once; Home Assistant's report of it ends it.
  {
    Wish w;
    want(w, "media_player.kitchen", "media_player.kitchen", Field::PLAYING, "1", "0", 1000);
    assert(w.live() && w.before == "1" && w.want == "0");
    assert(tick(w, 1000) == Outcome::SEND && w.phase == Phase::SENT && w.sent == "0");
    // A message from before the tap still says playing: the pause stays in front.
    assert(report(w, "1") == Outcome::KEEP && w.live());
    assert(report(w, "0") == Outcome::DONE && !w.live());
  }
  // A burst while the first is on its way: only the last wish goes out, once Home Assistant took the first, and nothing
  // when the burst ends on what was sent.
  {
    Wish w;
    tap(w, "light.desk", Field::ON_OFF, "off", "on", 0);
    assert(tick(w, 0) == Outcome::SEND);
    tap(w, "light.desk", Field::ON_OFF, "on", "off", 50);
    tap(w, "light.desk", Field::ON_OFF, "off", "on", 90);
    tap(w, "light.desk", Field::ON_OFF, "on", "off", 130);
    assert(w.queued() && w.want == "off" && w.sent == "on");
    assert(tick(w, 200) == Outcome::KEEP);  // waits for the answer, never a second action meanwhile
    assert(answer(w, true, 300) == Outcome::KEEP && w.phase == Phase::READY && w.before == "on");
    assert(tick(w, 300) == Outcome::SEND && w.sent == "off");
    assert(report(w, "on") == Outcome::KEEP);  // the first action's own report: what the second starts from
    assert(report(w, "off") == Outcome::DONE);
    Wish v;
    tap(v, "light.desk", Field::ON_OFF, "off", "on", 0);
    tick(v, 0);
    tap(v, "light.desk", Field::ON_OFF, "on", "off", 40);
    tap(v, "light.desk", Field::ON_OFF, "off", "on", 80);
    assert(!v.queued());
    assert(answer(v, true, 300) == Outcome::KEEP && v.phase == Phase::SENT);  // nothing newer: the hold starts
    assert(report(v, "on") == Outcome::DONE);
    // Home Assistant's report of the first ends the wait as its answer does.
    Wish r;
    tap(r, "light.desk", Field::ON_OFF, "off", "on", 0);
    tick(r, 0);
    tap(r, "light.desk", Field::ON_OFF, "on", "off", 40);
    assert(report(r, "on") == Outcome::KEEP && r.phase == Phase::READY);
    assert(tick(r, 60) == Outcome::SEND && r.sent == "off");
  }
  // A step (-/+) waits for the finger to rest: 16 to 20 is one call.
  {
    Wish w;
    for (int i = 0; i < 4; ++i)
      want(w, "climate.hall", "climate.hall", Field::HVAC_MODE, w.live() ? w.want : "16", std::to_string(17 + i), i * 100, 700);
    assert(tick(w, 300 + 699) == Outcome::KEEP);
    assert(tick(w, 300 + 700) == Outcome::SEND && w.sent == "20" && w.before == "16");
  }
  // Two steps that end where they began before the quiet is over: nothing goes out.
  {
    Wish w;
    want(w, "light.desk", "light.desk", Field::ON_OFF, "off", "on", 0, 700);
    want(w, "light.desk", "light.desk", Field::ON_OFF, "on", "off", 80, 700);
    assert(tick(w, 800) == Outcome::DROP && !w.live());
  }
  // Another value before the action went out is someone else's change: the wish goes out from there, and nothing
  // goes out when that already is the wish.
  {
    Wish w;
    want(w, "select.scene", "select.scene", Field::OPTION, "Day", "Night", 0, 700);
    assert(report(w, "Night") == Outcome::KEEP && w.before == "Night");
    assert(tick(w, 700) == Outcome::DROP);
  }
  // Home Assistant decides: another value than the wish (a fan that took the nearest speed, a mode it refused to keep)
  // ends the wish and shows.
  {
    Wish w;
    tap(w, "climate.hall", Field::HVAC_MODE, "heat", "heat_cool", 0);
    tick(w, 0);
    assert(report(w, "cool") == Outcome::CORRECTED && !w.live());
  }
  // A refusal puts the old value back at once and says so, also over a newer wish.
  {
    Wish w;
    tap(w, "switch.pump", Field::ON_OFF, "off", "on", 0);
    tick(w, 0);
    assert(answer(w, false, 500) == Outcome::REVERT && w.refused && !w.live() && w.before == "off");
    Wish q;
    tap(q, "switch.pump", Field::ON_OFF, "off", "on", 0);
    tick(q, 0);
    tap(q, "switch.pump", Field::ON_OFF, "on", "off", 100);
    assert(answer(q, false, 500) == Outcome::REVERT && q.before == "off");
  }
  // "It worked" without a change: TAP_HOLD after the answer the old value comes back, as Home Assistant's toggle does.
  {
    Wish w;
    tap(w, "switch.pump", Field::ON_OFF, "off", "on", 0);
    tick(w, 0);
    assert(answer(w, true, 600) == Outcome::KEEP);
    assert(tick(w, 600 + TAP_HOLD - 1) == Outcome::KEEP);
    assert(tick(w, 600 + TAP_HOLD) == Outcome::REVERT && !w.refused && w.phase == Phase::IDLE);
  }
  // A Hue room (#159): tapped off, its lamps report at once and the manager sends the room again with its old "on";
  // Home Assistant said "it worked" at 260. The tap's stand holds two seconds from there, and the room reporting itself
  // off a second later is the answer.
  {
    Wish w;
    tap(w, "light.room", Field::ON_OFF, "on", "off", 0);
    tick(w, 0);
    assert(report(w, "on") == Outcome::KEEP);
    answer(w, true, 260);
    assert(tick(w, 260 + TAP_HOLD - 1) == Outcome::KEEP);
    assert(report(w, "on") == Outcome::KEEP);
    assert(report(w, "off") == Outcome::DONE);
    Wish v;
    tap(v, "light.room", Field::ON_OFF, "on", "off", 0);
    tick(v, 0);
    assert(report(v, "unavailable") == Outcome::CORRECTED);
  }
  // No answer where none was asked for: back after HOLD_CAP; the eight-second verdict still finds it to say why.
  {
    Wish w;
    tap(w, "switch.pump", Field::ON_OFF, "off", "on", 0);
    tick(w, 0);
    assert(tick(w, HOLD_CAP) == Outcome::REVERT && w.phase == Phase::LAPSED && !w.live());
    assert(unanswered(w) == Outcome::KEEP && w.phase == Phase::IDLE);
    assert(unanswered(w) == Outcome::DONE);
    Wish waiting;
    tap(waiting, "switch.pump", Field::ON_OFF, "off", "on", 0);
    tick(waiting, 0);
    sent(waiting, true);
    assert(unanswered(waiting) == Outcome::REVERT && !waiting.live());
    Wish late;
    tap(late, "switch.pump", Field::ON_OFF, "off", "on", 0);
    tick(late, 0);
    tick(late, HOLD_CAP);
    assert(tick(late, LAPSED_KEEP) == Outcome::KEEP && late.phase == Phase::IDLE);
  }
  // Where no answer will come, a newer wish goes NEXT_UNWATCHED after the one before.
  {
    Wish w;
    tap(w, "light.desk", Field::ON_OFF, "off", "on", 0);
    tick(w, 0);
    sent(w, false);
    tap(w, "light.desk", Field::ON_OFF, "on", "off", 100);
    assert(tick(w, NEXT_UNWATCHED - 1) == Outcome::KEEP);
    assert(tick(w, NEXT_UNWATCHED) == Outcome::SEND && w.sent == "off" && w.before == "on");
  }
  // A slow device: Home Assistant was asked to answer, and the call takes four seconds. The wish waits for the answer
  // (as Home Assistant's toggle waits for its call), then the state; a second after it went out the tile says so.
  {
    Wish w;
    tap(w, "switch.slow", Field::ON_OFF, "off", "on", 0);
    assert(!slow(w, 5000));
    tick(w, 0);
    sent(w, true);
    assert(!slow(w, SLOW_SHOW - 1) && slow(w, SLOW_SHOW));
    assert(tick(w, HOLD_CAP) == Outcome::KEEP);
    answer(w, true, 4200);
    assert(report(w, "on") == Outcome::DONE && !slow(w, 4300));
    Wish never;
    tap(never, "switch.slow", Field::ON_OFF, "off", "on", 0);
    tick(never, 0);
    sent(never, true);
    assert(tick(never, WATCHED_CAP - 1) == Outcome::KEEP);
    assert(tick(never, WATCHED_CAP) == Outcome::REVERT);
  }
  // The clock wraps around.
  {
    Wish w;
    want(w, "light.desk", "light.desk", Field::ON_OFF, "off", "on", 0xFFFFFF00u, 700);
    assert(tick(w, 0xFFFFFF00u + 699) == Outcome::KEEP);
    assert(tick(w, 0xFFFFFF00u + 700) == Outcome::SEND);
    assert(tick(w, 0xFFFFFF00u + 700 + HOLD_CAP - 1) == Outcome::KEEP);
  }
  // Two lamps of one group are two wishes: a part (`item`) is part of what a wish is about.
  {
    Pool<3> pool;
    Wish &a = pool.slot("light.room", Field::LAMP_ON, "light.left");
    want(a, "light.room", "light.left", Field::LAMP_ON, "0", "1", 0, 0, "light.left");
    Wish &b = pool.slot("light.room", Field::LAMP_ON, "light.right");
    assert(&a != &b);
    want(b, "light.room", "light.right", Field::LAMP_ON, "0", "1", 0, 0, "light.right");
    assert(pool.find("light.room", Field::LAMP_ON, "light.left") == &a && pool.find("light.room", Field::LAMP_ON, "light.right") == &b);
    assert(!pool.find("light.room", Field::LAMP_ON));
  }
  // The pool: one wish per entity and field, a free slot next, the oldest given up when all are taken.
  {
    Pool<2> pool;
    Wish &a = pool.slot("light.a", Field::ON_OFF);
    want(a, "light.a", "light.a", Field::ON_OFF, "off", "on", 10);
    assert(&pool.slot("light.a", Field::ON_OFF) == &a);
    Wish &b = pool.slot("light.b", Field::ON_OFF);
    assert(&b != &a);
    want(b, "light.b", "light.b", Field::ON_OFF, "off", "on", 20);
    assert(pool.find("light.b", Field::ON_OFF) == &b && !pool.find("light.b", Field::OPTION));
    Wish &c = pool.slot("light.c", Field::ON_OFF);
    assert(&c == &a && !a.live());
    assert(pool.any());
  }
  return 0;
}
