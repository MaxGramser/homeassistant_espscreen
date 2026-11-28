// Opening a card: show_detail builds the card of a tile, refresh_detail paints it when its entity changes.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: what each card shows (the cards, each in its own part).
// What proves it: tests/test_optimistic_rule.py (a change paints before it builds).
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
inline void show_detail(unsigned index){
  if(index>=model.count&&index!=SENSOR_DETAIL)return;
  Tile &t=index==SENSOR_DETAIL?detail_sensor:model.tiles[index];
  // Another tile's card: a keypad left open for an alarm does not come back with it.
  if(alarm_pad.open&&t.entity!=alarm_pad.entity)alarm_close_pad();
  // A card that opens starts on a day (an hour for a tile whose graph shows one); switching ranges keeps it open.
  if(!detail_root||lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN)||detail_index!=index){
    history_hours=t.history_hours==1?1:24;history_asked_entity.clear();weather_view=0;select_page=0;
    // A player's card that opens shows its cover and colour as they are; one built again while open keeps its face.
    media_face=MediaFace{};
  }
  detail_index=index;
  // The card's own font is the tile title's as the look gave it (style_title), not the one the first cell wears right
  // now: a wide name there switches to another step, and this is kept for every card that opens after it.
  if(!detail_font)detail_font=widgets[0].title_font?widgets[0].title_font:lv_obj_get_style_text_font(widgets[0].title,LV_PART_MAIN);
  if(!detail_root){
    // The backdrop covers the page; the card itself is only as wide as a hand spans (overlay_card).
    detail_backdrop=lv_obj_create(lv_screen_active());lv_obj_remove_style_all(detail_backdrop);
    lv_obj_set_size(detail_backdrop,lv_pct(100),lv_pct(100));lv_obj_remove_flag(detail_backdrop,LV_OBJ_FLAG_SCROLLABLE);
    // Nothing leaks through to what lies under it, the same rule the effects page keeps. LVGL looks on
    // under an overlay that takes no press: a tap in the room a card leaves reached the tiles and the page
    // keys behind it, so a miss beside the range keys turned the page under the open card (firmware 0.2.82).
    lv_obj_add_flag(detail_backdrop,LV_OBJ_FLAG_CLICKABLE);
    detail_root=lv_obj_create(lv_screen_active());lv_obj_remove_style_all(detail_root);lv_obj_set_size(detail_root,lv_pct(100),lv_pct(100));lv_obj_remove_flag(detail_root,LV_OBJ_FLAG_SCROLLABLE);
  }
  lv_obj_set_style_bg_color(detail_backdrop,theme::color(theme::PAGE),0);lv_obj_set_style_bg_opa(detail_backdrop,LV_OPA_COVER,0);
  lv_obj_remove_flag(detail_backdrop,LV_OBJ_FLAG_HIDDEN);lv_obj_move_foreground(detail_backdrop);
  ++card_builds;
  detail_action_count=0;card_parts.clear();card_shape_of=nullptr;card_blocked=false;detail_status=nullptr;detail_badge_status=nullptr;detail_switch=nullptr;climate_number=nullptr;climate_ends[0]=climate_ends[1]=nullptr;climate_now_mark=nullptr;climate_keys[0]=climate_keys[1]=nullptr;detail_placed=false;detail_status_brief=false;history_forget();
  alarm_forget_widgets();media_progress_fill=nullptr;media_elapsed_label=nullptr;media_total_label=nullptr;media_detail_picture=nullptr;light_value=nullptr;
#ifdef SD_MOD_VACUUM_CARD
  vacuum_card::card_cleared();
#endif
  lv_obj_clean(detail_root);lv_obj_remove_flag(detail_root,LV_OBJ_FLAG_HIDDEN);lv_obj_move_foreground(detail_root);
  lv_obj_set_style_bg_color(detail_root,theme::color(theme::PAGE),0);lv_obj_set_style_bg_opa(detail_root,LV_OPA_COVER,0);
  lv_obj_set_style_bg_grad_dir(detail_root,LV_GRAD_DIR_NONE,0);
  media_knob=media_pill_obj=media_library_key=media_input_key=nullptr;
  // The calendar card's full screen (firmware 0.56.0+) is its own: the whole glass, its own header with the view key.
  if(t.domain()=="calendar"){calendar_view::open(detail_root,t,index);return;}
#ifdef SD_MOD_TODO
  // The to-do card's full screen (module todo, firmware 0.61.0+) is its own too: the whole list and its keyboard.
  if(t.domain()=="todo"){todo_view::open(detail_root,t,index);return;}
#endif
#ifdef SD_MOD_TEXT_EDIT
  // A text's field with the keyboard (module text_edit, firmware 0.61.0+); Home Assistant's own field is disabled while
  // the entity is unavailable (and empty while it has no value yet), and so is this one: such a text gets the plain card
  // that says so.
  if(tile_controls::text_entity(t.domain())&&t.received&&t.state!="unavailable"&&fresh()){text_edit_view::open(detail_root,t,index);return;}
#endif
  // The card's room: capped to what a hand spans and centred, unless it shows a picture (the media card's
  // cover art, a camera), which may fill the glass. Every size below follows from `width`.
  auto d=t.domain();
  // A day of a sensor is a picture as much as a cover is: it may take the whole glass, and only the row of
  // range keys under it keeps a hand's width (overlay_card::reach). Asked here because every size below
  // follows from `width`.
  const bool with_history=history_card(t);
  auto kind=d=="media_player"?overlay_card::picture:with_history||d=="weather"?overlay_card::graph:overlay_card::controls;
#ifdef SD_MOD_VACUUM_CARD
  // The vacuum card of the module takes the whole glass on landscape glass with a map, and on low glass.
  if(d=="vacuum"&&!with_history&&vacuum_card::wide(t))kind=overlay_card::picture;
#endif
  bool large=ui::large();
  // A card whose stack asks for more height than the glass has stands in two columns instead.
  const int columns=d=="climate"||d=="humidifier"?climate_columns(t,large):d=="cover"?cover_columns(t,large):d=="weather"?1
                     :d=="light"||d=="fan"?light_columns(large):1;
  overlay_card::frame(detail_root,kind,columns);
  // The room the frame just gave the card; LVGL reports the new width only after its next layout pass.
  int width=overlay_card::content_width(kind,columns), height=overlay_card::screen_height();int pad=overlay_card::pad(), top=ui::px(large?100:62), gap=ui::px(large?12:6),bh=ui::px(large?58:34),cw=(width-pad*2-gap)/2;
  // The top bar of every page a tap opens (detail_bar): the back key and the name, on the glass's edges.
  const auto top_bar=detail_bar::make(detail_root,t.name,{detail_bar::BACK,[](lv_event_t *){detail_command(-1);}});
  auto *back=top_bar.back,*heading=top_bar.title;
  const auto bm=detail_bar::metrics();
  int bar=bm.key,bar_x=bm.x,bar_y=bm.y;
  std::string state=card_status(t);
  // The vacuum and history cards draw their own state.
  if(d!="vacuum"&&d!="media_player"&&d!="climate"&&d!="humidifier"&&d!="light"&&d!="fan"&&d!="select"&&d!="input_select"&&!with_history){detail_status=detail_label(detail_root,screen_text::with_unit(state,t.unit),pad,ui::px(large?80:50),width-2*pad);lv_obj_set_style_text_align(detail_status,LV_TEXT_ALIGN_CENTER,0);lv_obj_set_style_text_color(detail_status,theme::color(theme::MUTED),0);card_bind(detail_status,t,detail_status_paint);}
  if(with_history){
    render_history_detail(t,large,width,height,pad);
  }else if(d=="vacuum"){
#ifdef SD_MOD_VACUUM_CARD
    vacuum_card::render(t,heading,width,height);
#else
    render_vacuum_detail(t,large,width,height,pad);
#endif
  }else if(d=="climate"||d=="humidifier"){
    // A humidifier is the thermostat's card in percent: its power key, the humidity it is set to, its modes.
    render_climate_detail(t,large,width,height,columns);
  }else if(d=="cover"){
    if(detail_status && control_font){lv_obj_set_style_text_font(detail_status,control_font,0);lv_obj_set_height(detail_status,lv_font_get_line_height(control_font));}
    render_cover_detail(t,large,width,height,pad,columns);
  }else if(d=="remote"){
    render_remote_detail(t,large,width,height,pad,top,bar,bar_x,bar_y);
  }else if(d=="select"||d=="input_select"){
    render_select_detail(t,large,width,height,pad,top,t.state);
  }else if(d=="media_player"){
    // "Now playing" (firmware 0.2.64+): the cover, the track, a running progress bar, round keys and the volume row, on
    // its cover's colour (worked out first: the top bar's keys stand on it too).
    render_media_detail(t,index,large,width,height,bar_y+bar+(ui::px(large?8:4)));
    media_top_bar(t,back,heading);
  }else if(d=="light"||d=="fan"){
    render_light_detail(t,large,width,height,columns);
  }else if(d=="weather"){
    render_weather_detail(t,large,width,height,columns);
  }else if(d=="alarm_control_panel"){
    render_alarm_detail(t,large,width,height,heading);
  }else if(d=="lock"){
    render_lock_detail(t,large,width,height,heading);
  }else if(d=="timer"){
    // The words follow the timer in place (docs/CARD_PARTS.md): running, paused or stopped, and Pause or Start.
    card_bind(detail_label(detail_root,"",pad,top,width-2*pad),t,[](lv_obj_t *o,const Tile &t,const CardPart &){
      label(o,tr(t.state=="active"?txt::timer_running:t.state=="paused"?txt::timer_paused:txt::timer_stopped));});
    auto *start=detail_button(tr(t.state=="active"?txt::timer_pause:txt::timer_start),pad,top+(ui::px(large?50:30)),cw,bh,40);
    card_bind(lv_obj_get_child(start,0),t,[](lv_obj_t *o,const Tile &t,const CardPart &){label(o,tr(t.state=="active"?txt::timer_pause:txt::timer_start));});
    detail_button(tr(txt::timer_cancel),pad+cw+gap,top+(ui::px(large?50:30)),cw,bh,41);
    card_shaped(t,entity_shape);
  }else if(d=="sun"){
    card_bind(detail_label(detail_root,"",pad,top,width-2*pad),t,[](lv_obj_t *o,const Tile &t,const CardPart &){
      label(o,fill(txt::sun_sunrise,"time",screen_text::clock_text(t.extra().sunrise,screen_settings::current.clock_24h!=0)));});
    card_bind(detail_label(detail_root,"",pad,top+lv_font_get_line_height(detail_font)+(ui::px(large?10:4)),width-2*pad),t,[](lv_obj_t *o,const Tile &t,const CardPart &){
      label(o,fill(txt::sun_sunset,"time",screen_text::clock_text(t.extra().sunset,screen_settings::current.clock_24h!=0)));});
    card_shaped(t,entity_shape);
  }
  // A card that leaves room sits in the middle of the glass; a picture fills it and stays where it is.
  // The back key and the name stay at the top of the card; the content under them is centred.
  if(kind==overlay_card::controls&&!detail_placed)overlay_card::centre(detail_root,2);
}
}

namespace runtime_tiles {
inline void history_received(){
  if(detail_root&&!lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN)&&detail_tile()&&
     detail_tile()->entity==history.entity&&history_hours==history.hours)refresh_detail(detail_index);
}
// An energy card's circle opens its sensor (firmware 0.47.0+), and the card's next moment brings the sensor's state.
inline void open_sensor_detail(const std::string &entity,const std::string &name,const std::string &state,const std::string &unit){
  detail_sensor=Tile{};detail_sensor.entity=entity;detail_sensor.name=name;detail_sensor.state=state;detail_sensor.unit=unit;
  detail_sensor.received=true;
  show_detail(SENSOR_DETAIL);
}
inline void sensor_detail_update(const std::string &entity,const std::string &state){
  if(detail_index!=SENSOR_DETAIL||detail_sensor.entity!=entity||detail_sensor.state==state)return;
  detail_sensor.state=state;refresh_detail(SENSOR_DETAIL);
}
inline void refresh_detail(unsigned index){
  if(!detail_root || lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN) || detail_index!=index)return;
  // A player's library or speaker menu over its card follows the player itself; the card is drawn again when they
  // close (firmware 0.24.0+).
  if(index<model.count && (media_library::visible()||media_library::menu_visible())){media_library::updated(model.tiles[index].entity);return;}
  // A card that paints itself follows in place, also under a finger (docs/CARD_PARTS.md).
  if(index<model.count && card_repaint(model.tiles[index]))return;
  auto *input=lv_indev_get_next(nullptr);if(input && lv_indev_get_state(input)==LV_INDEV_STATE_PRESSED)return;
  show_detail(index);
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
