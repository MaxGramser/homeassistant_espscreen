// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_paper_print.cpp -o /tmp/test_paper_print && /tmp/test_paper_print
// When a paper glass prints (paper_print.h), run on a glass that writes down what it was told, with a clock the test
// moves: every rule in the file's head has its case here.
#include "../components/paper_glass/paper_print.h"
#include <cassert>
#include <cstdio>
#include <string>
#include <vector>

using namespace paper_print;

static uint32_t now_ms = 0;
static std::vector<std::string> trail;  // "part" or "whole", in order
static std::vector<uint32_t> at;        // the moment of each
static bool timer_set = false;
static uint32_t timer_at = 0;
static Printer p;
static uint32_t wholes_before = 0;  // whole refreshes before the case began

// The clock runs `ms` on: the timer fires when its moment comes, as the paper glass's does.
static void run(uint32_t ms) {
  const uint32_t end = now_ms + ms;
  while (timer_set && static_cast<int32_t>(timer_at - end) <= 0) {
    now_ms = timer_at;
    timer_set = false;
    p.tick(now_ms);
  }
  now_ms = end;
}
// The panel takes `ms` for the refresh it was told to make.
static void panel_done(uint32_t ms = 700) {
  run(ms);
  p.printed(now_ms);
}
// A finger lands and lifts 60 ms later; what the press itself drew (its shade) is drawn under it.
static void tap() {
  p.finger(true, now_ms);
  p.drawn(40, now_ms);
  run(60);
  p.finger(false, now_ms);
}

// A screen that has been running: its first print, the whole one every start begins with, is behind it.
static void fresh(Rules rules = Rules{}) {
  now_ms = 50000;
  trail.clear();
  at.clear();
  timer_set = false;
  p = Printer{};
  p.rules = rules;
  p.glass.print = [](bool whole) {
    trail.push_back(whole ? "whole" : "part");
    at.push_back(now_ms);
  };
  p.glass.later = [](uint32_t ms) {
    timer_set = true;
    timer_at = now_ms + ms;
  };
  p.drawn(1000, now_ms);
  run(rules.most_ms);
  assert(trail.size() == 1 && trail[0] == "whole");
  p.printed(now_ms);
  now_ms = 100000;
  trail.clear();
  at.clear();
  timer_set = false;
  wholes_before = p.wholes();
}

static void a_burst_is_one_print() {
  fresh();
  // Four values from Home Assistant within a second: each restarts the quiet, and one print shows all four.
  for (int i = 0; i < 4; ++i) {
    p.drawn(20, now_ms);
    run(200);
  }
  assert(trail.empty());
  run(200);  // 350 ms after the last
  assert(trail.size() == 1 && trail[0] == "part");
  assert(at[0] == 100000 + 600 + 350);
  panel_done();
  run(20000);
  assert(trail.size() == 1);
}

static void a_stream_still_prints() {
  fresh();
  // A value every 100 ms without end never leaves a quiet: the most from the first of them prints it.
  for (int i = 0; i < 40 && trail.empty(); ++i) {
    p.drawn(5, now_ms);
    run(100);
  }
  assert(trail.size() == 1);
  assert(at[0] == 100000 + 1500);
}

static void nothing_prints_under_a_finger() {
  fresh();
  // The press's own shade is drawn the moment the finger lands. It is never printed: the finger lifts, the shade goes
  // and the tile's new state comes, and one print shows that.
  p.finger(true, now_ms);
  p.drawn(40, now_ms);
  run(60);
  assert(trail.empty());
  p.finger(false, now_ms);
  p.drawn(40, now_ms);  // the shade is gone, the lamp is on
  run(79);
  assert(trail.empty());
  run(1);
  assert(trail.size() == 1 && trail[0] == "part" && at[0] == 100000 + 60 + 80);
}

static void a_fade_ends_before_its_print() {
  fresh();
  // A card fades back for 200 ms after the finger lifted, a frame every 16 ms: no frame of the fade is printed, the
  // print comes when the drawing stood still.
  tap();
  uint32_t last = now_ms;
  for (int frame = 0; frame < 13; ++frame) {
    p.drawn(40, now_ms);
    last = now_ms;
    run(16);
  }
  assert(trail.empty());
  run(80);
  assert(trail.size() == 1 && at[0] == last + 80);
  panel_done();
  // Something that never stands still after a finger (a spinner someone forgot) is printed all the same.
  fresh();
  tap();
  const uint32_t lifted = now_ms;
  for (int frame = 0; frame < 40 && trail.empty(); ++frame) {
    p.drawn(5, now_ms);
    run(16);
  }
  assert(trail.size() == 1 && at[0] == lifted + 400);
}

static void a_finger_that_stays_is_shown() {
  fresh();
  // A hold: the line that grows under a held top bar, a slider under a finger that does not let go.
  p.finger(true, now_ms);
  for (int i = 0; i < 20 && trail.empty(); ++i) {
    p.drawn(10, now_ms);
    run(100);
  }
  assert(trail.size() == 1 && at[0] == 100000 + 1500);
}

static void an_answer_from_home_assistant_is_the_fingers() {
  fresh();
  tap();
  p.drawn(40, now_ms);
  run(80);
  assert(trail.size() == 1);
  panel_done();
  // Home Assistant's confirmation a moment after the tap is still the finger's: no 350 ms of quiet.
  run(100);
  p.drawn(40, now_ms);
  const uint32_t answered = now_ms;
  run(80);
  assert(trail.size() == 2 && at[1] == answered + 80);
  panel_done();
  // Long after it, a change waits its quiet again.
  run(5000);
  p.drawn(40, now_ms);
  run(349);
  assert(trail.size() == 2);
  run(1);
  assert(trail.size() == 3);
}

static void a_key_is_a_finger_that_lifted() {
  fresh();
  p.finger(false, now_ms);  // a page key
  p.drawn(900, now_ms);
  run(80);
  assert(trail.size() == 1 && at[0] == 100000 + 80);
}

static void nothing_prints_under_a_refresh() {
  fresh();
  tap();
  p.drawn(40, now_ms);
  run(80);
  assert(trail.size() == 1 && p.printing());
  // The panel is busy for 700 ms. What is drawn meanwhile waits for it, and prints once it is free.
  run(300);
  p.drawn(40, now_ms);
  run(300);
  assert(trail.size() == 1 && p.waiting());
  panel_done(100);
  assert(trail.size() == 2 && at[1] == now_ms);
}

static void a_layout_prints_once() {
  fresh();
  p.hold(true, now_ms);
  // Eight tiles a quarter of a second apart, each drawn as it comes.
  for (int i = 0; i < 8; ++i) {
    p.drawn(120, now_ms);
    run(250);
  }
  assert(trail.empty());
  p.hold(false, now_ms);
  // The hold is over: what is left is the quiet after the last of them.
  run(350);
  assert(trail.size() == 1);
  panel_done();
  // A hold that never ends lets go by itself.
  fresh();
  p.hold(true, now_ms);
  p.drawn(500, now_ms);
  run(9999);
  assert(trail.empty());
  run(1);
  assert(trail.size() == 1 && at[0] == 100000 + 10000);
}

// A page turned by a key: a share of the glass changes, the panel prints it.
static void turn_a_page(uint16_t permille) {
  p.finger(false, now_ms);
  p.drawn(permille, now_ms);
  run(80);
  panel_done();
}

static void traces_are_tidied_at_rest() {
  fresh();
  // Six page turns, each half the glass: three glasses' worth of partial refreshes.
  for (int i = 0; i < 6; ++i) {
    turn_a_page(500);
    run(1000);
  }
  assert(trail.size() == 6 && p.worn() == 3000);
  for (const auto &kind : trail) assert(kind == "part");
  // Nothing whole while someone is at it; half a minute after the last key the glass refreshes whole, once.
  run(20000);
  assert(trail.size() == 6);
  run(10000);
  assert(trail.size() == 7 && trail[6] == "whole" && p.worn() == 0);
  panel_done(2000);
  run(120000);
  assert(trail.size() == 7);
}

static void a_finger_puts_the_tidying_off() {
  fresh();
  for (int i = 0; i < 6; ++i) turn_a_page(500);
  run(25000);
  p.finger(false, now_ms);  // someone is back before the rest is over
  run(25000);
  assert(trail.size() == 6);
  run(5000);
  assert(trail.size() == 7 && trail[6] == "whole");
}

static void many_small_prints_are_enough_too() {
  fresh();
  for (int i = 0; i < 30; ++i) {  // a clock's minute, thirty times
    p.drawn(10, now_ms);
    run(350);
    panel_done();
    run(59000);
  }
  // The thirtieth made it enough; the rest since it has long passed in the minute after it.
  assert(p.parts() == 30 && p.wholes() == wholes_before + 1);
  assert(trail.back() == "whole");
}

static void far_past_enough_the_print_is_whole() {
  fresh();
  // Someone turns pages without a pause: no rest comes, and the traces would only grow.
  for (int i = 0; i < 9; ++i) turn_a_page(1000);
  assert(trail.size() == 9 && trail[8] == "whole" && p.worn() == 0);
  for (int i = 0; i < 8; ++i) assert(trail[i] == "part");
}

static void a_whole_one_on_request() {
  fresh();
  // With nothing drawn: a key that asks for a clean glass.
  p.whole_next(now_ms);
  assert(trail.size() == 1 && trail[0] == "whole");
  panel_done(2000);
  // With something drawn: that print is the whole one.
  p.drawn(100, now_ms);
  p.whole_next(now_ms);
  run(350);
  assert(trail.size() == 2 && trail[1] == "whole");
}

static void a_poster_prints_whole_and_seldom() {
  fresh(poster());
  for (int i = 0; i < 5; ++i) {
    p.drawn(10, now_ms);
    run(1000);
  }
  assert(trail.empty());
  run(2000);
  assert(trail.size() == 1 && trail[0] == "whole");
  panel_done(20000);
  // No tidying: every print was whole already.
  run(600000);
  assert(trail.size() == 1);
}

static void the_first_print_is_whole() {
  // What the panel shows at a start is what it showed before it: only a whole refresh takes that off cleanly.
  now_ms = 5000;
  trail.clear();
  timer_set = false;
  p = Printer{};
  p.glass.print = [](bool whole) { trail.push_back(whole ? "whole" : "part"); };
  p.drawn(20, now_ms);
  p.tick(now_ms + 350);
  assert(trail.size() == 1 && trail[0] == "whole");
  p.printed(now_ms + 2350);
  p.drawn(20, now_ms + 3000);
  p.tick(now_ms + 3350);
  assert(trail.size() == 2 && trail[1] == "part");
}

static void the_clock_may_wrap() {
  fresh();
  now_ms = 0xFFFFFF00u;
  p.drawn(10, now_ms);
  run(349);
  assert(trail.empty());
  run(1);
  assert(trail.size() == 1);
}

int main() {
  a_burst_is_one_print();
  a_stream_still_prints();
  nothing_prints_under_a_finger();
  a_fade_ends_before_its_print();
  a_finger_that_stays_is_shown();
  an_answer_from_home_assistant_is_the_fingers();
  a_key_is_a_finger_that_lifted();
  nothing_prints_under_a_refresh();
  a_layout_prints_once();
  traces_are_tidied_at_rest();
  a_finger_puts_the_tidying_off();
  many_small_prints_are_enough_too();
  far_past_enough_the_print_is_whole();
  a_whole_one_on_request();
  a_poster_prints_whole_and_seldom();
  the_first_print_is_whole();
  the_clock_may_wrap();
  std::puts("paper_print: ok");
  return 0;
}
