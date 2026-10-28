// A light's presets (components/smart_display/module_light_presets.h): their colours as Home Assistant draws its favourite
// colours, which one a light shows, the wish they make and how many keys a row holds.
#define LIGHT_PRESETS_TEST
#include "components/smart_display/module_light_presets.h"
#include <cassert>
#include <cstdio>

using namespace light_presets;

int main() {
  // Home Assistant's temperature2rgb and hs2rgb, values from its frontend.
  assert(kelvin_rgb(2700) == 0xFFA757);
  assert(kelvin_rgb(6500) == 0xFFFEFA);
  assert(kelvin_rgb(2000) == 0xFF890E);
  assert(hs_rgb(0, 100) == 0xFF0000);
  assert(hs_rgb(240, 100) == 0x0000FF);
  assert(hs_rgb(120, 0) == 0xFFFFFF);
  assert(hs_rgb(280, 41) == 0xDC96FF);
  // A hairline round a pale disc, as Home Assistant's luminosity > 0.8: cool white yes, a warm one no.
  assert(pale(make(80, 6500, 0, 0, true, false)));
  assert(!pale(make(80, 2700, 0, 0, true, false)));
  assert(!pale(make(80, 0, 0, 100, false, true)));
  assert(pale(make(30, 0, 0, 0, false, false)));  // a brightness alone: the amber field, its number on it
  // The brightness on it: dark on warm white and on the pale amber, white on a deep blue.
  assert(dark_ink(make(80, 2700, 0, 0, true, false)));
  assert(dark_ink(make(30, 0, 0, 0, false, false)));
  assert(dark_ink(make(80, 0, 0, 100, false, true)));      // WCAG: black reads better on pure red than white
  assert(!dark_ink(make(80, 0, 240, 100, false, true)));

  // What the app may send and what the screen takes.
  assert(make(0, 2700, 0, 0, true, false).level == 0);
  assert(make(101, 0, 0, 0, false, false).level == 0);
  assert(make(50, 900, 0, 0, true, false).level == 0);
  assert(make(50, 0, 360, 50, false, true).hue == 0);
  assert(make(50, 0, 10, 101, false, true).level == 0);
  assert(make(50, 0, 0, 0, false, false).kind == Preset::LEVEL);

  // Which one the light shows: its brightness to a percent, its white shade to 50 K, its colour to 3 degrees and 3 %.
  Light warm{true, true, 80, 2702, 30, 60, {}, {}};
  const Preset white = make(80, 2700, 0, 0, true, false), red = make(60, 0, 359, 90, false, true), half = make(80, 0, 0, 0, false, false);
  assert(shows(white, warm));
  assert(!shows(white, Light{true, true, 75, 2700, 0, 0, {}, {}}));
  assert(!shows(white, Light{true, false, 80, 2700, 30, 60, {}, {}}));   // a colour mode: Home Assistant names no white shade
  assert(!shows(white, Light{false, true, 80, 2700, 0, 0, {}, {}}));
  assert(shows(red, Light{true, false, 60, 2700, 1, 88, {}, {}}));       // 359 and 1 are two degrees apart
  assert(!shows(red, Light{true, false, 60, 2700, 10, 90, {}, {}}));
  assert(shows(half, warm));
  Presets ps; ps.items = {red, white, half}; ps.count = 3;
  assert(shown(ps, warm) == 1);
  assert(shown(ps, Light{}) == -1);

  // The wish: what it shows, what it reads of the light, and back.
  assert(value(white) == "80|k2700");
  assert(value(red) == "60|h359,90");
  assert(value(half) == "80|");
  assert(read(warm, true, Preset::WHITE) == "80|k2702");
  assert(read(warm, true, Preset::LEVEL) == "80|");
  assert(read(warm, false, Preset::WHITE) == "80|");
  assert(read(Light{false, true, 0, 2700, 0, 0, {}, {}}, true, Preset::WHITE) == "0|");
  assert(read(Light{true, false, 60, 2700, 359, 90, {}, {}}, true, Preset::COLOUR) == "60|h359,90");
  for (const auto &p : {white, red, half}) assert(value(parse(value(p))) == value(p));
  assert(colour_data(white).key2 == "color_temp_kelvin" && colour_data(white).value2 == "2700");
  assert(colour_data(red).key2 == "hs_color" && colour_data(red).value2 == "[359, 90]");
  assert(colour_data(half).key2.empty());

  // A row: four of 41 px with 10 between them in a Guition's 192 px; smaller down to 34; else fewer.
  auto r = row(192, 44, 4, 41, 34, 10);
  assert(r.count == 4 && r.size == 40 && r.length() <= 192);
  r = row(300, 44, 4, 41, 34, 10);
  assert(r.count == 4 && r.size == 41);
  r = row(140, 44, 4, 41, 34, 10);
  assert(r.count == 3 && r.size >= 34 && r.length() <= 140);
  r = row(30, 44, 4, 41, 34, 10);
  assert(r.count == 0);
  r = row(192, 30, 4, 41, 34, 10);   // a row lower than the key: the key as high as the row
  assert(r.count == 4 && r.size == 30);
  assert(row(192, 44, 0, 41, 34, 10).count == 0);

  // A light group, lamp by lamp: what Home Assistant 2026.9.2 made of a purple preset (60 %, 280/41) on a group of a lamp
  // with colour and white shades, a colour lamp, one that only takes white shades and one that only dims. The group's
  // average hue was 261: lamp by lamp it shows the preset.
  const Preset purple = make(60, 0, 280, 41, false, true), warm2 = make(80, 2700, 0, 0, true, false);
  Lamp mixed[4] = {{true, false, true, true, true, 60, 280, 41, 0},
                   {true, false, true, true, false, 60, 280, 41, 0},
                   {true, false, true, false, true, 60, 221, 20, 9861},
                   {true, false, true, false, false, 60, 0, 0, 0}};
  assert(group_shows(purple, mixed, 4));
  assert(!group_shows(warm2, mixed, 4));              // the lamp with white shades is not at 2700 K, and not at 80 %
  mixed[1].hue = 220;                                 // a colour lamp in another colour
  assert(!group_shows(purple, mixed, 4));
  mixed[1].hue = 280; mixed[3].on = false;            // a lamp off: the preset turns every lamp on
  assert(!group_shows(purple, mixed, 4));
  mixed[3].unavailable = true;                        // an unavailable one is not held against it
  assert(group_shows(purple, mixed, 4));
  // The white preset on the same group: the colour lamp in the warm colour Home Assistant made of 2700 K, the others white.
  Lamp white2700[3] = {{true, false, true, true, true, 80, 28, 65, 2700}, {true, false, true, true, false, 80, 28, 65, 0},
                       {true, false, true, false, true, 80, 28, 65, 2700}};
  assert(group_shows(warm2, white2700, 3));
  Presets two; two.items = {purple, warm2}; two.count = 2;
  assert(group_shown(two, white2700, 3, Light{}) == 1);
  Lamp none[1] = {{false, true, true, true, true, 0, 0, 0, 0}};
  assert(!group_shows(purple, none, 1));              // nothing available: nothing shows

  // An effect and the device's settings (a WLED's palette and speed), and the lamp's own preset (a WLED preset).
  Preset loop = make(70, 0, 280, 41, false, true);
  loop.effect = "Colorloop";
  loop.settings = {{"select.desk_color_palette", "Party", NAN}, {"number.desk_speed", "180", 180.0f}};
  Preset film; film.settings = {{"select.desk_preset", "Film", NAN}};
  assert(loop.valid() && !loop.device() && !loop.neutral());
  assert(film.valid() && film.device() && film.neutral());
  assert(!Preset{}.valid());
  Light desk{true, false, 70, 0, 280, 41, "Colorloop", {{"select.desk_color_palette", "Party", NAN}, {"number.desk_speed", "180", 180.2f},
                                                         {"select.desk_preset", "Film", NAN}}};
  assert(shows(loop, desk) && shows(film, desk));
  desk.effect = "Rainbow";
  assert(!shows(loop, desk) && shows(film, desk));
  desk.effect = "Colorloop"; desk.now[1].number = 120;
  assert(!shows(loop, desk));
  desk.now[2].text = "Lezen";
  assert(!shows(film, desk));
  // A plain key is told by its name's first characters; a coloured one by its colour (its brightness where asked for).
  Presets named; named.items = {film, loop, make(30, 0, 0, 0, false, false)}; named.count = 3;
  Preset rainbow = make(90, 0, 0, 0, false, false); rainbow.effect = "Rainbow";
  assert(named.label(film) == "Fi" && named.label(rainbow) == "Ra" && named.label(loop).empty() && named.label(named.items[2]) == "30");
  named.levels = true;
  assert(named.label(loop) == "70" && named.label(film) == "Fi");
  assert(initials("Éclair") == "Éc" && initials("A") == "A");

  std::puts("light presets ok");
  return 0;
}
