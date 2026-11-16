// Direct controls on wide cards.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the rules themselves, which are plain C++ without LVGL in tile_controls.h, tall_tile.h.
// What proves it: tests/test_tile_controls.cpp, tests/test_tall_tile.cpp, the layout audit (tests/test_layout_audit.py).
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// ---- Direct controls on wide cards (Home Assistant entity-row style) ----
struct PanelMetrics { int key_w, key_h, radius, gap, pill_w, pill_key, slider_w, slider_h, toggle_w, toggle_h, run_pad, text_gap, ext; };
// A thermostat's mode bar in a panel ("Mode"): a finger is the panel's key, the reach of one hand the look's.
inline climate_tile::Metrics bar_metrics(const PanelMetrics &m,bool large){
  climate_tile::Metrics cm;cm.large=large;cm.touch=m.key_h;cm.gap=m.gap;cm.max_width=ui::control_max_width();
  return cm;
}
inline void draw_mode_bar(Widgets &w,const Tile &t,lv_obj_t *parent,lv_obj_t *&track,lv_obj_t **segments,climate_tile::Rect bar,
                          int room,const climate_tile::Metrics &cm,bool large);
inline PanelMetrics panel_metrics(bool large) {
  return large ? PanelMetrics{ui::px(60), ui::px(46), ui::px(14), ui::px(8), ui::px(196), ui::px(52), ui::px(140), ui::px(44), ui::px(76), ui::px(40), ui::px(22), ui::px(8), ui::px(4)} : PanelMetrics{ui::px(40), ui::px(34), ui::px(9), ui::px(4), ui::px(128), ui::px(36), ui::px(90), ui::px(30), ui::px(48), ui::px(26), ui::px(14), ui::px(6), ui::px(6)};
}
// The same controls at the bottom of a full-page card (firmware 0.2.62+): keys a thumb finds without looking.
inline PanelMetrics panel_metrics_full(bool big) {
  return big ? PanelMetrics{ui::px(120), ui::px(84), ui::px(24), ui::px(16), ui::px(300), ui::px(84), ui::px(400), ui::px(56), ui::px(120), ui::px(60), ui::px(30), ui::px(8), ui::px(4)} : PanelMetrics{ui::px(80), ui::px(44), ui::px(12), ui::px(8), ui::px(200), ui::px(48), ui::px(260), ui::px(34), ui::px(76), ui::px(40), ui::px(18), ui::px(6), ui::px(4)};
}
inline lv_obj_t *panel_obj(lv_obj_t *parent,bool clickable) {
  auto *o=lv_obj_create(parent);lv_obj_remove_style_all(o);lv_obj_remove_flag(o,LV_OBJ_FLAG_SCROLLABLE);
  if(clickable)lv_obj_add_flag(o,LV_OBJ_FLAG_CLICKABLE);else lv_obj_remove_flag(o,LV_OBJ_FLAG_CLICKABLE);
  return o;
}
// Like the custom parts: a card without controls hides the slot's panel and a later card with
// the same control set shows it again.
inline void hide_panel(Widgets &w) {
  if(!w.panel)return;
  if(!lv_obj_has_flag(w.panel,LV_OBJ_FLAG_HIDDEN))lv_obj_add_flag(w.panel,LV_OBJ_FLAG_HIDDEN);
  w.panel_w=0;
  if(captured_slider && captured_slider==w.control_slider)captured_slider=nullptr;
}
inline void end_panel(Widgets &w) {
  if(!w.panel)return;
  hide_panel(w);
  if(!w.panel_mode.empty()){
    lv_obj_clean(w.panel);w.keys.fill(nullptr);w.key_icons.fill(nullptr);w.key_checked.fill(-1);w.segments.fill(nullptr);
    w.pill=w.pill_value=w.knob=w.control_slider=nullptr;w.knob_on=-1;w.panel_mode.clear();
#ifdef SD_MOD_LIGHT_PRESETS
    w.dots.fill(nullptr);w.dots_of=nullptr;w.dots_size=0;
#endif
  }
}
inline void control_event(lv_event_t *e);
// A pill key: rounded, pressed darker, checked in the accent, disabled faded.
inline lv_obj_t *panel_key(Widgets &w,unsigned n,lv_obj_t *parent,const PanelMetrics &m,int width,int height,bool transparent) {
  auto *key=panel_obj(parent,true);lv_obj_set_size(key,width,height);
  lv_obj_set_style_radius(key,transparent?LV_RADIUS_CIRCLE:m.radius,0);
  lv_obj_set_style_bg_opa(key,transparent?LV_OPA_TRANSP:LV_OPA_COVER,0);
  lv_obj_set_style_bg_opa(key,LV_OPA_COVER,LV_STATE_PRESSED);
  lv_obj_set_style_bg_opa(key,LV_OPA_COVER,LV_STATE_CHECKED);
  lv_obj_set_style_opa(key,LV_OPA_40,LV_STATE_DISABLED);
  lv_obj_set_ext_click_area(key,m.ext);
  size_t slot=&w-widgets.data();
  lv_obj_add_event_cb(key,control_event,LV_EVENT_SHORT_CLICKED,(void*)(uintptr_t)(slot*16+n));
  w.keys[n]=key;w.key_checked[n]=-1;
  return key;
}
inline lv_obj_t *panel_icon(Widgets &w,unsigned n,const lv_font_t *font) {
  auto *icon=lv_label_create(w.keys[n]);lv_obj_remove_flag(icon,LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_text_font(icon,font,0);center_icon(icon);w.key_icons[n]=icon;return icon;
}
// The - and + keys of a stepper as round keys inside its grey pill (firmware 0.3.3), with the number between them
// in the largest face that fits: the value is what the stepper is for, the keys only change it. The keys keep a
// finger's reach through their click area, which covers the pill's inset.
// The chip of a thermostat's range between its - and + (firmware 0.19.0), in the room (x, y, cw, ch) the number would
// take: the icon of the end they move, heat or cool, in that mode's colour, and its temperature in the largest of
// `faces` whose line is no taller than `face_h` (the pill's, as the single number's) and fits beside the icon. No digit
// to spare, as the single number keeps: every tap lays the tile out again. Without a range the chip hides.
inline void range_chip(Widgets &w,const Tile &t,int x,int y,int cw,int ch,int face_h,std::initializer_list<const lv_font_t *> faces){
  auto *chip=w.keys[2];
  if(!chip||t.domain()!="climate")return;
  const bool range=tile_controls::climate_range(t);
  set_hidden(chip,!range);
  if(w.pill_value)set_hidden(w.pill_value,range);
  w.key_commands[2]=range?tile_controls::RANGE_SWITCH:tile_controls::NONE;
  if(!range)return;
  const char *end=t.range_end==tile_controls::RANGE_HIGH?"cool":"heat";
  auto *icon=w.key_icons[2],*value=lv_obj_get_child(chip,1);
  label(icon,tile_controls::climate_mode_icon(end));
  set_color(icon,LV_STYLE_TEXT_COLOR,lv_color_hex(tile_controls::mode_color(end)));
  if(mini_icon_font&&(int)lv_font_get_line_height(lv_obj_get_style_text_font(icon,LV_PART_MAIN))>ch-ui::px(6))set_font(icon,mini_icon_font);
  const int icon_w=lv_font_get_line_height(lv_obj_get_style_text_font(icon,LV_PART_MAIN)),pad=ui::px(6);
  const std::string text=tile_controls::format_value(tile_controls::range_end(t,t.range_end),tile_controls::edit_step(t),"°");
  // Measured by the widest temperature this thermostat can show, as a single temperature is by its number: the face
  // stays the same from tap to tap, and the icon never makes the number smaller.
  const std::string widest=tile_controls::widest_setpoint(t);
  const lv_font_t *face=nullptr;
  for(const auto *candidate:faces){
    if(!candidate||!face_covers(candidate,widest))continue;
    face=candidate;
    if((int)lv_font_get_line_height(candidate)<=face_h&&text_width(widest,candidate)+pad<=cw)break;
  }
  if(!face)face=lv_obj_get_style_text_font(value,LV_PART_MAIN);
  set_font(value,face);label(value,text);
  lv_obj_set_pos(chip,x,y);lv_obj_set_size(chip,std::max(1,cw),std::max(1,ch));
  // The number may stand taller than the chip, as the single number stands in its pill: it is not cut at the chip's edge.
  lv_obj_add_flag(chip,LV_OBJ_FLAG_OVERFLOW_VISIBLE);
  // No room for the icon beside the widest number: the number alone, in the colour of its end, on every tap alike.
  const int tw=text_width(text,face);
  const bool with_icon=icon_w+pad/2+text_width(widest,face)+pad<=cw;
  set_hidden(icon,!with_icon);
  set_color(value,LV_STYLE_TEXT_COLOR,with_icon?theme::color(theme::INK):lv_color_hex(tile_controls::mode_color(end)));
  const int left=std::max(0,(cw-(with_icon?icon_w+pad/2:0)-tw)/2);
  lv_obj_set_align(icon,LV_ALIGN_TOP_LEFT);lv_obj_set_pos(icon,left,(ch-icon_w)/2);
  lv_obj_set_align(value,LV_ALIGN_TOP_LEFT);lv_obj_set_pos(value,left+(with_icon?icon_w+pad/2:0),(ch-(int)lv_font_get_line_height(face))/2);
}
// The - and + keys of a stepper as round keys inside its grey pill, the number or a range's chip between them.
inline void stepper_keys(Widgets &w,int width,int height,const lv_font_t *text_font,const Tile *tile=nullptr){
  const int in=std::max(2,ui::px(ui::large()?4:3)),d=std::max(1,height-2*in);
  for(int n=0;n<2;++n){
    if(!w.keys[n])continue;
    lv_obj_set_size(w.keys[n],d,d);lv_obj_set_pos(w.keys[n],n?width-in-d:in,in);
    lv_obj_set_style_bg_opa(w.keys[n],LV_OPA_COVER,0);lv_obj_set_ext_click_area(w.keys[n],in);center_icon(w.key_icons[n]);
  }
  if(tile)range_chip(w,*tile,in+d+in,in,width-2*(in+d+in),d,height,{watch_value_font,text_font,small_font});
  // Measured with a digit to spare, so the number a tap on + makes still fits the face chosen here.
  const std::string widest=std::string(lv_label_get_text(w.pill_value))+"8";
  const int room=width-2*(d+in)-ui::px(4);
  // A thermostat's range is two numbers: the small face before it gives up (never dots: LVGL writes them into the text
  // measured here, lvgl-dots-in-label-text).
  const lv_font_t *face=text_font;
  for(const auto *candidate:{watch_value_font,text_font,small_font})
    if(candidate&&face_covers(candidate,widest)&&(int)lv_font_get_line_height(candidate)<=height&&text_width(widest,candidate)<=room){face=candidate;break;}
  set_font(w.pill_value,face);
  const int lh=lv_font_get_line_height(face);
  lv_obj_set_pos(w.pill_value,in+d,(height-lh)/2);lv_obj_set_size(w.pill_value,std::max(1,width-2*(in+d)),lh);
}
// Build (once per control set) and lay out the panel; returns the width it takes
// from the text, including the gap, or 0 when the card shows no panel.
// `standing`: the height of a player's volume standing at the right of its card (volume_playback on a card wider than
// high, render_tall draws it among the card's parts): the panel holds the keys alone; -1 the keys alone, without room
// for the volume; 0 lays the volume over the keys.
// Compiled on its own (tile_panel.cpp): on Xtensa main.cpp's literal pool is at the edge of its reach.
int layout_panel(Widgets &w,const Tile &t,bool large,int content_w,int content_h,int standing=0);
inline theme::Face card_face(const Widgets &w) {
  const theme::Face given = plugin_host::face(w);
  if (given.kind != theme::Face::CARD || w.index >= model.count) return given;
  return theme::Face::of(model.tiles[w.index].background);
}
// Colours follow the card palette; called with the rest of the palette when it changes.
inline void style_panel(Widgets &w,const Tile &t,lv_color_t accent,lv_color_t text) {
  if(!w.panel || w.panel_mode.empty())return;
  const uint32_t surface=card_surface(w);
  lv_color_t card=lv_color_hex(surface);
  lv_color_t key_bg=lv_color_hex(theme::key_on(surface,236));
  lv_color_t key_pressed=lv_color_hex(theme::key_on(surface,212));
  w.panel_accent=accent;w.panel_text=text;
  for(unsigned n=0;n<3;++n){
    auto *key=w.keys[n];if(!key)continue;
    bool in_pill=w.pill && lv_obj_get_parent(key)==w.pill;
    if(n==2&&w.pill&&w.panel_mode=="setpoint"){   // a range's chip (range_chip): no fill of its own, grey while pressed
      set_color(key,LV_STYLE_BG_COLOR,theme::color(theme::CARD));set_color(key,LV_STYLE_BG_COLOR,theme::color(theme::STEPPER_KEY_PRESSED),LV_STATE_PRESSED);
      continue;
    }
    set_color(key,LV_STYLE_BG_COLOR,in_pill?theme::color(theme::STEPPER_KEY):key_bg);
    set_color(key,LV_STYLE_BG_COLOR,in_pill?theme::color(theme::STEPPER_KEY_PRESSED):key_pressed,LV_STATE_PRESSED);
    set_color(key,LV_STYLE_BG_COLOR,w.key_args[n]=="off" && w.panel_mode=="mode"?theme::color(theme::OFF):accent,LV_STATE_CHECKED);
    if(w.key_icons[n])set_color(w.key_icons[n],LV_STYLE_TEXT_COLOR,w.key_checked[n]==1?theme::color(theme::ON_ACCENT):text);
  }
  if(w.pill){set_color(w.pill,LV_STYLE_BG_COLOR,theme::color(theme::TRACK));if(w.pill_value)set_color(w.pill_value,LV_STYLE_TEXT_COLOR,text);}
  if(w.control_slider){
    bool on=fresh() && t.slider_active();
    lv_color_t fill=on?accent:theme::color(theme::OFF);
    // The track is the fill colour at 20 % over the card, as in Home Assistant.
    set_color(w.control_slider,LV_STYLE_BG_COLOR,lv_color_mix(fill,card,51),LV_PART_MAIN);
    set_color(w.control_slider,LV_STYLE_BG_COLOR,fill,LV_PART_INDICATOR);
    slider_bar(w.control_slider,slider_bar_shown(t,on));
  }
#ifdef SD_MOD_LIGHT_PRESETS
  if(t.presets)for(unsigned n=0;n<light_presets::MAX&&n<t.presets->count;++n)light_presets::paint(w.dots[n],t.presets->items[n]);
#endif
  if(w.knob){set_color(w.keys[0],LV_STYLE_BG_COLOR,theme::color(theme::PANEL_TOGGLE_OFF));set_color(w.keys[0],LV_STYLE_BG_COLOR,theme::color(theme::PANEL_TOGGLE_OFF_PRESSED),LV_STATE_PRESSED);}
}
inline void control_event(lv_event_t *e) {
  unsigned code=(uintptr_t)lv_event_get_user_data(e);unsigned slot=code/16,n=code%16;
  if(slot>=widgets.size() || n>=3)return;
  auto &w=widgets[slot];
  if(!enabled || !fresh() || w.index>=model.count || !w.keys[n])return;
  if(lv_obj_has_state(w.keys[n],LV_STATE_DISABLED))return;
  uint32_t now=esphome::millis();
  auto &t=model.tiles[w.index];
  if(t.row_span()>1&&!t.full&&!tile_controls::panel_available(t))return;
  int command=w.key_commands[n];
  bool step=command==tile_controls::STEP_DOWN || command==tile_controls::STEP_UP;
  bool held=lv_event_get_code(e)==LV_EVENT_LONG_PRESSED_REPEAT;
  if(held){ if(!step || now-t.edit_since<300)return; }  // three steps a second while holding
  else if(step){ if(!screen_input::touch_guard.accept_repeat(now,400+slot*16+n)){ESP_LOGI("touch","tap on control %u ignored: %s",(unsigned)slot,screen_input::touch_guard.reason().c_str());return;} }
  else if(tile_controls::wanted(t,command,w.key_args[n]).valid?!allowed_wish(now,400+slot*16+n,"control "+std::to_string(slot))
                                                               :!allowed(now,400+slot*16+n,"control "+std::to_string(slot)))return;
  if(!t.available())return;
  if(held)touch_feedback::step(command==tile_controls::STEP_UP?1:-1);   // each step of a held key clicks (touch_feedback.h)
  // A range (firmware 0.19.0): the chip switches the end the -/+ move, heat or cool; the -/+ move that end.
  if(command==tile_controls::RANGE_SWITCH&&tile_controls::climate_range(t)){
    t.range_end=t.range_end==tile_controls::RANGE_HIGH?tile_controls::RANGE_LOW:tile_controls::RANGE_HIGH;
    refresh_tile(w.index,redraw_log::TileWhy::finger);return;
  }
  if(step&&tile_controls::climate_range(t)){
    range_step(t,command==tile_controls::STEP_UP?1:-1);
    if(detail_root&&!lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN)&&detail_index==w.index)climate_paint_ends(t);
    refresh_tile(w.index,redraw_log::TileWhy::finger);return;
  }
  if(step){
    // Local at once, tap after tap; tick() sends the last value after a short pause.
    float current=std::isfinite(t.edit_value)?t.edit_value:tile_controls::edit_target(t);
    t.edit_value=tile_controls::step_value(current,tile_controls::edit_step(t),t.minimum,t.maximum,command==tile_controls::STEP_UP?1:-1);
    t.edit_since=now;t.edit_sent=false;
    if(w.pill_value){std::string suffix=tile_controls::thermostat(t)?tile_controls::setpoint_suffix(t):screen_text::unit_suffix(t.unit);label(w.pill_value,tile_controls::format_value(t.edit_value,tile_controls::edit_step(t),suffix.c_str()));}
    return;
  }
  if(command==tile_controls::OPEN_CARD){active_index=w.index;show_detail(w.index);return;}
  if(t.waiting(now))return;
  key_press(t,command,w.key_args[n]);
}
// The one spinner of the firmware: a busy card, the starting screen and a camera that loads (firmware 0.2.73+). The
// ring in the spinner paint, the arc in Home Assistant's blue. Null where the board builds no spinner.
inline lv_obj_t *spinner_create(lv_obj_t *parent, int size, int arc) {
#if LV_USE_SPINNER
  auto *spinner = lv_spinner_create(parent);
  lv_spinner_set_anim_params(spinner, 900, 200);
  lv_obj_set_size(spinner, size, size);
  lv_obj_remove_flag(spinner, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_arc_width(spinner, arc, LV_PART_MAIN);
  lv_obj_set_style_arc_width(spinner, arc, LV_PART_INDICATOR);
  lv_obj_add_style(spinner, theme::style(theme::Paint::spinner), LV_PART_MAIN);
  lv_obj_set_style_arc_color(spinner, lv_color_hex(theme::ha::RAIN), LV_PART_INDICATOR);
  lv_obj_set_style_bg_opa(spinner, LV_OPA_TRANSP, LV_PART_KNOB);
  lv_obj_set_style_pad_all(spinner, 0, LV_PART_KNOB);
  return spinner;
#else
  (void) parent; (void) size; (void) arc;
  return nullptr;
#endif
}
// A busy card is covered by a translucent white sheet with a small spinner until
// Home Assistant confirms; the sheet also swallows taps meanwhile.
inline void set_busy(Widgets &w,bool busy,bool large){
  if(!busy){if(w.busy)lv_obj_add_flag(w.busy,LV_OBJ_FLAG_HIDDEN);return;}
  if(!w.busy){
    w.busy=lv_obj_create(w.tile);lv_obj_remove_style_all(w.busy);lv_obj_remove_flag(w.busy,LV_OBJ_FLAG_SCROLLABLE);lv_obj_add_flag(w.busy,LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_style(w.busy,theme::style(theme::Paint::veil),0);lv_obj_set_style_bg_opa(w.busy,LV_OPA_60,0);
    lv_obj_set_style_radius(w.busy,lv_obj_get_style_radius(w.tile,LV_PART_MAIN),0);
    w.spinner=spinner_create(w.busy,ui::px(large?30:20),ui::px(large?4:3));
    if(w.spinner)lv_obj_center(w.spinner);
  }
  // Cover the whole card, padding included, at the width the card asks for: a slot that just turned
  // wide is still single width in LVGL's own coordinates. Unchanged sizes cost LVGL nothing.
  lv_obj_set_pos(w.busy,-lv_obj_get_style_pad_left(w.tile,LV_PART_MAIN),-lv_obj_get_style_pad_top(w.tile,LV_PART_MAIN));
  lv_obj_set_size(w.busy,tile_width(w),tile_height(w));
  lv_obj_remove_flag(w.busy,LV_OBJ_FLAG_HIDDEN);
  // Controls and custom parts created after the sheet would otherwise paint over its right side.
  if(lv_obj_get_index(w.busy)!=(int32_t)lv_obj_get_child_count(w.tile)-1)lv_obj_move_foreground(w.busy);
}
// A camera whose picture fills its card turns the firmware's one spinner in the middle of the card while that picture
// loads (firmware 0.3.3), the size a busy card's has: a page turn to a camera shows it coming, never an empty card.
inline void set_loading(Widgets &w,bool on,int width,int height){
  if(!on){if(w.loading)lv_obj_add_flag(w.loading,LV_OBJ_FLAG_HIDDEN);return;}
  const bool large=ui::large();const int size=ui::px(large?30:20);
  if(!w.loading)w.loading=spinner_create(w.tile,size,ui::px(large?4:3));
  if(!w.loading)return;
  lv_obj_set_pos(w.loading,(width-size)/2,(height-size)/2);
  lv_obj_remove_flag(w.loading,LV_OBJ_FLAG_HIDDEN);
}
// The card that takes a whole page (firmware 0.2.62+). Without a control it is one big button: the icon in a
// large circle with the name and the state under it (the circle in the state colour, the card white or its own
// pastel like every other card), so a wall switch reads from across the room and a push anywhere works. With a
// small slider, direct controls or a graph the double-width card's head stays on top and the control takes
// a strip at the bottom, so a tap anywhere else still does what a tap on the tile does. The built-in cards
// (clock, forecast, sun path) simply get the whole page.
// A media player over the whole page (firmware 0.2.64+): the head as on every full card, and under it the media card
// itself, wide: the cover at the left, the track, the bar and the keys beside it, the volume row along the bottom.
// Parts: 0 placeholder, 1 its icon, 2 title, 3 artist, 4 track, 5 fill, 6 elapsed, 7 total, 8-10 keys, 11 volume
// down, 12 slider, 13 volume up (firmware 0.39.0; a mute key and the percentage before), MEDIA_PICTURE (14) the cover. Built once per slot and moved on every redraw.
inline void media_tile_key_event(lv_event_t *e){
  unsigned code=(uintptr_t)lv_event_get_user_data(e);unsigned slot=code/16,n=code%16;
  if(slot>=widgets.size() || n>2)return;
  auto &w=widgets[slot];
  if(!enabled || !fresh() || w.index>=model.count || w.extra_mode!="media")return;
  if(lv_obj_has_state(lv_event_get_target_obj(e),LV_STATE_DISABLED))return;
  const uint32_t now=esphome::millis();
  auto &t=model.tiles[w.index];
  // Play or pause is a wish; the track keys are not.
  if(!(n==1&&!media_off(t)?allowed_wish(now,500+slot*16+n,"media key "+std::to_string(slot)):allowed(now,500+slot*16+n,"media key "+std::to_string(slot))))return;
  if(!t.available() || t.waiting(now))return;
  static const int commands[]={21,20,22};
  media_action(t,n==1 && media_off(t)?24:commands[n]);
}
inline void render_media_full(Widgets &w,const Tile &t,bool big,int content_w,int content_h,int head_h){
  using namespace media_card;
  using namespace tile_controls;
  const auto &x=t.extra();
  const Metrics m=media_metrics(big,x.media_duration);
  const int top=head_h+(ui::px(big?8:4));
  const Layout l=layout(m,content_w,std::max(40,content_h-top-(ui::px(big?4:2))));
  begin_extra(w,"media",content_w,content_h);
  auto at=[&](Rect r){r.y+=top;return r;};
  const bool usable=fresh()&&t.available(),track=usable&&has_track(t.state),play=media_card::playing(t.state);
  const uint32_t f=t.supported;auto can=[&](uint32_t bit){return usable&&(!f||(f&bit));};
  const size_t slot=&w-widgets.data();
  // The placeholder and the player's icon; the cover comes over them once the app served it. A board that draws no
  // pictures has neither (firmware 0.46.0): the player stands in the middle of the room instead.
  if(l.art.w){
    w.parts[0]=media_box(w.extra,w.parts[0],at(l.art),theme::tint(theme::ha::LIGHT_BLUE,51),l.art_radius);
    lv_obj_remove_flag(w.parts[0],LV_OBJ_FLAG_HIDDEN);
    const std::string glyph=icon_for(t);
    // The big icon where the square holds it (a cover that shrank for the volume row may not), else the tile's icon.
    const lv_font_t *placeholder_font=big_icon_font&&font_has(big_icon_font,glyph)&&lv_font_get_line_height(big_icon_font)<=l.art.h?big_icon_font:w.icon_font;
    if(!w.parts[1]){w.parts[1]=lv_label_create(w.parts[0]);lv_obj_remove_flag(w.parts[1],LV_OBJ_FLAG_CLICKABLE);}
    set_font(w.parts[1],placeholder_font);set_color(w.parts[1],LV_STYLE_TEXT_COLOR,theme::rgb(theme::icon(theme::ha::LIGHT_BLUE)));label(w.parts[1],glyph);lv_obj_center(w.parts[1]);
  }else if(w.parts[0])lv_obj_add_flag(w.parts[0],LV_OBJ_FLAG_HIDDEN);
  // The colour behind the cover's rounded corners: the card's own, as the palette below will paint it (firmware 0.3.2).
  // Read from the card, it was the colour of whatever the card showed before, so a new card asked for a cover with the
  // wrong corners first and for the right one after its first drawing.
  const uint32_t ground=t.transparent?card_ground(w):card_surface(w);
  const bool pictured=camera_supported()&&track&&!x.media_picture.empty();
  w.cover_entity=pictured?t.entity:std::string();w.cover_mark=pictured?x.media_picture:std::string();
  w.cover_size=l.art.w;w.cover_ground=ground;w.cover_rect=at(l.art);
  // What the store has of its cover is drawn at once; the loader fetches it otherwise (card_picture_wants), on the glass
  // and ahead for a kept page, and the card draws itself again when it is here.
  lv_image_dsc_t *src=pictured?picture_of(cover_key(w.cover_entity,w.cover_mark,w.cover_size,w.cover_ground)):nullptr;
  if(src){
    const std::string key=cover_key(w.cover_entity,w.cover_mark,w.cover_size,w.cover_ground);
    w.parts[MEDIA_PICTURE]=media_picture_show(w.extra,w.parts[MEDIA_PICTURE],at(l.art),src);w.cover_shown=key;w.cover_hold=0;
  }else if(w.parts[MEDIA_PICTURE]){
    // The player's cover of before stays while the next one is on its way, and a moment while it shows none, as on the
    // card (MediaFace, firmware 0.52.0): the square stood empty between two tracks. Only where the store keeps it.
    const uint32_t now=esphome::millis();
    const bool keep=pictures_kept()&&!warming&&w.cover_shown.rfind("cover|"+t.entity+"|",0)==0;
    if(keep&&!w.cover_hold)w.cover_hold=(now+(pictured?MEDIA_FACE_WAIT_MS:MEDIA_FACE_HOLD_MS))|1;
    if(!keep||static_cast<int32_t>(now-w.cover_hold)>=0){
      lv_obj_delete(w.parts[MEDIA_PICTURE]);w.parts[MEDIA_PICTURE]=nullptr;
      w.cover_shown.clear();w.cover_hold=0;
    }
  }
  // Title, artist · album, left-aligned beside the cover, in the middle without one.
  const lv_font_t *title_font=watch_font?watch_font:w.title_font,*artist_font=control_font?control_font:w.title_font,*small=small_font?small_font:w.title_font;
  const lv_text_align_t words_align=m.art?LV_TEXT_ALIGN_LEFT:LV_TEXT_ALIGN_CENTER;
  auto text=[&](unsigned i,const lv_font_t *font,const Rect &r,lv_text_align_t align,const std::string &value,theme::Role role){
    auto *p=part_label(w,i,font,r.x,r.y+top,r.w,align,value);lv_label_set_long_mode(p,LV_LABEL_LONG_DOT);set_color(p,LV_STYLE_TEXT_COLOR,theme::color(role));lv_obj_remove_flag(p,LV_OBJ_FLAG_HIDDEN);return p;
  };
  // The title and the artist line roll by when they are too long (firmware 0.2.77+), as on the card.
  marquee(text(2,title_font,l.title,words_align,track&&!x.media_title.empty()?x.media_title:std::string(idle_text(usable?t.state:"unavailable")),theme::INK));
  if(l.artist)marquee(text(3,artist_font,l.artist_line,words_align,track?subtitle(x.media_artist,x.media_album):std::string(),theme::MUTED));
  else if(w.parts[3])lv_obj_add_flag(w.parts[3],LV_OBJ_FLAG_HIDDEN);
  // The progress bar and its times, wherever the keys are: at nought with 0:00 at both ends without a track or a length
  // (a stream, the moment between two tracks), as on the card (firmware 0.52.0; it went and came back before).
  // A stream keeps the bar empty, with "Live" where the time stands (media_live).
  w.media_bar_w=l.bar.w;
  const bool barred=!(usable&&media_off(t)),timed=track&&x.media_duration,live=media_live(t);
  w.media_live=live;
  if(barred){
    w.parts[4]=media_box(w.extra,w.parts[4],at(l.bar),theme::hex(theme::TRACK),LV_RADIUS_CIRCLE);lv_obj_remove_flag(w.parts[4],LV_OBJ_FLAG_HIDDEN);
    Rect fill=at(l.bar);fill.w=std::max(l.bar.h,timed?l.bar.w*std::max(0,progress(x.media_position,x.media_position_at,now_epoch(),play,x.media_duration))/1000:0);
    w.parts[5]=media_box(w.extra,w.parts[5],fill,media_accent(),LV_RADIUS_CIRCLE);
    if(live)lv_obj_add_flag(w.parts[5],LV_OBJ_FLAG_HIDDEN);else lv_obj_remove_flag(w.parts[5],LV_OBJ_FLAG_HIDDEN);
  }else for(unsigned i:{4u,5u})if(w.parts[i])lv_obj_add_flag(w.parts[i],LV_OBJ_FLAG_HIDDEN);
  if(barred&&l.times){
    if(live)text(6,small,l.elapsed,LV_TEXT_ALIGN_LEFT,tr(txt::camera_live),theme::INK);
    else text(6,small,l.elapsed,LV_TEXT_ALIGN_LEFT,clock_text(timed?elapsed_seconds(x.media_position,x.media_position_at,now_epoch(),play,x.media_duration):0),theme::SUBTLE);
    text(7,small,l.total,LV_TEXT_ALIGN_RIGHT,live?std::string():clock_text(timed?x.media_duration:0),theme::SUBTLE);
  }else for(unsigned i:{6u,7u})if(w.parts[i])lv_obj_add_flag(w.parts[i],LV_OBJ_FLAG_HIDDEN);
  // The keys and the volume row. Their events carry the slot: the tile in it may change with the page. An off player
  // shows one power key and no volume row.
  const lv_font_t *key_font=mini_icon_font?mini_icon_font:w.icon_font;
  auto user=[&](unsigned n){return (void*)(uintptr_t)(slot*16+n);};
  auto show=[&](unsigned i,bool on){if(w.parts[i]){if(on)lv_obj_remove_flag(w.parts[i],LV_OBJ_FLAG_HIDDEN);else lv_obj_add_flag(w.parts[i],LV_OBJ_FLAG_HIDDEN);}};
  const bool off=usable && media_off(t), volume=!off && std::isfinite(t.volume);
  if(off){
    w.parts[9]=media_key(w.extra,w.parts[9],at(l.play),glyph::STANDBY,w.icon_font,true,false,can(feature::MEDIA_TURN_ON),media_tile_key_event,user(1));
    show(9,can(feature::MEDIA_TURN_ON));
  }else{
    w.parts[8]=media_key(w.extra,w.parts[8],at(l.prev),glyph::PREVIOUS,key_font,false,false,can(feature::MEDIA_PREVIOUS),media_tile_key_event,user(0));
    w.parts[9]=media_key(w.extra,w.parts[9],at(l.play),play?glyph::PAUSE:glyph::PLAY,w.icon_font,true,false,can(feature::MEDIA_PLAY|feature::MEDIA_PAUSE),media_tile_key_event,user(1));
    w.parts[10]=media_key(w.extra,w.parts[10],at(l.next),glyph::NEXT,key_font,false,false,can(feature::MEDIA_NEXT),media_tile_key_event,user(2));
    show(9,true);
  }
  show(8,!off);show(10,!off);
  if(volume)media_volume_row(w.extra,&w.parts[11],at(l.minus),at(l.volume),at(l.plus),t,big,usable,(void*)(uintptr_t)w.index,false,key_font);
  show(11,volume);show(12,volume);show(13,volume);
}
// A thermostat's mode bar (firmware 0.3.3): under its -/+ on a card of "Temperature and mode" (the tall card's parts
// 2 and 4..9) and on its own as the panel of "Mode" (the panel's pill and segments, firmware 0.19.0). One bar, one
// drawing, one press: a segment says its place in the bar, and the bar's modes are climate_bar_keys for the room it
// holds, so the press finds the mode the segment shows.
constexpr int CLIMATE_MODE_PARTS=climate_tile::SEGMENTS;
// The segments of the bar a card shows: its panel's for "Mode", its tall card's otherwise.
inline lv_obj_t *const *mode_bar_segments(const Widgets &w){
  if(w.panel_mode=="mode")return w.segments.data();
  return w.extra_mode=="tall"?&w.parts[4]:nullptr;
}
inline void climate_mode_key_event(lv_event_t *e){
  const unsigned code=(uintptr_t)lv_event_get_user_data(e),slot=code/16,n=code%16;
  if(slot>=widgets.size())return;
  auto &w=widgets[slot];if(w.index>=model.count)return;
  auto *const *segments=mode_bar_segments(w);if(!segments)return;
  unsigned room=0;
  for(int i=0;i<CLIMATE_MODE_PARTS;++i)if(segments[i]&&!lv_obj_has_flag(segments[i],LV_OBJ_FLAG_HIDDEN))++room;
  auto &t=model.tiles[w.index];const uint32_t now=esphome::millis();
  if(n>=room||!enabled||!fresh()||!t.available()||t.waiting(now)||!tile_controls::thermostat(t))return;
  std::array<tile_controls::Key,CLIMATE_MODE_PARTS> keys;
  if(n>=tile_controls::climate_bar_keys(t,keys,room))return;
  if(!allowed_wish(now,700+slot*8+n,"control "+std::to_string(slot)))return;
  if(keys[n].command==tile_controls::OPEN_CARD){active_index=w.index;show_detail(w.index);return;}
  key_press(t,keys[n].command,keys[n].arg);
}
// One segment of a thermostat's mode bar: the mode's icon, its word where the bar has room, and the mode it is in
// filled in Home Assistant's colour for it with a white icon on it. `code`: its card's slot * 16 and its place.
inline void mode_segment(lv_obj_t *&p,lv_obj_t *parent,unsigned code,climate_tile::Rect r,const tile_controls::Key &k,bool words,
                         const lv_font_t *glyphs,const lv_font_t *text,bool ready,const Tile &t){
  if(!p){
    p=lv_obj_create(parent);lv_obj_remove_style_all(p);lv_obj_set_style_radius(p,LV_RADIUS_CIRCLE,0);
    lv_obj_set_style_bg_opa(p,LV_OPA_COVER,LV_STATE_PRESSED);lv_obj_set_style_opa(p,LV_OPA_40,LV_STATE_DISABLED);
    lv_obj_add_flag(p,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(p,LV_OBJ_FLAG_SCROLLABLE);
    for(int c=0;c<2;++c){auto *label=lv_label_create(p);lv_obj_remove_flag(label,LV_OBJ_FLAG_CLICKABLE);}
    lv_obj_add_event_cb(p,climate_mode_key_event,LV_EVENT_SHORT_CLICKED,(void*)(uintptr_t)code);
  }
  lv_obj_set_pos(p,r.x,r.y);lv_obj_set_size(p,r.w,r.h);lv_obj_remove_flag(p,LV_OBJ_FLAG_HIDDEN);
  const bool mode=k.command==tile_controls::HVAC_MODE;
  lv_obj_set_style_bg_opa(p,k.checked?LV_OPA_COVER:LV_OPA_TRANSP,0);
  // A humidifier's mode has no colour of its own in Home Assistant: the one it is in takes the humidifier's blue.
  if(k.checked)set_color(p,LV_STYLE_BG_COLOR,lv_color_hex(theme::foreground(tile_controls::humidifier(t)?tile_controls::accent(t):tile_controls::mode_color(k.arg))));
  set_color(p,LV_STYLE_BG_COLOR,theme::color(theme::KEY_PRESSED),LV_STATE_PRESSED);
  const auto ink=k.checked?theme::color(theme::ON_ACCENT):theme::color(mode?theme::SLATE:theme::MUTED);
  auto *icon=lv_obj_get_child(p,0),*word=lv_obj_get_child(p,1);
  set_font(icon,glyphs);label(icon,k.icon);set_color(icon,LV_STYLE_TEXT_COLOR,ink);
  const bool with_word=words&&mode;
  const std::string name=with_word?tile_controls::thermostat_mode_text(t,k.arg):"";
  const int gh=lv_font_get_line_height(glyphs),space=ui::px(ui::large()?6:3),tw=with_word?text_width(name,text)+2:0;
  const int x0=(r.w-gh-(with_word?space+tw:0))/2;
  lv_obj_set_pos(icon,x0,(r.h-gh)/2);lv_obj_set_size(icon,gh,gh);lv_obj_set_style_text_align(icon,LV_TEXT_ALIGN_CENTER,0);
  set_hidden(word,!with_word);
  if(with_word){
    set_font(word,text);label(word,name);set_color(word,LV_STYLE_TEXT_COLOR,ink);
    const int th=lv_font_get_line_height(text);lv_obj_set_pos(word,x0+gh+space,(r.h-th)/2);lv_obj_set_size(word,tw,th);
  }
  if(ready)lv_obj_remove_state(p,LV_STATE_DISABLED);else lv_obj_add_state(p,LV_STATE_DISABLED);
}
// The whole bar in `bar` of `parent`: its track, and a segment per mode climate_bar_keys picks for `room`, with words
// beside the icons where every segment has room for its own ("Heat", "Cool", "Auto"). Segments past them hide.
inline void draw_mode_bar(Widgets &w,const Tile &t,lv_obj_t *parent,lv_obj_t *&track,lv_obj_t **segments,climate_tile::Rect bar,
                          int room,const climate_tile::Metrics &cm,bool large){
  if(!track){track=lv_obj_create(parent);lv_obj_remove_style_all(track);lv_obj_set_style_bg_opa(track,LV_OPA_COVER,0);
    lv_obj_set_style_radius(track,LV_RADIUS_CIRCLE,0);lv_obj_remove_flag(track,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(track,LV_OBJ_FLAG_SCROLLABLE);}
  lv_obj_set_pos(track,bar.x,bar.y);lv_obj_set_size(track,bar.w,bar.h);lv_obj_remove_flag(track,LV_OBJ_FLAG_HIDDEN);
  set_color(track,LV_STYLE_BG_COLOR,theme::color(theme::TRACK));
  std::array<tile_controls::Key,CLIMATE_MODE_PARTS> modes;
  const unsigned count=tile_controls::climate_bar_keys(t,modes,std::max(0,room));
  const auto seg=climate_tile::segments(cm,bar,(int)count);
  const lv_font_t *glyphs=mini_icon_font?mini_icon_font:w.icon_font;
  bool words=count>0;
  for(unsigned n=0;n<count&&words;++n)
    words=modes[n].command!=tile_controls::HVAC_MODE||seg[n].w>=lv_font_get_line_height(glyphs)+ui::px(large?26:14)+
          text_width(tile_controls::thermostat_mode_text(t,modes[n].arg),w.value_font);
  const unsigned slot=&w-widgets.data();
  const bool ready=fresh()&&t.available()&&!t.waiting(esphome::millis());
  for(unsigned n=0;n<(unsigned)CLIMATE_MODE_PARTS;++n){
    if(n<count)mode_segment(segments[n],parent,slot*16+n,seg[n],modes[n],words,glyphs,w.value_font,ready,t);
    else if(segments[n])lv_obj_add_flag(segments[n],LV_OBJ_FLAG_HIDDEN);
  }
}
// The cover cards the cover layout draws (firmware 0.57.0, hello feature cover_rows): any card with its slats chosen,
// and a card of one cell with a control chosen at all (on large glass a 1x1 holds a bar or a row of keys). The add-on
// sends a one-row card its slats and a 1x1 its control only to a screen that says cover_rows.
inline bool cover_row_card(const Tile &t){
  if(t.domain()!="cover")return false;
  if(tile_controls::cover_tilt_selected(t))return true;
  const auto kind=tile_controls::panel_kind(t);
  return t.column_span()==1&&t.row_span()==1&&!t.full&&(kind=="position"||kind=="buttons");
}
inline cover_tile::Layout cover_tile_layout(const Tile &t,tall_tile::Rect body,int touch,int gap,int caption){
  // Capability, not freshness, decides the layout: while HA reconnects the same keys stay, greyed out (ready below).
  if(!cover_row_card(t))return {};
  const auto card=tile_controls::cover_card(t);std::array<tile_controls::Key,3> keys;
  const auto kind=tile_controls::panel_kind(t);
  const bool position=kind=="position"&&card.position;
  const bool tilt=tile_controls::cover_tilt_selected(t);
  // Slats chosen on a cover that reports none (a motor swapped, a group that lost its venetian blind): a card larger than
  // one cell keeps the card it has without them, as before firmware 0.57.0; a 1x1 still lays out its primary control.
  const bool one_cell=t.column_span()==1&&t.row_span()==1&&!t.full;
  if(tilt&&!card.tilt&&!card.tilt_keys&&!one_cell)return {};
  // A blind worked by its position gets its open, stop and close as well where the card has room for them too.
  return cover_tile::layout(body,touch,gap,caption,2*touch,
    position,kind=="buttons"?tile_controls::keys_for(t,keys):0,
    tilt&&card.tilt,tilt&&card.tilt_keys?tile_controls::cover_tilt_keys(t,keys):0,
    position&&card.keys?tile_controls::cover_keys(t,keys):0,t.row_span()>1||t.full);
}
// A cover card whose slats share one row with its primary control (cover_tile::SWAP) shows one of the two: the swap key
// turns it. By the tile's index, so it stays while the card is drawn again; a new layout starts at the primary
// (cancel_layout_input clears the table, so an index that is another cover's now does not inherit the swap).
inline std::array<uint8_t,TILES_MAX> cover_swapped{};
inline void render_cover_tile(Widgets &w,const Tile &t,const cover_tile::Layout &l,int width,int height);
// Both overlay and tile use the same feature-filtered cover commands. Slot ownership is resolved on every tap;
// stale/offline/waiting entities stay inert. A cover card's keys: tag slot*16 + group*3 + key (group 0 the primary, 1 the slats, 2 open/stop/close beside the
// sliders), slot*16 + 15 the swap key.
inline void cover_tile_key_event(lv_event_t *e){
  const unsigned tag=(uintptr_t)lv_event_get_user_data(e),slot=tag/16,part=tag%16;
  if(slot>=widgets.size()||(part>=9&&part!=15))return;
  auto &w=widgets[slot];if(w.index>=model.count||w.extra_mode!="cover_tilt")return;
  const auto &t=model.tiles[w.index];
  if(part==15){
    if(!enabled||!screen_input::touch_guard.accept(esphome::millis(),600+tag))return;
    cover_swapped[w.index]^=1;w.cached_active=-1;refresh_tile(w.index,redraw_log::TileWhy::finger);return;
  }
  // The cards of this layout: the tilt cards and, since the one-row cards (0.57.0), the 1x1 with buttons or a
  // position, whose keys answered nothing while this asked for the slats alone (GitHub #363).
  if(!enabled||!fresh()||!t.available()||t.waiting(esphome::millis())||!cover_row_card(t))return;
  std::array<tile_controls::Key,3> keys;
  const unsigned group=part/3,count=group==1?tile_controls::cover_tilt_keys(t,keys):group==2?tile_controls::cover_keys(t,keys):tile_controls::keys_for(t,keys);
  if(part%3>=count||keys[part%3].disabled)return;
  if(!screen_input::touch_guard.accept(esphome::millis(),600+tag))return;
  cover_key(model.tiles[w.index],keys[part%3].command);
}
inline void render_cover_tile(Widgets &w,const Tile &t,const cover_tile::Layout &l,int width,int height){
  hide_panel(w);
  const unsigned index=w.index<TILES_MAX?w.index:0;
  if(l.swap.empty())cover_swapped[index]=0;
  const bool swapped=cover_swapped[index];
  // Rebuild only when structure, physical size, theme or the swap changes, never for live position updates (which
  // must not interrupt an active drag).
  const int signature=(int)t.supported+(tile_controls::panel_kind(t)=="position"?256:0)+
    (tile_controls::panel_kind(t)=="buttons"?512:0)+(theme::dark?1024:0)+(swapped?2048:0)+(int)l.tier*4096;
  if(w.extra_mode=="cover_tilt"&&(w.hand_cx!=width||w.hand_cy!=height||w.hand_width!=signature))end_extra(w);
  begin_extra(w,"cover_tilt",width,height);w.hand_cx=width;w.hand_cy=height;w.hand_width=signature;
  const int slot=&w-widgets.data(),gap=ui::px(ui::large()?8:4);
  const bool ready=fresh()&&t.available()&&!t.waiting(esphome::millis());
  const lv_font_t *icons=mini_icon_font?mini_icon_font:w.icon_font;
  auto key=[&](int part,const tall_tile::Rect &r,const char *glyph,bool on){
    w.parts[part]=media_key(w.extra,w.parts[part],{r.x,r.y,r.w,r.h},glyph,icons,false,false,on,cover_tile_key_event,(void*)(uintptr_t)(slot*16+(part==13?15:part-4)));
    lv_obj_set_ext_click_area(w.parts[part],0);
    set_color(w.parts[part],LV_STYLE_BG_COLOR,lv_color_hex(cover_track()));
    set_color(lv_obj_get_child(w.parts[part],0),LV_STYLE_TEXT_COLOR,lv_color_hex(COVER_ACCENT));
  };
  for(int i=0;i<3;++i){
    const auto &g=l.groups[i];if(g.area.empty())continue;
    if(i<2&&!l.swap.empty()&&(i==1)!=swapped)continue;
    const float value=i?t.extra().tilt:t.position;
    if(i<2&&!g.caption.empty()){
      // The word and the value where both fit, else the word, else the value of a slider, else nothing: never cut.
      const std::string word=tr(i?txt::cover_tilt:txt::cover_position);
      const std::string number=g.slider&&std::isfinite(value)?screen_text::percent((int)std::lround(value)):"";
      std::string caption;
      for(const auto &c:{number.empty()?std::string():word+" "+number,word,number})
        if(!c.empty()&&text_width(c,w.value_font)<=g.caption.w){caption=c;break;}
      auto *label=part_label(w,i,w.value_font,g.caption.x,g.caption.y,g.caption.w,LV_TEXT_ALIGN_CENTER,caption);
      set_color(label,LV_STYLE_TEXT_COLOR,theme::color(theme::MUTED));
    }
    if(g.slider){
      auto *&slider=w.parts[2+i];
      if(!slider)slider=g.lying?cover_bar(w.extra,g.control.x,g.control.y,g.control.w,g.control.h,value,i,slider_event,nullptr,t.tilt_middle)
                               :cover_slider(w.extra,g.control.x,g.control.y,g.control.w,g.control.h,value,i,slider_event,nullptr,t.tilt_middle);
      if(captured_slider!=slider)lv_slider_set_value(slider,std::isfinite(value)?(int)std::lround((i?value:100-value)*10):(i?500:0),LV_ANIM_OFF);
      if(ready)lv_obj_remove_state(slider,LV_STATE_DISABLED);else lv_obj_add_state(slider,LV_STATE_DISABLED);
      travel_look(slider,t,i==1,i!=1);
    }else{
      std::array<tile_controls::Key,3> keys;
      const unsigned count=i==1?tile_controls::cover_tilt_keys(t,keys):i==2?tile_controls::cover_keys(t,keys):tile_controls::keys_for(t,keys);
      if(!count)continue;
      // In a row the keys share its width; in a stack they share its height, each as high as the stack allows.
      const int along=g.horizontal?(g.control.w-(int)(count-1)*gap)/(int)count:g.control.w;
      const int across=g.horizontal?g.control.h:(g.control.h-(int)(count-1)*gap)/(int)count;
      for(unsigned n=0;n<count;++n){
        const tall_tile::Rect r{g.control.x+(g.horizontal?(int)n*(along+gap):0),g.control.y+(g.horizontal?0:(int)n*(across+gap)),along,across};
        key(4+i*3+n,r,keys[n].icon,ready&&!keys[n].disabled);
      }
    }
  }
  // The swap key shows what the row turns into: the slats, or the blind again.
  if(!l.swap.empty())key(13,l.swap,swapped?tile_controls::glyph::SHADE:tile_controls::glyph::SLATS,ready);
}
// Additional rows extend the existing heading and controls. Compact tiles never
// enter this path. The selected control kind and its events remain authoritative.
// A heading's circle carries the look's icon in the look's proportion (base_circle). On a card too narrow or too short
// for that, the circle may take up to half the width first; below that the icon steps down to the control keys' icon
// font (the same glyphs, smaller), so it never spills out of its circle. No icon font of its own (firmware 0.3.1).
inline const lv_font_t *heading_icon(const Widgets &w,int &circle,int max_side,int width){
  if(circle>=w.base_circle||!mini_icon_font)return w.icon_font;
  circle=std::min({w.base_circle,max_side,width/2});
  return circle>=w.base_circle?w.icon_font:mini_icon_font;
}
// A live camera's picture is the card, on every size: its name at the bottom on the shade the app made there, or
// nothing on it at all. A camera's state ("Idle") says nothing next to its own picture. The name stands where the
// picture will put it while the card waits for it, so the card does not move when the picture comes. False for a
// camera the app has no picture of (or a screen that cannot ask now): the caller then draws the head its size has.
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
