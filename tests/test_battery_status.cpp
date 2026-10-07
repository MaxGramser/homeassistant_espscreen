// The battery in the top bar (firmware 0.41.0, docs/BATTERY.md): Home Assistant's icon for a level and whether it
// charges (frontend src/common/entity/battery_icon.ts, batteryLevelIcon), what the item shows, and when "Only when low"
// shows it (battery_status.h, header_bar.h).
#include "screen_text_en.h"
#include "components/smart_display/header_bar.h"
#include <cassert>
#include <cmath>
#include <cstdio>
using battery_status::icon;
using header_bar::Device;
using header_bar::Item;
using header_bar::Kind;

int main() {
  // No number: battery-unknown, charging or not.
  assert(icon(NAN, false) == 0xF0091 && icon(NAN, true) == 0xF0091);
  // The level in tens, halves up as JavaScript's Math.round does; the full battery from 95 %.
  assert(icon(100, false) == 0xF0079 && icon(95, false) == 0xF0079);
  assert(icon(94, false) == 0xF0082);                                // battery-90
  assert(icon(76, false) == 0xF0081);                                // battery-80, the preview's battery
  assert(icon(15, false) == 0xF007B && icon(14.9f, false) == 0xF007A);  // battery-20, battery-10
  assert(icon(5.1f, false) == 0xF007A);                              // over 5 % still battery-10
  // 5 % or less: the alert outline.
  assert(icon(5, false) == 0xF10CD && icon(0, false) == 0xF10CD);
  // Charging from 10 % up: the charging icon of the same ten; the full one at 95 % and over.
  assert(icon(10, true) == 0xF089C && icon(14, true) == 0xF089C);    // battery-charging-10
  assert(icon(15, true) == 0xF0086);                                 // battery-charging-20
  assert(icon(50, true) == 0xF089D && icon(70, true) == 0xF089E);    // battery-charging-50, -70
  assert(icon(95, true) == 0xF0084 && icon(100, true) == 0xF0084);   // battery-charging
  // Charging under 10 %: the charging outline.
  assert(icon(9.9f, true) == 0xF089F && icon(0, true) == 0xF089F);
  // Every ten has its own glyph, none of them 0.
  for (int level = 0; level <= 100; ++level) assert(icon(level, false) && icon(level, true));

  // Low: a reading at or under 20 %, charging or not; no reading is nothing to warn about yet.
  battery_status::Reading r;
  r.present = true;
  r.level = 20;
  assert(battery_status::low(r));
  r.charging = 1;
  assert(battery_status::low(r));
  r.level = 21;
  assert(!battery_status::low(r));
  r.level = NAN;
  assert(!battery_status::low(r));

  // The top bar's battery item: Home Assistant's icon, the percentage when asked, only on a screen with a battery.
  Item battery;
  battery.kind = header_bar::kind("battery");
  assert(battery.kind == Kind::battery);
  Device device{true, -58, true};
  assert(!header_bar::device_item(battery, device).shown);  // no battery on this screen
  device.battery.present = true;
  device.battery.level = 76;
  device.battery.charging = 0;
  auto shown = header_bar::device_item(battery, device);
  assert(shown.shown && shown.icon == 0xF0081 && shown.text.empty());
  battery.text = "%";
  assert(header_bar::device_item(battery, device).text == "76%");
  device.battery.level = 75.5f;
  assert(header_bar::device_item(battery, device).text == "76%");
  device.battery.charging = 1;
  assert(header_bar::device_item(battery, device).icon == 0xF008A);  // battery-charging-80
  // Without a reading yet: battery-unknown and no number.
  device.battery.level = NAN;
  shown = header_bar::device_item(battery, device);
  assert(shown.shown && shown.icon == 0xF0091 && shown.text.empty());
  // Only when low: gone above 20 %, there at 20 % or less.
  battery.only_weak = true;
  device.battery.charging = 0;
  device.battery.level = 64;
  assert(!header_bar::device_item(battery, device).shown);
  device.battery.level = 18;
  shown = header_bar::device_item(battery, device);
  assert(shown.shown && shown.icon == 0xF007B && shown.text == "18%");

  // What find_battery() hands over: no battery until a level is there, then its reading, clamped to 0 to 100.
  assert(!battery_status::read().present);
  float level = 104;
  battery_status::level = [&level]() { return level; };
  auto read = battery_status::read();
  assert(read.present && read.level == 100 && read.charging == -1);
  level = NAN;
  assert(std::isnan(battery_status::read().level));
  battery_status::charging = []() { return 1; };
  level = 42;
  read = battery_status::read();
  assert(read.level == 42 && read.charging == 1);

  std::puts("test_battery_status: PASS");
  return 0;
}
