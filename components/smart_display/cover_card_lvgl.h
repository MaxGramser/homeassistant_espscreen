// The cover card and its parts.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the rules themselves, which are plain C++ without LVGL in cover_tile.h, cover_paint.h, cover_travel.h.
// What proves it: web/wasm/test_cover_keys.mjs, tests/test_cover_card.py.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// ---- Cover card (firmware 0.2.50+): Home Assistant's cover dialog in the style of the vacuum and climate cards ----
// A tall slider per movement: the position as a blind hanging from the top (a fully open cover shows none of it)
// and the tilt as a handle over slats, each with its value below, like Home Assistant's own sliders. Open, stop
// and close as a row of pill keys under them; the key of the direction the cover moves is filled. A slider
// sends its value when the finger lifts, and shows it while it moves.
// Home Assistant's purple for covers; the track and the slats are its tints (cover_paint.h).
inline constexpr uint32_t COVER_ACCENT = cover_paint::ACCENT;
inline uint32_t cover_track(){return cover_paint::track();}
inline lv_obj_t *cover_values[2]{};
inline void cover_slider_event(lv_event_t *e){
  auto *slider=lv_event_get_target_obj(e);auto code=lv_event_get_code(e);
  const bool tilt=(uintptr_t)lv_event_get_user_data(e)==1;
  if(code==LV_EVENT_VALUE_CHANGED){
    // The range reaches past 0 and 1000 only to keep the handle inside the track.
    int raw=lv_slider_get_value(slider);
    if(raw<0||raw>1000){raw=std::clamp(raw,0,1000);lv_slider_set_value(slider,raw,LV_ANIM_OFF);}
    int percent=(int)std::lround(raw/10.0f);
    if(auto *value=cover_values[tilt?1:0])label(value,screen_text::percent(tilt?percent:100-percent));
    return;
  }
  if(code!=LV_EVENT_RELEASED||detail_index>=model.count)return;
  auto &t=model.tiles[detail_index];
  if(!fresh()||!t.available()||!screen_input::touch_guard.accept_slider(esphome::millis(),390+(tilt?1:0)))return;
  const int raw=lv_slider_get_value(slider);
  const auto call=tile_controls::cover_position_action(t,raw,tilt);
  const float percent=std::lround(std::clamp(raw,0,1000)/10.0f);
  cover_go(t,call,tilt?percent:100-percent,0,tilt);
}
// One slider. The position fills from the top by how far the cover is closed; the tilt has no fill and its
// handle moves over the slats, drawn at their angle (firmware 0.57.0).
inline lv_obj_t *cover_slider(lv_obj_t *parent,int x,int y,int w,int h,float value,bool tilt,lv_event_cb_t callback=nullptr,void *user=nullptr,bool middle=false){
  int radius=std::max(8,w/7),handle_h=std::max(4,w/18),handle_w=tilt?w*3/5:w*2/5,inset=std::max(6,w/9);
  if(tilt)detail_shape(parent,x,y,w,h,cover_track(),radius);
  auto *slider=lv_slider_create(parent);lv_obj_remove_style_all(slider);
  lv_obj_set_pos(slider,x,y);lv_obj_set_size(slider,w,h);lv_slider_set_orientation(slider,LV_SLIDER_ORIENTATION_VERTICAL);
  lv_obj_set_style_radius(slider,radius,LV_PART_MAIN);lv_obj_set_style_radius(slider,radius,LV_PART_INDICATOR);
  lv_obj_set_style_bg_color(slider,lv_color_hex(cover_track()),LV_PART_MAIN);lv_obj_set_style_bg_opa(slider,tilt?LV_OPA_TRANSP:LV_OPA_COVER,LV_PART_MAIN);
  lv_obj_set_style_bg_color(slider,lv_color_hex(COVER_ACCENT),LV_PART_INDICATOR);lv_obj_set_style_bg_opa(slider,tilt?LV_OPA_TRANSP:LV_OPA_COVER,LV_PART_INDICATOR);
  lv_obj_set_style_bg_color(slider,tilt?lv_color_hex(COVER_ACCENT):theme::color(theme::KNOB),LV_PART_KNOB);lv_obj_set_style_bg_opa(slider,LV_OPA_COVER,LV_PART_KNOB);
  lv_obj_set_style_radius(slider,LV_RADIUS_CIRCLE,LV_PART_KNOB);
  lv_obj_set_style_opa(slider,LV_OPA_50,LV_STATE_DISABLED);
  // LVGL centres the knob on the end of the fill in a square as wide as the slider; the pads shrink it to a
  // handle bar. The position's handle sits inside the blind, an inset above its edge; the tilt's is centred.
  int side=-(w-handle_w)/2;
  lv_obj_set_style_pad_left(slider,side,LV_PART_KNOB);lv_obj_set_style_pad_right(slider,side,LV_PART_KNOB);
  if(tilt){
    int squeeze=-(w-2*handle_h)/2;
    lv_obj_set_style_pad_top(slider,squeeze,LV_PART_KNOB);lv_obj_set_style_pad_bottom(slider,squeeze,LV_PART_KNOB);
    // A margin past both ends keeps the handle on the track at 0 and 100 %.
    int margin=1000*(inset+handle_h)/std::max(1,h-2*(inset+handle_h));
    lv_slider_set_range(slider,-margin,1000+margin);
    lv_slider_set_value(slider,std::isfinite(value)?(int)std::lround(std::clamp(value,0.0f,100.0f)*10):500,LV_ANIM_OFF);
    lv_obj_add_event_cb(slider,cover_paint::slats_draw,LV_EVENT_DRAW_MAIN_BEGIN,(void*)(uintptr_t)(middle?1:0));
  }else{
    lv_obj_set_style_pad_top(slider,inset+handle_h-w/2,LV_PART_KNOB);lv_obj_set_style_pad_bottom(slider,1-inset-w/2,LV_PART_KNOB);
    // Reversed, the fill hangs from the top; the stub past 0 holds the handle of a cover that is fully open.
    int stub=inset+handle_h+inset,below=1000*stub/std::max(1,h-stub);
    lv_slider_set_range(slider,1000,-below);
    lv_slider_set_value(slider,std::isfinite(value)?(int)std::lround((100.0f-std::clamp(value,0.0f,100.0f))*10):0,LV_ANIM_OFF);
  }
  // A thin track is fine to look at, not to hit: the touch area is grown to a finger's size.
  overlay_card::touchable(slider,w);
  if(callback){lv_obj_remove_flag(slider,LV_OBJ_FLAG_GESTURE_BUBBLE);lv_obj_set_ext_click_area(slider,0);lv_obj_add_event_cb(slider,callback,LV_EVENT_ALL,user);}
  else {
  lv_obj_add_event_cb(slider,cover_slider_event,LV_EVENT_VALUE_CHANGED,(void*)(uintptr_t)(tilt?1:0));
  lv_obj_add_event_cb(slider,cover_slider_event,LV_EVENT_RELEASED,(void*)(uintptr_t)(tilt?1:0));
  if(detail_action_count<32)detail_actions[detail_action_count++]=slider;
  }
  return slider;
}
inline void slider_handle(lv_obj_t *slider,int width,int height);
// The same two lying across a card one bar high (firmware 0.57.0), as Home Assistant's cover-position and
// cover-tilt-position tile features: the position fills from the left by how far the cover is closed (Home Assistant's
// slider is `inverted`), so a closed cover is a full bar, as the standing slider and the tile's strip are; the white
// handle of every tile bar (slider_handle); the tilt keeps its slats and its accent handle.
inline lv_obj_t *cover_bar(lv_obj_t *parent,int x,int y,int w,int h,float value,bool tilt,lv_event_cb_t callback,void *user,bool middle=false){
  lv_obj_t *slider=nullptr;
  if(tilt)slider=cover_paint::tilt_bar(parent,x,y,w,h,value,middle);
  else{
    slider=lv_slider_create(parent);lv_obj_remove_style_all(slider);
    lv_obj_set_pos(slider,x,y);lv_obj_set_size(slider,w,h);lv_slider_set_orientation(slider,LV_SLIDER_ORIENTATION_HORIZONTAL);
    lv_obj_set_style_bg_color(slider,lv_color_hex(cover_track()),LV_PART_MAIN);lv_obj_set_style_bg_opa(slider,LV_OPA_COVER,LV_PART_MAIN);
    lv_obj_set_style_bg_color(slider,lv_color_hex(COVER_ACCENT),LV_PART_INDICATOR);lv_obj_set_style_bg_opa(slider,LV_OPA_COVER,LV_PART_INDICATOR);
    lv_obj_set_style_opa(slider,LV_OPA_50,LV_STATE_DISABLED);
    lv_obj_set_style_radius(slider,2,LV_PART_KNOB);lv_obj_add_style(slider,theme::style(theme::Paint::knob),LV_PART_KNOB);
    lv_obj_set_style_bg_opa(slider,LV_OPA_COVER,LV_PART_KNOB);
    slider_handle(slider,w,h);
    lv_slider_set_value(slider,std::isfinite(value)?(int)std::lround((100.0f-std::clamp(value,0.0f,100.0f))*10):0,LV_ANIM_OFF);
  }
  overlay_card::touchable(slider,h);
  lv_obj_remove_flag(slider,LV_OBJ_FLAG_GESTURE_BUBBLE);lv_obj_set_ext_click_area(slider,0);
  lv_obj_add_event_cb(slider,callback,LV_EVENT_ALL,user);
  return slider;
}
// A row of pill keys with an icon each, as the climate card's modes. A key that cannot move the cover further
// is drawn disabled and left out of the keys the card enables again once Home Assistant answers.
// A key of the cover card (arg: its command): the direction the cover moves in lit, a key at its end stop faded.
inline void cover_key_paint(lv_obj_t *button,const Tile &t,const CardPart &part){
  std::array<tile_controls::Key,3> keys;
  unsigned n=tile_controls::cover_keys(t,keys);
  const tile_controls::Key *key=nullptr;
  for(unsigned i=0;i<n;++i)if(keys[i].command==part.arg)key=&keys[i];
  if(!key){n=tile_controls::cover_tilt_keys(t,keys);for(unsigned i=0;i<n;++i)if(keys[i].command==part.arg)key=&keys[i];}
  if(!key)return;
  set_color(button,LV_STYLE_BG_COLOR,key->checked?lv_color_hex(COVER_ACCENT):theme::color(theme::CARD));
  set_color(button,LV_STYLE_BG_COLOR,key->checked?lv_color_hex(theme::ha::PURPLE_PRESSED):theme::color(theme::KEY),LV_STATE_PRESSED);
  set_number(button,LV_STYLE_BORDER_WIDTH,key->checked?0:1);
  if(auto *glyph=lv_obj_get_child(button,0))set_color(glyph,LV_STYLE_TEXT_COLOR,theme::color(key->checked?theme::ON_ACCENT:theme::INK));
  paint_state(button,LV_STATE_DISABLED,card_blocked||key->disabled);
}
inline void cover_key_row(const Tile &t,const std::array<tile_controls::Key,3> &keys,unsigned count,int x,int y,int w,int h,int gap,const lv_font_t *icons){
  int key_w=count?(w-gap*((int)count-1))/(int)count:0;
  for(unsigned i=0;i<count;++i){
    const auto &key=keys[i];
    auto *button=detail_button("",x+(int)i*(key_w+gap),y,key_w,h,70+key.command);
    lv_obj_set_style_radius(button,h/2,0);
    lv_obj_set_style_border_color(button,theme::color(theme::LINE),0);
    auto *glyph=lv_obj_get_child(button,0);
    lv_obj_set_style_text_font(glyph,icons,0);lv_label_set_text(glyph,key.icon);
    lv_obj_set_size(glyph,LV_SIZE_CONTENT,LV_SIZE_CONTENT);lv_obj_center(glyph);
    card_bind(button,t,cover_key_paint,"",key.command);
  }
}
// A battery-powered cover shows its level at the top right, across from the back key: the meter over the
// percentage, red below 20 % (the battery sensor of its device, app 0.2.58+).
inline void cover_battery(const Tile &t,bool large,int width){
  if(!std::isfinite(t.battery))return;
  const lv_font_t *font=large?detail_font:(control_font?control_font:detail_font);
  // In the top bar's place for a key at the right (detail_bar), on the glass's edge.
  const auto slot=bar_key();
  int bar=slot.w,bar_y=slot.y,meter_w=ui::px(large?30:22),meter_h=ui::px(large?15:11),gap=ui::px(large?4:2);
  int level=(int)std::lround(std::clamp(t.battery,0.0f,100.0f));
  int line=lv_font_get_line_height(font),block=meter_h+gap+line,cx=slot.x+bar/2,y=bar_y+(bar-block)/2;
  vacuum_battery(detail_root,cx-meter_w/2-1,y,meter_w,meter_h,t.battery);
  detail_text(detail_root,screen_text::percent(level),cx-bar/2-8,y+meter_h+gap,bar+16,font,LV_TEXT_ALIGN_CENTER,theme::MUTED);
}
// A blind's slider is dragged, so it needs millimetres of glass, not a share of it: a panel that is wide and
// short (800 x 480 at 217 dpi, a 480 x 272 strip) cannot give a stack of slider, value and keys that height
// while half its width stays empty. Such a card stands in two columns instead: the sliders at their full
// height on the left, the keys beside them.
inline int cover_slider_min(bool large){return ui::mm(large?22:16);}
inline int cover_need_height(const Tile &t,bool large){
  auto card=tile_controls::cover_card(t);
  std::array<tile_controls::Key,3> keys,tilt_keys;
  const unsigned key_count=card.keys?tile_controls::cover_keys(t,keys):0;
  const unsigned tilt_count=card.tilt_keys?tile_controls::cover_tilt_keys(t,tilt_keys):0;
  const int rows=(key_count?1:0)+(tilt_count?1:0),gap=ui::px(large?12:6);
  const int text_h=lv_font_get_line_height(large?detail_font:(control_font?control_font:detail_font));
  const int value_h=lv_font_get_line_height(watch_font?watch_font:detail_font);
  const int box=cover_slider_min(large)+(large?value_h+text_h:0)+2*ui::px(large?16:6);
  return ui::px(large?108:72)+box+gap+rows*ui::px(large?64:38)+(rows>1?gap:0)+ui::px(large?18:6);
}
inline int cover_columns(const Tile &t,bool large){
  const auto card=tile_controls::cover_card(t);
  if(!card.position&&!card.tilt)return 1;   // a garage door has no slider to make tall
  return overlay_card::columns(cover_need_height(t,large),ui::mm(30));
}
// ---- The cover card's parts (docs/CARD_PARTS.md) ----
// A position (arg 0) or tilt (arg 1) slider follows the blind as it moves, unless a finger holds it.
inline float cover_value(const Tile &t,bool tilt){return tilt?t.extra().tilt:t.position;}
inline void cover_slider_paint(lv_obj_t *slider,const Tile &t,const CardPart &part){
  travel_look(slider,t,part.arg,!part.arg);
  if(lv_obj_has_state(slider,LV_STATE_PRESSED))return;
  const float v=cover_value(t,part.arg);
  const int raw=part.arg?(std::isfinite(v)?(int)std::lround(std::clamp(v,0.0f,100.0f)*10):500)
                        :(std::isfinite(v)?(int)std::lround((100.0f-std::clamp(v,0.0f,100.0f))*10):0);
  if(lv_slider_get_value(slider)!=raw)lv_slider_set_value(slider,raw,LV_ANIM_OFF);
}
inline void cover_value_paint(lv_obj_t *value,const Tile &t,const CardPart &part){
  const float v=cover_value(t,part.arg);
  label(value,std::isfinite(v)?screen_text::percent((int)std::lround(std::clamp(v,0.0f,100.0f))):std::string("--"));
}
// A door that only opens and closes: its icon in the field follows its state.
inline void cover_icon_paint(lv_obj_t *icon,const Tile &t,const CardPart &){label(icon,icon_for(t));}
// The line under the name, Home Assistant's words for the state (with the unit where there is one).
inline void detail_status_paint(lv_obj_t *line,const Tile &t,const CardPart &){label(line,screen_text::with_unit(card_status(t),t.unit));}
// What decides the cover card's parts: its sliders and keys, and the battery at the top. The position, the tilt,
// the direction it moves in and its end stops are painted.
inline uint32_t cover_card_shape(const Tile &t){
  Fingerprint f;auto add=[&](const std::string &text){f.add(text);f.write('|');};
  const auto card=tile_controls::cover_card(t);
  add(t.entity);add(std::to_string(t.supported));add(t.device_class);
  f.write(card.position);f.write(card.tilt);f.write(card.keys);f.write(card.tilt_keys);
  add(std::isfinite(t.battery)?std::to_string((int)std::lround(t.battery)):"");
  return f.value;
}
inline void render_cover_detail(Tile &t,bool large,int width,int height,int pad,int columns=1){
  auto card=tile_controls::cover_card(t);
  cover_battery(t,large,width);
  // A cover group's key (firmware 0.57.0): in the top bar at the right, where a light group's lamps key stands, it opens
  // the group's page with a card per cover (group_page.h); after the battery where the cover has one.
  if(group_page::available(t))climate_round_key(bar_key(std::isfinite(t.battery)?1:0),tile_controls::glyph::SLATS,mini_icon_font,theme::KEY,theme::INK,720);
  const lv_font_t *text=large?detail_font:(control_font?control_font:detail_font);
  const lv_font_t *big=watch_font?watch_font:detail_font;
  cover_values[0]=cover_values[1]=nullptr;
  int inner=width-2*pad,gap=ui::px(large?12:6),key_h=ui::px(large?64:38),bottom=height-(ui::px(large?18:6));
  // The tile icons' own size where it fits the keys (42 px on the Guition, 28 on the CYD).
  const lv_font_t *key_icons=widgets[0].icon_font && lv_font_get_line_height(widgets[0].icon_font)<=key_h-6?widgets[0].icon_font:(mini_icon_font?mini_icon_font:detail_font);
  std::array<tile_controls::Key,3> keys,tilt_keys;
  unsigned key_count=card.keys?tile_controls::cover_keys(t,keys):0,tilt_count=card.tilt_keys?tile_controls::cover_tilt_keys(t,tilt_keys):0;
  int rows=(key_count?1:0)+(tilt_count?1:0);
  int top=ui::px(large?108:72);
  const int n=(card.position?1:0)+(card.tilt?1:0);
  // Two columns on glass that is wide and short: the sliders keep the whole height on the left, the keys
  // stand beside them. A card in one column is the stack it has always been.
  const bool split=columns>=2 && n>0;
  const int edge=split?ui::px(16):(large?16:6);
  const int slider_w=split?ui::px(76):ui::px(large?(n==2?120:140):(n==2?48:56));
  const int slider_gap=split?ui::px(32):(large?ui::px(48):(n==2?16:0));
  int box_w=inner,keys_w=inner,keys_x=pad,keys_y=0,box_h=0;
  if(split){
    box_w=std::min(inner-ui::mm(30)-ui::column_gap(),n*slider_w+(n-1)*slider_gap+2*edge);
    keys_w=inner-box_w-ui::column_gap();
    keys_x=pad+box_w+ui::column_gap();
    box_h=bottom-top;
  }else{
    keys_y=bottom-rows*key_h-(rows>1?gap:0);
    box_h=keys_y-gap-top;
  }
  // The value and the name go under a slider, or beside it on a small screen where that fits. Two sliders
  // beside their values need more width than a 240 px panel in portrait has, and the card then stacks them.
  const int side_label=ui::px(n==2?76:96);
  const bool beside_fits=n*(slider_w+ui::px(8)+side_label)+(n-1)*slider_gap+2*ui::px(6)<=inner;
  const bool under=large||split||!beside_fits;
  if(card.position||card.tilt){
    detail_card(pad,top,box_w,box_h);
    struct Part{bool tilt;float value;const char *caption;};
    Part parts[2];int count=0;
    if(card.position)parts[count++]={false,t.position,tr(txt::cover_position)};
    if(card.tilt)parts[count++]={true,t.extra().tilt,tr(txt::cover_tilt)};
    int value_h=lv_font_get_line_height(big),caption_h=lv_font_get_line_height(text);
    auto percent=[](float value){return std::isfinite(value)?screen_text::percent((int)std::lround(std::clamp(value,0.0f,100.0f))):std::string("--");};
    if(under){
      // Columns: the slider with its value and name below.
      int slider_h=box_h-2*edge-value_h-caption_h+4;
      int x=pad+(box_w-(count*slider_w+(count-1)*slider_gap))/2;
      for(int i=0;i<count;++i,x+=slider_w+slider_gap){
        card_bind(cover_slider(detail_root,x,top+edge,slider_w,slider_h,parts[i].value,parts[i].tilt,nullptr,nullptr,t.tilt_middle),t,cover_slider_paint,"",parts[i].tilt);
        int ty=top+edge+slider_h+2,room=slider_w+slider_gap-4;
        cover_values[parts[i].tilt?1:0]=card_bind(detail_text(detail_root,percent(parts[i].value),x-(room-slider_w)/2,ty,room,big,LV_TEXT_ALIGN_CENTER,theme::INK),t,cover_value_paint,"",parts[i].tilt);
        detail_text(detail_root,parts[i].caption,x-(room-slider_w)/2,ty+value_h,room,text,LV_TEXT_ALIGN_CENTER,theme::SUBTLE);
      }
    }else{
      // The small screen puts the value and name beside each slider.
      int slider_h=box_h-2*edge,label_w=side_label;
      int column=slider_w+8+label_w,x=pad+(box_w-(count*column+(count-1)*slider_gap))/2;
      for(int i=0;i<count;++i,x+=column+slider_gap){
        card_bind(cover_slider(detail_root,x,top+edge,slider_w,slider_h,parts[i].value,parts[i].tilt,nullptr,nullptr,t.tilt_middle),t,cover_slider_paint,"",parts[i].tilt);
        int ty=top+(box_h-value_h-caption_h)/2;
        cover_values[parts[i].tilt?1:0]=card_bind(detail_text(detail_root,percent(parts[i].value),x+slider_w+8,ty,label_w,big,LV_TEXT_ALIGN_LEFT,theme::INK),t,cover_value_paint,"",parts[i].tilt);
        detail_text(detail_root,parts[i].caption,x+slider_w+8,ty+value_h,label_w,text,LV_TEXT_ALIGN_LEFT,theme::SUBTLE);
      }
    }
  }else{
    // Open and close only (a garage door, a gate): the cover's icon on a halo and its state, as the vacuum's hero.
    detail_card(pad,top,box_w,box_h);
    const lv_font_t *icon_font=widgets[0].icon_font?widgets[0].icon_font:mini_icon_font;
    int halo=std::min(box_h-24,ui::px(large?120:72));
    auto *ring=detail_shape(detail_root,pad+(box_w-halo)/2,top+(box_h-halo)/2,halo,halo,cover_track(),halo/2);
    if(icon_font)card_bind(detail_text(ring,icon_for(t),0,(halo-lv_font_get_line_height(icon_font))/2,halo,icon_font,LV_TEXT_ALIGN_CENTER,theme::foreground(COVER_ACCENT)),t,cover_icon_paint);
  }
  // Beside the sliders the keys stand under each other, like the switch on the wall next to a blind; under
  // them they keep their rows. A card with tilt keys as well falls back to rows when a stack would not fit.
  const int stacked=(int)(key_count+tilt_count);
  const bool stack_keys=split && stacked*key_h+(stacked-1)*gap<=box_h;
  if(stack_keys){
    const int key_w=std::min(keys_w,ui::mm(45));
    const int x=keys_x+(keys_w-key_w)/2;
    int y=top+(box_h-(stacked*key_h+(stacked-1)*gap))/2;
    auto one=[&](const tile_controls::Key &key){
      std::array<tile_controls::Key,3> single{key,{},{}};
      cover_key_row(t,single,1,x,y,key_w,key_h,gap,key_icons);
      y+=key_h+gap;
    };
    for(unsigned i=0;i<key_count;++i)one(keys[i]);
    for(unsigned i=0;i<tilt_count;++i)one(tilt_keys[i]);
  }else{
    int y=split?top+(box_h-rows*key_h-(rows>1?gap:0))/2:keys_y;
    if(key_count){cover_key_row(t,keys,key_count,keys_x,y,keys_w,key_h,gap,key_icons);y+=key_h+gap;}
    if(tilt_count)cover_key_row(t,tilt_keys,tilt_count,keys_x,y,keys_w,key_h,gap,key_icons);
  }
  card_shaped(t,cover_card_shape);
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
