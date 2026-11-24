// The light and fan card and its parts.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the rules themselves, which are plain C++ without LVGL in light_card.h, light_controls.h.
// What proves it: tests/test_light_card.cpp, tests/test_light_controls.cpp.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// ---- Light and fan card (firmware 0.2.80): the last card that was built in YAML ----
// A light without colour and a fan open this: a white card with a standing slider, the value under it and what
// it is under that, and the power key in the top bar across from the back key, where the thermostat has it. A
// light with colour or a colour temperature opens the colour card instead, as it always did.
//
// Until now this was `brightness_overlay`: a full-screen widget tree that sat in the LVGL tree whether it was
// open or not, eight sizes per board file, its own scripts for the preview and the send, and a slider whose
// fill was rounded less than its track, which made LVGL draw it through a buffer of 61 KB (0.2.93). It is a
// card like the others now - light_card.h says where the parts go, this draws them, the card is made when it
// opens and cleaned away when it closes - and the value it sends goes the way a tile's own slider goes
// (commit_slider: the 1 % floor of a light, the held value while it fades, the touch guard).
inline lv_obj_t *light_value=nullptr;

// What the board brings to the card: its class, the fonts it writes with and its top bar.
inline light_card::Metrics light_metrics(bool large) {
  const lv_font_t *big=watch_value_font?watch_value_font:(watch_font?watch_font:detail_font);
  const lv_font_t *text=large?detail_font:(control_font?control_font:detail_font);
  const lv_font_t *icons=tile_icon_font();
  light_card::Metrics m;
  m.large=large;
  m.value_h=lv_font_get_line_height(big);
  m.text_h=lv_font_get_line_height(text);
  m.icon_h=icons?lv_font_get_line_height(icons):ui::px(large?42:28);
  m.touch=ui::touch_min();
  m.pad=overlay_card::pad();
  const auto bar=detail_bar::metrics();
  m.bar=bar.key;m.bar_x=bar.x;m.bar_y=bar.y;
  return m;
}
// One column or two: the stack's own height decides, as it does for the thermostat and the blind.
inline int light_columns(bool large) {
  const auto m=light_metrics(large);
  return overlay_card::columns(light_card::stacked_height(m),m.slider_w()+2*m.edge());
}
// What the card writes beside the slider: the percentage, or the word Home Assistant uses when it is off.
// What the card writes under the slider: the percentage the slider stands at, or Home Assistant's own word for
// a light that is off, unavailable, or on without a brightness of its own.
inline std::string light_value_text(const Tile &t) {
  const int raw=slider_value(t);
  if(t.state=="on"&&raw>0)return screen_text::percent((raw+5)/10);
  return card_status(t);
}
inline void light_slider_event(lv_event_t *e) {
  auto *slider=lv_event_get_target_obj(e);const auto code=lv_event_get_code(e);
  if(code==LV_EVENT_VALUE_CHANGED){
    // The range reaches past its ends only to keep the handle inside the track (slider_handle).
    int raw=lv_slider_get_value(slider);
    if(raw<0||raw>1000){raw=std::clamp(raw,0,1000);lv_slider_set_value(slider,raw,LV_ANIM_OFF);}
    if(light_value)label(light_value,screen_text::percent((int)std::lround(raw/10.0f)));
    return;
  }
  // The send is the tile slider's own: the 1 % floor, the value held while the light fades, the touch guard.
  if(code==LV_EVENT_RELEASED&&screen_input::touch_guard.accept_slider(esphome::millis(),380))commit_slider(detail_index,lv_slider_get_value(slider));
}
// The standing slider of the card, drawn like the blind's: one radius on the track and the fill (a fill rounded
// less than its track costs a layer of tens of kilobytes on every redraw), a handle bar inside the fill.
inline lv_obj_t *light_slider(int x,int y,int w,int h,int raw,uint32_t accent,bool enabled,bool amber) {
  const int radius=std::max(8,w/7),handle_h=std::max(4,w/18),handle_w=w*2/5,inset=std::max(6,w/9);
  auto *slider=lv_slider_create(detail_root);lv_obj_remove_style_all(slider);
  lv_obj_set_pos(slider,x,y);lv_obj_set_size(slider,w,h);lv_slider_set_orientation(slider,LV_SLIDER_ORIENTATION_VERTICAL);
  lv_obj_set_style_radius(slider,radius,LV_PART_MAIN);lv_obj_set_style_radius(slider,radius,LV_PART_INDICATOR);
  // A light's track is the pale amber Home Assistant gives it; a fan's is the neutral one, so the track
  // never fights the fill's own colour.
  lv_obj_set_style_bg_color(slider,theme::color(amber&&raw>0?theme::AMBER_TRACK:theme::TRACK),LV_PART_MAIN);lv_obj_set_style_bg_opa(slider,LV_OPA_COVER,LV_PART_MAIN);
  lv_obj_set_style_bg_color(slider,lv_color_hex(accent),LV_PART_INDICATOR);lv_obj_set_style_bg_opa(slider,LV_OPA_COVER,LV_PART_INDICATOR);
  lv_obj_set_style_bg_color(slider,theme::color(theme::KNOB),LV_PART_KNOB);lv_obj_set_style_bg_opa(slider,LV_OPA_COVER,LV_PART_KNOB);
  lv_obj_set_style_radius(slider,LV_RADIUS_CIRCLE,LV_PART_KNOB);
  lv_obj_set_style_opa(slider,LV_OPA_50,LV_STATE_DISABLED);
  // LVGL centres the knob on the end of the fill in a square as wide as the slider; the pads shrink that square
  // to a handle bar and drop it an inset inside the fill, the way the blind's handle sits inside the blind.
  const int side=-(w-handle_w)/2;
  lv_obj_set_style_pad_left(slider,side,LV_PART_KNOB);lv_obj_set_style_pad_right(slider,side,LV_PART_KNOB);
  lv_obj_set_style_pad_top(slider,-(w-handle_h)/2-inset,LV_PART_KNOB);
  lv_obj_set_style_pad_bottom(slider,-(w-handle_h)/2+inset,LV_PART_KNOB);
  // Room past the bottom end only, so the handle still sits on the track at 0 (the event snaps the value back).
  // Not past the top: the fill is what the value is, and a slider that reached 1000 of a range that ran to
  // 1000 + margin stopped a handle's width short of the top at 100 % - which is exactly what it looked like.
  const int below=1000*(inset+handle_h)/std::max(1,h-(inset+handle_h));
  lv_slider_set_range(slider,-below,1000);
  lv_slider_set_value(slider,std::clamp(raw,0,1000),LV_ANIM_OFF);
  if(!enabled)lv_obj_add_state(slider,LV_STATE_DISABLED);
  lv_obj_remove_flag(slider,LV_OBJ_FLAG_GESTURE_BUBBLE);
  lv_obj_add_event_cb(slider,light_slider_event,LV_EVENT_ALL,nullptr);
  return slider;
}
// ---- The light and fan card's parts (docs/CARD_PARTS.md) ----
// The standing slider: where the tile's strip stands (slider_value), in the light's own colour, on the pale amber
// track while a light is lit. A finger on it keeps it.
inline void light_slider_paint(lv_obj_t *slider,const Tile &t,const CardPart &part){
  const int raw=t.state=="on"?slider_value(t):0;
  set_color(slider,LV_STYLE_BG_COLOR,theme::color(part.arg&&raw>0?theme::AMBER_TRACK:theme::TRACK),LV_PART_MAIN);
  set_color(slider,LV_STYLE_BG_COLOR,lv_color_hex(tile_controls::accent(t)),LV_PART_INDICATOR);
  paint_state(slider,LV_STATE_DISABLED,!t.available());
  if(!lv_obj_has_state(slider,LV_STATE_PRESSED)&&lv_slider_get_value(slider)!=std::clamp(raw,0,1000))lv_slider_set_value(slider,std::clamp(raw,0,1000),LV_ANIM_OFF);
}
// The round field of a light that only switches: pale amber while it is on.
inline void light_halo_paint(lv_obj_t *halo,const Tile &t,const CardPart &){
  set_color(halo,LV_STYLE_BG_COLOR,theme::color(t.state=="on"?theme::AMBER_TRACK:theme::TRACK));
}
// The entity's icon on the foot of the slider (arg 1) or in the field: white on a lit fill, the light's colour on the
// field while on, grey while off.
inline void light_icon_paint(lv_obj_t *glyph,const Tile &t,const CardPart &part){
  const bool on=t.state=="on";
  const int raw=on?slider_value(t):0;
  label(glyph,icon_for(t));
  set_color(glyph,LV_STYLE_TEXT_COLOR,lv_color_hex(part.arg?(raw>0?theme::hex(theme::ON_ACCENT):theme::hex(theme::ICON_OFF))
                                                          :(on?tile_controls::accent(t):theme::hex(theme::ICON_OFF))));
}
inline void light_value_paint(lv_obj_t *value,const Tile &t,const CardPart &){label(value,light_value_text(t));}
#ifdef SD_MOD_LIGHT_PRESETS
// A light's presets, drawn by module_light_presets.cpp (a compilation unit of its own): a tile's panel, the colour card's
// row or column and the dimming card's row (docs/LIGHT_PRESETS.md).
struct PanelMetrics;
int preset_panel(Widgets &w, const Tile &t, const PanelMetrics &m, bool taller, int content_w, int content_h, int fill, int &panel_h);
void colour_presets_paint(const Tile &t);
int colour_column();
bool colour_beside();
void colour_presets_draw(lv_obj_t *card, bool beside, int top, int bottom, int y);
void light_card_presets(const Tile &t, int x, int y, int width, int height, bool left);
#endif
// What decides the light card's parts: whether it dims. On and off, the level and the colour are painted.
inline uint32_t light_card_shape(const Tile &t){
  Fingerprint f;f.add(t.entity);f.write('|');f.write(tile_controls::light_dims(t)?'d':'s');
#ifdef SD_MOD_LIGHT_PRESETS
  f.write(t.presets?(char)('0'+t.presets->count):'-');
#endif
  f.write(group_page::available(t)?'g':'-');
  return f.value;
}
inline void render_light_detail(Tile &t,bool large,int width,int height,int columns) {
  const lv_font_t *big=watch_value_font?watch_value_font:(watch_font?watch_font:detail_font);
  const lv_font_t *text=large?detail_font:(control_font?control_font:detail_font);
  const lv_font_t *mini=mini_icon_font?mini_icon_font:detail_font;
  const lv_font_t *icons=tile_icon_font();
  const auto m=light_metrics(large);
  const bool dims=tile_controls::light_dims(t);
  int presets_h=0;
#ifdef SD_MOD_LIGHT_PRESETS
  // A light's presets (module light_presets): a row under it all, or under the value where the card stands in two columns.
  const bool presets=t.domain()=="light"&&dims&&t.presets&&t.presets->count;
  if(presets)presets_h=light_presets::card_key();
#endif
  const auto l=light_card::layout(m,width,height,columns,dims,presets_h);
  detail_placed=true;   // the layout has already put every part where the glass has room for it
  // The big value says what the state line would have said, so the card draws no second one.
  if(detail_status){lv_obj_add_flag(detail_status,LV_OBJ_FLAG_HIDDEN);detail_status=nullptr;}

  const bool on=t.state=="on";
  const uint32_t accent=tile_controls::accent(t);
  // The power key, across from the back key: lit while the light or the fan is on.
  card_bind(climate_round_key(bar_key(),tile_controls::glyph::POWER,mini,
                              on?theme::ACCENT_TINT:theme::KEY,on?theme::ACCENT_ICON:theme::ICON_OFF,LIGHT_POWER),t,power_key_paint);
  // A light group that only dims or switches opens this card, not the colour card: its lamps key stands beside the
  // power key, as on the colour card, and opens the group's page with a card per lamp (GROUP_PAGE, group_page.h, GitHub #458).
  if(group_page::available(t))climate_round_key(bar_key(1),tile_controls::glyph::LAMPS,mini,theme::KEY,theme::INK,GROUP_PAGE);

  detail_card(l.card.x,l.card.y,l.card.w,l.card.h);
  // Where the slider stands is the tile's own answer (slider_value), so the strip on the tile and the card it
  // opens never disagree - including the value held in front while a light fades towards it.
  const int raw=on?slider_value(t):0;
  if(dims){
    auto *slider=light_slider(l.slider.x,l.slider.y,l.slider.w,l.slider.h,raw,accent,t.available(),t.domain()=="light");
    overlay_card::touchable(slider,l.slider.w);
    card_bind(slider,t,light_slider_paint,"",t.domain()=="light");
  }else if(!l.halo.empty()){
    // A light that only switches: its icon on a round field where the slider would be, lit while it is on, the
    // way the blind's card shows a door that only opens and closes. The power key in the bar does the work.
    // The same two colours the slider's track has, so a light that dims and one that only switches are the
    // same card with the same palette: the light's own pale amber while it is on, the neutral track while off.
    card_bind(detail_shape(detail_root,l.halo.x,l.halo.y,l.halo.w,l.halo.h,
                           theme::hex(on?theme::AMBER_TRACK:theme::TRACK),l.halo.w/2),t,light_halo_paint);
  }
  // The entity's icon rides on the foot of the slider, or in the middle of the round field, where the fill is
  // and a finger is not, as it did on the overlay before it and as Home Assistant draws it.
  if(!l.icon.empty()&&icons&&lv_font_get_line_height(icons)<=l.icon.h+ui::px(4)){
    const uint32_t ink=dims?(raw>0?theme::hex(theme::ON_ACCENT):theme::hex(theme::ICON_OFF))
                           :(on?accent:theme::hex(theme::ICON_OFF));
    auto *glyph=detail_text(detail_root,icon_for(t),l.icon.x,l.icon.y,l.icon.w,icons,LV_TEXT_ALIGN_CENTER,ink);
    lv_obj_remove_flag(glyph,LV_OBJ_FLAG_CLICKABLE);
    card_bind(glyph,t,light_icon_paint,"",dims);
  }
  light_value=card_bind(detail_text(detail_root,light_value_text(t),l.value.x,l.value.y,l.value.w,big,
                                    l.columns==2?LV_TEXT_ALIGN_LEFT:LV_TEXT_ALIGN_CENTER,theme::hex(theme::INK)),t,light_value_paint);
  // The caption only where the words exist: a light says what the slider is, a fan's speed has no word of its
  // own in the screen's languages and does without (the name at the top says which fan it is).
  if(!l.caption.empty()&&dims&&t.domain()=="light")
    detail_text(detail_root,tr(txt::light_brightness),l.caption.x,l.caption.y,l.caption.w,text,
                l.columns==2?LV_TEXT_ALIGN_LEFT:LV_TEXT_ALIGN_CENTER,theme::hex(theme::SUBTLE));
#ifdef SD_MOD_LIGHT_PRESETS
  if(presets&&!l.presets.empty())light_card_presets(t,l.presets.x,l.presets.y,l.presets.w,l.presets.h,l.columns==2);
#endif
  card_shaped(t,light_card_shape);
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
