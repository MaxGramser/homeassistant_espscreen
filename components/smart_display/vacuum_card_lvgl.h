// The vacuum card every board has (the module's card with the map is module_vacuum_card).
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the rules themselves, which are plain C++ without LVGL in vacuum_model.h.
// What proves it: tests/test_vacuum_model.cpp, tests/test_vacuum_card.py.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// ---- Vacuum card ----
// A robot with its state and battery, the two commands used most, and one block that says how it cleans:
// the cleaning mode, then suction and water. Only the rows the chosen mode uses are shown, and they sit
// below the mode, so a tap never moves the control under the finger. Native shapes and labels only.
// Native shapes keep the robot crisp without image buffers or extra layers.
// The state colour, as Home Assistant colours a vacuum: teal while cleaning, blue on the way back, amber
// when paused, red on an error; a docked or idle robot keeps the card's own blue. `tint` is the halo.
struct VacuumLook { uint32_t accent, tint; };
inline VacuumLook vacuum_look(const std::string &state){
  using namespace theme::ha;
  const uint32_t accent=state=="cleaning"?TEAL:state=="returning"?BLUE:state=="paused"?ORANGE:state=="error"?RED:SKY;
  // A robot at rest has the quietest halo.
  return {accent,theme::tint(accent,accent==SKY?22:36)};
}
// A robot seen from above on a halo: a white body with a rim, the laser turret, a light bar in the state colour.
inline void vacuum_robot(lv_obj_t *parent,int x,int y,int size,const VacuumLook &look){
  auto *halo=detail_shape(parent,x,y,size,size,look.tint,size/2);
  int r=size*72/100,rim=std::max(1,size/44);
  auto *body=detail_shape(halo,(size-r)/2,(size-r)/2,r,r,theme::ROBOT_BODY,r/2);
  lv_obj_set_style_border_width(body,rim,0);lv_obj_set_style_border_color(body,theme::color(theme::ROBOT_RIM),0);
  int c=r-2*rim;auto s=[&](int v){return std::max(1,v*c/100);};
  detail_shape(body,s(32),s(10),s(36),s(36),theme::ROBOT_TOP,s(18));
  detail_shape(body,s(41),s(19),s(18),s(18),theme::ROBOT_LENS,s(9));
  detail_shape(body,s(31),s(70),s(38),std::max(3,s(7)),look.accent,s(4));
}
// A battery like a phone's: outline, level fill (red below 20 %) and a small cap.
inline void vacuum_battery(lv_obj_t *parent,int x,int y,int w,int h,float level){
  int line=std::max(1,h/7),fill_w=w-4*line,fill=std::clamp((int)std::lround(fill_w*level/100.0f),0,fill_w);
  auto *shell=detail_shape(parent,x,y,w,h,theme::CARD,std::max(2,h/4));
  lv_obj_set_style_bg_opa(shell,LV_OPA_TRANSP,0);
  lv_obj_set_style_border_width(shell,line,0);lv_obj_set_style_border_color(shell,theme::color(theme::BATTERY),0);
  if(fill)detail_shape(shell,line,line,fill,h-4*line,level<20?theme::foreground(theme::ha::ALARM):theme::hex(theme::SLATE),std::max(1,h/9));
  detail_shape(parent,x+w,y+h*3/10,std::max(2,line+1),h-2*(h*3/10),theme::BATTERY,1);
}
// Battery meter, level and a green bolt while charging, in one row from `x`; returns the row's width.
// Without a parent it only measures.
inline int vacuum_power(lv_obj_t *parent,const Tile &t,int x,int y,const lv_font_t *font,bool large){
  const lv_font_t *bolt_font=large && watch_icon_font?watch_icon_font:mini_icon_font;
  std::string percent=screen_text::percent((int)std::lround(t.battery));
  int h=lv_font_get_line_height(font),meter_w=ui::px(large?30:22),meter_h=ui::px(large?15:11),gap=ui::px(large?10:6),words=text_width(percent,font);
  int bolt_w=t.extra().charging && bolt_font?text_width("\U000F0241",bolt_font):0;
  int width=meter_w+3+gap+words+(bolt_w?gap/2+bolt_w:0);
  if(!parent)return width;
  vacuum_battery(parent,x,y+(h-meter_h)/2,meter_w,meter_h,t.battery);
  int px=x+meter_w+3+gap;
  detail_text(parent,percent,px,y,words+2,font,LV_TEXT_ALIGN_LEFT,theme::MUTED);
  if(bolt_w)detail_text(parent,"\U000F0241",px+words+gap/2,y+(h-lv_font_get_line_height(bolt_font))/2,bolt_w+2,bolt_font,LV_TEXT_ALIGN_LEFT,theme::foreground(theme::ha::CHARGING));
  return width;
}
// A command button with its icon before the words, the two centred as one group.
inline lv_obj_t *vacuum_command(const char *icon,const char *text,int x,int y,int w,int h,int command,bool primary,
                                const lv_font_t *font,const lv_font_t *icon_font,int radius){
  auto *button=detail_button(text,x,y,w,h,command);
  const uint32_t ink=theme::hex(primary?theme::ON_ACCENT:theme::INK);
  lv_obj_set_style_radius(button,radius,0);
  lv_obj_set_style_bg_color(button,theme::color(primary?theme::ACCENT:theme::CARD),0);
  if(!primary){
    lv_obj_set_style_border_width(button,1,0);lv_obj_set_style_border_color(button,theme::color(theme::LINE),0);
    lv_obj_set_style_bg_color(button,theme::color(theme::KEY),LV_STATE_PRESSED);
  }
  int gap=std::max(6,h/7),icon_w=text_width(icon,icon_font),words=text_width(text,font);
  int group=icon_w+gap+words,left=std::max(4,(w-group)/2);
  auto *glyph=lv_label_create(button);lv_label_set_text(glyph,icon);lv_obj_remove_flag(glyph,LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_text_font(glyph,icon_font,0);lv_obj_set_style_text_color(glyph,lv_color_hex(ink),0);
  lv_obj_align(glyph,LV_ALIGN_LEFT_MID,left,0);
  button_words(button,font,ink,w-left-icon_w-gap-4,left+icon_w+gap);
  return button;
}
// The vacuum's rows: the same control, showing the value just tapped while Home Assistant has not answered.
// A chip of a vacuum row (arg: the row's kind, value: its choice): chosen while it is what the row shows, the value
// just tapped while Home Assistant has not answered.
inline void vacuum_chip_paint(lv_obj_t *segment,const Tile &t,const CardPart &part){
  const Choice *row=t.choice((char)part.arg);
  if(row)segment_paint(segment,tile_controls::shown_value(t,*row,esphome::millis())==part.value);
}
inline void vacuum_segments(const Tile &t,const Choice &row,int first,int x,int y,int w,int h,uint32_t track,bool border,const lv_font_t *font){
  const std::string &chosen=tile_controls::shown_value(t,row,esphome::millis());
  int index=-1;
  for(size_t i=0;i<row.values.size();++i)if(row.values[i]==chosen)index=(int)i;
  const auto made=segments(x,y,w,h,row.labels,index,first,track,border,font,small_font);
  for(size_t i=0;i<made.size()&&i<row.values.size();++i)card_bind(made[i],t,vacuum_chip_paint,row.values[i],row.kind);
}
// What the vacuum card's state line says: the wait, a slow wish, or Home Assistant's word.
inline std::string vacuum_badge_text(const Tile &t){
  const uint32_t now=esphome::millis();
  return t.loading(now)?tr(txt::tile_command_sent):wish_slow(t.entity,now)?tr(txt::tile_updating):detail_state(t);
}
inline void vacuum_badge_paint(lv_obj_t *line,const Tile &t,const CardPart &){label(line,vacuum_badge_text(t));}
// What decides the vacuum card's parts: which rows it has (a mode that only mops has no suction), the state that
// names its keys and its look, the room on the way and the battery. A chip just tapped is painted.
inline bool vacuum_hero(const Tile &t){return ui::large()||(!t.choice('m')&&!t.choice('w'));}
inline uint32_t vacuum_card_shape(const Tile &t){
  Fingerprint f;auto add=[&](const std::string &text){f.add(text);f.write('|');};
  const uint32_t now=esphome::millis();
  const auto rows=tile_controls::vacuum_rows(t,now);
  add(t.entity);add(std::to_string(t.supported));add(t.state);add(t.extra().room);
  add(std::isfinite(t.battery)?std::to_string((int)std::lround(t.battery)):"");
  f.write(rows.suction);f.write(rows.water);
  for(char kind:{'m','s','w'})if(const Choice *c=t.choice(kind)){f.write(kind);for(const auto &v:c->values)add(v);for(const auto &l:c->labels)add(l);}
  if(const Choice *mode=t.choice('m')){
    f.write(tile_controls::vacuum_role(t,now));
    f.write(tile_controls::shown_value(t,*mode,now).find("smart")!=std::string::npos);
  }
  // The state line of the small card is as wide as its words.
  if(!vacuum_hero(t))add(vacuum_badge_text(t));
  return f.value;
}
inline void render_vacuum_detail(Tile &t,bool large,int width,int height,int pad){
  uint32_t now=esphome::millis();
  auto rows=tile_controls::vacuum_rows(t,now);
  const Choice *mode=t.choice('m'),*suction=rows.suction?t.choice('s'):nullptr,*water=rows.water?t.choice('w'):nullptr;
  bool automatic=mode && tile_controls::vacuum_role(t,now)=='a';
  const lv_font_t *text=large?detail_font:(control_font?control_font:detail_font);
  const lv_font_t *big=watch_font?watch_font:detail_font;
  const lv_font_t *icons=mini_icon_font?mini_icon_font:detail_font;
  VacuumLook look=vacuum_look(t.state);
  bool cleaning=t.state=="cleaning",paused=t.state=="paused";
  bool battery=std::isfinite(t.battery),on_the_way=cleaning||paused||t.state=="returning";
  int inner=width-2*pad,gap=ui::px(large?12:6),radius=lv_obj_get_style_radius(widgets[0].tile,LV_PART_MAIN);
  std::string state=vacuum_badge_text(t);
  // A robot with little to set gets a hero on the small screen too; one with mode and water rows uses a status row.
  bool small_hero=!large && !mode && !t.choice('w');
  int y=ui::px(large?92:52);
  // The blocks of the card, and what each of them may give up when the glass is shorter than they ask for
  // (a 800 x 480 panel at 217 dpi asked for 550 px). The portrait is the first to give, the keys the last.
  const bool hero_form=large||small_hero;
  int hero_h=ui::px(large?108:60),action_h=ui::px(large?54:(small_hero?40:36));
  int mode_h=ui::px(large?48:34),row_h=ui::px(large?44:32),step=ui::px(large?10:6),edge=ui::px(large?14:0);
  const int note_h=lv_font_get_line_height(text),line_h=lv_font_get_line_height(text);
  const bool any_row=mode||suction||water;
  auto block_h=[&]{
    return (mode?mode_h:0)+(suction?(mode?step:0)+row_h:0)+(water?((mode||suction)?step:0)+row_h:0)+
           (automatic?step+note_h+step:0);
  };
  auto total_h=[&]{
    return y+(hero_form?hero_h+gap:line_h+gap+ui::px(4))+action_h+gap+(any_row?block_h()+2*edge:0)+ui::px(large?18:6);
  };
  if(total_h()>height){
    const int rows_shown=(suction?1:0)+(water?1:0);
    const int steps=(suction&&mode?1:0)+(water&&(mode||suction)?1:0)+(automatic?2:0);
    ui::shrink({{&hero_h,ui::px(large?76:48)},
                {&step,ui::px(4),std::max(1,steps)},
                {&mode_h,ui::touch_min()},
                {&row_h,std::max(ui::touch_min()*3/4,note_h+ui::px(6)),std::max(1,rows_shown)},
                {&edge,ui::px(4),2},
                {&action_h,ui::touch_min()},
                {&gap,ui::px(4),3},
                {&y,ui::px(large?64:40)}},
               total_h()-height);
  }
  if(hero_form){
    int robot=std::min(ui::px(large?84:48),hero_h-ui::px(large?12:6));
    int edge_hero=ui::px(large?12:6);
    auto *hero=detail_card(pad,y,inner,hero_h);
    vacuum_robot(hero,edge_hero,(hero_h-robot)/2,robot,look);
    // Locate, when the robot can do it (VacuumEntityFeature.LOCATE; unknown features keep the button).
    bool locate=large && (!t.supported || (t.supported & tile_controls::feature::VACUUM_LOCATE));
    int key=std::min(ui::px(48),hero_h-ui::px(8)),text_x=edge_hero+robot+(ui::px(large?18:12)),text_w=inner-text_x-(locate?key+2*edge_hero:edge_hero);
    int line=lv_font_get_line_height(big),text_h=lv_font_get_line_height(text),space=ui::px(large?6:3);
    bool room=on_the_way && !t.extra().room.empty();
    int block=line+(room?space+text_h:0)+(battery?space+text_h:0),ty=(hero_h-block)/2;
    detail_badge_status=card_bind(detail_text(hero,state,text_x,ty,text_w,big,LV_TEXT_ALIGN_LEFT,theme::INK),t,vacuum_badge_paint);
    ty+=line;
    if(room){ty+=space;detail_text(hero,t.extra().room,text_x,ty,text_w,text,LV_TEXT_ALIGN_LEFT,theme::MUTED);ty+=text_h;}
    if(battery){ty+=space;vacuum_power(hero,t,text_x,ty,text,large);}
    if(locate){
      auto *find=detail_button("",pad+inner-edge_hero-key-6,y+(hero_h-key)/2,key,key,3);
      lv_obj_set_style_radius(find,LV_RADIUS_CIRCLE,0);lv_obj_set_style_bg_color(find,theme::color(theme::TRACK),0);
      lv_obj_set_style_bg_color(find,theme::color(theme::KEY_PRESSED),LV_STATE_PRESSED);
      auto *glyph=lv_obj_get_child(find,0);lv_obj_set_style_text_font(glyph,icons,0);lv_label_set_text(glyph,"\U000F034E");
      lv_obj_set_style_text_color(glyph,theme::color(theme::SLATE),0);lv_obj_set_size(glyph,LV_SIZE_CONTENT,LV_SIZE_CONTENT);lv_obj_center(glyph);
    }
    y+=hero_h+gap;
  }else{
    // Status row: a dot in the state colour, the state (and the room on the way), the battery at the right.
    int line=lv_font_get_line_height(text),dot=8,power_w=battery?vacuum_power(nullptr,t,0,0,text,false):0;
    detail_shape(detail_root,pad+2,y+(line-dot)/2,dot,dot,look.accent,dot/2);
    int words=inner-dot-10-power_w-12,state_w=std::min(words,text_width(state,text)+2);
    detail_badge_status=card_bind(detail_text(detail_root,state,pad+dot+10,y,state_w,text,LV_TEXT_ALIGN_LEFT,theme::INK),t,vacuum_badge_paint);
    if(on_the_way && !t.extra().room.empty() && words-state_w>24)
      detail_text(detail_root," · "+t.extra().room,pad+dot+10+state_w,y,words-state_w,text,LV_TEXT_ALIGN_LEFT,theme::MUTED);
    if(battery)vacuum_power(detail_root,t,pad+inner-power_w,y,text,false);
    y+=line+(gap+4);
  }
  // Start (or pause, or resume) as the one blue button, dock beside it.
  int start_w=large?(inner-gap)*2/3:(inner-gap)/2;
  vacuum_command(cleaning?"\U000F03E4":"\U000F040A",tr(cleaning?(large?txt::vacuum_pause_cleaning:txt::vacuum_pause):paused?txt::vacuum_resume:(large?txt::vacuum_start_cleaning:txt::vacuum_clean)),
                 pad,y,start_w,action_h,cleaning?1:0,true,text,icons,large?radius:action_h/2);
  vacuum_command("\U000F05F8",tr(txt::vacuum_dock),pad+start_w+gap,y,inner-start_w-gap,action_h,2,false,text,icons,large?radius:action_h/2);
  y+=action_h+gap;
  card_shaped(t,vacuum_card_shape);
  if(!mode && !suction && !water){
    auto *note=detail_text(detail_root,tr(txt::vacuum_auto_suction),pad,y+gap,inner,text,LV_TEXT_ALIGN_CENTER,theme::SUBTLE);(void)note;
    return;
  }
  // How it cleans. The Guition groups the rows on one white card; the small screen has no room for a card.
  const int icon_w=ui::px(large?40:26);
  const int block=block_h();
  const uint32_t track=theme::hex(large?theme::TRACK:theme::CARD);
  if(large)detail_card(pad,y,inner,block+2*edge);
  int x=pad+edge,w=inner-2*edge;
  y+=edge;
  if(mode){vacuum_segments(t,*mode,50,x,y,w,mode_h,track,!large,text);y+=mode_h+step;}
  auto level=[&](const Choice &row,int first,const char *icon){
    detail_text(detail_root,icon,x,y+(row_h-lv_font_get_line_height(icons))/2,icon_w,icons,LV_TEXT_ALIGN_LEFT,theme::SUBTLE);
    vacuum_segments(t,row,first,x+icon_w,y,w-icon_w,row_h,track,!large,text);
    y+=row_h+step;
  };
  if(suction)level(*suction,10,"\U000F0210");
  if(water)level(*water,60,"\U000F058C");
  if(automatic){
    bool smart=tile_controls::shown_value(t,*mode,now).find("smart")!=std::string::npos;
    detail_text(detail_root,tr(smart?txt::vacuum_robot_chooses:txt::vacuum_per_room),x,y,w,text,LV_TEXT_ALIGN_CENTER,theme::SUBTLE);
  }
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
