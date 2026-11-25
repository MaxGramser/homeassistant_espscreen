// The open card: its labels, keys and sliders, and the commands they send.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the rules themselves, which are plain C++ without LVGL in overlay_card.h, detail_bar.h.
// What proves it: web/wasm/test_runtime.mjs.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// `closed`: the slider holds the closed share (every position slider, standing or lying, and a tile's strip), else the tilt.
inline void travel_look(lv_obj_t *slider, const Tile &t, bool tilt, bool closed) {
  if (!slider) return;
  const bool on = t.travelling() && t.travel.tilt == tilt;
  auto raw = [&](float v) { return (int) std::lround(std::clamp(closed ? 100.0f - v : v, 0.0f, 100.0f) * 10); };
  const float from = t.travel.real, to = t.travel.to;
  travel_stripe::set(slider, on && std::isfinite(to), std::isfinite(from) ? raw(from) : raw(to < 50 ? 100 : 0), raw(to));
  if (on == lv_obj_has_state(slider, LV_STATE_USER_1)) return;
  if (on) {
    if (!tilt) lv_obj_set_style_bg_opa(slider, LV_OPA_40, LV_PART_INDICATOR | LV_STATE_USER_1);
    lv_obj_set_style_opa(slider, tilt ? LV_OPA_40 : LV_OPA_TRANSP, LV_PART_KNOB | LV_STATE_USER_1);
    lv_obj_set_style_opa(slider, LV_OPA_COVER, LV_PART_KNOB | LV_STATE_USER_1 | LV_STATE_PRESSED);
    lv_obj_add_state(slider, LV_STATE_USER_1);
  } else {
    lv_obj_remove_state(slider, LV_STATE_USER_1);
  }
}
// A key of a tile (a wide tile's row, a thermostat's mode bar): a wish where the key changes a value it can show
// (tile_controls::wanted), the plain action otherwise.
inline void key_press(Tile &t, int command, const std::string &arg = "") {
  const auto a = tile_controls::key_action(t, command, arg);
  if (!a.valid()) return;
  if (t.domain() == "cover") { cover_key(t, command); return; }
  const auto w = tile_controls::wanted(t, command, arg);
  if (!w.valid) { action(a.service, t.entity, a.key, a.value); return; }
  if (w.field == optimistic::Field::HVAC_MODE) { climate_mode_wish(t, w.value); return; }
  wish(t, w.field, w.value, a.service, a.key, a.value, w.field == optimistic::Field::PLAYING ? media_entity(t) : std::string());
}
inline bool wish_unanswered(const std::string &target) {
  bool any = false;
  for (auto &w : wishes.wishes) {
    if (w.target != target) continue;
    const auto outcome = optimistic::unanswered(w);
    if (outcome == optimistic::Outcome::DONE) continue;
    any = true;
    wish_revert(w, true, true, outcome == optimistic::Outcome::REVERT);
  }
  return any;
}
inline const lv_font_t *detail_font=nullptr;
inline lv_obj_t *detail_actions[32]{};
inline unsigned detail_action_count=0;
inline lv_obj_t *detail_status=nullptr;
inline lv_obj_t *detail_badge_status=nullptr;
inline lv_obj_t *detail_switch=nullptr;
inline lv_obj_t *detail_label(lv_obj_t *parent,const std::string &text,int x,int y,int width) {
  auto *label=lv_label_create(parent);lv_label_set_text(label,text.c_str());lv_obj_set_pos(label,x,y);lv_obj_set_width(label,width);
  lv_obj_set_style_text_font(label,detail_font,0);lv_obj_set_style_text_color(label,theme::color(theme::INK),0);
  lv_label_set_long_mode(label,LV_LABEL_LONG_DOT);lv_obj_set_height(label,lv_font_get_line_height(detail_font));return label;
}
inline std::string detail_state(const Tile &t){
  if(tile_controls::text_value(t))return tile_controls::text_shown(t);
  if(t.domain()=="person")return t.state=="home"?tr(txt::ha_person_home):t.state=="not_home"?tr(txt::ha_person_not_home):t.state;
  if(t.domain()=="sun")return tr(t.state=="above_horizon"?txt::ha_sun_above_horizon:txt::ha_sun_below_horizon);
  if(t.domain()=="timer")return timer_text(t);
  if(t.domain()=="script"||t.domain()=="scene"||t.domain()=="button"||t.domain()=="input_button")return t.state=="on"?tr(txt::script_running):last_run_text(t.last_run);
  if(t.domain()=="binary_sensor"&&(t.state=="on"||t.state=="off"))return tile_controls::binary_state_text(t.device_class,t.state=="on");
  if(t.state=="on")return tr(txt::ha_on);
  if(t.state=="off")return tr(txt::ha_off);
  if(t.state=="docked")return tr(txt::ha_vacuum_docked);
  if(t.state=="cleaning")return tr(txt::ha_vacuum_cleaning);
  if(t.state=="paused")return tr(txt::ha_vacuum_paused);
  if(t.state=="returning")return tr(txt::ha_vacuum_returning);
  if(t.state=="idle")return tr(txt::ha_vacuum_idle);
  if(t.state=="error")return tr(txt::vacuum_check_robot);
  if(!t.available())return tr(txt::ha_unavailable);
  // A weather's condition is Home Assistant's key ("clear-night"), never a word: the screen says it in its own
  // language, as the weather cards and the editor do.
  if(t.domain()=="weather"){const std::string word=weather_text(t.state);if(word!=t.state)return word;}
  // Home Assistant's word where the screen has none of its own (firmware 0.2.58+).
  if(!t.extra().state_word.empty())return t.extra().state_word;
  return t.unit.empty()?t.state:screen_text::localize(t.state);
}
inline void alarm_close_pad();
inline void lock_card_closed();
// Every way a card closes (Back, standby, Back to page 1, another card) also forgets a code half typed on an alarm's
// keypad: it never waits in memory for the next person at the screen.
inline void colour_close();
#ifdef SD_MOD_VACUUM_CARD
// The vacuum card of the module (module_vacuum_card.cpp, a compilation unit of its own).
}  // namespace runtime_tiles
#include "module_vacuum_card.h"
namespace runtime_tiles {
#endif
inline void hide_detail(){
  alarm_close_pad();lock_card_closed();
  // The colour card is a card as well, and closes on every way a card closes.
  colour_close();
  // A plugin's card closes on every way Tessera's own cards close (docs/PLUGINS.md).
  plugin_host::close_card();
  if(detail_backdrop)lv_obj_add_flag(detail_backdrop,LV_OBJ_FLAG_HIDDEN);if(detail_root)lv_obj_add_flag(detail_root,LV_OBJ_FLAG_HIDDEN);
#ifdef SD_MOD_VACUUM_CARD
  vacuum_card::closed();
#endif
#ifdef SD_MOD_TODO
  todo_view::closed();
#endif
#ifdef SD_MOD_TEXT_EDIT
  text_edit_view::closed();
#endif
  // A player's library and speaker menu go with its card (firmware 0.24.0+), after it: the card stays as it was.
  media_library::close();}
inline int slider_value(const Tile &t){
  auto d=t.domain();float value=0;
  if(d=="light")value=std::isfinite(t.brightness)?t.brightness/255:0;
  if(d=="fan")value=std::isfinite(t.percentage)?t.percentage/100:0;
  // A blind's bar is the blind itself: the closed part is filled, so a closed cover is a full bar, as on its card and in
  // Home Assistant's own cover dialog (firmware 0.2.66+; before, the bar filled with the open part, the other way round).
  if(d=="cover")value=std::isfinite(t.position)?(100-t.position)/100:1;
  if(d=="media_player")value=std::isfinite(t.volume)?t.volume:0;
  if(d=="number"||d=="input_number") {char *end;float state=strtof(t.state.c_str(),&end);if(end!=t.state.c_str() && t.maximum>t.minimum)value=(state-t.minimum)/(t.maximum-t.minimum);}
  // A humidifier's slider is the humidity it is set to, over its own range (Home Assistant's target-humidity slider).
  if(d=="humidifier"&&std::isfinite(t.target)&&t.maximum>t.minimum)value=(t.target-t.minimum)/(t.maximum-t.minimum);
  return std::clamp((int)std::lround(value*1000),0,1000);
}
inline lv_obj_t *captured_slider=nullptr;
inline bool slider_changed=false;
inline int slider_held=0;
inline void slider_event(lv_event_t *e);
inline void commit_slider(unsigned i,int raw,bool tilt=false){
  if(i>=model.count || !fresh())return;auto &t=model.tiles[i];if(!t.available() || t.waiting(esphome::millis()))return;
  float value=std::clamp(raw,0,1000)/1000.0f;auto d=t.domain();
  if(d=="cover"){
    if(tilt&&!tile_controls::cover_tilt_selected(t))return;
    const auto call=tile_controls::cover_position_action(t,raw,tilt);
    const float percent=std::lround(std::clamp(raw,0,1000)/10.0f);
    cover_go(t,call,tilt?percent:100-percent,0,tilt);
    return;
  }
  if(tilt)return;
  // A light's slider stops at 1 %, as in Home Assistant; tapping the card turns it off.
  // The slider stays where the finger left it while the light fades towards it (Tile::hold_slider).
  // On an off light or fan the slider turns it on: that goes out as a wish (docs/OPTIMISTIC.md), so the tile lights up
  // at once and goes dark again when Home Assistant does not follow.
  auto slide=[&](const char *service,const char *key,int sent){
    if(t.state=="off")wish(t,optimistic::Field::ON_OFF,"on",service,key,std::to_string(sent));
    else action(service,t.entity,key,std::to_string(sent));
    t.hold_slider(esphome::millis(),sent);
  };
  if(d=="light")slide("light.turn_on","brightness",std::max(3,(int)std::lround(value*255)));
  if(d=="fan")slide("fan.set_percentage","percentage",(int)std::lround(value*100));
  if(d=="media_player"){action("media_player.volume_set",media_entity(t),"volume_level",std::to_string(value));t.hold_slider(esphome::millis(),value);}
  if(d=="number"||d=="input_number") {
    if(!std::isfinite(t.minimum)||!std::isfinite(t.maximum)||t.maximum<=t.minimum||t.step<=0)return;
    value=std::clamp(t.minimum+std::round(value*(t.maximum-t.minimum)/t.step)*t.step,t.minimum,t.maximum);
    action(d+".set_value",t.entity,"value",std::to_string(value)); }
  if(d=="humidifier"&&t.maximum>t.minimum){
    const float step=std::max(1.0f,tile_controls::edit_step(t));
    const int sent=(int)std::lround(std::clamp(t.minimum+std::round(value*(t.maximum-t.minimum)/step)*step,t.minimum,t.maximum));
    action("humidifier.set_humidity",t.entity,"humidity",std::to_string(sent));}
}
// Where the finger landed on a slider, the value it had, and whether it landed beside the strip (in the tile's lower
// half that the strip claims, slider_zone) and moved: a press beside the strip that never moves is a tap on the tile.
inline lv_point_t slider_press{0,0};inline int slider_press_value=0;inline bool slider_press_beside=false,slider_press_moved=false,slider_press_held=false;
// The card a strip belongs to, for a press beside the strip that turns out to be the card's tap or hold.
inline lv_obj_t *strip_card(lv_obj_t *slider){for(auto &w:widgets)if(w.slider==slider)return w.tile;return nullptr;}
// An off light or fan shows only the track (slider_bar), so a finger dragging it would move nothing it can see: while it
// drags, the fill and the handle follow it as a ghost in the tile's colour, and letting go paints the card as it is then,
// solid when the light went on (the wish in commit_slider) or bare again when nothing went out.
inline lv_obj_t *ghost_slider=nullptr;
inline void ghost_show(lv_obj_t *slider){
  if(ghost_slider==slider || lv_obj_get_style_bg_opa(slider,LV_PART_INDICATOR)!=LV_OPA_TRANSP)return;
  for(auto &w:widgets)if((w.slider==slider || w.control_slider==slider) && w.index<model.count){
    CardScope scope(w);  // a finger on the slider, outside render_slot
    set_color(slider,LV_STYLE_BG_COLOR,lv_color_hex(theme::state(tile_controls::accent(model.tiles[w.index]))),LV_PART_INDICATOR);
    set_number(slider,LV_STYLE_BG_OPA,LV_OPA_30,LV_PART_INDICATOR);
    set_number(slider,LV_STYLE_BG_OPA,LV_OPA_60,LV_PART_KNOB);
    ghost_slider=slider;return;}
}
inline void ghost_end(lv_obj_t *slider){
  if(ghost_slider!=slider)return;
  ghost_slider=nullptr;
  for(auto &w:widgets)if(w.slider==slider || w.control_slider==slider){w.paint_again();refresh_tile(w.index,redraw_log::TileWhy::finger);return;}
}
inline void slider_event(lv_event_t *e){
  auto *slider=lv_event_get_target_obj(e);auto code=lv_event_get_code(e);
  if(code==LV_EVENT_PRESSED){captured_slider=slider;slider_changed=false;slider_press_moved=false;slider_press_beside=false;slider_press_held=false;
    slider_press_value=lv_slider_get_value(slider);
    if(auto *indev=lv_indev_active()){lv_indev_get_point(indev,&slider_press);lv_area_t a;lv_obj_get_coords(slider,&a);slider_press_beside=slider_press.x<a.x1 || slider_press.x>a.x2 || slider_press.y<a.y1 || slider_press.y>a.y2;}
    // Beside the strip the card lights up as under a tap, until the finger starts dragging.
    if(slider_press_beside)if(auto *card=strip_card(slider))lv_obj_add_state(card,LV_STATE_PRESSED);}
  if(code==LV_EVENT_PRESSING && captured_slider==slider && !slider_press_moved){
    if(auto *indev=lv_indev_active()){lv_point_t p;lv_indev_get_point(indev,&p);if(std::abs(p.x-slider_press.x)>=10 || std::abs(p.y-slider_press.y)>=10){slider_press_moved=true;
      if(auto *card=strip_card(slider))lv_obj_remove_state(card,LV_STATE_PRESSED);}}}
  // A finger resting beside the strip holds the card, as it would without the strip's claim on the card.
  if(code==LV_EVENT_LONG_PRESSED && captured_slider==slider && slider_press_beside && !slider_press_moved && !slider_press_held){
    if(auto *card=strip_card(slider)){slider_press_held=true;lv_obj_send_event(card,LV_EVENT_LONG_PRESSED,nullptr);}}
  if((code==LV_EVENT_RELEASED || code==LV_EVENT_PRESS_LOST) && slider_press_beside)if(auto *card=strip_card(slider))lv_obj_remove_state(card,LV_STATE_PRESSED);
  // On release LVGL sets the value once more from the last touch point: log it when that throws a
  // dragged slider to one of its ends, so a stray touch sample shows up (screen_input::release_jump).
  if(code==LV_EVENT_VALUE_CHANGED && captured_slider==slider){
    auto *indev=lv_indev_active();int raw=lv_slider_get_value(slider);
    if(!indev || lv_indev_get_state(indev)!=LV_INDEV_STATE_RELEASED)slider_held=raw;
    else if(slider_changed && screen_input::release_jump(slider_held,raw,lv_slider_get_min_value(slider),lv_slider_get_max_value(slider))){
      lv_point_t point;lv_indev_get_point(indev,&point);
      ESP_LOGW("slider","Tile slider jumped on release: %d -> %d (touch x=%d y=%d)",slider_held,raw,(int)point.x,(int)point.y);
    }
  }
  // The range reaches below zero only to draw the round end at 0 (slider_handle).
  if(code==LV_EVENT_VALUE_CHANGED && lv_slider_get_value(slider)<0)lv_slider_set_value(slider,0,LV_ANIM_OFF);
  if(code==LV_EVENT_VALUE_CHANGED && captured_slider==slider)slider_changed=true;
  if(code==LV_EVENT_VALUE_CHANGED && captured_slider==slider && (!slider_press_beside || slider_press_moved))ghost_show(slider);
  if(code==LV_EVENT_PRESS_LOST && captured_slider==slider){captured_slider=nullptr;slider_changed=false;ghost_end(slider);}
  if(code==LV_EVENT_RELEASED && captured_slider==slider){
    // The ghost ends after everything below, the send included, whichever way the release goes.
    struct GhostEnd{lv_obj_t *slider;~GhostEnd(){ghost_end(slider);}} ghost{slider};
    unsigned index=(uintptr_t)lv_event_get_user_data(e);bool tilt=false;
    // A slider among a card's own parts (the media tile's volume) belongs to the tile the slot shows now.
    bool cover_strip=false;
    for(auto &w:widgets)if(w.slider==slider || w.control_slider==slider || (w.extra && lv_obj_get_parent(slider)==w.extra)){index=w.index;cover_strip=w.extra_mode=="cover_tilt";tilt=cover_strip&&w.parts[3]==slider;break;}
    bool changed=slider_changed;captured_slider=nullptr;slider_changed=false;
    // A finger that landed beside a tile's strip and let go without moving tapped the tile (or held it, sent above):
    // the value LVGL set from that point on release goes back, and the tile's own rules decide what the tap does.
    if(slider_press_beside && !slider_press_moved){
      if(auto *card=strip_card(slider)){
        lv_slider_set_value(slider,slider_press_value,LV_ANIM_OFF);
        ESP_LOGI("slider","%s beside the strip of %s: the tile's",slider_press_held?"Hold":"Tap",model.tiles[index].entity.c_str());
        if(!slider_press_held)lv_obj_send_event(card,LV_EVENT_SHORT_CLICKED,nullptr);
        return;}
    }
    // A finger let go within the edge band of the glass meant the slider's end (screen_input::edge_snap).
    if(auto *indev=lv_indev_active();indev && lv_obj_get_width(slider)>=lv_obj_get_height(slider)){
      lv_point_t p;lv_indev_get_point(indev,&p);lv_area_t a;lv_obj_get_coords(slider,&a);
      int screen=lv_display_get_horizontal_resolution(lv_obj_get_display(slider));
      int snap=screen_input::edge_snap(p.x,a.x1,a.x2,screen,screen_input::edge_snap_band);
      if(snap){int end=snap>0?(int)lv_slider_get_max_value(slider):std::max(0,(int)lv_slider_get_min_value(slider));
        ESP_LOGI("slider","Let go %d px from the %s edge: slider %d -> %d",snap>0?screen-1-(int)p.x:(int)p.x,snap>0?"right":"left",(int)lv_slider_get_value(slider),end);
        lv_slider_set_value(slider,end,LV_ANIM_OFF);changed=true;}
    }
    if(index<model.count&&model.tiles[index].row_span()>1&&!model.tiles[index].full)
      for(const auto &w:widgets)if(w.control_slider==slider&&!tile_controls::panel_available(model.tiles[index]))return;
    if(changed && screen_input::touch_guard.accept_slider(esphome::millis(),200+index))
      commit_slider(index,lv_slider_get_value(slider),tilt);
  }
}
inline void show_detail(unsigned index);
// A chip on the vacuum card: the service call goes out, the chip shows the choice at once, and the card
// waits for Home Assistant like after its other buttons. The card is drawn again once this tap's event
// has finished, because a chosen mode can add or remove the suction and water rows.
inline void redraw_detail(){
  // A card that paints itself follows at once and in place (docs/CARD_PARTS.md); another is built again after the event.
  if(detail_root&&!lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN)&&detail_index<model.count&&card_repaint(model.tiles[detail_index]))return;
  lv_async_call([](void *){if(detail_root && !lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN))show_detail(detail_index);},nullptr);
}
// A chip of a vacuum's row, as a wish (docs/OPTIMISTIC.md): the suction is the vacuum's own, the mode and the water
// selects of its device.
inline void choose(Tile &t,Choice &row,const std::string &value){
  if(value==row.current)return;
  auto a=tile_controls::choice_action(t,row.kind,value);if(!a.valid())return;
  wish(t,optimistic::Field::VACUUM_ROW,value,a.service,a.key,a.value,row.kind=='s'?t.entity:row.entity,std::string(1,row.kind));
}
// What a key on a card does; `cmd` is the key's command. Shared by the plain keys (detail_button) and the round
// keys of the media card. -1 is Back.
inline void alarm_command(int cmd);
inline void lock_command(int cmd);
inline bool alarm_pad_open();
inline bool alarm_keypad_first(const Tile &t);
// The card keys whose change is a wish (docs/OPTIMISTIC.md): play or pause, mute, shuffle, repeat, an option, a mode,
// a thermostat's rows and the power keys.
inline bool wish_command(int cmd){
  return cmd==20||cmd==23||cmd==25||cmd==26||(cmd>=SELECT_OPTION_FIRST&&cmd<SELECT_OPTION_FIRST+64)||
         (cmd>=CLIMATE_MODE_FIRST&&cmd<CLIMATE_ROW_FIRST+12)||cmd==CLIMATE_POWER||cmd==LIGHT_POWER;
}
inline void detail_command(int cmd){
  // Back on the alarm's keypad goes back to its card; everywhere else it closes the card.
  // A panel that goes off is its keypad (alarm_keypad_first): back closes the card, there is no card behind it.
  if(cmd==-1&&alarm_pad_open()){
    const bool first=alarm_keypad_first(model.tiles[detail_index]);
    alarm_close_pad();
    if(first)hide_detail();else redraw_detail();
    return;
  }
#ifdef SD_MOD_VACUUM_CARD
  // A view of the vacuum card (its rooms, routines, suction and water) goes back to the card.
  if(cmd==-1&&vacuum_card::back())return;
#endif
  if(cmd==-1){hide_detail();return;}
  // The alarm panel's modes, digits, Clear and OK (600-621): the digits count every clean tap, like the -/+ keys.
  if(cmd>=600&&cmd<=621){alarm_command(cmd);return;}
  // A lock's keys (700-702): Lock, Unlock, Open door.
  if(cmd>=700&&cmd<=709){lock_command(cmd);return;}
  // A group's key (GROUP_PAGE): its page over the card, of covers or of lamps.
  if(cmd==GROUP_PAGE){if(const Tile *t=detail_tile())group_page::open(t->entity);return;}
  // History ranges (firmware 0.2.51+): redraw after this event, which belongs to a key the redraw deletes.
  if(cmd>=160&&cmd<163){
    static const uint32_t hours[]={1,24,168};
    if(detail_tile()&&allowed(esphome::millis(),300+cmd,"history range")&&history_hours!=hours[cmd-160]){
      history_hours=hours[cmd-160];
      lv_async_call([](void *){if(detail_root&&!lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN))show_detail(detail_index);},nullptr);
    }
    return;
  }
  // The setpoint's - and +: every clean tap counts, also while the last one is still on its way to Home
  // Assistant, so a series of taps is one series of steps (the send waits for the last of them).
  if(cmd==CLIMATE_END_LOW||cmd==CLIMATE_END_HIGH){
    if(detail_index>=model.count)return;
    auto &tile=model.tiles[detail_index];
    tile.range_end=cmd==CLIMATE_END_HIGH?tile_controls::RANGE_HIGH:tile_controls::RANGE_LOW;
    climate_paint_ends(tile);
    refresh_tile(detail_index,redraw_log::TileWhy::finger);   // the tile's chip says the same end
    return;
  }
  if(cmd==CLIMATE_DOWN||cmd==CLIMATE_UP){
    if(!fresh()||detail_index>=model.count)return;
    auto &tile=model.tiles[detail_index];
    if(!tile.available()||!screen_input::touch_guard.accept_repeat(esphome::millis(),300+cmd))return;
    climate_step(tile,cmd==CLIMATE_UP?1:-1);
    return;
  }
  // A key of a remote's keypad (firmware 0.22.0+): the command its integration takes for it, sent as a remote sends it.
  // Every clean tap counts, as on the -/+ keys, so down, down, down moves three rows; only a bounce is dropped.
  if(cmd>=REMOTE_KEY_FIRST&&cmd<REMOTE_KEY_FIRST+RK_COUNT){
    if(!fresh()||detail_index>=model.count)return;
    auto &t=model.tiles[detail_index];
    const auto &keys=t.extra().keypad;const unsigned i=cmd-REMOTE_KEY_FIRST;
    if(!t.available()||i>=keys.size()||keys[i].empty()||!screen_input::touch_guard.accept_repeat(esphome::millis(),300+cmd))return;
    remote_key(t.entity,keys[i]);
    return;
  }
  if(!fresh()||detail_index>=model.count)return;
  {
    const std::string what="card button "+model.tiles[detail_index].entity;
    if(!(wish_command(cmd)?allowed_wish(esphome::millis(),300+cmd,what):allowed(esphome::millis(),300+cmd,what)))return;
  }
  auto &t=model.tiles[detail_index];
  // A player's library and its speakers (firmware 0.24.0+) open while a key of it is still on its way.
  if(cmd==27){media_library::open(t.entity);return;}
  if(cmd==28){media_library::speakers(t.entity);return;}
  if(cmd==29){media_library::inputs(t.entity);return;}
#ifdef SD_MOD_VACUUM_CARD
  // The vacuum card's own keys (800-899): picks and views at once, its actions when the robot answers.
  if(vacuum_card::handles(cmd)){vacuum_card::command(t,cmd);return;}
#endif
  if(!t.available()||t.waiting(esphome::millis()))return;
  if(cmd<4){const char *services[]={"vacuum.start","vacuum.pause","vacuum.return_to_base","vacuum.locate"};action(services[cmd],t.entity);}
  // Vacuum rows: 10-15 suction, 50-55 cleaning mode, 60-65 water.
  static const std::pair<int,char> rows[]={{10,'s'},{50,'m'},{60,'w'}};
  for(const auto &[first,kind]:rows)
    if(cmd>=first && cmd<first+6){auto *row=t.choice(kind);if(row && cmd-first<(int)row->values.size())choose(t,*row,row->values[cmd-first]);}
  // The media card's keys (20-26, and 30 its power key's turn off, GitHub #239); its volume slider goes through
  // commit_slider.
  if((cmd>=20 && cmd<=26) || cmd==30)media_action(t,cmd);
  // A row of the select card: chosen at once on the card, confirmed by Home Assistant's next state.
  if(cmd>=SELECT_OPTION_FIRST&&cmd<SELECT_OPTION_FIRST+64&&cmd-SELECT_OPTION_FIRST<(int)t.extra().options.size()){
    const std::string option=t.extra().options[cmd-SELECT_OPTION_FIRST];
    // A remote's activity (firmware 0.22.0+) turns it on with that activity, as Home Assistant's dialog does
    // (more-info-remote.ts: remote.turn_on with `activity`). The row shows the choice at once.
    if(t.domain()=="remote"){
      if(option==t.extra().activity&&t.state=="on")return;
      wish(t,optimistic::Field::ACTIVITY,option,"remote.turn_on","activity",option);
      return;
    }
    if(option==t.state)return;
    wish(t,optimistic::Field::OPTION,option,t.domain()+".select_option","option",option);
    return;
  }
  // Cover keys: 70 + tile_controls::Command (open, stop, close and the tilt keys).
  if(cmd>=70 && cmd<130){if(t.domain()=="cover")cover_key(t,cmd-70);}
  if(cmd==40)action(t.state=="active"?"timer.pause":"timer.start",t.entity);
  if(cmd==41)action("timer.cancel",t.entity);
  // The climate card: a mode (200-207), a fan or swing choice (210-221) and the power key (230). The card
  // shows the choice at once and waits for Home Assistant, like the vacuum card's chips.
  if(cmd>=CLIMATE_MODE_FIRST&&cmd<CLIMATE_MODE_FIRST+8){
    const auto modes=tile_controls::climate_modes(t);
    const unsigned i=cmd-CLIMATE_MODE_FIRST;
    if(i<modes.size()&&tile_controls::humidifier(t)&&modes[i]!=t.extra().humidifier_mode){
      wish(t,optimistic::Field::HUMIDIFIER_MODE,modes[i],"humidifier.set_mode","mode",modes[i]);
    }else if(i<modes.size()&&!tile_controls::humidifier(t)&&modes[i]!=tile_controls::lower_case(t.state)){
      climate_mode_wish(t,modes[i]);
    }
    return;
  }
  if(cmd>=CLIMATE_ROW_FIRST&&cmd<CLIMATE_ROW_FIRST+12){
    const auto rows=tile_controls::climate_rows(t);
    const unsigned r=(cmd-CLIMATE_ROW_FIRST)/6,i=(cmd-CLIMATE_ROW_FIRST)%6;
    if(r<rows.size()&&i<rows[r].values.size()&&rows[r].values[i]!=rows[r].current){
      const char kind=rows[r].kind;
      const std::string value=rows[r].values[i];
      const auto a=tile_controls::climate_row_action(kind,value);
      using F=optimistic::Field;
      wish(t,kind=='m'?F::HUMIDIFIER_MODE:kind=='f'?F::FAN_MODE:F::SWING_MODE,value,a.service,a.key,a.value);
    }
    return;
  }
  if(cmd==LIGHT_POWER){
    // The same toggle a tap on the tile does.
    toggle_wish(t);
    return;
  }
  if(cmd==CLIMATE_POWER){
    climate_power(t);
    redraw_detail();
    return;
  }
}
inline lv_obj_t *detail_button(const char *text,int x,int y,int width,int height,int command){
  auto *button=lv_obj_create(detail_root);lv_obj_remove_style_all(button);lv_obj_set_pos(button,x,y);lv_obj_set_size(button,width,height);
  lv_obj_set_style_bg_color(button,theme::color(command==0?theme::ACCENT:theme::BUTTON),0);lv_obj_set_style_bg_opa(button,LV_OPA_COVER,0);lv_obj_set_style_radius(button,12,0);lv_obj_add_flag(button,LV_OBJ_FLAG_CLICKABLE);
  auto *label=detail_label(button,text,6,0,width-12);lv_obj_center(label);lv_obj_set_style_text_align(label,LV_TEXT_ALIGN_CENTER,0);if(command==0)lv_obj_set_style_text_color(label,theme::color(theme::ON_ACCENT),0);lv_obj_remove_flag(label,LV_OBJ_FLAG_CLICKABLE);
  lv_obj_add_event_cb(button,[](lv_event_t *e){detail_command((intptr_t)lv_event_get_user_data(e));},LV_EVENT_SHORT_CLICKED,(void*)(intptr_t)command);
  lv_obj_set_style_bg_color(button,theme::color(theme::ACCENT_PRESSED),LV_STATE_PRESSED);
  lv_obj_set_style_transform_width(button,-2,LV_STATE_PRESSED);lv_obj_set_style_transform_height(button,-2,LV_STATE_PRESSED);
  lv_obj_set_style_opa(button,LV_OPA_50,LV_STATE_DISABLED);
  if(command>=0 && detail_action_count<32)detail_actions[detail_action_count++]=button;
  return button;
}

// A key in the last row of a card that fills the glass also takes the strip between it and the glass's bottom edge:
// a finger aimed at a key that low lands on that strip as often as on the key (a 10.1 inch read taps on the history
// card's week as 787-794 of 800, below the key's touch area that ended at 786). An invisible catcher from the key's
// foot to `bottom` gives that strip to the key: it presses the key, so the key shows the press, and its tap is the
// key's command, through the same guard (detail_command). Not a detail action of its own.
inline void detail_reach_down(lv_obj_t *key,int command,int bottom){
  lv_obj_update_layout(key);
  lv_area_t a;lv_obj_get_coords(key,&a);
  lv_area_t root;lv_obj_get_coords(detail_root,&root);
  const int top=a.y2+1-root.y1;
  if(bottom<=top)return;
  auto *catcher=lv_obj_create(detail_root);lv_obj_remove_style_all(catcher);
  lv_obj_set_pos(catcher,a.x1-root.x1,top);lv_obj_set_size(catcher,a.x2-a.x1+1,bottom-top);
  lv_obj_add_flag(catcher,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(catcher,LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_user_data(catcher,key);
  lv_obj_add_event_cb(catcher,[](lv_event_t *e){
    auto *self=lv_event_get_current_target_obj(e);auto *k=static_cast<lv_obj_t*>(lv_obj_get_user_data(self));
    const auto code=lv_event_get_code(e);
    if(code==LV_EVENT_PRESSED)lv_obj_add_state(k,LV_STATE_PRESSED);
    else if(code==LV_EVENT_RELEASED||code==LV_EVENT_PRESS_LOST)lv_obj_remove_state(k,LV_STATE_PRESSED);
    else if(code==LV_EVENT_SHORT_CLICKED)detail_command((intptr_t)lv_event_get_user_data(e));
  },LV_EVENT_ALL,(void*)(intptr_t)command);
}

// The width a line of text is drawn at, for a layout that has to know before it places it.
inline int text_width(const std::string &text,const lv_font_t *font){
  lv_point_t size;lv_text_get_size(&size,text.c_str(),font,0,0,LV_COORD_MAX,LV_TEXT_FLAG_NONE);return size.x;
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
