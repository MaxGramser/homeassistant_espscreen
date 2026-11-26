// The logbook line of an action, run: components/smart_display/action_log.h. When a line is due (repeats on one entity
// fold, another entity gets its own, the oldest of the remembered ones makes room, the millisecond counter wraps) and
// how the message reads with the English texts the screens ship.
#include "screen_text_en.h"
#include "components/smart_display/action_log.h"
#include <cassert>
#include <cstdio>
#include <string>
using action_log::FOLD_MS;
using action_log::message;
using action_log::Recent;

int main() {
  const std::string with_tile = screen_text::tr(screen_text::txt::status_logbook_tile);
  const std::string without_tile = screen_text::tr(screen_text::txt::status_logbook_page);

  {  // One line for a tap, none for what follows it at once, one again after the fold.
    Recent r;
    assert(r.due("light.desk", 1000));
    assert(!r.due("light.desk", 1001));
    assert(!r.due("light.desk", 1000 + FOLD_MS - 1));
    assert(r.due("light.desk", 1000 + FOLD_MS));
    assert(!r.due("light.desk", 1000 + FOLD_MS + 10));
  }
  {  // Each entity folds by itself.
    Recent r;
    assert(r.due("light.desk", 1000));
    assert(r.due("climate.room", 1001));
    assert(!r.due("light.desk", 1002));
    assert(!r.due("climate.room", 1003));
  }
  {  // Four are remembered; a fifth takes the place of the one written longest ago, and the others still fold.
    Recent r;
    assert(r.due("a.one", 100));
    assert(r.due("a.two", 200));
    assert(r.due("a.three", 300));
    assert(r.due("a.four", 400));
    assert(r.due("a.five", 500));
    assert(!r.due("a.two", 600));
    assert(!r.due("a.five", 600));
    assert(r.due("a.one", 600));  // forgotten, so it is written again: never a line too few
  }
  {  // The counter wraps after 49 days: a line just before and an action just after still fold, a later one is written.
    Recent r;
    assert(r.due("light.desk", 0xFFFFFF00u));
    assert(!r.due("light.desk", 0x00000010u));
    assert(r.due("light.desk", 0x00000010u + FOLD_MS));
  }
  // The message names the screen, the page and the tile, and leaves the tile out when no tile of the page shows the entity.
  assert(message(with_tile, without_tile, "Hall screen", "Living room", "Thermostat") ==
         "operated on Hall screen, page Living room, tile Thermostat");
  assert(message(with_tile, without_tile, "Hall screen", "Living room", "") == "operated on Hall screen, page Living room");
  // A name with braces of its own stays as it is, and fills nothing else.
  assert(message(with_tile, without_tile, "{page}", "{tile}", "{screen}") == "operated on {page}, page {tile}, tile {screen}");
  // A language orders the names as its sentence needs.
  assert(message("{tile} / {page} / {screen}", "", "S", "P", "T") == "T / P / S");
  std::puts("action_log: ok");
  return 0;
}
