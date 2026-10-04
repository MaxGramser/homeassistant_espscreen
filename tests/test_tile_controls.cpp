#include "screen_text_en.h"
// c++ -std=c++17 -Wall -Wextra -pedantic tests/test_tile_controls.cpp -o /tmp/test_tile_controls && /tmp/test_tile_controls
#define THEME_TEST
#include "../components/smart_display/tile_controls.h"
#include <cassert>
#include <cmath>
#include <cstring>

using namespace tile_controls;
using runtime_tiles::Tile;

static Tile make(const char *entity, const char *state, uint32_t supported = 0) {
  Tile t; t.entity = entity; t.state = state; t.supported = supported; t.received = true; return t;
}

int main() {
  // -/+ steps snap to the entity's grid and stay inside its range.
  assert(step_value(20.0f, 0.5f, 16, 32, 1) == 20.5f);
  assert(step_value(20.3f, 0.5f, 16, 32, -1) == 20.0f);
  assert(step_value(31.8f, 1.0f, 16, 32, 1) == 32.0f);
  assert(step_value(16.0f, 1.0f, 16, 32, -1) == 16.0f);
  assert(step_value(NAN, 1.0f, 16, 32, 1) == 17.0f);
  assert(step_value(5.0f, 0.0f, NAN, NAN, 1) == 6.0f);
  assert(format_value(20.0f, 1.0f, "°") == "20°");
  assert(format_value(20.5f, 0.5f, "°") == "20.5°");
  assert(format_value(NAN, 0.5f, "°") == "--");

  // Curtain: horizontal arrows, open disabled when fully open, stop only when supported.
  Tile curtain = make("cover.curtains", "open", 15); curtain.device_class = "curtain"; curtain.position = 100; curtain.controls = "buttons";
  std::array<Key, 3> keys;
  assert(keys_for(curtain, keys) == 3);
  assert(!strcmp(keys[0].icon, glyph::EXPAND) && keys[0].command == COVER_OPEN && keys[0].disabled);
  assert(keys[1].command == COVER_STOP && !keys[1].disabled);
  assert(!strcmp(keys[2].icon, glyph::COLLAPSE) && keys[2].command == COVER_CLOSE && !keys[2].disabled);
  assert(key_action(curtain, COVER_CLOSE).service == "cover.close_cover");
  Tile shutter = make("cover.shutter", "closed", 3); shutter.controls = "buttons";
  assert(keys_for(shutter, keys) == 2 && !strcmp(keys[0].icon, glyph::UP) && keys[1].disabled);
  assert(status_text(curtain) == "Open · 100%");
  assert(status_text(shutter) == "Closed");

  // The cover card (firmware 0.2.50+). Motionblinds venetian blinds report every feature (255).
  Tile blind = make("cover.venetianblind_0001", "open", 255); blind.device_class = "blind"; blind.position = 60; blind.edit_extra().tilt = 40;
  CoverCard card = cover_card(blind);
  assert(card.position && card.tilt && card.keys && !card.tilt_keys);
  assert(cover_card_status(blind) == "Open · 60% · Tilt 40%");
  assert(cover_keys(blind, keys) == 3 && !strcmp(keys[0].icon, glyph::UP) && !keys[0].disabled && !keys[2].disabled && !keys[2].checked);
  blind.state = "closing";
  assert(cover_keys(blind, keys) == 3 && keys[2].checked && !keys[0].checked);
  assert(cover_tilt_keys(blind, keys) == 3 && keys[0].command == COVER_OPEN_TILT && keys[2].command == COVER_CLOSE_TILT);
  assert(key_action(blind, COVER_OPEN_TILT).service == "cover.open_cover_tilt");
  assert(key_action(blind, COVER_STOP_TILT).service == "cover.stop_cover_tilt" && key_action(blind, COVER_CLOSE_TILT).service == "cover.close_cover_tilt");
  CoverCard curtain_card = cover_card(curtain);
  assert(curtain_card.position && !curtain_card.tilt && curtain_card.keys && !curtain_card.tilt_keys);
  assert(cover_card_status(curtain) == "Open · 100%");
  // A garage door: open, stop and close only; close is disabled while it is closed.
  Tile garage = make("cover.garage", "closed", 11); garage.device_class = "garage";
  CoverCard garage_card = cover_card(garage);
  assert(!garage_card.position && !garage_card.tilt && garage_card.keys && !garage_card.tilt_keys);
  assert(cover_keys(garage, keys) == 3 && keys[2].disabled && !keys[0].disabled);
  // Slats that tilt without a position get tilt keys; a key that cannot tilt further is disabled.
  Tile slats = make("cover.slats", "open", 3 | 16 | 32); slats.edit_extra().tilt = 100;
  CoverCard slats_card = cover_card(slats);
  assert(slats_card.tilt_keys && !slats_card.tilt && !slats_card.position);
  assert(cover_tilt_keys(slats, keys) == 2 && keys[0].disabled && !keys[1].disabled);
  assert(cover_card_status(slats) == "Open");
  // Features not reported yet: the card offers the three keys, a tile's key row stays empty as before.
  Tile unknown = make("cover.new", "unknown", 0);
  CoverCard unknown_card = cover_card(unknown);
  assert(unknown_card.keys && !unknown_card.position && cover_keys(unknown, keys) == 3);
  unknown.controls = "buttons";
  assert(keys_for(unknown, keys) == 0);

  // Slat selection never replaces primary controls or invents capabilities.
  for(uint32_t flags=0;flags<256;++flags){
    Tile t=make("cover.test","open",flags);t.controls="position_tilt";
    assert(cover_tilt_selected(t)&&panel_kind(t)=="position");
    assert(panel_available(t)==bool(flags&feature::COVER_POSITION));
    t.controls="buttons_tilt";assert(panel_kind(t)=="buttons");
    assert(keys_for(t,keys)==unsigned(bool(flags&1)+bool(flags&8)+bool(flags&2)));
    for(int raw:{-100,0,255,1000,1200})for(bool tilt:{false,true}){
      const auto call=cover_position_action(t,raw,tilt);
      assert(call.valid()==(tilt?bool(flags&128):(flags==0||bool(flags&4))));  // unknown features: position still goes
      if(call.valid()){
        const int percent=(int)std::lround(std::clamp(raw,0,1000)/10.0f);
        assert(call.value==std::to_string(tilt?percent:100-percent));
        assert(call.key==(tilt?"tilt_position":"position"));
        assert(call.service==(tilt?"cover.set_cover_tilt_position":"cover.set_cover_position"));
      }
    }
    t.controls="tilt";assert(panel_kind(t).empty()&&!panel_available(t));
    assert(cover_card(t).tilt==bool(flags&128));
    assert(cover_tilt_keys(t,keys)==unsigned(bool(flags&16)+bool(flags&64)+bool(flags&32)));
  }

  auto absent=make("cover.test","unavailable",255);
  assert(!cover_position_action(absent,500,true).valid()&&!cover_position_action(absent,500,false).valid());

  // Vacuum: the state decides which key the first one is, never whether a key can be pressed (firmware 0.2.90+).
  // A robot still saying "docked" while it is already cleaning used to leave Stop and Dock unreachable, exactly
  // when they were wanted: a state word is Home Assistant's news, and news can be late.
  Tile robot = make("vacuum.s8", "docked", 30524); robot.controls = "buttons";
  assert(keys_for(robot, keys) == 3);
  assert(!strcmp(keys[0].icon, glyph::PLAY) && keys[0].command == VACUUM_START && !keys[0].disabled);
  assert(keys[1].command == VACUUM_STOP && !keys[1].disabled);
  assert(keys[2].command == VACUUM_DOCK && !keys[2].disabled);
  assert(key_action(robot, VACUUM_START).service == "vacuum.start");
  robot.state = "cleaning";
  assert(keys_for(robot, keys) == 3 && keys[0].command == VACUUM_PAUSE && !keys[1].disabled && !keys[2].disabled);
  // The one thing that does grey a key: a command of this tile is out and Home Assistant has not answered. The
  // whole row waits with it, after the same 400 ms grace the busy sheet and the cards use, and no longer than
  // the same cap. A timer's Cancel follows the same rule: idle is a state, not a reason to close the key.
  robot.begin(10000);
  assert(keys_for(robot, keys, 10000) == 3 && !keys[0].disabled);       // inside the grace: nothing flickers
  assert(keys_for(robot, keys, 10500) == 3 && keys[0].disabled && keys[1].disabled && keys[2].disabled);
  assert(keys_for(robot, keys, 20000) == 3 && !keys[0].disabled);       // the wait ran out
  robot.observe(robot.revision + 1);                                     // Home Assistant answered
  assert(keys_for(robot, keys, 10500) == 3 && !keys[0].disabled);

  Tile old_robot = make("vacuum.old", "docked", feature::VACUUM_TURN_ON | feature::VACUUM_RETURN); old_robot.controls = "buttons";
  assert(keys_for(old_robot, keys) == 2 && key_action(old_robot, VACUUM_START).service == "vacuum.turn_on");
  // Media: playback keys follow supported_features; mute flips is_volume_muted.
  Tile sonos = make("media_player.sonos", "playing", 8321599); sonos.volume = 0.17f; sonos.edit_extra().media_title = "TV"; sonos.controls = "playback";
  assert(keys_for(sonos, keys) == 3 && !strcmp(keys[1].icon, glyph::PAUSE) && keys[1].command == MEDIA_PLAY_PAUSE);
  assert(status_text(sonos) == "TV · 17%");
  Action mute = key_action(sonos, MEDIA_MUTE);
  assert(mute.service == "media_player.volume_mute" && mute.key == "is_volume_muted" && mute.value == "true");
  sonos.muted = true; assert(key_action(sonos, MEDIA_MUTE).value == "false");
  Tile radio = make("media_player.radio", "idle", feature::MEDIA_PLAY | feature::MEDIA_PAUSE); radio.controls = "playback";
  assert(keys_for(radio, keys) == 1 && !strcmp(keys[0].icon, glyph::PLAY));
  assert(status_text(radio) == "Idle");

  radio.supported=feature::MEDIA_PLAY; radio.state="idle";
  assert(key_action(radio,MEDIA_PLAY_PAUSE).service=="media_player.media_play");
  radio.state="playing";assert(keys_for(radio,keys)==1&&keys[0].disabled);assert(!key_action(radio,MEDIA_PLAY_PAUSE).valid());
  radio.supported=feature::MEDIA_PAUSE;assert(key_action(radio,MEDIA_PLAY_PAUSE).service=="media_player.media_pause");
  radio.state="idle";assert(keys_for(radio,keys)==1&&keys[0].disabled);assert(!key_action(radio,MEDIA_PLAY_PAUSE).valid());

  // Climate: one mode bar for "Mode" and for "Temperature and mode" (firmware 0.19.0), never a row of keys.
  Tile ac = make("climate.ac", "cool"); ac.edit_extra().hvac_modes = "[\"off\",\"heat_cool\",\"cool\",\"heat\",\"fan_only\",\"dry\"]"; ac.controls = "mode"; ac.current = 21.5f; ac.target = 20; ac.step = 1;
  assert(panel_kind(ac) == "mode" && !is_key_row(panel_kind(ac)) && keys_for(ac, keys) == 0);
  assert(panel_available(ac));
  std::array<Key, 6> mode_row;
  // The mode bar (firmware 0.3.3): heat and cool first, never off (the tile's circle switches it), the current mode
  // always shown.
  assert(climate_bar_keys(ac, mode_row) == 5 && mode_row[0].arg == "heat" && mode_row[1].arg == "cool" && mode_row[1].checked);
  assert(mode_row[2].arg == "heat_cool" && mode_row[3].arg == "dry" && mode_row[4].arg == "fan_only");
  for (unsigned i = 0; i < 5; ++i) assert(mode_row[i].arg != "off");
  assert(climate_bar_keys(ac, mode_row, 2) == 2 && mode_row[0].arg == "heat" && mode_row[1].arg == "cool");
  assert(climate_bar_keys(ac, mode_row, 3) == 3 && mode_row[1].arg == "cool" && mode_row[2].command == OPEN_CARD);
  Tile drying = ac; drying.state = "dry";
  assert(climate_bar_keys(drying, mode_row, 3) == 3 && mode_row[1].arg == "dry" && mode_row[1].checked && mode_row[2].command == OPEN_CARD);
  assert(climate_bar_keys(drying, mode_row, 2) == 2 && mode_row[1].arg == "dry");
  Tile radiator = ac; radiator.edit_extra().hvac_modes = "[\"off\",\"heat\"]";
  assert(climate_bar_keys(radiator, mode_row) == 0);
  assert(climate_bar_keys(ac, mode_row, 1) == 0);
  // A device with one mode besides off has no bar, so "Mode" draws nothing for it; two modes make a bar.
  assert(!panel_available(radiator));
  Tile three = ac; three.edit_extra().hvac_modes = "[\"off\",\"heat\",\"cool\"]";
  assert(panel_available(three) && climate_bar_keys(three, mode_row) == 2 && mode_row[1].arg == "cool" && mode_row[1].checked);
  Action mode = key_action(ac, HVAC_MODE, "heat");
  assert(!key_action(ac, OPEN_CARD).valid());
  assert(mode.service == "climate.set_hvac_mode" && mode.key == "hvac_mode" && mode.value == "heat");
  assert(status_text(ac) == "Cool · 21.5°");
  ac.edit_extra().hvac_action = "cooling"; assert(status_text(ac) == "Cooling · 21.5°");
  assert(edit_target(ac) == 20 && edit_step(ac) == 1);
  Action set = edit_action(ac, step_value(edit_target(ac), edit_step(ac), ac.minimum, ac.maximum, 1));
  assert(set.service == "climate.set_temperature" && set.key == "temperature" && set.value == "21");
  assert(edit_action(ac, 20.5f).value == "20.5");

  // A thermostat set to a range (firmware 0.19.0), decided as Home Assistant's thermostat card decides it: a single target
  // it supports and reports first, else a range with both ends. A -/+ edit of one end sends both.
  Tile ecobee = make("climate.ecobee", "heat_cool", 442); ecobee.step = 1;
  assert(!climate_range(ecobee));
  ecobee.edit_extra().target_low = 20; ecobee.edit_extra().target_high = 24;
  assert(climate_range(ecobee) && range_end(ecobee, RANGE_LOW) == 20 && range_end(ecobee, RANGE_HIGH) == 24);
  ecobee.edit_high = 25;
  assert(range_end(ecobee, RANGE_HIGH) == 25 && range_end(ecobee, RANGE_LOW) == 20);
  Action range = edit_action(ecobee, ecobee.edit_value);
  assert(range.service == "climate.set_temperature" && range.key == "target_temp_low" && range.value == "20" &&
         range.key2 == "target_temp_high" && range.value2 == "25");
  ecobee.edit_value = 21.5f; assert(edit_action(ecobee, ecobee.edit_value).value == "21.5");
  Tile both = ecobee; both.supported = 3; assert(climate_range(both));
  both.target = 22; assert(!climate_range(both));           // a single target it reports comes first
  Tile single = ecobee; single.supported = 385; assert(!climate_range(single));
  // The widest a thermostat's -/+ can show, to measure its face by once: 7 to 35 in halves, 45 to 95 in wholes, to 110.
  Tile halves = make("climate.halves", "heat", 1); halves.minimum = 7; halves.maximum = 35; halves.step = 0.5f;
  assert(widest_setpoint(halves) == "88.8°");
  Tile wholes = make("climate.wholes", "heat", 1); wholes.minimum = 45; wholes.maximum = 95; wholes.step = 1;
  assert(widest_setpoint(wholes) == "88°");
  wholes.maximum = 110; assert(widest_setpoint(wholes) == "888°");
  wholes.minimum = -20; wholes.maximum = 30; assert(widest_setpoint(wholes) == "-88°");
  // The room's temperature as Home Assistant sends it, not always with one decimal.
  assert(temperature_text(73) == "73°" && temperature_text(21.5f) == "21.5°" && temperature_text(21.25f) == "21.25°");

  // A humidifier (firmware 0.42.0) is a thermostat in percent: its humidity between - and +, its modes as the mode bar,
  // its words and icons Home Assistant's, its action in the line; Home Assistant's blue whether it dries or humidifies.
  Tile dry = make("humidifier.laundry", "on", 1); dry.device_class = "dehumidifier";
  dry.edit_extra().hvac_modes = "[\"normal\",\"away\"]"; dry.edit_extra().humidifier_mode = "normal"; dry.edit_extra().hvac_action = "drying";
  dry.current = 68; dry.target = 55; dry.minimum = 0; dry.maximum = 100; dry.step = 1;
  assert(thermostat(dry) && humidifier(dry) && !climate_off(dry) && accent(dry) == theme::ha::BLUE);
  assert(climate_card_status(dry, true) == "Drying · 68%" && climate_card_status(dry) == "Drying · Now 68%");
  assert(status_text(dry) == "Drying · 68%" && humidity_text(45.5f) == "45.5%" && reading_text(dry, 68) == "68%");
  assert(std::strcmp(setpoint_suffix(dry), "%") == 0 && edit_target(dry) == 55);
  const auto humid = edit_action(dry, step_value(55, 1, 0, 100, 1));
  assert(humid.service == "humidifier.set_humidity" && humid.key == "humidity" && humid.value == "56");
  assert(edit_action(dry, 54.6f).value == "55");   // Home Assistant takes a whole percentage
  assert(humidifier_named_modes(dry) && climate_modes(dry).size() == 2 && climate_rows(dry).empty());
  assert(climate_bar_keys(dry, mode_row) == 2 && mode_row[0].arg == "normal" && mode_row[0].checked && !mode_row[1].checked);
  assert(std::strcmp(mode_row[1].icon, humidifier_mode_icon("away")) == 0);
  const auto away = key_action(dry, HVAC_MODE, "away");
  assert(away.service == "humidifier.set_mode" && away.key == "mode" && away.value == "away");
  dry.controls = "setpoint"; assert(panel_available(dry));
  dry.controls = "slider"; assert(panel_available(dry));
  dry.controls = "mode"; assert(panel_available(dry));
  dry.controls = "toggle"; assert(panel_available(dry) && key_action(dry, TOGGLE).service == "humidifier.turn_off");
  dry.controls = "setpoint_mode"; assert(climate_modes_selected(dry) && panel_kind(dry) == "setpoint");
  assert(tap_route(dry, false).route == TapRoute::CARD);
  // Off: Home Assistant reports the action off, the line says so with the humidity it measures.
  Tile off = dry; off.state = "off"; off.edit_extra().hvac_action = "off";
  assert(climate_off(off) && climate_card_status(off, true) == "Off · 68%" && key_action(off, TOGGLE).service == "humidifier.turn_on");
  // Without an action or a sensor (a plain integration): On or Off alone.
  Tile plain = make("humidifier.cellar", "on"); plain.target = 60;
  assert(climate_card_status(plain, true) == "On" && climate_modes(plain).empty() && climate_bar_keys(plain, mode_row) == 0);
  // A mode of the integration's own has no icon: the card lists the modes as a row of words instead of round keys.
  Tile own = dry; own.edit_extra().hvac_modes = "[\"normal\",\"laundry\",\"auto\"]";
  assert(!humidifier_named_modes(own) && climate_modes(own).empty());
  const auto word_rows = climate_rows(own);
  assert(word_rows.size() == 1 && word_rows[0].kind == 'm' && word_rows[0].labels[1] == "laundry" && word_rows[0].labels[2] == "Auto");
  assert(climate_row_action('m', "laundry").service == "humidifier.set_mode");

  // Numbers edit their own state; selects step through their options with wrap-around.
  Tile number = make("number.target", "55"); number.minimum = 0; number.maximum = 100; number.step = 5;
  assert(edit_target(number) == 55 && edit_action(number, step_value(55, 5, 0, 100, -1)).value == "50");
  assert(edit_action(number, 50).service == "number.set_value");
  Tile select = make("select.stand", "Comfort"); select.edit_extra().options = {"Eco", "Comfort", "Boost"}; select.controls = "stepper";
  assert(panel_kind(select) == "chevrons");
  assert(keys_for(select, keys) == 2 && !keys[0].disabled);
  assert(key_action(select, SELECT_NEXT).value == "Boost" && key_action(select, SELECT_PREVIOUS).value == "Eco");
  select.state = "Boost"; assert(key_action(select, SELECT_NEXT).value == "Eco");
  select.edit_extra().options.resize(1); assert(keys_for(select, keys) == 2 && keys[0].disabled);

  // Timer, run buttons and toggles.
  Tile timer = make("timer.eggs", "active"); timer.controls = "buttons";
  assert(keys_for(timer, keys) == 2 && keys[0].command == TIMER_PAUSE && !keys[1].disabled);
  timer.state = "idle"; assert(keys_for(timer, keys) == 2 && keys[0].command == TIMER_START && !keys[1].disabled);
  assert(key_action(make("scene.evening", "unknown"), RUN).service == "scene.turn_on");
  assert(key_action(make("script.all", "off"), RUN).service == "script.turn_on");
  assert(key_action(make("input_button.bell", "unknown"), RUN).service == "input_button.press");
  assert(!strcmp(run_label("scene"), "Activate") && !strcmp(run_label("button"), "Press"));
  assert(key_action(make("switch.desk", "on"), TOGGLE).service == "switch.turn_off");
  assert(key_action(make("light.lamp", "off"), TOGGLE).service == "light.turn_on");
  assert(!key_action(make("sensor.x", "1"), TOGGLE).valid());
  assert(!key_action(make("sensor.x", "1"), RUN).valid());
  // A toggle key sends what its tap asks for and then shows the new stand; firmware 0.2.59 to 0.2.71 showed it first
  // and so sent an off light light.turn_off.
  Tile off_lamp = make("light.lamp", "off");
  assert(press_key(off_lamp, TOGGLE).service == "light.turn_on" && off_lamp.state == "on" && off_lamp.optimistic_tap);
  off_lamp.undo_optimistic(); assert(off_lamp.state == "off");
  Tile on_fan = make("fan.ceiling", "on");
  assert(press_key(on_fan, TOGGLE).service == "fan.turn_off" && on_fan.state == "off");
  Tile odd = make("sensor.x", "1");
  assert(!press_key(odd, TOGGLE).valid() && odd.state == "1" && !odd.optimistic_tap);
  Tile shut = make("cover.shutter", "closed", 3);
  assert(press_key(shut, COVER_OPEN).service == "cover.open_cover" && shut.state == "closed" && !shut.optimistic_tap);

  // Panel kinds.
  Tile lamp = make("light.lamp", "on"); lamp.controls = "brightness";
  assert(is_slider(panel_kind(lamp)) && !is_key_row(panel_kind(lamp)));
  assert(is_key_row("playback") && !is_key_row("mode") && !is_key_row("setpoint"));

  // Climate mode colours follow Home Assistant; anything else is grey.
  assert(mode_color("heat") == 0xFF6F22 && mode_color("cool") == 0x2196F3 && mode_color("off") == 0x9E9E9E);

  // Vacuum rows: the cleaning mode decides which of suction and water the card shows.
  Tile pippa = make("vacuum.s8", "docked", 30524);
  auto row = [](char kind, const char *entity, const char *current, std::vector<std::string> values, const char *roles = "") {
    runtime_tiles::Choice c; c.kind = kind; c.entity = entity; c.current = current; c.values = values; c.labels = values; c.roles = roles; return c;
  };
  pippa.edit_extra().choices = {row('m', "select.woonkamer_s8_schoonmaakmodus", "vac_and_mop", {"vacuum", "vac_and_mop", "mop", "custom"}, "vbma"),
                   row('w', "select.s8_intensiteit_van_dweilen", "intense", {"mild", "standard", "intense"}),
                   row('s', "", "", {"quiet", "balanced", "turbo", "max", "max_plus"})};
  pippa.edit_extra().fan_speed = "max";
  settle_suction(pippa.edit_extra());
  assert(pippa.choice('s')->current == "max" && pippa.extra().choices.size() == 3);
  auto rows = vacuum_rows(pippa, 0);
  assert(rows.suction && rows.water && vacuum_role(pippa, 0) == 'b');
  pippa.choice('m')->current = "mop"; rows = vacuum_rows(pippa, 0);
  assert(!rows.suction && rows.water);
  pippa.choice('m')->current = "vacuum"; rows = vacuum_rows(pippa, 0);
  assert(rows.suction && !rows.water);
  pippa.choice('m')->current = "custom"; rows = vacuum_rows(pippa, 0);
  assert(!rows.suction && !rows.water && vacuum_role(pippa, 0) == 'a');
  pippa.choice('m')->current = "something_new"; assert(vacuum_role(pippa, 0) == 'b');
  // A tapped chip shows while Home Assistant is busy, and the old value once it gave up.
  pippa.choice('m')->current = "vac_and_mop"; pippa.choice('m')->sent = "mop";
  pippa.begin(1000);
  assert(shown_value(pippa, *pippa.choice('m'), 1500) == "mop" && vacuum_rows(pippa, 1500).water && !vacuum_rows(pippa, 1500).suction);
  assert(shown_value(pippa, *pippa.choice('m'), 9000) == "vac_and_mop");
  assert(choice_action(pippa, 'm', "mop").service == "select.select_option" && choice_action(pippa, 'm', "mop").key == "option");
  assert(choice_action(pippa, 's', "turbo").service == "vacuum.set_fan_speed" && choice_action(pippa, 's', "turbo").value == "turbo");
  // An older manager sends no suction row: the vacuum's own four speeds, with the card's names.
  Tile old_robot2 = make("vacuum.old", "docked", 30524);
  old_robot2.edit_extra().fan_speeds = {"quiet", "balanced"}; old_robot2.edit_extra().fan_speed = "balanced";
  settle_suction(old_robot2.edit_extra());
  assert(old_robot2.choice('s') && old_robot2.choice('s')->labels[1] == "Normal" && old_robot2.choice('s')->current == "balanced");
  rows = vacuum_rows(old_robot2, 0);
  assert(rows.suction && !rows.water && !choice_action(old_robot2, 'm', "mop").valid());

  // Binary sensors (firmware 0.2.53+) in the words of their device class, Home Assistant's own since app 0.2.90 (the
  // English table of the tests); no class or an unknown one says On and Off.
  assert(!strcmp(binary_state_text("door", true), "Open") && !strcmp(binary_state_text("door", false), "Closed"));
  assert(!strcmp(binary_state_text("motion", true), "Detected") && !strcmp(binary_state_text("motion", false), "Clear"));
  assert(!strcmp(binary_state_text("moisture", true), "Wet") && !strcmp(binary_state_text("moisture", false), "Dry"));
  assert(!strcmp(binary_state_text("battery_charging", false), "Not charging") && !strcmp(binary_state_text("battery", true), "Low"));
  assert(!strcmp(binary_state_text("", true), "On") && !strcmp(binary_state_text("", false), "Off"));
  assert(!strcmp(binary_state_text("future_class", true), "On") && !strcmp(binary_state_text("Door", true), "On"));

  // Tap routing (firmware 0.2.58). `legacy` is runtime_tiles::event() of firmware 0.2.56, line by line: every tap
  // choice an existing layout can hold must route exactly as before, so no screen changes behaviour on the update.
  struct Legacy { TapRoute route; std::string service; bool busy; };
  auto legacy = [](const Tile &tile, bool hold) -> Legacy {
    const std::string d = tile.domain();
    if (tile.tap == "none") return {TapRoute::NONE, "", false};
    bool open = hold || d == "climate" || d == "vacuum" || d == "cover";
    if (!hold && tile.tap == "detail") open = true;
    if (!hold && tile.tap == "toggle") open = false;
    if (d == "media_player" && tile.tap == "toggle" && !hold) return {TapRoute::ACTION, "media_player.toggle", false};
    if (d == "climate" && tile.tap == "toggle" && !hold) return {TapRoute::ACTION, "climate.toggle", false};
    if (d == "timer" && !open) return {TapRoute::ACTION, tile.state == "active" ? "timer.pause" : "timer.start", false};
    if (d == "sensor" || d == "binary_sensor" || d == "weather" || d == "number" || d == "input_number" || d == "select" ||
        d == "input_select" || d == "media_player" || d == "vacuum" || d == "cover" || d == "sun" || d == "person" || d == "timer")
      return {TapRoute::CARD, "", true};
    // A thermostat joined the computed cards in 0.2.9x: it opens CARD, and marks the tile busy while it opens,
    // like the vacuum and the cover beside it. Every other domain still routes exactly as firmware 0.2.56 did.
    if (d == "climate" && open) return {TapRoute::CARD, "", true};
    // A light that only dims and a fan joined them in 0.2.80: the card with the standing slider is the runtime's
    // now, so they open CARD and mark the tile busy while it opens. A light with a colour or a colour
    // temperature keeps the board's own colour card (OVERLAY), which is what these tiles have no modes for.
    if (open && (d == "light" || d == "fan") && !light_colour(tile)) return {TapRoute::CARD, "", true};
    if (open) return d == "light" || d == "vacuum" || d == "fan" ? Legacy{TapRoute::OVERLAY, "", true} : Legacy{TapRoute::CARD, "", false};
    if (d == "light" || d == "switch" || d == "input_boolean" || d == "fan") return {TapRoute::ACTION, d + ".toggle", false};
    if (d == "scene" || d == "script") return {TapRoute::ACTION, d + ".turn_on", false};
    if (d == "button" || d == "input_button") return {TapRoute::ACTION, d + ".press", false};
    return {TapRoute::NONE, "", false};
  };
  const char *domains[] = {"light", "switch", "input_boolean", "scene", "script", "climate", "vacuum", "fan", "cover", "sensor",
                           "binary_sensor", "input_select", "select", "number", "input_number", "weather", "media_player",
                           "button", "input_button", "sun", "timer", "person"};
  // What validate_layout accepted before 0.2.67: `toggle` only on these six domains.
  auto toggled_before = [](const std::string &d) {
    return d == "light" || d == "switch" || d == "input_boolean" || d == "fan" || d == "media_player" || d == "climate";
  };
  int compared = 0;
  // "action" without an action (an app before 0.2.67) taps like firmware 0.2.56 did with a value it didn't know: automatically.
  for (const char *domain : domains) for (const char *choice : {"auto", "detail", "toggle", "none", "action"})
    for (const char *state : {"on", "off", "active", "idle", "open"}) for (bool hold : {false, true}) {
      Tile tile = make((std::string(domain) + ".x").c_str(), state);
      tile.tap = choice;
      Tap now = tap_route(tile, hold);
      if (std::string(choice) == "toggle" && !toggled_before(domain)) {
        // New in 0.2.58: a short tap toggles any entity the app allowed it for; holding still opens the card as before.
        if (!hold) { assert(now.route == TapRoute::ACTION && now.service == std::string(domain) + ".toggle"); continue; }
      }
      Legacy before = legacy(tile, hold);
      assert(now.route == before.route && now.service == before.service);
      if (now.route != TapRoute::ACTION) assert(now.busy == before.busy);
      ++compared;
    }
  assert(compared == 1020);  // 22 domains x 5 choices x 5 states x 2 gestures, less the 80 new short toggles
  // The example of issue #7: a short tap on a cover set to On / off sends cover.toggle; holding opens its card.
  Tile issue7 = make("cover.curtain", "open", feature::COVER_OPEN | feature::COVER_CLOSE | feature::COVER_STOP);
  issue7.tap = "toggle";
  assert(tap_route(issue7, false).route == TapRoute::ACTION && tap_route(issue7, false).service == "cover.toggle");
  assert(tap_route(issue7, true).route == TapRoute::CARD);
  issue7.tap = "auto";
  assert(tap_route(issue7, false).route == TapRoute::CARD && tap_route(issue7, false).busy);
  // An action of the tile's own choosing (firmware 0.2.58): a short tap performs it, holding still opens the card.
  issue7.tap = "action";
  issue7.edit_extra().action = "cover.set_cover_position";
  issue7.edit_extra().action_data = {{"position", "50"}};
  assert(tap_route(issue7, false).route == TapRoute::CUSTOM && tap_route(issue7, false).service == "cover.set_cover_position");
  assert(tap_route(issue7, true).route == TapRoute::CARD);
  // A lock (firmware 0.5.0): a tap is its own (lock at once, or ask before unlocking), holding or "detail" opens the
  // card, "none" does nothing; its colours are Home Assistant's, green while locked although it is inactive.
  {
    Tile lock = make("lock.front_door", "locked");
    assert(tap_route(lock, false).route == TapRoute::LOCK && tap_route(lock, true).route == TapRoute::CARD);
    lock.tap = "detail";
    assert(tap_route(lock, false).route == TapRoute::CARD);
    lock.tap = "none";
    assert(tap_route(lock, false).route == TapRoute::NONE);
    assert(!make("lock.a", "locked").active() && make("lock.a", "unlocked").active() && make("lock.a", "jammed").active());
    assert(accent(make("lock.a", "locked")) == theme::ha::GREEN && accent(make("lock.a", "unlocking")) == theme::ha::ORANGE &&
           accent(make("lock.a", "jammed")) == theme::ha::RED && accent(make("lock.a", "open")) == theme::ha::RED);
  }
  // An automation (firmware 0.7.0, GitHub #62): a tap switches it on or off and holding runs its actions (Home Assistant's
  // Run actions, automation.trigger); set to "run" the other way round. Coloured as Home Assistant does: amber while on,
  // grey while off; a run button only while its actions run, whether the automation is on or off.
  {
    Tile automation = make("automation.curtains", "on");
    assert(runtime_tiles::valid_entity("automation.curtains"));
    Tap tap = tap_route(automation, false), held = tap_route(automation, true);
    assert(tap.route == TapRoute::ACTION && tap.service == "automation.toggle");
    assert(held.route == TapRoute::ACTION && held.service == "automation.trigger");
    automation.tap = "toggle";
    assert(tap_route(automation, false).service == "automation.toggle" && tap_route(automation, true).service == "automation.trigger");
    automation.tap = "run";
    tap = tap_route(automation, false); held = tap_route(automation, true);
    assert(tap.route == TapRoute::ACTION && tap.service == "automation.trigger");
    assert(held.route == TapRoute::ACTION && held.service == "automation.toggle");
    automation.tap = "none";
    assert(tap_route(automation, false).route == TapRoute::NONE && tap_route(automation, true).route == TapRoute::NONE);
    automation.tap = "detail";
    assert(tap_route(automation, false).route == TapRoute::CARD && tap_route(automation, true).route == TapRoute::CARD);
    automation.tap = "action";
    automation.edit_extra().action = "automation.turn_off";
    assert(tap_route(automation, false).route == TapRoute::CUSTOM && tap_route(automation, true).service == "automation.trigger");
    // "run" is an automation's alone: a script set to it (a stored value it never gets) taps as before.
    Tile script = make("script.x", "off"); script.tap = "run";
    assert(!script.runs() && tap_route(script, false).service == "script.turn_on");
    // The keys of a wide or tall card: the switch and the run button.
    Tile on = make("automation.a", "on"), off = make("automation.a", "off");
    assert(key_action(on, TOGGLE).service == "automation.turn_off" && key_action(off, TOGGLE).service == "automation.turn_on");
    assert(key_action(on, RUN).service == "automation.trigger" && key_action(on, RUN).key.empty());
    assert(!strcmp(run_label("automation"), "Run"));
    on.controls = "toggle"; assert(panel_available(on));
    on.controls = "run"; assert(panel_available(on));
    // Colours: on amber, off grey, unavailable grey.
    assert(on.active() && !off.active() && !make("automation.a", "unavailable").active());
    assert(accent(on) == theme::ha::AMBER);
    Tile button = make("automation.a", "on"); button.tap = "run";
    assert(button.runs() && !button.active());
    button.running = true; assert(button.active());
    Tile idle_off = make("automation.a", "off"); idle_off.tap = "run"; idle_off.running = true;
    assert(idle_off.active());
    idle_off.running = false; assert(!idle_off.active());
  }
  // A remote (firmware 0.22.0, GitHub #117): a tap opens its card, as Home Assistant's tile card opens its dialog; the
  // tap option "toggle" switches it. Amber while on, grey while off (state_color.ts: --state-active-color).
  {
    Tile remote = make("remote.living_room", "on");
    assert(runtime_tiles::valid_entity("remote.living_room"));
    Tap tap = tap_route(remote, false), held = tap_route(remote, true);
    assert(tap.route == TapRoute::CARD && held.route == TapRoute::CARD);
    remote.tap = "toggle";
    assert(tap_route(remote, false).route == TapRoute::ACTION && tap_route(remote, false).service == "remote.toggle");
    assert(tap_route(remote, true).route == TapRoute::CARD);
    remote.tap = "action";
    remote.edit_extra().action = "remote.send_command";
    assert(tap_route(remote, false).route == TapRoute::CUSTOM && tap_route(remote, false).service == "remote.send_command");
    Tile on = make("remote.a", "on"), off = make("remote.a", "off");
    assert(key_action(on, TOGGLE).service == "remote.turn_off" && key_action(off, TOGGLE).service == "remote.turn_on");
    on.controls = "toggle"; assert(panel_available(on));
    assert(on.active() && !off.active() && !make("remote.a", "unavailable").active());
    assert(accent(on) == theme::ha::AMBER);
  }
  assert(runtime_tiles::valid_action("cover.toggle") && runtime_tiles::valid_action("sonos.snapshot") && runtime_tiles::valid_action("homeassistant.turn_on"));
  assert(!runtime_tiles::valid_action("cover") && !runtime_tiles::valid_action("Cover.toggle") && !runtime_tiles::valid_action("a.b.c") &&
         !runtime_tiles::valid_action(".toggle") && !runtime_tiles::valid_action("cover.") && !runtime_tiles::valid_action("cover.to ggle"));
  // Home Assistant's state colours (firmware 0.2.71+): what a tile shows while it is active; inactive is grey.
  {
    using namespace theme::ha;
    auto colour = [](const char *entity, const char *state, const char *device_class = "", const char *unit = "") {
      Tile t = make(entity, state); t.device_class = device_class; t.unit = unit; return accent(t);
    };
    assert(colour("climate.a", "cool") == BLUE && colour("climate.a", "heat") == DEEP_ORANGE && colour("climate.a", "dry") == ORANGE);
    assert(colour("climate.a", "fan_only") == CYAN && colour("climate.a", "auto") == GREEN && colour("climate.a", "heat_cool") == AMBER);
    assert(colour("climate.a", "eco") == AMBER);  // a mode Home Assistant has no colour for: its active colour
    for (const char *alarm : {"battery", "carbon_monoxide", "gas", "heat", "lock", "moisture", "problem", "safety", "smoke", "sound", "tamper"})
      assert(alarm_class(alarm) && colour("binary_sensor.a", "on", alarm) == RED);
    for (const char *calm : {"door", "window", "motion", "occupancy", "opening", "plug", "battery_charging", ""})
      assert(!alarm_class(calm) && colour("binary_sensor.a", "on", calm) == AMBER);
    assert(colour("sensor.a", "70", "battery", "%") == GREEN && colour("sensor.a", "69.5", "battery", "%") == ORANGE);
    assert(colour("sensor.a", "30", "battery", "%") == ORANGE && colour("sensor.a", "29.9", "battery", "%") == RED);
    assert(colour("sensor.a", "low", "battery") == BLUE && colour("sensor.a", "5%", "battery", "%") == TEAL);  // no number
    assert(colour("sensor.a", "50", "humidity", "%") == TEAL && colour("sensor.a", "21", "temperature", "°C") == DEEP_ORANGE);
    assert(colour("script.a", "on") == AMBER && colour("timer.a", "active") == AMBER && colour("camera.a", "streaming") == AMBER);
    assert(colour("light.a", "on") == AMBER && colour("switch.a", "on") == AMBER && colour("input_boolean.a", "on") == AMBER);
    assert(colour("scene.a", "2026-09-18T20:00:00+00:00") == PURPLE && colour("cover.a", "open") == PURPLE);
    assert(colour("select.a", "eco") == INDIGO && colour("number.a", "3") == TEAL && colour("fan.a", "on") == CYAN);
    assert(colour("media_player.a", "playing") == LIGHT_BLUE && colour("vacuum.a", "cleaning") == TEAL && colour("vacuum.a", "error") == RED);
    assert(colour("person.a", "home") == GREEN && colour("person.a", "Work") == BLUE);
    assert(colour("sun.sun", "above_horizon") == AMBER && colour("sun.sun", "below_horizon") == INDIGO);
    assert(colour("screen.clock", "") == BLUE && colour("image.a", "unknown") == BLUE && colour("button.a", "unknown") == BLUE);
    // Every condition Home Assistant's weather knows, in its colour.
    assert(weather_color("sunny") == AMBER && weather_color("clear-night") == DEEP_PURPLE && weather_color("partlycloudy") == BLUE_GREY);
    assert(weather_color("cloudy") == LIGHT_GREY && weather_color("fog") == GREY && weather_color("rainy") == BLUE);
    assert(weather_color("pouring") == INDIGO && weather_color("snowy") == ICE && weather_color("snowy-rainy") == LIGHT_BLUE);
    assert(weather_color("hail") == CYAN && weather_color("lightning") == YELLOW && weather_color("lightning-rainy") == LIME);
    assert(weather_color("windy") == GREEN && weather_color("windy-variant") == GREEN && weather_color("exceptional") == RED);
    assert(weather_color("something-new") == AMBER && colour("weather.a", "pouring") == INDIGO);
  }
  // Fan and swing settings in Home Assistant's words where it names them, an integration's own as its name.
  assert(climate_setting_text('f', "low") == "Low" && climate_setting_text('s', "both") == "Both");
  assert(climate_setting_text('f', "quiet_night") == "Quiet night" && climate_setting_text('s', "low") == "Low");
  // Tall panels retain their chosen group but suppress unavailable capabilities.
  Tile limited = make("light.relay", "on"); limited.controls="brightness"; limited.modes="[\"onoff\"]";
  assert(!panel_available(limited)); limited.modes="[\"brightness\"]"; assert(panel_available(limited));
  limited=make("cover.blind","open",3); limited.controls="position"; assert(!panel_available(limited));
  limited.supported=4; assert(panel_available(limited));
  limited=make("fan.simple","on",0); limited.controls="speed"; assert(!panel_available(limited));
  limited.supported=1; assert(panel_available(limited));
  // A range thermostat has the -/+ too, with the chip for its end (firmware 0.19.0), as Home Assistant's tile has its target
  // temperature feature for one; a thermostat without a temperature to set has none.
  limited=make("climate.range","heat_cool",2); limited.controls="setpoint"; assert(panel_available(limited));
  limited.supported=0; assert(!panel_available(limited));
  limited.supported=1; assert(panel_available(limited));
  limited=make("media_player.mute","playing",8); limited.controls="volume"; assert(panel_available(limited));
  limited.controls="playback"; assert(!panel_available(limited));
  limited.supported=16; assert(panel_available(limited));
  limited.state="unavailable"; assert(!panel_available(limited));
  return 0;
}
