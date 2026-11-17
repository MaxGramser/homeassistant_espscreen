// The helpers several cards share: a card's frame and its words, the round shapes, words that fit their room, a
// button's words, the segmented control, the status line under a card's name and a card's round key. Each card part
// included after this one uses them; none of them knows a card of its own.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place, before the first card, and uses what stands before it there (the model, the widgets,
// the detail card's root and keys). ESPHome also includes every header of a component on its own (esphome.h): there
// this file is empty, which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: a card's own layout, which each card part and its plain header (climate_card.h,
// media_card.h, ...) hold.
// What proves it: web/wasm/layout_audit.mjs through tests/test_layout_audit.py (every card on every board shape), the
// preview's card tests (web/wasm/test_*.mjs), and the builds of tools/profiles.py SAMPLE.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
inline lv_obj_t *detail_text(lv_obj_t *parent,const std::string &text,int x,int y,int width,const lv_font_t *font,lv_text_align_t align,uint32_t color){
  auto *l=detail_label(parent,text,x,y,std::max(1,width));lv_obj_set_style_text_font(l,font,0);lv_obj_set_height(l,lv_font_get_line_height(font));
  lv_obj_set_style_text_align(l,align,0);lv_obj_set_style_text_color(l,lv_color_hex(color),0);return l;
}
inline lv_obj_t *detail_text(lv_obj_t *parent,const std::string &text,int x,int y,int width,const lv_font_t *font,lv_text_align_t align,theme::Role role){
  return detail_text(parent,text,x,y,width,font,align,theme::hex(role));
}
inline lv_obj_t *detail_card(int x,int y,int w,int h){
  auto *card=lv_obj_create(detail_root);lv_obj_remove_style_all(card);lv_obj_remove_flag(card,LV_OBJ_FLAG_SCROLLABLE);lv_obj_remove_flag(card,LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_pos(card,x,y);lv_obj_set_size(card,w,h);
  lv_obj_set_style_bg_color(card,theme::color(theme::CARD),0);lv_obj_set_style_bg_opa(card,LV_OPA_COVER,0);
  lv_obj_set_style_radius(card,lv_obj_get_style_radius(widgets[0].tile,LV_PART_MAIN),0);
  lv_obj_set_style_border_width(card,1,0);lv_obj_set_style_border_color(card,theme::color(theme::LINE),0);
  return card;
}
// A font's line height as an int: LVGL gives an int32_t, which is a long on the ESP32 and std::max wants one type.
inline int line_of(const lv_font_t *f){return f?(int)lv_font_get_line_height(f):0;}
inline lv_obj_t *detail_shape(lv_obj_t *parent,int x,int y,int w,int h,uint32_t color,int radius){
  auto *o=lv_obj_create(parent);lv_obj_remove_style_all(o);lv_obj_set_pos(o,x,y);lv_obj_set_size(o,w,h);
  lv_obj_set_style_radius(o,radius,0);lv_obj_set_style_bg_color(o,lv_color_hex(color),0);lv_obj_set_style_bg_opa(o,LV_OPA_COVER,0);
  lv_obj_remove_flag(o,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(o,LV_OBJ_FLAG_SCROLLABLE);return o;
}
inline lv_obj_t *detail_shape(lv_obj_t *parent,int x,int y,int w,int h,theme::Role role,int radius){
  return detail_shape(parent,x,y,w,h,theme::hex(role),radius);
}
// The status line under a tile's name, once its room is known. LVGL cuts the end of a line that doesn't fit, which
// is where this line carries its news, so (firmware 0.2.76+):
//   `shorter`  another wording of the whole line, taken when the full one doesn't fit ("Yest. 9:15 PM");
//   `tail`     the end that has to stay readable (a robot's battery): the words in front of it take the dots,
//              "Angedockt / 10 %" becomes "Angedo… / 10 %".
// A line that fits, or a room too small for the tail itself, is left to LVGL as before.
// True when `face` has a glyph for every character of `text`: a board's fonts carry listed glyphs only, and a
// letter outside the list draws as nothing.
inline bool face_covers(const lv_font_t *face,const std::string &text){
  size_t i=0;lv_font_glyph_dsc_t dsc;
  while(uint32_t cp=header_bar::next_codepoint(text,i))if(!lv_font_get_glyph_dsc(face,&dsc,cp,0))return false;
  return true;
}
inline void fit_value(lv_obj_t *obj,const std::string &value,const std::string &shorter,const std::string &tail,int room){
  const lv_font_t *font=lv_obj_get_style_text_font(obj,LV_PART_MAIN);
  if(!font||room<=0||text_width(value,font)<=room)return;
  if(!shorter.empty()&&shorter!=value&&text_width(shorter,font)<=room){label(obj,shorter);return;}
  if(tail.empty()||value.size()<=tail.size())return;
  static const std::string dots="…";
  const int head_room=room-text_width(dots+tail,font);
  if(head_room<=0)return;
  const std::string head=value.substr(0,value.size()-tail.size());
  std::string cut;
  for(size_t i=0;i<head.size();){
    size_t next=i+1;
    while(next<head.size()&&(static_cast<unsigned char>(head[next])&0xC0)==0x80)++next;
    if(text_width(head.substr(0,next),font)>head_room)break;
    cut=head.substr(0,next);i=next;
  }
  while(!cut.empty()&&cut.back()==' ')cut.pop_back();
  label(obj,cut+dots+tail);
}
// Put a detail_button's words in `font`, sized to the words and centred (or at `x` when given).
inline lv_obj_t *button_words(lv_obj_t *button,const lv_font_t *font,uint32_t color,int available,int x=-1){
  auto *label=lv_obj_get_child(button,0);
  lv_obj_set_style_text_font(label,font,0);lv_obj_set_style_text_color(label,lv_color_hex(color),0);
  lv_obj_set_size(label,std::min(available,text_width(lv_label_get_text(label),font)+2),lv_font_get_line_height(font));
  if(x<0)lv_obj_center(label);else lv_obj_align(label,LV_ALIGN_LEFT_MID,x,0);
  return label;
}
// A segmented control: one rounded track, each option as wide as its words plus an equal share of the room
// left, the chosen one filled in blue; `chosen` is the option's place in the list, -1 for none. The options
// answer as first..first+5. However thin the row is drawn, each option keeps a finger's worth of touch area,
// so a segmented row on a short panel is still hittable (overlay_card::touchable).
// A segment's look, chosen or not.
inline void segment_paint(lv_obj_t *segment,bool selected){
  set_number(segment,LV_STYLE_BG_OPA,selected?LV_OPA_COVER:LV_OPA_TRANSP);
  set_color(segment,LV_STYLE_BG_COLOR,theme::color(selected?theme::ACCENT:theme::ACCENT_TINT),LV_STATE_PRESSED);
  if(auto *words=lv_obj_get_child(segment,0))set_color(words,LV_STYLE_TEXT_COLOR,theme::color(selected?theme::ON_ACCENT:theme::INK));
}
// A key's glyph set again only when it is another one: centring a glyph measures its ink (center_icon).
inline void paint_glyph(lv_obj_t *key,const char *glyph){
  auto *icon=lv_obj_get_child(key,0);
  if(!icon||!strcmp(lv_label_get_text(icon),glyph))return;
  lv_label_set_text(icon,glyph);center_icon(icon);
}
// A state on or off, set only when it changes.
inline void paint_state(lv_obj_t *obj,lv_state_t state,bool on){
  if(lv_obj_has_state(obj,state)==on)return;
  if(on)lv_obj_add_state(obj,state);else lv_obj_remove_state(obj,state);
}
// A row of choices; returns its segments, for a card that binds them (card_bind).
inline std::vector<lv_obj_t *> segments(int x,int y,int w,int h,const std::vector<std::string> &labels,int chosen,int first,uint32_t track,bool border,const lv_font_t *font,const lv_font_t *smaller=nullptr){
  std::vector<lv_obj_t *> made;
  int n=std::min<int>((int)labels.size(),6);if(n<=0||w<=0||h<=0)return made;
  auto *bar=detail_shape(detail_root,x,y,w,h,track,h/2);
  if(border){lv_obj_set_style_border_width(bar,1,0);lv_obj_set_style_border_color(bar,theme::color(theme::LINE),0);}
  int inset=std::max(3,h/12),room=w-2*inset,words=0;int widths[6];
  for(int i=0;i<n;++i)words+=text_width(labels[i],font);
  // A narrow row reads better in smaller letters than in "A…" and "Med…": the words shrink before they are cut.
  if(words+n*ui::px(10)>room&&smaller&&smaller!=font&&lv_font_get_line_height(smaller)<=h-2*inset)font=smaller;
  words=0;
  for(int i=0;i<n;++i){widths[i]=text_width(labels[i],font);words+=widths[i];}
  int share=(room-words)/n;
  int sx=x+inset;
  for(int i=0;i<n;++i){
    int sw=i==n-1?x+w-inset-sx:(words<=room?widths[i]+share:room/n);
    bool selected=i==chosen;
    auto *segment=detail_button(labels[i].c_str(),sx,y+inset,sw,h-2*inset,first+i);
    lv_obj_set_style_radius(segment,(h-2*inset)/2,0);
    lv_obj_set_style_bg_color(segment,theme::color(theme::ACCENT),0);
    lv_obj_set_style_bg_opa(segment,selected?LV_OPA_COVER:LV_OPA_TRANSP,0);
    lv_obj_set_style_bg_opa(segment,LV_OPA_COVER,LV_STATE_PRESSED);
    if(!selected)lv_obj_set_style_bg_color(segment,theme::color(theme::ACCENT_TINT),LV_STATE_PRESSED);
    button_words(segment,font,theme::hex(selected?theme::ON_ACCENT:theme::INK),sw-6);
    overlay_card::touchable(segment,h-2*inset);
    made.push_back(segment);
    sx+=sw;
  }
  return made;
}
inline std::string alarm_card_line(const Tile &t);
inline std::string lock_card_line(const Tile &t);
inline std::string cover_status_line(const Tile &t){return t.available()?tile_controls::cover_card_status(t):tr(txt::ha_unavailable);}
// The line under a card's name: the domain that writes its own says it here, so the card, its refresh and the
// second-by-second tick all show the same words.
inline std::string card_status(const Tile &t,bool brief=false){
  // A wish Home Assistant takes long to square says so on every card, as on its tile (docs/OPTIMISTIC.md).
  if(wish_slow(t.entity,esphome::millis()))return tr(txt::tile_updating);
  const auto d=t.domain();
  if(d=="cover")return cover_status_line(t);
  if(d=="climate"||d=="humidifier")return tile_controls::climate_card_status(t,brief);
  if(d=="alarm_control_panel")return alarm_card_line(t);
  if(d=="lock")return lock_card_line(t);
  return detail_state(t);
}
// Set while the state line lives in a smaller place than its own line (the climate card's caption), so the
// second-by-second refresh writes the same short form the card drew.
inline bool detail_status_brief=false;
// A round key of a card: the - and the + beside a thermostat's setpoint, and the power key in the top bar
// of the thermostat and of a light or fan. It takes a climate_card::Rect because that card asked first;
// every card's rectangle is the same four numbers.
inline lv_obj_t *climate_round_key(const climate_card::Rect &r,const char *icon,const lv_font_t *font,theme::Role fill,theme::Role ink,int command){
  auto *key=detail_button("",r.x,r.y,r.w,r.h,command);
  lv_obj_set_style_radius(key,LV_RADIUS_CIRCLE,0);
  lv_obj_set_style_bg_color(key,theme::color(fill),0);
  lv_obj_set_style_bg_color(key,theme::color(theme::KEY_PRESSED),LV_STATE_PRESSED);
  auto *glyph=lv_obj_get_child(key,0);
  if(font)lv_obj_set_style_text_font(glyph,font,0);
  lv_label_set_text(glyph,icon);
  lv_obj_set_style_text_color(glyph,theme::color(ink),0);
  lv_obj_set_size(glyph,LV_SIZE_CONTENT,LV_SIZE_CONTENT);lv_obj_center(glyph);
  return key;
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
