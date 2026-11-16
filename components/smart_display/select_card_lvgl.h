// The select card and its parts, also a remote's activities.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What proves it: web/wasm/test_card_parts.mjs.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// ---- Select card (firmware 0.3.3) ----
// A select's options as rows of one white card, like a list in Home Assistant's more-info dialog: the option it is
// on stands on the pale accent with a check at its end, a tap on another row chooses that one and shows it at once.
// Wide glass that has more options than one column holds gets a second column (read top to bottom, then the next);
// options that still do not fit go to a next page with the same chevrons and dots as the tile pages.
inline int select_page=0;
inline void select_pager_step(int step){
  select_page+=step;
  redraw_detail();
}
// What is chosen: a select's state, or the activity a remote runs (firmware 0.22.0+).
// A power key in a card's top bar (light, fan, remote, switch): lit while the entity is on.
inline void power_key_paint(lv_obj_t *key,const Tile &t,const CardPart &){
  const bool on=t.state=="on";
  set_color(key,LV_STYLE_BG_COLOR,theme::color(on?theme::ACCENT_TINT:theme::KEY));
  if(auto *glyph=lv_obj_get_child(key,0))set_color(glyph,LV_STYLE_TEXT_COLOR,theme::color(on?theme::ACCENT_ICON:theme::ICON_OFF));
}
// ---- The select card's parts (docs/CARD_PARTS.md), also a remote's activities ----
// The option the card shows as chosen: a select's state, a remote's activity while it is on.
inline std::string select_current(const Tile &t){
  if(t.domain()=="remote")return t.state=="on"?t.extra().activity:std::string();
  return t.state;
}
// A row (value: its option): the tint and the tick while it is the chosen one; the name leaves the tick its room.
inline void select_row_paint(lv_obj_t *row,const Tile &t,const CardPart &part){
  const bool chosen=part.value==select_current(t);
  set_number(row,LV_STYLE_BG_OPA,chosen?LV_OPA_COVER:LV_OPA_TRANSP);
  set_color(row,LV_STYLE_BG_COLOR,theme::color(chosen?theme::ACCENT_TINT:theme::CARD_PRESSED),LV_STATE_PRESSED);
  auto *name=lv_obj_get_child(row,0),*mark=lv_obj_get_child(row,1);
  if(!name||!mark)return;
  const int side=lv_obj_get_style_x(name,LV_PART_MAIN);
  set_number(name,LV_STYLE_WIDTH,chosen?lv_obj_get_style_x(mark,LV_PART_MAIN)-side-side/2:lv_obj_get_style_width(row,LV_PART_MAIN)-2*side);
  set_hidden(mark,!chosen);
}
// What decides the select card's parts: its options and the page of them it shows. The chosen one is painted.
inline uint32_t select_card_shape(const Tile &t){
  Fingerprint f;auto add=[&](const std::string &text){f.add(text);f.write('|');};
  add(t.entity);add(std::to_string(select_page));
  for(const auto &o:t.extra().options)add(o);
  if(t.domain()=="remote")f.write(t.extra().keypad.empty());
  return f.value;
}
inline void render_select_detail(const Tile &t,bool large,int width,int height,int pad,int top,const std::string &current){
  const auto &options=t.extra().options;
  const int n=(int)options.size();
  if(!n)return;
  const lv_font_t *text=control_font?control_font:detail_font,*glyphs=mini_icon_font?mini_icon_font:detail_font;
  const int row_h=std::max(ui::touch_min(),ui::px(large?52:36)),inset=ui::px(large?6:4),gap=ui::px(large?4:2);
  // Paged, the options end above the pager every page shares across the foot of the glass (page_bar.h).
  const int pager_h=page_bar::height(),card_w=std::min(width-2*pad,ui::control_max_width());
  const int room=height-top-pad;
  auto rows_in=[&](int span){return std::max(1,(span-2*inset+gap)/(row_h+gap));};
  // Two columns once one does not hold every option and each column keeps room for a word of some length.
  const int columns=n>rows_in(room)&&card_w>=2*ui::px(large?200:130)+gap?2:1;
  int rows=rows_in(room);
  const bool paged=n>rows*columns;
  if(paged)rows=rows_in(room-pager_h-gap);
  const int per_page=rows*columns,pages=(n+per_page-1)/per_page;
  select_page=std::clamp(select_page,0,pages-1);
  const int first=select_page*per_page,shown=std::min(per_page,n-first);
  // A card of one page is as tall as its rows; a paged card keeps the height of a full page on every page.
  const int used_rows=paged?rows:(shown+columns-1)/columns;
  const int card_h=2*inset+used_rows*row_h+(used_rows-1)*gap,x=(width-card_w)/2;
  auto *card=detail_card(x,top,card_w,card_h);
  const int col_w=(card_w-2*inset-(columns-1)*gap)/columns;
  for(int k=0;k<shown;++k){
    const int i=first+k,c=k/used_rows,r=k%used_rows;
    const bool chosen=options[i]==current;
    auto *row=lv_obj_create(card);lv_obj_remove_style_all(row);
    lv_obj_set_pos(row,inset+c*(col_w+gap),inset+r*(row_h+gap));lv_obj_set_size(row,col_w,row_h);
    lv_obj_add_flag(row,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(row,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_radius(row,ui::px(large?12:8),0);
    lv_obj_set_style_bg_opa(row,chosen?LV_OPA_COVER:LV_OPA_TRANSP,0);lv_obj_set_style_bg_color(row,theme::color(theme::ACCENT_TINT),0);
    lv_obj_set_style_bg_opa(row,LV_OPA_COVER,LV_STATE_PRESSED);
    lv_obj_set_style_bg_color(row,theme::color(chosen?theme::ACCENT_TINT:theme::CARD_PRESSED),LV_STATE_PRESSED);
    lv_obj_set_style_opa(row,LV_OPA_50,LV_STATE_DISABLED);
    const int side=ui::px(large?16:10),check=lv_font_get_line_height(glyphs);
    auto *name=detail_text(row,options[i],side,(row_h-lv_font_get_line_height(text))/2,col_w-2*side-(chosen?check+side/2:0),text,
                           LV_TEXT_ALIGN_LEFT,theme::INK);
    lv_label_set_long_mode(name,LV_LABEL_LONG_DOT);lv_obj_remove_flag(name,LV_OBJ_FLAG_CLICKABLE);
    // Every row has its tick, shown on the chosen one, so choosing another is a paint and not a new card.
    auto *mark=detail_text(row,"\U000F012C",col_w-side-check,(row_h-check)/2,check,glyphs,LV_TEXT_ALIGN_RIGHT,theme::ACCENT_ICON);
    lv_obj_remove_flag(mark,LV_OBJ_FLAG_CLICKABLE);
    card_bind(row,t,select_row_paint,options[i]);
    lv_obj_add_event_cb(row,[](lv_event_t *e){detail_command((intptr_t)lv_event_get_user_data(e));},LV_EVENT_SHORT_CLICKED,
                        (void*)(intptr_t)(SELECT_OPTION_FIRST+i));
    if(detail_action_count<32)detail_actions[detail_action_count++]=row;
  }
  card_shaped(t,select_card_shape);
  if(!paged)return;
  // The pager every page shares (page_bar.h), across the foot of the glass.
  page_bar::show(page_bar::make(detail_root,select_pager_step),select_page,pages);
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
