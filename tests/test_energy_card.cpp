#include "screen_text_en.h"
// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_energy_card.cpp -o /tmp/test_energy_card && /tmp/test_energy_card
#include "../components/smart_display/energy_card.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <string>

using namespace energy_card;

// Roboto's line is 1.17 of its size; widths in em, near enough for layout. A glyph of the icon font is one em.
static int line(int size) { return (int) std::lround(size * 1.172); }
static int wide(const std::string &s, int size) {
  double em = 0;
  for (size_t i = 0; i < s.size(); ++i) {
    const unsigned char c = s[i];
    if (c >= 0xF0) { em += 1.0; i += 3; }
    else if (c == ' ') em += 0.25;
    else if (c == '%') em += 0.73;
    else if (c >= 'A' && c <= 'Z') em += 0.65;
    else if ((c & 0xC0) != 0x80) em += 0.56;
  }
  return (int) std::lround(em * size);
}

// A board's look, density and the energy card's room (content of the card) for a few sizes.
struct Board {
  const char *name;
  int dpi;
  bool standard;
  struct Size { const char *name; int w, h; bool fits; } sizes[3];
};
static const Board BOARDS[] = {
    {"cyd", 143, false, {{"2x2", 286, 94, false}, {"full", 286, 151, true}, {nullptr, 0, 0, false}}},
    {"cyd standing", 143, false, {{"1x2", 208, 106, false}, {"1x3", 208, 169, true}, {"full", 206, 232, true}}},
    {"guition", 170, true, {{"2x2", 424, 223, true}, {"full", 424, 353, true}, {nullptr, 0, 0, false}}},
    {"waveshare 4.3", 217, true, {{"2x2", 478, 203, false}, {"full", 738, 326, true}, {nullptr, 0, 0, false}}},
    {"waveshare 7", 133, true, {{"2x2", 364, 178, true}, {"3x3", 560, 280, true}, {"full", 756, 382, true}}},
    {"guition p4", 149, true, {{"2x2", 474, 257, true}, {"3x3", 727, 401, true}, {"full", 1230, 687, true}}},
};

static Measure measure(const Board &b) {
  ui::configure(b.dpi, b.standard ? "standard" : "compact");
  const double scale = b.dpi / double(b.standard ? 170 : 143);
  auto sz = [&](int n) { return (int) std::lround(n * scale); };
  // The looks' font sizes (packages/looks): watch value, headline, sublabel big, sublabel; icon, mini, watch icon.
  const int sizes[FACES] = {sz(b.standard ? 38 : 22), sz(b.standard ? 27 : 18), sz(b.standard ? 21 : 14), sz(b.standard ? 16 : 11),
                            sz(b.standard ? 42 : 28), sz(b.standard ? 26 : 18), sz(b.standard ? 18 : 12)};
  Measure m;
  for (int f = 0; f < FACES; ++f) m.line[f] = f >= ICON ? sizes[f] : line(sizes[f]);
  m.width = [sizes](Face f, const std::string &s) { return wide(s, sizes[f]); };
  return m;
}

// The card's words as the screen gives them (screen.energy.* in English).
static Words W() {
  Words w;
  w.solar = "Solar"; w.grid = "Grid"; w.battery = "Battery"; w.home = "Home"; w.other = "Other";
  return w;
}

// The noon of the bench house: sun 5.2 kW, the battery charging 1.5 kW, 1.2 kW to the grid, four devices.
static Data noon() {
  Data d;
  d.solar = d.grid = d.battery = true;
  d.solar_w = 5200; d.to_grid = 1200; d.to_battery = 1500; d.home = 2500; d.soc = 64;
  d.s2h = 2500; d.s2g = 1200; d.s2b = 1500;
  d.solar_entity = "sensor.inverter_solar_power"; d.grid_entity = "sensor.p1_meter_power"; d.battery_entity = "sensor.battery_power";
  d.devices = {{"Washing Machine Power", "sensor.washing_machine_power", 0xF072A, 1200}, {"Heat Pump Power", "sensor.heat_pump_power", 0xF1A43, 600},
               {"Office Power", "sensor.office_power", 0, 180}, {"Fridge Power", "sensor.fridge_power", 0xF0290, 85}};
  return d;
}
static Data night_car() {  // 11.4 kW from the grid, the widest number a house shows
  Data d;
  d.solar = d.grid = d.battery = true;
  d.from_grid = 11400; d.home = 11400; d.g2h = 11400; d.soc = 15;
  d.devices = {{"EV", "sensor.wallbox_charging_power", 0xF0B6C, 11000}, {"Heat Pump Power", "sensor.heat_pump_power", 0xF1A43, 200}};
  return d;
}
static Data busy() {  // seven devices at once
  Data d = night_car();
  d.from_grid = 6345; d.from_battery = 3000; d.home = 9345; d.g2h = 6345; d.b2h = 3000; d.soc = 58;
  d.devices = {{"EV", "", 0xF0B6C, 3700}, {"Oven Power", "", 0, 2000}, {"Dishwasher Power", "", 0, 1800}, {"Heat Pump Power", "", 0, 1200},
               {"Washing Machine Power", "", 0, 500}, {"TV Power", "", 0, 120}, {"Fridge Power", "", 0, 85}};
  return d;
}

struct Box { float x0, y0, x1, y1; };
static Box glyphs(const Text &t, const Measure &m, const Board &b) {
  // The letters, not the line's leading: 18 % to 88 % of the line, as the add-on's audit takes them.
  ui::configure(b.dpi, b.standard ? "standard" : "compact");
  const int tw = m.width(t.face, t.s);
  const float x = t.centre ? t.x + (t.w - tw) / 2.f : t.x;
  const float h = m.line[t.face];
  return {x, t.y + h * 0.18f, x + tw, t.y + h * 0.88f};
}

static int checks = 0;
static void check(bool ok, const char *what, const Board &b, const char *size) {
  ++checks;
  if (!ok) { std::printf("FAIL %s on %s %s\n", what, b.name, size); assert(false); }
}

static void audit(const Scene &sc, const Measure &m, const Board &b, const char *size, int w, int h) {
  // Inside the card.
  for (auto &c : sc.circles) check(c.c.x - c.d / 2.f >= -0.5f && c.c.x + c.d / 2.f <= w + 0.5f && c.c.y - c.d / 2.f >= -0.5f && c.c.y + c.d / 2.f <= h + 0.5f, "circle inside the card", b, size);
  std::vector<std::pair<Box, int>> outside;  // words outside circles, with their circle or -1
  for (auto &t : sc.texts) {
    const Box g = glyphs(t, m, b);
    check(g.x0 >= -0.5f && g.x1 <= w + 0.5f && g.y0 >= -0.5f && g.y1 <= h + 0.5f, "word inside the card", b, size);
    const float mx = (g.x0 + g.x1) / 2, my = (g.y0 + g.y1) / 2;
    int owner = -1;
    for (size_t i = 0; i < sc.circles.size(); ++i) {
      const auto &c = sc.circles[i];
      if (std::hypot(mx - c.c.x, my - c.c.y) < c.d / 2.f) owner = int(i);
    }
    if (owner >= 0) {  // inside its ring: half width against the half chord at the glyphs' top and bottom
      const auto &c = sc.circles[owner];
      const float r_in = c.d / 2.f - std::max(2.f, c.d / 40.f);
      for (float yy : {g.y0, g.y1}) {
        const float dy = std::fabs(yy - c.c.y), half = std::sqrt(std::max(0.f, r_in * r_in - dy * dy));
        check(g.x0 >= c.c.x - half - 1 && g.x1 <= c.c.x + half + 1, "word inside its ring", b, size);
      }
    } else {
      for (auto &c : sc.circles) {  // 3 px of air to every circle
        const float nx = std::min(std::max(c.c.x, g.x0), g.x1), ny = std::min(std::max(c.c.y, g.y0), g.y1);
        check(std::hypot(nx - c.c.x, ny - c.c.y) >= c.d / 2.f + 2, "word clear of the circles", b, size);
      }
      check(sc.cut || t.s.find("...") == std::string::npos, "no name cut off where one fits whole", b, size);
      check(m.width(t.face, t.s) <= t.w + 2, "a name fits its width", b, size);
    }
    outside.push_back({g, owner});
  }
  for (size_t i = 0; i < outside.size(); ++i)
    for (size_t j = i + 1; j < outside.size(); ++j) {
      if (outside[i].second >= 0 && outside[i].second == outside[j].second) continue;  // one circle's stacked lines
      const Box &a = outside[i].first, &c = outside[j].first;
      const bool apart = a.x1 + 2 <= c.x0 || c.x1 + 2 <= a.x0 || a.y1 <= c.y0 || c.y1 <= a.y0;
      check(apart, "words apart", b, size);
    }
  // The dots run on their lines: every point of a path is the middle of a drawn line or turn.
  for (auto &f : sc.flows) {
    for (int k = 0; k <= 20; ++k) {
      const P p = along(f.path, k / 20.f);
      check(p.x > -sc.d && p.x < w + sc.d && p.y > -sc.d && p.y < h + sc.d, "a dot stays on the card", b, size);
    }
    check(f.seconds >= 0.75f && f.seconds <= 6.f, "a dot's pace", b, size);
  }
}

int main() {
  // Numbers as power-flow-card-plus writes them.
  assert(power(0) == "0 W");
  assert(power(453.4f) == "453 W");
  assert(power(999.4f) == "999 W");
  assert(power(999.6f) == "1 kW");
  assert(power(2550) == "2.6 kW");
  assert(power(-1200) == "1.2 kW");
  assert(power(11400) == "11.4 kW");
  assert(power(2550, ',') == "2,6 kW" && power(450, ',') == "450 W");  // the screen's own decimal mark
  assert(std::fabs(duration(0) - 6.f) < 0.01f && std::fabs(duration(1000) - 3.375f) < 0.01f && duration(5000) == 0.75f);
  assert(battery_glyph(64) == 0xF007F && battery_glyph(100) == 0xF0079 && battery_glyph(3) == 0xF008E);

  for (auto &b : BOARDS) {
    const Measure m = measure(b);
    for (auto &size : b.sizes) {
      if (!size.name) continue;
      for (const Data &data : {noon(), night_car(), busy()}) {
        ui::configure(b.dpi, b.standard ? "standard" : "compact");
        const Scene sc = build(data, m, size.w, size.h, W());
        check(sc.ok == size.fits, size.fits ? "the diagram fits" : "too small says so", b, size.name);
        check(offered(size.w, size.h) == size.fits, "the editor offers the sizes that fit", b, size.name);
        if (!sc.ok) continue;
        audit(sc, m, b, size.name, size.w, size.h);
      }
    }
  }
  // Every card the editor offers fits (offered, web/src/model/ui-scale.ts energyFits): on each density and look a board
  // has (boards.json), from the least room up, wide or narrow, lying or standing.
  {
    const struct { int dpi; bool standard; } looks[] = {{143, false}, {146, false}, {133, true}, {149, true}, {165, true},
                                                         {170, true}, {187, true}, {217, true}, {294, true}};
    for (auto &l : looks) {
      const Board b{"density", l.dpi, l.standard, {}};
      const Measure m = measure(b);
      ui::configure(l.dpi, l.standard ? "standard" : "compact");
      const int w0 = ui::mm(MIN_WIDTH_MM), h0 = ui::mm(l.standard ? MIN_HEIGHT_MM_STANDARD : MIN_HEIGHT_MM_COMPACT);
      for (int w : {w0, w0 + ui::mm(7), ui::mm(55), ui::mm(90), ui::mm(160)})
        for (int h : {h0, h0 + 1, h0 + ui::mm(3), h0 + ui::mm(9), ui::mm(60), ui::mm(110)})
          for (const Data &data : {noon(), night_car(), busy()}) {
            ui::configure(l.dpi, l.standard ? "standard" : "compact");
            assert(offered(w, h));
            const Scene sc = build(data, m, w, h, W());
            check(sc.ok, "an offered size fits", b, "sweep");
            audit(sc, m, b, "sweep", w, h);
          }
    }
  }
  // A house whose biggest device has a long name still shows its devices: whole where they fit, else cut (Guition page).
  {
    const Board &g = BOARDS[2];
    const Measure m = measure(g);
    ui::configure(g.dpi, "standard");
    const Scene sc = build(noon(), m, 424, 353, W());
    assert(sc.ok && sc.devices >= 2);
  }
  // A tall, narrow card turns the diagram; a wide one keeps it lying.
  {
    const Board &cyd = BOARDS[1];
    const Measure m = measure(cyd);
    assert(build(noon(), m, 206, 232, W()).vertical);
    const Board &g = BOARDS[2];
    const Measure mg = measure(g);
    assert(!build(noon(), mg, 424, 223, W()).vertical);
  }
  // Seven devices on the 10-inch: three of them and Other with the rest.
  {
    const Board &p4 = BOARDS[5];
    const Measure m = measure(p4);
    ui::configure(p4.dpi, "standard");
    const Scene sc = build(busy(), m, 1230, 687, W());
    assert(sc.devices == 4);
    bool other = false;
    for (auto &t : sc.texts) other |= t.s == "Other";
    assert(other);
  }
  // With more devices than places the biggest keep one, in the order Home Assistant lists them; the rest are Other.
  {
    const Board &p4 = BOARDS[5];
    const Measure m = measure(p4);
    ui::configure(p4.dpi, "standard");
    Data d = busy();
    std::rotate(d.devices.begin(), d.devices.end() - 1, d.devices.end());  // the fridge (85 W) listed first
    const Scene sc = build(d, m, 1230, 687, W());
    std::vector<std::string> names;
    for (auto &t : sc.texts) if (t.s == "EV" || t.s == "Oven Power" || t.s == "Dishwasher Power" || t.s == "Fridge Power" || t.s == "Other") names.push_back(t.s);
    assert(sc.devices == 4);
    assert((names == std::vector<std::string>{"EV", "Oven Power", "Dishwasher Power", "Other"}));
  }
  // A tap finds the circle and its sensor; the house has none.
  {
    const Board &g = BOARDS[2];
    const Measure m = measure(g);
    ui::configure(g.dpi, "standard");
    const Scene sc = build(noon(), m, 424, 353, W());
    const Circle *solar = nullptr;
    for (auto &c : sc.circles) if (c.entity == "sensor.inverter_solar_power") solar = &c;
    assert(solar);
    const Circle *found = hit(sc, solar->c.x + 2, solar->c.y - 3, ui::mm(7));
    assert(found && found->entity == "sensor.inverter_solar_power");
  }
  std::printf("energy card: %d checks passed\n", checks);
  return 0;
}
