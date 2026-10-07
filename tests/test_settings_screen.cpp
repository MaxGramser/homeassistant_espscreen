#define SETTINGS_SCREEN_TEST
#include "screen_text_en.h"
#include "../components/smart_display/settings_screen.h"
#include <cassert>
#include <string>

using namespace settings_screen;

// The row of a page by its label, so a test says what it means.
static const Row &row_named(const Page &page, const std::string &label) {
  for (uint8_t i = 0; i < page.count; ++i)
    if (label == label_text(page.rows[i])) return page.rows[i];
  assert(false);
  return page.rows[0];
}

int main() {
  // ---- the duration ladder: seconds low down, quarters of an hour up top, and symmetric ----
  assert(ladder_step(60) == 30 && ladder_step(600) == 60 && ladder_step(1800) == 300);
  assert(ladder_step(3600) == 900 && ladder_step(36000) == 1800);
  Row timeout = duration(screen_text::txt::settings_after, nullptr, nullptr, 30, 3600);
  assert(stepped(timeout, 120, 1) == 150 && stepped(timeout, 120, -1) == 90);
  assert(stepped(timeout, 300, 1) == 360 && stepped(timeout, 360, -1) == 300);
  assert(stepped(timeout, 300, -1) == 270 && stepped(timeout, 270, 1) == 300);
  assert(stepped(timeout, 30, -1) == 30 && stepped(timeout, 3600, 1) == 3600);
  assert(at_end(timeout, 30, -1) && at_end(timeout, 3600, 1) && !at_end(timeout, 120, -1));

  // ---- a number stops at its ends, a moment walks around midnight ----
  Row percent = number(screen_text::txt::settings_brightness, nullptr, nullptr, 5, 100, 5, "%");
  assert(stepped(percent, 100, 1) == 100 && stepped(percent, 5, -1) == 5 && stepped(percent, 95, 1) == 100);
  Row start = moment(screen_text::txt::settings_starts, nullptr, nullptr);
  assert(stepped(start, 1320, 1) == 1335 && stepped(start, 1425, 1) == 0 && stepped(start, 0, -1) == 1425);
  assert(!at_end(start, 0, -1));
  // Holding the key walks whole hours, and first lands on the hour it is in.
  assert(stepped(start, 1320, 1, true) == 1380 && stepped(start, 1320, -1, true) == 1260);
  assert(stepped(start, 1327, 1, true) == 1380 && stepped(start, 1327, -1, true) == 1320);
  assert(stepped(start, 1380, 1, true) == 1440 % 1440);   // 23:00 + 1 h wraps to 00:00
  assert(stepped(start, 0, -1, true) == 1380);            // 00:00 - 1 h is 23:00

  // ---- texts ----
  assert(duration_text(45) == "45 sec" && duration_text(60) == "1 min" && duration_text(120) == "2 min");
  assert(duration_text(3600) == "1 h" && duration_text(5400) == "1 h 30" && duration_text(86400) == "24 h");
  assert(moment_text(1320, true) == "22:00" && moment_text(0, true) == "00:00");
  assert(moment_text(1320, false) == "10:00 PM" && moment_text(0, false) == "12:00 AM");
  assert(moment_text(750, false) == "12:30 PM" && moment_text(60, false) == "1:00 AM");

  // ---- a switch's knob: inset at the left when off, flush with the same inset at the right when on ----
  // The Guition switch is 62 by 34 (a 28 px knob), the CYD one 40 by 22 (an 18 px knob).
  assert(knob_x(62, 34, false) == 3 && knob_x(62, 34, true) == 31 && 31 + 28 + 3 == 62);
  assert(knob_x(40, 22, false) == 2 && knob_x(40, 22, true) == 20 && 20 + 18 + 2 == 40);

  // ---- rows read and write the real settings ----
  screen_settings::current = screen_settings::Settings{};
  const Page &light = pages[1];
  const Row &brightness = row_named(light, "Brightness");
  assert(value_text(brightness) == "100%");
  brightness.write(40);
  assert(screen_settings::current.brightness == 40 && value_text(brightness) == "40%");
  // Lowering the normal brightness pulls the two dim levels down with it, exactly like the add-on.
  screen_settings::current.standby_brightness = 60;
  brightness.write(30);
  assert(screen_settings::current.standby_brightness == 30);
  const Row &standby = row_named(light, "Standby brightness");
  standby.write(90);
  assert(screen_settings::current.standby_brightness == 30);  // never above the normal brightness
  assert(screen_settings::current.valid());
  // Dark mode (firmware 0.2.54+) sits right under Brightness, a switch of its own outside the frozen block.
  assert(light.count == 6 && light.rows[1].kind == Kind::toggle && std::string(label_text(light.rows[1])) == "Dark mode");
  // A backlight without levels (firmware 0.2.90+): the normal brightness goes, and standby is the switch it really
  // is. Both write the same key, so the app and Home Assistant keep reading one number.
  {
    const Row &standby_switch = row_named(light, "Screen on in standby");
    assert(dimmable && visible_row(brightness) && visible_row(standby) && !visible_row(standby_switch));
    dimmable = false;
    assert(!visible_row(brightness) && !visible_row(standby) && visible_row(standby_switch));
    screen_settings::current.brightness = 100;
    standby_switch.write(0);
    assert(screen_settings::current.standby_brightness == 0 && value_text(standby_switch) == "Off");
    standby_switch.write(1);
    assert(screen_settings::current.standby_brightness == 100 && value_text(standby_switch) == "On");
    // Greyed out with auto standby off, exactly as the percentage row is.
    screen_settings::current.standby_enabled = 0;
    assert(!live_row(standby_switch));
    screen_settings::current.standby_enabled = 1;
    assert(live_row(standby_switch));
    const Row &night_switch = row_named(pages[2], "Screen on at night");
    assert(visible_row(night_switch) && !visible_row(row_named(pages[2], "Night brightness")));
    dimmable = true;
    screen_settings::current.standby_brightness = 30;
  }
  // A screen that cannot go dark (firmware 0.2.91+): no standby, and no night, which is standby with a clock. The
  // rows go, the Night page goes from the menu, and the switch that ties page 1 to standby goes with them.
  {
    const Row &auto_standby = row_named(light, "Auto standby");
    const Row &standby_after = row_named(light, "Standby after");
    const Row &standby_switch = row_named(light, "Screen on in standby");
    const Row &night_page = row_named(pages[0], "Night");
    const Row &night_mode = row_named(pages[2], "Night mode");
    const Row &night_brightness = row_named(pages[2], "Night brightness");
    const Row &also_on_standby = row_named(pages[3], "Also on standby");
    assert(can_standby && visible_row(auto_standby) && visible_row(standby_after) && visible_row(standby) &&
           visible_row(night_page) && visible_row(night_mode) && visible_row(night_brightness) && visible_row(also_on_standby));
    can_standby = false;
    assert(!visible_row(auto_standby) && !visible_row(standby_after) && !visible_row(standby) && !visible_row(standby_switch));
    assert(!visible_row(night_page) && !visible_row(night_mode) && !visible_row(night_brightness) && !visible_row(also_on_standby));
    for (uint8_t i = 0; i < pages[2].count; ++i) assert(!visible_row(pages[2].rows[i]));
    // What it can still do stays: the brightness, the dark look, and every row of the Screen page but that one.
    assert(visible_row(brightness) && visible_row(row_named(light, "Dark mode")) && visible_row(row_named(pages[3], "Back to Home")));
    // A board that can neither dim nor go dark shows neither the percentage nor the switch.
    dimmable = false;
    assert(!visible_row(standby) && !visible_row(standby_switch));
    dimmable = true;
    can_standby = true;
    assert(visible_row(auto_standby) && visible_row(night_page));
  }
  const Row &dark = row_named(light, "Dark mode");
  assert(value_text(dark) == "Off");
  dark.write(1);
  assert(dark_mode == 1 && value_text(dark) == "On");
  dark.write(0);
  assert(dark_mode == 0 && value_text(dark) == "Off");

  const Page &screen = pages[3];
  // Page buttons (firmware 0.2.69+) follows Swipe between pages: on by default, off takes the bar away.
  {
    const Row &buttons = row_named(screen, "Page buttons");
    assert(buttons.kind == Kind::toggle && &buttons == &row_named(screen, "Swipe between pages") + 1);
    assert(page_buttons == 1 && value_text(buttons) == "On");
    buttons.write(0);
    assert(page_buttons == 0 && value_text(buttons) == "Off");
    assert(set("page_buttons", 0) == SetResult::same);
    buttons.write(1);
    assert(page_buttons == 1);
  }
  // The home key in the top bar (firmware 0.2.100+): on by default, the row right after Page buttons.
  {
    const Row &key = row_named(screen, "Show home button");
    assert(key.kind == Kind::toggle && &key == &row_named(screen, "Page buttons") + 1);
    assert(home_button == 1 && value_text(key) == "On");
    key.write(0);
    assert(home_button == 0 && value_text(key) == "Off");
    assert(set("home_button", 0) == SetResult::same);
    key.write(1);
    assert(home_button == 1);
  }
  // 12 or 24 hours is chosen for every screen at once in ESP Screens (app 0.2.90): the page has no row for it, and
  // the value still arrives through set() and the layout message.
  for (uint8_t i = 0; i < screen.count; ++i) assert(std::string(label_text(screen.rows[i])) != "Clock");
  set("clock_24h", 0);
  assert(screen_settings::current.clock_24h == 0);
  const Row &home = row_named(screen, "Back to Home");
  home.write(0);
  assert(auto_home == 0 && value_text(home) == "Off");
  // Two rows say Rotation: the half turn of every board, and the quarter turns a square screen adds; one shows.
  const Row &half = row_named(screen, "Rotation");
  const Row *quarter = nullptr;
  for (uint8_t i = 0; i < screen.count; ++i)
    if (&screen.rows[i] != &half && label_text(screen.rows[i]) == std::string("Rotation")) quarter = &screen.rows[i];
  assert(quarter);
  quarter_turns = false;
  assert(visible_row(half) && !visible_row(*quarter));
  half.write(1);
  assert(rotation == 180 && value_text(half) == "180°");
  half.write(0);
  assert(rotation == 0);
  quarter_turns = true;
  assert(!visible_row(half) && visible_row(*quarter));
  quarter->write(2);
  assert(rotation == 180 && value_text(*quarter) == "180°");
  quarter->write(3);
  assert(rotation == 270);
  quarter->write(0);
  assert(rotation == 0);

  // ---- every page hangs together: menu rows open a real page, controls can be worked ----
  assert(PAGE_COUNT == 5);
  for (uint8_t p = 0; p < PAGE_COUNT; ++p) {
    const Page &page = pages[p];
    assert(page.title != NO_TEXT && *screen_text::tr(page.title) && page.count && page.count <= 8);
    for (uint8_t i = 0; i < page.count; ++i) {
      const Row &row = page.rows[i];
      assert(row.label != NO_TEXT && *label_text(row));
      if (row.kind == Kind::page) assert(row.opens > 0 && row.opens < PAGE_COUNT && *row.icon);
      if (row.kind == Kind::toggle || row.kind == Kind::choice || row.kind == Kind::number ||
          row.kind == Kind::duration || row.kind == Kind::moment)
        assert(row.read && row.write);
      if (row.kind == Kind::number) assert(row.step > 0 && row.high > row.low);
      if (row.kind == Kind::duration) assert(row.high > row.low);
      if (row.kind == Kind::choice) assert((row.options || row.option_keys != NO_TEXT) && row.option_count);
      if (row.kind == Kind::info) assert(row.text);
      // An action takes the glass away for a while, so every one of them has the words it asks first.
      if (row.kind == Kind::action) assert(row.run && *row.icon && row.confirm != NO_TEXT && *screen_text::tr(row.confirm));
    }
  }

  // ---- Calibrate touch: the row is there exactly where a wizard is ----
  // Nothing says "this glass is resistive" twice: the board that builds a wizard binds the hook, every other
  // board leaves it null, so the row cannot show where there is nothing to run.
  const Row *calibrate = nullptr;
  for (uint8_t i = 0; i < pages[4].count; ++i)
    if (pages[4].rows[i].label == screen_text::txt::settings_calibrate_touch) calibrate = &pages[4].rows[i];
  assert(calibrate && calibrate->kind == Kind::action);
  calibrate_touch = nullptr;
  assert(!visible_row(*calibrate));
  static int calibrations = 0;
  calibrate_touch = [] { ++calibrations; };
  assert(visible_row(*calibrate));
  calibrate->run();
  assert(calibrations == 1);
  calibrate_touch = nullptr;
  // Every page is reachable from the menu.
  bool reached[PAGE_COUNT] = {true};
  for (uint8_t i = 0; i < pages[0].count; ++i) reached[pages[0].rows[i].opens] = true;
  for (bool page : reached) assert(page);

  // ---- how many rows fit, and when the pager appears ----
  bool paged = false;
  assert(fitting_rows(180, 34, 4, 26, 4, paged) == 4 && !paged);   // CYD: four rows, no pager
  assert(fitting_rows(180, 34, 4, 26, 6, paged) == 4 && paged);    // six rows: 4 + 2
  assert(fitting_rows(372, 52, 8, 40, 6, paged) == 6 && !paged);   // Guition: the whole group at once
  assert(fitting_rows(372, 52, 8, 40, 9, paged) == 5 && paged);
  assert(fitting_rows(40, 34, 4, 26, 5, paged) >= 1);              // never zero rows

  // ---- a change is stored, applied and reported once ----
  static int stored = 0, applied = 0;
  static std::string last_key;
  static int32_t last_value = 0;
  store = [] { ++stored; };
  apply = [] { ++applied; };
  report = [](const char *key, int32_t value) { last_key = key; last_value = value; };
  row_named(light, "Auto standby").write(0);
  assert(stored == 1 && applied == 1 && last_key == "standby_enabled" && last_value == 0);
  row_named(screen, "After").write(600);
  assert(stored == 2 && last_key == "auto_home_seconds" && last_value == 600 && auto_home_seconds == 600);

  // ---- set(): the one path for the rows and for Home Assistant's entities (firmware 0.2.49+) ----
  // A value the screen already has is not stored, applied or reported: an automation may set it on every change.
  SetResult result = set("standby_enabled", 0);
  assert(result == SetResult::same && stored == 2 && applied == 2);
  result = set("auto_home_seconds", 600);
  assert(result == SetResult::same && stored == 2);
  // Every key ESP Screens knows lands on the screen, clamped the way the page steps it.
  screen_settings::current = screen_settings::Settings{};
  quarter_turns = true;
  const struct { const char *key; int32_t value, expected; } cases[] = {
      {"standby_enabled", 5, 1}, {"standby_seconds", 10, 60}, {"standby_seconds", 999999, 86400},
      {"brightness", 1, 5}, {"brightness", 250, 100}, {"standby_brightness", 101, 100}, {"night_enabled", 0, 0},
      {"night_start", -5, 0}, {"night_end", 2000, 1439}, {"night_brightness", 7, 7}, {"clock_24h", 0, 0},
      {"home_on_standby", 1, 1}, {"swipe_pages", 2, 1}, {"rotation", 100, 90}, {"rotation", 400, 270},
      {"auto_home", 0, 0}, {"auto_home_seconds", 5, 30}, {"auto_home_seconds", 99999, 3600},
      {"dark_mode", 7, 1}, {"page_buttons", 0, 0}, {"home_button", 0, 0},
  };
  for (const auto &c : cases) {
    result = set(c.key, c.value);
    assert(result != SetResult::unknown);
    if (result == SetResult::changed) assert(last_key == c.key && last_value == c.expected);
  }
  assert(screen_settings::current.standby_seconds == 86400 && screen_settings::current.brightness == 100);
  assert(screen_settings::current.night_start == 0 && screen_settings::current.night_end == 1439);
  assert(swipe_pages == 1 && rotation == 270 && auto_home == 0 && auto_home_seconds == 3600 && dark_mode == 1 &&
         page_buttons == 0 && home_button == 0);
  assert(screen_settings::current.valid());
  // Dark mode again is the same look: nothing stored, applied or reported; off is a change.
  {
    const int stored_before = stored, applied_before = applied;
    assert(set("dark_mode", 1) == SetResult::same && stored == stored_before && applied == applied_before);
    assert(set("dark_mode", 0) == SetResult::changed && last_key == "dark_mode" && last_value == 0 && dark_mode == 0);
    set("dark_mode", 1);
  }
  // A lower brightness pulls both dim levels down, and reports the brightness itself.
  set("standby_brightness", 60);
  set("night_brightness", 50);
  result = set("brightness", 30);
  assert(result == SetResult::changed && last_key == "brightness" && last_value == 30);
  assert(screen_settings::current.standby_brightness == 30 && screen_settings::current.night_brightness == 30);
  result = set("standby_brightness", 90);
  assert(result == SetResult::same && screen_settings::current.standby_brightness == 30);
  // A half turn is every screen's; a quarter turn only a square one's.
  quarter_turns = false;
  result = set("rotation", 180);
  assert(result == SetResult::changed && rotation == 180);
  // What the screen cannot do, or does not know, is refused without a store.
  const int before = stored;
  result = set("rotation", 90);
  assert(result == SetResult::unknown && rotation == 180);
  result = set("show_clock", 0);
  assert(result == SetResult::unknown);
  result = set("beep", 1);
  assert(result == SetResult::unknown && stored == before);

  // ---- what the screen tells ESP Screens it can do (firmware 0.2.99) ----
  // One word per ability, space separated and in the order of the list, so the add-on reads the same words
  // whatever the board. A screen that can do none of them says so: "none" is an answer, silence is not.
  const bool dimmable_before = dimmable, standby_before = can_standby;
  dimmable = true;  can_standby = true;   assert(features() == "dimmable standby");
  dimmable = true;  can_standby = false;  assert(features() == "dimmable");
  dimmable = false; can_standby = true;   assert(features() == "standby");
  dimmable = false; can_standby = false;  assert(features() == "none");
  // A screen with a battery (firmware 0.41.0) says so too, so ESP Screens offers the top bar's battery item.
  battery_status::level = []() { return 50.0f; };
  dimmable = true;  can_standby = true;   assert(features() == "dimmable standby battery");
  dimmable = false; can_standby = false;  assert(features() == "battery");
  battery_status::level = nullptr;
  dimmable = dimmable_before; can_standby = standby_before;
}
