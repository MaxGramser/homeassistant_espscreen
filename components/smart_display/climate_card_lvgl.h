// The climate card and its parts.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the rules themselves, which are plain C++ without LVGL in climate_card.h, climate_tile.h.
// What proves it: tests/test_climate_card.cpp, web/wasm/test_climate_detail.mjs.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// ---- Climate card (firmware 0.2.80): one computed card on every board ----
// Home Assistant's thermostat dialog in this look, worked out from the entity's own attributes: the state
// under the name, a white card with the setpoint between a round - and a round + key, a key per mode, and a
// white card with a segmented row for the fan and for the swing. Until now every board carried its own table
// of pixels for this card (six layouts in the board file) and only the Guition's table had room for the fan
// and swing rows, which is why a CYD sent them to a second page. climate_card.h works out where the parts go;
// this draws them, and the same card now stands on every board.
inline lv_obj_t *climate_number=nullptr;   // the setpoint itself: a -/+ tap moves it before Home Assistant answers

// What the board brings to the card: its class, the fonts it writes with and where its top bar sits.
inline climate_card::Metrics climate_metrics(bool large){
  const lv_font_t *text=large?detail_font:(control_font?control_font:detail_font);
  const lv_font_t *small=small_font?small_font:text;
  const lv_font_t *number=setpoint_font?setpoint_font:(watch_font?watch_font:detail_font);
  const lv_font_t *icons=tile_icon_font();
  climate_card::Metrics m;
  m.large=large;
  const lv_font_t *small_number=watch_font?watch_font:(control_font?control_font:detail_font);
  m.number_h=lv_font_get_line_height(number);
  m.number_w=text_width("-88.8°",number);
  m.small_number_h=std::min<int>(m.number_h,lv_font_get_line_height(small_number));
  m.small_number_w=text_width("-88.8°",small_number);
  m.caption_h=lv_font_get_line_height(small);
  m.text_h=lv_font_get_line_height(text);
  m.status_h=m.text_h;  // the state line is written in the text font: on dense glass taller than the default 25 px
  m.icon_h=icons?lv_font_get_line_height(icons):m.text_h;
  const auto bar=detail_bar::metrics();
  m.bar=bar.key;m.bar_x=bar.x;m.bar_y=bar.y;
  m.touch=ui::touch_min();
  return m;
}
// Where the card's content begins: under the top bar.
inline int climate_top(const climate_card::Metrics &m){return m.bar_y+m.bar+ui::px(m.large?8:4);}
// One column, or two on glass too short for the stack (a 480 x 272 panel, a wide seven-inch).
inline int climate_columns(const Tile &t,bool large){
  const climate_card::Metrics m=climate_metrics(large);
  const int modes=(int)tile_controls::climate_modes(t).size(),rows=(int)tile_controls::climate_rows(t).size();
  return overlay_card::columns(climate_top(m)+climate_card::need_height(m,modes,rows)+m.margin(),climate_card::min_column(m));
}
inline std::string climate_number_text(const Tile &t){
  const float shown=std::isfinite(t.edit_value)?t.edit_value:tile_controls::edit_target(t);
  return tile_controls::format_value(shown,tile_controls::edit_step(t),tile_controls::setpoint_suffix(t));
}
// A range (firmware 0.19.0): its two ends side by side in the number's place, as on Home Assistant's thermostat card.
// A tap picks the end the -/+ move (Tile::range_end, the same one the tile's chip shows); that one is drawn in full,
// the other at 70 %.
// A range (heat/cool, firmware 0.25.0): under the number the device's whole span as an LVGL scale, the range on it as
// Home Assistant's dual thermostat draws it (ha-control-circular-slider, renderArc): the low end's colour runs from
// the minimum up to the low target, the high end's from the high target up to the maximum, both at half opacity, and
// the bare track between the two targets. Where the room lies outside the range, the part the device has to cover
// (current to target) is drawn in full, with a mark at the current temperature; inside it nothing marks the room, the
// state line says it. A knob stands on each end; a tap on one chooses the end the -/+ move, and the number shows that
// end. The -/+ and the chosen knob take that side's tint, so what a key moves is always in sight.
inline lv_obj_t *climate_ends[2]={nullptr,nullptr};       // the knob of each end
inline lv_obj_t *climate_now_mark=nullptr;                // the current temperature on the band, while it is outside the range
inline lv_obj_t *climate_keys[2]={nullptr,nullptr};       // the - and +, which take the chosen side's colour
inline int climate_track_x=0,climate_track_w=1,climate_track_y=0,climate_knob_d=24;
inline std::vector<std::string> climate_tick_words;inline std::vector<const char*> climate_tick_src;
inline lv_style_t climate_sec_style[5];inline bool climate_sec_init=false;   // heat 50 %, cool 50 %, heat full, cool full, the bare track
// The swatch a side of a range is drawn in: Home Assistant's heat and cool, as the tiles' own card colours.
inline uint32_t range_tint(uint8_t end){return theme::surface(theme::swatch(end==tile_controls::RANGE_HIGH?"blue":"orange"));}
inline int range_units(const Tile &t,float v){return (int)std::lround((v-t.minimum)/tile_controls::edit_step(t));}
inline int range_x(const Tile &t,float v){
  const float span=std::max(0.01f,t.maximum-t.minimum);
  return climate_track_x+(int)std::lround(std::clamp((v-t.minimum)/span,0.f,1.f)*climate_track_w);
}
// The parts that follow the chosen end and the values: the number, the keys' tint, the knobs and the room's mark.
inline void climate_paint_ends(const Tile &t){
  const float step=tile_controls::edit_step(t);
  const float low=tile_controls::range_end(t,tile_controls::RANGE_LOW),high=tile_controls::range_end(t,tile_controls::RANGE_HIGH);
  if(climate_number)label(climate_number,tile_controls::format_value(tile_controls::range_end(t,t.range_end),step,"°"));
  for(auto *key:climate_keys)if(key)lv_obj_set_style_bg_color(key,lv_color_hex(range_tint(t.range_end)),0);
  for(uint8_t i=0;i<2;++i){
    if(!climate_ends[i])continue;
    const uint8_t end=i?tile_controls::RANGE_HIGH:tile_controls::RANGE_LOW;
    const bool chosen=end==t.range_end;
    const int d=chosen?climate_knob_d:climate_knob_d*3/4;
    lv_obj_set_size(climate_ends[i],d,d);
    lv_obj_set_pos(climate_ends[i],range_x(t,i?high:low)-d/2,climate_track_y-d/2);
    lv_obj_set_style_border_width(climate_ends[i],chosen?ui::px(3):ui::px(2),0);
    lv_obj_set_style_bg_color(climate_ends[i],chosen?lv_color_hex(range_tint(end)):theme::color(theme::CARD),0);
  }
  if(climate_now_mark&&std::isfinite(t.current))lv_obj_set_x(climate_now_mark,range_x(t,t.current)-ui::px(2)/2);
}
// One step of a range's chosen end, never past the other end: the number follows the finger at once, tick() sends both
// ends after a short pause.
inline void range_step(Tile &t,int direction){
  const float step=tile_controls::edit_step(t);
  const float low=tile_controls::range_end(t,tile_controls::RANGE_LOW),high=tile_controls::range_end(t,tile_controls::RANGE_HIGH);
  if(t.range_end==tile_controls::RANGE_HIGH)t.edit_high=tile_controls::step_value(high,step,low,t.maximum,direction);
  else t.edit_value=tile_controls::step_value(low,step,t.minimum,high,direction);
  t.edit_since=esphome::millis();t.edit_sent=false;
}
// A -/+ tap: the number follows the finger at once, tick() sends the last value after a short pause, exactly
// as the -/+ pill on a wide tile does. On a range it moves the chosen end.
inline void climate_step(Tile &t,int direction){
  if(tile_controls::climate_range(t)){
    range_step(t,direction);
    climate_paint_ends(t);
    if(detail_index<model.count)refresh_tile(detail_index,redraw_log::TileWhy::finger);
    return;
  }
  const uint32_t now=esphome::millis();
  const float current=std::isfinite(t.edit_value)?t.edit_value:tile_controls::edit_target(t);
  t.edit_value=tile_controls::step_value(current,tile_controls::edit_step(t),t.minimum,t.maximum,direction);
  t.edit_since=now;t.edit_sent=false;
  // The number and the keys at the ends of the span follow in place (docs/CARD_PARTS.md).
  if(!card_repaint(t)&&climate_number)label(climate_number,climate_number_text(t));
}
// Holding a key steps three times a second.
inline void climate_hold(lv_event_t *e){
  const int direction=(int)(intptr_t)lv_event_get_user_data(e);
  if(detail_index>=model.count)return;
  auto &t=model.tiles[detail_index];
  if(!fresh()||!t.available()||esphome::millis()-t.edit_since<300)return;
  climate_step(t,direction);
  touch_feedback::step(direction);   // each step of a held key clicks, as a detent (touch_feedback.h)
}
// A humidifier's dial (firmware 0.42.0+): Home Assistant's humidity ring (ha-control-circular-slider) round the number,
// as a picture and not a control (the - and + set it, a finger on a small ring would not): a 270 degree track, the part from the minimum to the target filled
// at half strength (from the target to the maximum for a dehumidifier), the part still to go from the humidity now to
// the target in full while the device has work to do, a dot at the humidity now and a white knob at the target.
inline void humidity_ring(const Tile &t,const climate_card::Rect &card,const climate_card::Rect &minus,const climate_card::Rect &plus,bool large){
#if LV_USE_ARC
  const int d=std::min(plus.x-minus.right()-ui::px(large?16:8),card.h-ui::px(large?16:8));
  if(d<ui::px(70))return;
  const int cx=card.cx(),cy=card.cy(),w=std::max(ui::px(large?10:6),d/14);
  const bool off=tile_controls::climate_off(t),dry=t.device_class=="dehumidifier";
  const uint32_t colour=off?theme::hex(theme::OFF):theme::state(tile_controls::accent(t));
  auto arc=[&](int a0,int a1,uint32_t c,lv_opa_t opa){
    if(a1<=a0)return;
    auto *o=lv_arc_create(detail_root);lv_obj_remove_style_all(o);lv_obj_set_size(o,d,d);lv_obj_set_pos(o,cx-d/2,cy-d/2);
    lv_obj_remove_flag(o,LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_style_arc_width(o,w,LV_PART_MAIN);lv_obj_set_style_arc_rounded(o,true,LV_PART_MAIN);
    lv_obj_set_style_arc_color(o,lv_color_hex(c),LV_PART_MAIN);lv_obj_set_style_arc_opa(o,opa,LV_PART_MAIN);
    lv_obj_set_style_arc_opa(o,LV_OPA_TRANSP,LV_PART_INDICATOR);
    lv_arc_set_bg_angles(o,a0%360,a1%360);
  };
  const float span=std::max(1.0f,t.maximum-t.minimum);
  auto angle=[&](float v){return 135+(int)std::lround(std::clamp((v-t.minimum)/span,0.0f,1.0f)*270);};
  auto point=[&](int a,int size,uint32_t c,lv_opa_t opa,bool knob){
    const int r=d/2-w/2;
    const int x=cx+(int)std::lround(r*std::cos(a*3.14159265f/180)),y=cy+(int)std::lround(r*std::sin(a*3.14159265f/180));
    auto *o=detail_shape(detail_root,x-size/2,y-size/2,size,size,c,LV_RADIUS_CIRCLE);
    lv_obj_remove_flag(o,LV_OBJ_FLAG_CLICKABLE);lv_obj_set_style_bg_opa(o,opa,0);
    if(knob){lv_obj_set_style_shadow_width(o,ui::px(6),0);lv_obj_set_style_shadow_opa(o,LV_OPA_30,0);}
  };
  arc(135,405,theme::hex(theme::TRACK),LV_OPA_COVER);
  const float target=std::isfinite(t.edit_value)?t.edit_value:t.target;
  if(std::isfinite(target)){
    if(!off)arc(dry?angle(target):135,dry?405:angle(target),colour,LV_OPA_50);
    const bool work=!off&&std::isfinite(t.current)&&(dry?t.current>target:t.current<target);
    if(work)arc(dry?angle(target):angle(t.current),dry?angle(t.current):angle(target),colour,LV_OPA_COVER);
    if(!off&&std::isfinite(t.current))point(angle(t.current),std::max(ui::px(6),w*2/3),theme::hex(theme::INK),LV_OPA_50,false);
    point(angle(target),w+ui::px(large?8:4),theme::hex(theme::CARD),LV_OPA_COVER,true);
  }
#else
  (void)t;(void)card;(void)minus;(void)plus;(void)large;
#endif
}
// ---- The climate card's parts (docs/CARD_PARTS.md): each paints itself from the tile ----
// The mode keys a card shows: the first `count` modes, and the mode in use in the last key when it lies beyond them,
// so the card always says where it stands.
inline std::vector<std::string> climate_shown_keys(const std::vector<std::string> &modes,int count,const std::string &mode){
  std::vector<std::string> keys(modes.begin(),modes.begin()+std::min<int>(count,(int)modes.size()));
  if((int)modes.size()>count&&count>0)for(int i=count;i<(int)modes.size();++i)if(modes[i]==mode)keys.back()=mode;
  return keys;
}
inline int climate_card_mode_keys=0;  // how many mode keys the open card has
// The power key: lit while the device runs in any mode.
inline void climate_power_paint(lv_obj_t *key,const Tile &t,const CardPart &){
  const bool off=tile_controls::climate_off(t);
  set_color(key,LV_STYLE_BG_COLOR,theme::color(off?theme::KEY:theme::ACCENT_TINT));
  if(auto *glyph=lv_obj_get_child(key,0))set_color(glyph,LV_STYLE_TEXT_COLOR,theme::color(off?theme::ICON_OFF:theme::ACCENT_ICON));
}
// The number between - and +: the value being set, grey while the device is off.
inline void climate_number_paint(lv_obj_t *number,const Tile &t,const CardPart &){
  label(number,climate_number_text(t));
  set_color(number,LV_STYLE_TEXT_COLOR,theme::color(tile_controls::climate_off(t)?theme::OFF:theme::INK));
}
// - or + (arg -1 or 1): faded at the end of the device's span.
inline void climate_limit_paint(lv_obj_t *key,const Tile &t,const CardPart &part){
  const float shown=std::isfinite(t.edit_value)?t.edit_value:tile_controls::edit_target(t);
  const bool known=std::isfinite(shown)&&!tile_controls::climate_range(t);
  const bool end=known&&(part.arg<0?shown<=t.minimum:shown>=t.maximum);
  paint_state(key,LV_STATE_DISABLED,card_blocked||end);
}
// A mode key (value: its mode), in Home Assistant's colour for its mode while it is the one in use.
inline void climate_mode_paint(lv_obj_t *key,const Tile &t,const CardPart &part){
  const bool selected=!tile_controls::climate_off(t)&&part.value==tile_controls::current_mode(t);
  const uint32_t colour=tile_controls::humidifier(t)?tile_controls::accent(t):tile_controls::mode_color(part.value);
  set_color(key,LV_STYLE_BG_COLOR,selected?lv_color_hex(colour):theme::color(theme::CARD));
  set_number(key,LV_STYLE_BORDER_WIDTH,selected?0:1);
  if(auto *glyph=lv_obj_get_child(key,0))set_color(glyph,LV_STYLE_TEXT_COLOR,theme::color(selected?theme::ON_ACCENT:theme::SLATE));
}
// A segment of the fan or swing row (arg: the row's kind, value: its choice).
inline void climate_row_paint(lv_obj_t *segment,const Tile &t,const CardPart &part){
  // The rows are worked out once per paint of the card, not once per segment.
  static uint32_t pass=0;static std::vector<tile_controls::ClimateRow> rows;
  if(pass!=card_pass){pass=card_pass;rows=tile_controls::climate_rows(t);}
  for(const auto &row:rows)if(row.kind==(char)part.arg){segment_paint(segment,row.current==part.value);return;}
}
// The line that says what the device does (arg 1: the short words of the caption under the number).
inline void card_status_paint(lv_obj_t *line,const Tile &t,const CardPart &part){ label(line,card_status(t,part.arg!=0)); }
// What decides the climate card's parts: its modes and rows, a range's band and a humidifier's ring, which draw their
// values into their shape. A mode, a fan speed, the number, on and off are painted.
inline uint32_t climate_card_shape(const Tile &t){
  Fingerprint f;
  auto add=[&](const std::string &text){f.add(text);f.write('|');};
  auto number=[&](float v){char b[24];snprintf(b,sizeof(b),"%.2f",v);add(b);};
  add(t.entity);f.write(fresh()&&t.available());add(t.unit);add(t.device_class);
  number(t.minimum);number(t.maximum);number(t.step);add(std::to_string(t.supported));
  const auto modes=tile_controls::climate_modes(t);
  for(const auto &m:modes)add(m);
  f.write('|');for(const auto &k:climate_shown_keys(modes,climate_card_mode_keys,tile_controls::current_mode(t)))add(k);
  for(const auto &row:tile_controls::climate_rows(t)){f.write(row.kind);add(row.icon);for(const auto &v:row.values)add(v);for(const auto &w:row.labels)add(w);}
  const bool range=tile_controls::climate_range(t),wet=tile_controls::humidifier(t);
  f.write(range);f.write(wet);
  if(range){number(tile_controls::range_end(t,tile_controls::RANGE_LOW));number(tile_controls::range_end(t,tile_controls::RANGE_HIGH));number(t.current);number(t.edit_value);number(t.edit_high);f.write(t.range_end);}
  if(wet){number(t.current);number(tile_controls::edit_target(t));number(t.edit_value);add(t.extra().hvac_action);f.write(tile_controls::climate_off(t));}
  return f.value;
}
inline void render_climate_detail(Tile &t,bool large,int width,int height,int columns){
  const lv_font_t *text=large?detail_font:(control_font?control_font:detail_font);
  const lv_font_t *small=small_font?small_font:text;
  const lv_font_t *number_font=setpoint_font?setpoint_font:(watch_font?watch_font:detail_font);
  const lv_font_t *tile_icons=tile_icon_font();
  const lv_font_t *mini=mini_icon_font?mini_icon_font:detail_font;
  const auto modes=tile_controls::climate_modes(t);
  const auto rows=tile_controls::climate_rows(t);
  const climate_card::Metrics m=climate_metrics(large);
  const int top=climate_top(m);
  const bool range=tile_controls::climate_range(t);
  // A range's band takes the place of the word under the number: the knob, a hair of air, and the degrees under the
  // knobs where they stay clear of them.
  climate_card::Metrics mr=m;
  if(range){
    const int knob=std::clamp(m.min_row()-ui::px(6),ui::px(18),ui::px(26));
    mr.caption_h=knob+ui::px(4)+m.caption_h;
  }
  auto l=climate_card::layout(mr,width,top,height-m.margin(),(int)modes.size(),(int)rows.size(),columns,range);
  // A humidifier's ring takes the setpoint card's height, the - and + a finger's size at its sides.
  if(tile_controls::humidifier(t)){
    const auto &c=l.setpoint;const int key=std::max(m.touch,ui::px(large?64:40)),in=m.key_inset();
    l.minus={c.x+in,c.cy()-key/2,key,key};l.plus={c.right()-in-key,c.cy()-key/2,key,key};
    const int block=l.number.h+(l.caption.empty()?0:l.caption.h);
    l.number.y=c.cy()-block/2;if(!l.caption.empty())l.caption.y=l.number.bottom();
  }
  const bool off=tile_controls::climate_off(t),known=std::isfinite(tile_controls::edit_target(t))||std::isfinite(t.edit_value);
  const std::string mode=tile_controls::current_mode(t);
  detail_placed=true;   // the layout has already put every block where the glass has room for it

  // The power key, across from the back key: lit while the device runs in any mode.
  climate_card_mode_keys=0;
  card_bind(climate_round_key(bar_key(),tile_controls::glyph::POWER,mini,off?theme::KEY:theme::ACCENT_TINT,
                              off?theme::ICON_OFF:theme::ACCENT_ICON,CLIMATE_POWER),t,climate_power_paint);
  if(!l.status.empty()){
    detail_status=card_bind(detail_text(detail_root,"",l.status.x,l.status.y,l.status.w,text,LV_TEXT_ALIGN_CENTER,theme::MUTED),t,card_status_paint);
  }
  // The setpoint: the number between the two keys, the word under it while there is room.
  detail_card(l.setpoint.x,l.setpoint.y,l.setpoint.w,l.setpoint.h);
  const lv_font_t *key_icons=tile_icons&&lv_font_get_line_height(tile_icons)<=l.minus.h-ui::px(8)?tile_icons:mini;
  auto *down=climate_round_key(l.minus,tile_controls::glyph::MINUS,key_icons,theme::TRACK,theme::INK,CLIMATE_DOWN);
  auto *up=climate_round_key(l.plus,tile_controls::glyph::PLUS,key_icons,theme::TRACK,theme::INK,CLIMATE_UP);
  // A range stops at the other end in climate_step; a single setpoint fades the key at the end of the span.
  card_bind(down,t,climate_limit_paint,"",-1);card_bind(up,t,climate_limit_paint,"",1);
  (void)known;
  for(lv_obj_t *key:{down,up})lv_obj_add_event_cb(key,climate_hold,LV_EVENT_LONG_PRESSED_REPEAT,(void*)(intptr_t)(key==up?1:-1));
  const lv_font_t *face=l.small_number?(watch_font?watch_font:number_font):number_font;
  if(range){
    // One number, the end last chosen; under it the band (see climate_paint_ends above).
    climate_number=detail_text(detail_root,"",l.number.x,l.number.y,l.number.w,face,LV_TEXT_ALIGN_CENTER,off?theme::OFF:theme::INK);
    climate_keys[0]=down;climate_keys[1]=up;
    const auto &sw=l.caption;
    const float step=tile_controls::edit_step(t);
    const float low=tile_controls::range_end(t,tile_controls::RANGE_LOW),high=tile_controls::range_end(t,tile_controls::RANGE_HIGH);
    // The knob stays a touch smaller than its row, so it keeps clear of the digits above it.
    climate_knob_d=std::clamp(m.min_row()-ui::px(6),ui::px(18),ui::px(26));
    const int track_h=std::max(ui::px(6),climate_knob_d/3);
    auto *scale=lv_scale_create(detail_root);lv_obj_remove_style_all(scale);
    climate_track_x=sw.x+climate_knob_d/2;climate_track_w=sw.w-climate_knob_d;climate_track_y=sw.y+climate_knob_d/2+ui::px(2);
    // The band's centre line is climate_track_y: the scale draws its main line just inside its top edge. Its side
    // padding holds the band's round ends, which reach half a width past the first and last value.
    lv_obj_set_pos(scale,climate_track_x-track_h/2,climate_track_y-track_h/2);lv_obj_set_size(scale,climate_track_w+track_h,sw.h-climate_knob_d/2-ui::px(2)+track_h/2);
    lv_obj_set_style_pad_left(scale,track_h/2,LV_PART_MAIN);lv_obj_set_style_pad_right(scale,track_h/2,LV_PART_MAIN);
    lv_scale_set_mode(scale,LV_SCALE_MODE_HORIZONTAL_BOTTOM);
    lv_obj_remove_flag(scale,LV_OBJ_FLAG_CLICKABLE);
    const int units=std::max(1,range_units(t,t.maximum));
    lv_scale_set_range(scale,0,units);
    // A tick a degree places the labels; only the ticks with a degree under them are drawn, every 5 or 10 degrees.
    const int degrees=std::max(1,(int)std::lround(t.maximum-t.minimum));
    const int every=degrees>40?10:5;
    lv_scale_set_total_tick_count(scale,degrees+1);
    lv_scale_set_major_tick_every(scale,every);
    lv_scale_set_label_show(scale,true);
    climate_tick_words.clear();climate_tick_src.clear();
    for(int d=0;d<=degrees;d+=every)climate_tick_words.push_back(tile_controls::format_value(t.minimum+d,1,"°"));
    for(auto &w:climate_tick_words)climate_tick_src.push_back(w.c_str());
    climate_tick_src.push_back(nullptr);
    lv_scale_set_text_src(scale,climate_tick_src.data());
    // The main line only sets the band's place; the sections draw it, so no two lines mix at the ends.
    lv_obj_set_style_line_width(scale,track_h,LV_PART_MAIN);lv_obj_set_style_line_opa(scale,LV_OPA_TRANSP,LV_PART_MAIN);
    lv_obj_set_style_line_opa(scale,LV_OPA_TRANSP,LV_PART_ITEMS);lv_obj_set_style_length(scale,0,LV_PART_ITEMS);
    lv_obj_set_style_line_width(scale,1,LV_PART_INDICATOR);lv_obj_set_style_line_color(scale,theme::color(theme::LINE),LV_PART_INDICATOR);
    lv_obj_set_style_length(scale,track_h/2+ui::px(4),LV_PART_INDICATOR);
    // The degrees start under the knobs: the gap after the tick is what the knob reaches past the tick. (pad_bottom
    // of the indicator part is that gap in a straight scale; pad_radial only counts in a round one.)
    lv_obj_set_style_pad_bottom(scale,std::max(0,climate_knob_d/2-(track_h/2+ui::px(4))+ui::px(2)),LV_PART_INDICATOR);
    lv_obj_set_style_text_font(scale,small,LV_PART_INDICATOR);lv_obj_set_style_text_color(scale,theme::color(theme::SUBTLE),LV_PART_INDICATOR);
    if(!climate_sec_init){for(auto &st:climate_sec_style)lv_style_init(&st);climate_sec_init=true;}
    const char *sides[2]={"heat","cool"};
    for(int i=0;i<5;++i){
      lv_style_set_line_width(&climate_sec_style[i],track_h);
      lv_style_set_line_color(&climate_sec_style[i],i==4?theme::color(theme::TRACK):lv_color_hex(tile_controls::mode_color(sides[i%2])));
      lv_style_set_line_opa(&climate_sec_style[i],i<2?LV_OPA_50:LV_OPA_COVER);
    }
    const int lo=range_units(t,low),hi=range_units(t,high);
    const int cur=std::isfinite(t.current)?std::clamp(range_units(t,t.current),0,units):-1;
    auto band=[&](int style,int from,int to){
      if(to<from)return;
      auto *sec=lv_scale_add_section(scale);
      lv_scale_set_section_range(scale,sec,from,to);
      lv_scale_set_section_style_main(scale,sec,&climate_sec_style[style]);
    };
    band(4,lo,hi);band(0,0,lo);band(1,hi,units);
    const bool cold=cur>=0&&cur<=lo,hot=cur>=0&&cur>=hi;
    if(cold)band(2,cur,lo);
    if(hot)band(3,hi,cur);
    // A section's line has square ends (the scale reads only its width, colour and opacity): the band's two round
    // ends are two discs, opaque in the half-mixed colour, so where they overlap the section's end nothing darkens.
    for(int i=0;i<2;++i){
      auto *cap=detail_shape(detail_root,(i?climate_track_x+climate_track_w:climate_track_x)-track_h/2,climate_track_y-track_h/2,track_h,track_h,theme::mix(tile_controls::mode_color(sides[i]),theme::hex(theme::CARD),128),LV_RADIUS_CIRCLE);
      lv_obj_remove_flag(cap,LV_OBJ_FLAG_CLICKABLE);
    }
    for(uint8_t i=0;i<2;++i){
      auto *knob=detail_button("",0,0,climate_knob_d,climate_knob_d,i?CLIMATE_END_HIGH:CLIMATE_END_LOW);
      lv_obj_set_style_radius(knob,LV_RADIUS_CIRCLE,0);
      lv_obj_set_style_bg_color(knob,theme::color(theme::CARD),0);
      lv_obj_set_style_bg_color(knob,lv_color_hex(range_tint(i?tile_controls::RANGE_HIGH:tile_controls::RANGE_LOW)),LV_STATE_PRESSED);
      lv_obj_set_style_border_color(knob,lv_color_hex(tile_controls::mode_color(sides[i])),0);
      lv_obj_set_style_shadow_width(knob,ui::px(6),0);lv_obj_set_style_shadow_opa(knob,LV_OPA_20,0);
      lv_obj_set_ext_click_area(knob,ui::touch_min()/2);
      climate_ends[i]=knob;
    }
    // The room's mark: a line a little taller than the band, only while the device has work to do. Home Assistant
    // cuts a gap in its arc of 24 px; in a band this thin a gap reads as a stain, a line reads.
    climate_now_mark=detail_shape(detail_root,0,climate_track_y-track_h/2-ui::px(2),ui::px(2),track_h+ui::px(4),theme::hex(theme::INK),ui::px(1));
    lv_obj_remove_flag(climate_now_mark,LV_OBJ_FLAG_CLICKABLE);
    if(!cold&&!hot)lv_obj_add_flag(climate_now_mark,LV_OBJ_FLAG_HIDDEN);
    climate_paint_ends(t);
  }else{
    if(tile_controls::humidifier(t))humidity_ring(t,l.setpoint,l.minus,l.plus,large);
    climate_number=card_bind(detail_text(detail_root,"",l.number.x,l.number.y,l.number.w,face,LV_TEXT_ALIGN_CENTER,off?theme::OFF:theme::INK),t,climate_number_paint);
  }
  // The word under the number, or what the thermostat is doing when the glass had no room for a line of its own.
  if(!range&&!l.caption.empty()){
    auto *caption=detail_text(detail_root,l.caption_is_status?std::string():std::string(tr(txt::climate_target)),
                              l.caption.x,l.caption.y,l.caption.w,small,LV_TEXT_ALIGN_CENTER,theme::SUBTLE);
    if(l.caption_is_status){detail_status=card_bind(caption,t,card_status_paint,"",1);detail_status_brief=true;}
  }
  // One key per mode, in Home Assistant's colour for the one in use. A device with one mode shows none: the
  // power key already turns it on and off.
  if(l.mode_count){
    const int shown_modes=std::min<int>(l.mode_count,(int)modes.size());
    const int key_w=(l.modes.w-(shown_modes-1)*l.mode_gap)/std::max(1,shown_modes);
    // More modes than keys: the mode in use takes the last key, so the card always says where it stands.
    climate_card_mode_keys=shown_modes;
    const std::vector<std::string> keys=climate_shown_keys(modes,shown_modes,mode);
    std::vector<int> commands(shown_modes);
    for(int i=0;i<shown_modes;++i)commands[i]=CLIMATE_MODE_FIRST+(int)(std::find(modes.begin(),modes.end(),keys[i])-modes.begin());
    const lv_font_t *mode_icons=tile_icons&&lv_font_get_line_height(tile_icons)<=l.modes.h-ui::px(6)?tile_icons:mini;
    for(int i=0;i<shown_modes;++i){
      auto *key=detail_button("",l.modes.x+i*(key_w+l.mode_gap),l.modes.y,key_w,l.modes.h,commands[i]);
      lv_obj_set_style_radius(key,l.modes.h/2,0);
      lv_obj_set_style_bg_color(key,theme::color(theme::KEY),LV_STATE_PRESSED);
      lv_obj_set_style_border_color(key,theme::color(theme::LINE),0);
      auto *glyph=lv_obj_get_child(key,0);
      if(mode_icons)lv_obj_set_style_text_font(glyph,mode_icons,0);
      lv_label_set_text(glyph,tile_controls::thermostat_mode_icon(t,keys[i]));
      lv_obj_set_size(glyph,LV_SIZE_CONTENT,LV_SIZE_CONTENT);lv_obj_center(glyph);
      card_bind(key,t,climate_mode_paint,keys[i]);
    }
  }
  // The fan and the swing, each a row of choices behind its icon, on one white card.
  if(l.row_count){
    detail_card(l.settings.x,l.settings.y,l.settings.w,l.settings.h);
    for(int i=0;i<l.row_count&&i<(int)rows.size();++i){
      const auto &row=rows[i];
      const int icon_h=mini?lv_font_get_line_height(mini):m.text_h;
      detail_text(detail_root,row.icon,l.row_icons[i].x,l.row_icons[i].y+(l.row_icons[i].h-icon_h)/2,l.row_icons[i].w,mini,LV_TEXT_ALIGN_LEFT,theme::SUBTLE);
      int chosen=-1;
      for(size_t v=0;v<row.values.size();++v)if(row.values[v]==row.current)chosen=(int)v;
      const auto made=segments(l.row_tracks[i].x,l.row_tracks[i].y,l.row_tracks[i].w,l.row_tracks[i].h,row.labels,chosen,
                               CLIMATE_ROW_FIRST+i*6,theme::hex(theme::TRACK),false,text,small);
      for(size_t v=0;v<made.size()&&v<row.values.size();++v)card_bind(made[v],t,climate_row_paint,row.values[v],row.kind);
    }
  }
  // Everything that changes with a mode, a choice, the number or on and off paints itself from here on.
  card_shaped(t,climate_card_shape);
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
