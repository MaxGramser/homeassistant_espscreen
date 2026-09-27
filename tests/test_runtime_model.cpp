#include "screen_text_en.h"
#include "../components/smart_display/runtime_model.h"
#include <cassert>
// A test fixture uses the same single-store transaction as the receiver.
static void seed(runtime_tiles::Model &m, std::initializer_list<const char *> entities, unsigned pages = 1) {
  assert(m.begin(entities.size(), pages, "Home"));
  unsigned i = 0;
  for (const auto *entity : entities) { m.tiles[i].entity = entity; m.slots[i] = i; ++i; }
  m.configured = true;
}
int main() {
  using namespace runtime_tiles;
  Model m;
  assert(!m.ready());
  assert(!valid_entity("light.a;script.bad") && !valid_entity("light.") && !valid_entity("zone.home") && valid_entity("lock.frontdoor"));
  assert(m.begin(3, 2, "Home") && !m.configured && !m.ready());
  m.tiles[0].entity = "light.a";
  m.tiles[0].state = "on";
  m.configured = true;
  assert(!m.ready());
  for (auto &tile : m.tiles) tile.received = true;
  assert(m.ready() && m.accepts(0, "light.a"));
  assert(!m.accepts(10, "light.a") && !m.accepts(0, "light.removed"));
  // Beginning a replacement clears old states after reserving the new buffers.
  assert(m.begin(12, 3, "Twelve") && m.tiles.size() == 12 && m.count == 12);
  assert(!m.configured && m.tiles[0].state.empty());
  assert(m.begin(48, 8, "Maximum") && m.count == 48 && m.page_data.records.size() == 8);
  assert(!m.begin(49, 8, "Too many") && !m.configured && m.count == 48);
  assert(!m.begin(0, 9, "Too many pages"));
  assert(!m.begin(0, 0, "No page"));
  assert(m.begin(0, 1, "Empty")); m.configured = true; assert(m.ready());
  assert(m.begin(0, 1, "") && m.title == screen_text::tr(screen_text::txt::status_home));
}
// Built-in and new Home Assistant domains, plus wide-tile packing.
static void test_domains_and_sizes() {
  using namespace runtime_tiles;
  Model m;
  assert(valid_entity("screen.clock") && !valid_entity("screen.other"));
  assert(valid_entity("sun.sun") && valid_entity("timer.kitchen") && valid_entity("person.max"));
  seed(m, {"screen.clock", "weather.home", "light.a", "sensor.b", "person.max", "timer.egg", "sun.sun"}, 2);
  assert(m.tiles[0].available() && !m.tiles[1].available());  // built-in cards need no HA state
  // A scene or button that never ran is unknown in Home Assistant and can still be pressed; other unknown states can't act.
  for (const char *entity : {"scene.evening", "button.restart", "input_button.doorbell"}) {
    runtime_tiles::Tile never; never.entity = entity; never.received = true; never.state = "unknown";
    assert(never.available());
    never.state = "unavailable"; assert(!never.available());
  }
  { runtime_tiles::Tile lamp; lamp.entity = "light.lamp"; lamp.received = true; lamp.state = "unknown"; assert(!lamp.available()); }
  { runtime_tiles::Tile waiting; waiting.entity = "scene.evening"; waiting.state = "unknown"; assert(!waiting.available()); }
  m.tiles[4].received = m.tiles[5].received = true;
  m.tiles[4].state = "home"; assert(m.tiles[4].active());
  m.tiles[5].state = "active"; assert(m.tiles[5].active());
  m.tiles[5].state = "idle"; assert(!m.tiles[5].active());
  m.tiles[1].full = true; m.tiles[1].wide = true;
  assert(m.tiles[1].cells() == 6 && m.tiles[0].cells() == 1);
}
struct RunExtra { RunExtra() { test_domains_and_sizes(); } } run_extra;
// Placement checks reject overlap before a received tile can occupy the grid.
static void test_explicit_slots() {
  using namespace runtime_tiles;
  Model m;
  seed(m, {"light.a", "light.b", "screen.page_1"}, 3);
  assert(m.valid_placement(0, 5, false, false));
  assert(!m.valid_placement(0, 5, false, true));
  assert(!m.valid_placement(0, 1, true, false));
  assert(!m.valid_placement(0, 18, false, false));
  assert(!m.valid_placement(3, 0, false, false));
  m.slots[0] = 4; m.tiles[0].wide = true; m.tiles[0].received = true;
  assert(!m.valid_placement(1, 5, false, false));
  assert(m.valid_placement(1, 6, true, false));
  m.slots[1] = 6; m.tiles[1].full = true; m.tiles[1].received = true;
  assert(!m.valid_placement(2, 11, false, false));
  assert(m.valid_placement(2, 12, false, false));
  m.slots[2] = 12;
  std::array<Placement, TILES_MAX> p;
  assert(place(m, p) == 3 && p[0].slot == 4 && p[1].page == 1 && p[2].page == 2);
}
struct RunSlots { RunSlots() { test_explicit_slots(); } } run_slots;
static void test_rectangular_slots() {
  using namespace runtime_tiles;
  Model m;
  assert(m.begin(3, 2, "Rectangles"));
  assert(m.valid_placement(0, 1, false, false, 2));
  m.slots[0] = 1; m.tiles[0].height = 2; m.tiles[0].received = true;
  assert(m.tiles[0].cells() == 2);
  assert(m.valid_placement(1, 2, false, false));
  assert(!m.valid_placement(1, 3, false, false));
  assert(!m.valid_placement(1, 4, false, false, 2));
  assert(!m.valid_placement(1, 1, false, true, 2));
  assert(m.valid_placement(1, 6, false, true, 2));
  m.slots[1] = 6; m.tiles[1].wide = m.tiles[1].received = true; m.tiles[1].height = 2;
  assert(m.tiles[1].cells() == 4);
  assert(!m.valid_placement(2, 9, false, false));
  assert(m.valid_placement(2, 10, false, true));
}
struct RunRectangles { RunRectangles() { test_rectangular_slots(); } } run_rectangles;
// What only some tiles carry lives in an Extra that exists only while a state needs it.
static void test_extra() {
  using namespace runtime_tiles;
  Tile lamp;
  assert(!lamp.extra_ptr() && lamp.extra().options.empty() && !lamp.choice('m'));
  lamp.set_extra(Extra{});
  assert(!lamp.extra_ptr());  // an empty block is never allocated
  Extra climate; climate.hvac_modes = "[\"off\",\"heat\"]"; climate.hvac_action = "heating";
  lamp.set_extra(std::move(climate));
  Extra *kept = lamp.extra_ptr();
  assert(kept && lamp.extra().hvac_action == "heating");
  Extra again; again.hvac_action = "idle";
  lamp.set_extra(std::move(again));
  assert(lamp.extra_ptr() == kept && lamp.extra().hvac_action == "idle" && lamp.extra().hvac_modes.empty());
  Tile copy = lamp;  // a copy owns its own block
  copy.edit_extra().hvac_action = "cooling";
  assert(lamp.extra().hvac_action == "idle" && copy.extra().hvac_action == "cooling");
  lamp.set_extra(Extra{});
  assert(!lamp.extra_ptr() && lamp.extra().hvac_action.empty());
  Extra robot; Choice mode; mode.kind = 'm'; mode.values = {"vacuum", "mop"}; robot.choices.push_back(mode); robot.room = "Kitchen";
  Tile vacuum; vacuum.set_extra(std::move(robot));
  assert(vacuum.choice('m') && vacuum.choice('m')->values.size() == 2 && !vacuum.choice('w') && vacuum.extra().room == "Kitchen");
  vacuum.choice('m')->sent = "mop";
  assert(static_cast<const Tile &>(vacuum).choice('m')->sent == "mop");
  // A new layout resets the slots, blocks included.
  Model m;
  seed(m, {"vacuum.robot"});
  m.tiles[0] = vacuum;
  seed(m, {"light.a"}); assert(!m.tiles[0].extra_ptr());
}
struct RunTileExtra { RunTileExtra() { test_extra(); } } run_tile_extra;
// Sliders keep their colour the way Home Assistant's tile sliders do: grey for an off light or fan and a media
// player that is off or in standby, coloured for a player that plays, a cover open or closed and a number.
static void test_slider_colours() {
  using namespace runtime_tiles;
  Model m;
  seed(m, {"light.a", "fan.b", "media_player.c", "cover.d", "number.e", "input_number.f"});
  auto &light = m.tiles[0], &fan = m.tiles[1], &player = m.tiles[2], &cover = m.tiles[3], &number = m.tiles[4], &setpoint = m.tiles[5];
  player.state = "playing"; assert(!player.slider_active());  // nothing received yet
  for (size_t i = 0; i < m.count; ++i) m.tiles[i].received = true;
  light.state = "on"; assert(light.slider_active());
  light.state = "off"; assert(!light.slider_active());
  fan.state = "on"; assert(fan.slider_active());
  fan.state = "off"; assert(!fan.slider_active());
  for (const char *state : {"playing", "paused", "idle", "buffering", "on"}) { player.state = state; assert(player.slider_active()); }
  for (const char *state : {"off", "standby", "unavailable", "unknown"}) { player.state = state; assert(!player.slider_active()); }
  for (const char *state : {"open", "opening", "closing", "closed"}) { cover.state = state; assert(cover.slider_active()); }
  cover.state = "unavailable"; assert(!cover.slider_active());
  number.state = "21.5"; assert(number.slider_active());
  number.state = "unknown"; assert(!number.slider_active());
  setpoint.state = "55.0"; assert(setpoint.slider_active());
}
struct RunSliderColours { RunSliderColours() { test_slider_colours(); } } run_slider_colours;
// Home Assistant's stateActive() (firmware 0.2.71+): what it calls inactive is grey on the screen. (`lights` was the
// full-page tint of firmware 0.2.62 to 0.2.76, gone since 0.2.77: the cases stay as a record of the rule.)
static void test_state_active() {
  using namespace runtime_tiles;
  struct Case { const char *entity, *state; bool active, lights; };
  for (const Case &c : std::initializer_list<Case>{
           {"climate.airco", "off", false, false}, {"climate.airco", "cool", true, true}, {"climate.airco", "heat", true, true},
           {"climate.airco", "heat_cool", true, true}, {"climate.airco", "fan_only", true, true}, {"climate.airco", "dry", true, true},
           {"light.a", "on", true, true}, {"light.a", "off", false, false}, {"switch.a", "on", true, true},
           {"input_boolean.a", "off", false, false}, {"fan.a", "on", true, true}, {"fan.a", "off", false, false},
           {"cover.a", "open", true, true}, {"cover.a", "opening", true, true}, {"cover.a", "closing", true, true},
           {"cover.a", "closed", false, false}, {"media_player.a", "playing", true, true}, {"media_player.a", "paused", true, true},
           {"media_player.a", "idle", true, true}, {"media_player.a", "on", true, true}, {"media_player.a", "standby", false, false},
           {"media_player.a", "off", false, false}, {"vacuum.a", "cleaning", true, true}, {"vacuum.a", "returning", true, true},
           {"vacuum.a", "error", true, true}, {"vacuum.a", "docked", false, false}, {"vacuum.a", "idle", false, false},
           {"vacuum.a", "paused", false, false}, {"script.a", "on", true, true}, {"script.a", "off", false, false},
           {"timer.a", "active", true, true}, {"timer.a", "paused", false, false}, {"timer.a", "idle", false, false},
           {"camera.a", "streaming", true, true}, {"camera.a", "recording", true, true}, {"camera.a", "idle", false, false},
           {"person.a", "home", true, true}, {"person.a", "Work", true, true}, {"person.a", "not_home", false, false},
           {"binary_sensor.a", "on", true, true}, {"binary_sensor.a", "off", false, false},
           // Always active in Home Assistant: coloured, but never lit.
           {"sensor.a", "21.5", true, false}, {"number.a", "3", true, false}, {"input_number.a", "3", true, false},
           {"select.a", "eco", true, false}, {"input_select.a", "eco", true, false}, {"weather.a", "rainy", true, false},
           {"sun.sun", "above_horizon", true, false}, {"sun.sun", "below_horizon", true, false},
           {"scene.a", "2026-09-18T20:00:00+00:00", true, false}, {"scene.a", "unknown", true, false},
           {"button.a", "unknown", true, false}, {"input_button.a", "unknown", true, false}, {"image.a", "unknown", true, false},
           // "off" is inactive in every domain, a select's option too; unknown too, except where the state is a moment.
           {"select.a", "off", false, false}, {"sensor.a", "unknown", false, false}, {"light.a", "unavailable", false, false},
           {"scene.a", "unavailable", false, false}}) {
    Tile t; t.entity = c.entity; t.state = c.state; t.received = true;
    assert(t.active() == c.active);
    (void) c.lights;
  }
  // Nothing received yet is inactive; a built-in card has no state and is always active.
  { Tile t; t.entity = "light.a"; t.state = "on"; assert(!t.active()); }
  for (const char *entity : {"screen.clock", "screen.settings", "screen.page_2"}) {
    Tile t; t.entity = entity; assert(t.active());
  }
  // A closed blind: grey card, coloured slider.
  { Tile t; t.entity = "cover.a"; t.state = "closed"; t.received = true; assert(!t.active() && t.slider_active()); }
}
struct RunStateActive { RunStateActive() { test_state_active(); } } run_state_active;
// Stable page records own their title. Only the explicit screen source follows the screen title.
static void test_page_titles() {
  using namespace runtime_tiles;
  Model m;
  seed(m, {"screen.page_1", "screen.page_1"}, 3);
  m.page_data.records[1].title = "Kitchen";
  assert(m.title_of(0) == "Home" && m.title_of(1) == "Kitchen" && m.title_of(7) == "Home");
  m.title = "Upstairs";
  assert(m.title_of(0) == "Upstairs" && m.title_of(1) == "Kitchen");
  assert(m.accepts(0, "screen.page_1") && m.accepts(1, "screen.page_1"));
  m.tiles[0].icon = "a"; m.tiles[1].icon = "b";
  assert(m.tiles[0].icon != m.tiles[1].icon);
}
struct RunPageTitles { RunPageTitles() { test_page_titles(); } } run_page_titles;
static size_t test_room = 0;
static void test_tile_room() {
  using namespace runtime_tiles;
  Model m;
  seed(m, {"light.a"});
  tile_room = [] { return test_room; };
  test_room = 48 * sizeof(Tile) + 8 * sizeof(page_protocol::Page) - 1;
  assert(!m.begin(48, 8, "Maximum"));
  assert(m.refusal == "Error: insufficient layout memory" && m.configured && m.count == 1);
  assert(m.tiles[0].entity == "light.a" && m.title == "Home");
  ++test_room;
  assert(m.begin(48, 8, "Maximum") && m.count == 48 && m.refusal.empty());
  test_room = 0;
  assert(m.begin(0, 1, "Empty"));  // Existing capacity needs no new allocation.
  Model empty;
  assert(!empty.begin(0, 1, "Empty"));  // A first empty page still needs a bar.
  tile_room = nullptr;
}
struct RunTileRoom { RunTileRoom() { test_tile_room(); } } run_tile_room;
static unsigned allocation_attempt = 0, fail_attempt = 0;
static bool cancelled_for_replacement = false;
static void test_allocation_failure_preserves_layout() {
  using namespace runtime_tiles;
  for (unsigned failure : {1u, 2u}) {
    Model m;
    seed(m, {"light.a"});
    m.tiles[0].received = true;
    m.tiles[0].state = "on";
    m.page_data.records[0].id = 123;
    auto *original = &m.tiles[0];
    allocation_attempt = 0; fail_attempt = failure; cancelled_for_replacement = false;
    layout_memory::allocation_allowed = [](size_t) { return ++allocation_attempt != fail_attempt; };
    assert(!m.begin(12, 3, "Replacement", [] { cancelled_for_replacement = true; }));
    assert(!cancelled_for_replacement && m.ready() && m.count == 1 && m.title == "Home");
    assert(&m.tiles[0] == original && m.tiles[0].state == "on" && m.page_data.records[0].id == 123);
    assert(m.refusal == "Error: insufficient layout memory");
    // Retry with the same capacity under total allocation failure: no extra
    // record memory is needed and cancellation occurs only after preparation.
    allocation_attempt = 0;
    layout_memory::allocation_allowed = [](size_t) { ++allocation_attempt; return false; };
    assert(m.begin(1, 1, "Replacement", [] { cancelled_for_replacement = true; }));
    assert(cancelled_for_replacement && allocation_attempt == 0 && m.refusal.empty());
    assert(&m.tiles[0] == original && m.tiles[0].state.empty() && !m.configured);
    layout_memory::allocation_allowed = nullptr;
  }
}
struct RunAllocationFailure { RunAllocationFailure() { test_allocation_failure_preserves_layout(); } } run_allocation_failure;
// One redraw bit for each of the 48 tiles (firmware 0.2.65+); 32 bits sent tiles 33-48 through a full redraw.
static void test_tile_bits() {
  using namespace runtime_tiles;
  assert(tile_bit(0) == 1 && tile_bit(31) == (uint64_t{1} << 31) && tile_bit(47) == (uint64_t{1} << 47));
  assert(tile_bit(grid.max_tiles() - 1) && !tile_bit(64) && !tile_bit(grid.max_tiles() + 100));
  uint64_t dirty = tile_bit(33) | tile_bit(47);
  assert((dirty & tile_bit(33)) && (dirty & tile_bit(47)) && !(dirty & tile_bit(1)) && !(dirty & tile_bit(32)));
  for (size_t a = 0; a < grid.max_tiles(); ++a) for (size_t b = a + 1; b < grid.max_tiles(); ++b) assert(!(tile_bit(a) & tile_bit(b)));
}
struct RunTileBits { RunTileBits() { test_tile_bits(); } } run_tile_bits;
// Clock texts without sscanf (firmware 0.2.75+): the same answers the sscanf versions gave.
static void test_clock_texts() {
  using namespace runtime_tiles;
  assert(duration_seconds("0:05:00") == 300 && duration_seconds("1:02:03") == 3723 && duration_seconds("12:00:00") == 43200);
  assert(duration_seconds("5:30") == 330 && duration_seconds("0:00:05.5") == 5 && duration_seconds("5:00:") == 300);
  assert(duration_seconds("1:2:3:4") == 3723);
  assert(duration_seconds("") == 0 && duration_seconds("12") == 0 && duration_seconds("1 day, 2:03:04") == 0);
  assert(duration_seconds("idle") == 0 && duration_seconds(":05") == 0);
  assert(minutes_of("06:45") == 405 && minutes_of("0:00") == 0 && minutes_of("23:59") == 1439 && minutes_of("07:30:00") == 450);
  assert(minutes_of("24:00") == -1 && minutes_of("12:60") == -1 && minutes_of("12") == -1 && minutes_of("") == -1);
  assert(minutes_of("x6:45") == -1 && minutes_of(" 6: 45") == 405 && duration_seconds("1: 59:") == 119);
  // A running timer never shows more than its duration, whatever the clocks' whole seconds make of it.
  assert(timer_left(1003, 999, "0:00:03") == 3 && timer_left(1003, 1000, "0:00:03") == 3 && timer_left(1003, 1001, "0:00:03") == 2);
  assert(timer_left(1003, 1003, "0:00:03") == 0 && timer_left(1003, 1010, "0:00:03") == 0 && timer_left(1003, 0, "0:00:03") == 0);
  assert(timer_left(1300, 1000, "0:05:00") == 300 && timer_left(1300, 1000, "") == 300 && timer_left(1300, 1000, "idle") == 300);
  unsigned v[3] = {9, 9, 9};
  assert(clock_parts("7:8", v, 3) == 2 && v[0] == 7 && v[1] == 8 && v[2] == 9);
}
struct RunClockTexts { RunClockTexts() { test_clock_texts(); } } run_clock_texts;
