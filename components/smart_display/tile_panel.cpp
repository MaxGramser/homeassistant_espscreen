// A tile's panel (layout_panel, runtime_tiles.h): the direct controls at the right of a wide card or under a taller card's
// name, built once per control set and laid out on every render.
//
// Compiled on its own, as page_receiver.cpp is: on Xtensa the literal pool of one object file must stay within reach of
// all of its code (docs/RELEASING.md, "The Xtensa literal range"), and main.cpp, where every inline header lands, is at
// that edge.
#include "esphome/core/log.h"
#include "runtime_tiles.h"

namespace runtime_tiles {

int layout_panel(Widgets &w,const Tile &t,bool large,int content_w,int content_h,int standing) {
  std::string mode=tile_controls::panel_kind(t);
  // A full card that draws its setpoint and mode keys as rows (render_tall) takes the taller card's control sizes.
  const bool taller=t.row_span()>1 && (!w.full || tile_controls::climate_modes_selected(t));
  // A full-page card fills the glass whatever the grid under it, so its keys follow the room the card has on the glass:
  // large keys once its content runs 56 mm along its longer side, the way the keys stand in a row. Before (firmware
  // 0.35.0) the height of one cell decided, so more rows chosen (a 10.1-inch with eight) gave the whole page the small
  // keys. Every board keeps what it had: the CYD's card (at most 51 mm) the small keys, every other the large.
  PanelMetrics m=w.full?panel_metrics_full(std::max(content_w,content_h)>=ui::mm(56)):panel_metrics(large);
  if(taller){
    m.key_h=std::max(ui::touch_min(),ui::px(large?48:34));m.key_w=m.key_h;
    if(t.domain()=="media_player"){m.key_h=media_tall_key(m.key_h,content_h);m.key_w=m.key_h;}
    m.pill_w=std::min(content_w,ui::control_max_width());m.pill_key=m.key_h;
    m.slider_h=m.key_h;m.toggle_h=m.key_h;m.ext=0;
    if(mode=="toggle"){
      const auto toggle=tall_tile::toggle(content_w,m.toggle_h);
      if(toggle.empty()){hide_panel(w);return 0;}
      m.toggle_w=toggle.w;
    }
    m.slider_w=std::max(ui::touch_min(),m.pill_w-m.key_h-m.gap);
    // A resized panel is rebuilt once, not on each live state update.
    if(w.panel_layout_w!=content_w||w.panel_layout_h!=content_h){end_panel(w);w.panel_mode.clear();}
    w.panel_layout_w=content_w;w.panel_layout_h=content_h;
  }
  const int knob_pad=taller?ui::px(large?4:3):4;
  const lv_font_t *icon_font=w.full?w.icon_font:mini_icon_font?mini_icon_font:w.icon_font;
  const lv_font_t *text_font=control_font?control_font:w.title_font;
  auto d=t.domain();
  // A wide card's controls fill every cell after its first (rest_content_width); a card over the whole page
  // keeps the wide sizes of panel_metrics_full, centred under it. A row of keys divides that room between three
  // of them, and never takes a key above the size the look gives it.
  // A full card's sizes are the look's, but its glass can be narrower than they are (a small screen standing up):
  // every width stays inside the card, and a key never below the touch minimum.
  if(w.full){
    m.pill_w=std::min(m.pill_w,content_w);
    m.slider_w=std::min(m.slider_w,std::max(ui::touch_min(),content_w-m.key_h-m.gap));
    m.toggle_w=std::min(m.toggle_w,content_w);
  }
  const int fill=(w.full||taller)?m.pill_w:rest_content_width(w);
  // That room follows the card's width (GitHub #250): a slot that showed a card of another width builds its parts again,
  // as a taller card does when it is resized.
  if(!w.full&&!taller){
    if(w.panel_layout_w!=fill){end_panel(w);w.panel_mode.clear();}
    w.panel_layout_w=fill;w.panel_layout_h=0;
  }
  const int keys_room=w.full?content_w:fill;
  const int key_w=std::min(m.key_w,std::max(ui::touch_min(),(keys_room-2*m.gap)/3));
  // A player's volume shares that room with its mute key; every other slider takes it whole.
  const int track=(w.full||taller)?(mode=="volume"?m.slider_w:m.pill_w):(mode=="volume"?std::max(ui::touch_min(),fill-m.gap-m.key_h):fill);
  // A player's volume over its playback keys (volume_playback) on a taller card: one panel, the slider a row above.
  const bool pair=taller&&mode=="playback"&&tile_controls::media_volume_selected(t);
  const int pair_w=pair?std::max(3*key_w+2*m.gap,m.pill_w):0;
  // 1: the volume over the keys, 2: standing at the card's right, 3: no room for it, the keys alone.
  const uint8_t pair_form=!pair?0:standing>0?2:standing<0?3:1;
  auto make_slider=[&](int width,int h){
    auto *slider=lv_slider_create(w.panel);w.control_slider=slider;
    lv_obj_remove_flag(slider,LV_OBJ_FLAG_GESTURE_BUBBLE);lv_obj_remove_flag(slider,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_size(slider,width,h);
    lv_obj_set_style_pad_all(slider,0,LV_PART_MAIN);
    lv_obj_set_style_bg_opa(slider,LV_OPA_COVER,LV_PART_MAIN);lv_obj_set_style_bg_opa(slider,LV_OPA_COVER,LV_PART_INDICATOR);
    // The handle is a short white bar inside the fill, like Home Assistant's slider.
    lv_obj_set_style_radius(slider,2,LV_PART_KNOB);lv_obj_add_style(slider,theme::style(theme::Paint::knob),LV_PART_KNOB);lv_obj_set_style_bg_opa(slider,LV_OPA_COVER,LV_PART_KNOB);
    slider_handle(slider,width,h);
    lv_obj_set_style_border_width(slider,0,LV_PART_KNOB);lv_obj_set_style_shadow_width(slider,0,LV_PART_KNOB);
    lv_obj_set_ext_click_area(slider,m.ext+2);
    lv_obj_add_event_cb(slider,slider_event,LV_EVENT_ALL,(void*)(uintptr_t)w.index);
  };
  if(!w.panel){w.panel=panel_obj(w.tile,false);}
  if(w.panel_mode!=mode || w.panel_full!=w.full || w.panel_tall!=taller || w.panel_pair!=pair_form){
    end_panel(w);w.panel_mode=mode;w.panel_full=w.full;w.panel_tall=taller;w.panel_pair=pair_form;w.panel_dirty=true;
    if(tile_controls::is_key_row(mode)){
      for(unsigned n=0;n<3;++n){panel_key(w,n,w.panel,m,key_w,m.key_h,false);panel_icon(w,n,icon_font);}
      // Standing at the card's right (form 2), the volume is one of the card's own parts (render_tall, media_standing).
      if(pair_form==1)make_slider(pair_w,m.slider_h);
#ifdef SD_MOD_LIGHT_PRESETS
    }else if(mode=="presets"||mode=="brightness_presets"){
      // The keys are made per render (preset_keys), as many as the room holds; the slider of the pair once.
      if(mode=="brightness_presets")make_slider(m.pill_w,m.slider_h);

#endif
    }else if(mode=="mode"){
      // Drawn per render (draw_mode_bar): the track and a segment per mode, as many as its width holds.
    }else if(mode=="setpoint"||mode=="stepper"){
      w.pill=panel_obj(w.panel,false);lv_obj_set_size(w.pill,fill,m.key_h+2);
      lv_obj_set_style_radius(w.pill,LV_RADIUS_CIRCLE,0);lv_obj_set_style_bg_opa(w.pill,LV_OPA_COVER,0);
      panel_key(w,0,w.pill,m,m.pill_key,m.key_h+2,true);panel_icon(w,0,icon_font);lv_label_set_text(w.key_icons[0],tile_controls::glyph::MINUS);
      panel_key(w,1,w.pill,m,m.pill_key,m.key_h+2,true);panel_icon(w,1,icon_font);lv_label_set_text(w.key_icons[1],tile_controls::glyph::PLUS);
      // Holding -/+ keeps stepping (LVGL repeats while pressed); one call goes out after the finger rests.
      for(unsigned n=0;n<2;++n)lv_obj_add_event_cb(w.keys[n],control_event,LV_EVENT_LONG_PRESSED_REPEAT,(void*)(uintptr_t)((&w-widgets.data())*16+n));
      lv_obj_set_pos(w.keys[0],0,0);lv_obj_set_pos(w.keys[1],fill-m.pill_key,0);
      w.pill_value=lv_label_create(w.pill);lv_obj_remove_flag(w.pill_value,LV_OBJ_FLAG_CLICKABLE);
      lv_obj_set_style_text_font(w.pill_value,text_font,0);lv_obj_set_style_text_align(w.pill_value,LV_TEXT_ALIGN_CENTER,0);
      lv_label_set_long_mode(w.pill_value,LV_LABEL_LONG_CLIP);
      // A thermostat's range (firmware 0.19.0): in the number's place the end the -/+ move, its heat or cool icon before
      // the temperature, on the pill as a single temperature stands there; a tap switches it and lights it up while
      // the finger is down. The third key of the panel, on the panel above the pill, so the pill's own children stay.
      if(t.domain()=="climate"){
        panel_key(w,2,w.panel,m,m.pill_key,m.key_h,true);panel_icon(w,2,icon_font);
        auto *value=lv_label_create(w.keys[2]);lv_obj_remove_flag(value,LV_OBJ_FLAG_CLICKABLE);
        set_color(w.keys[2],LV_STYLE_BG_COLOR,theme::color(theme::STEPPER_KEY),LV_STATE_PRESSED);
        lv_obj_add_flag(w.keys[2],LV_OBJ_FLAG_HIDDEN);
      }
      lv_obj_set_size(w.pill_value,std::max(1,fill-2*m.pill_key),lv_font_get_line_height(text_font));
      lv_obj_set_pos(w.pill_value,m.pill_key,(m.key_h+2-lv_font_get_line_height(text_font))/2);
      w.key_commands[0]=tile_controls::STEP_DOWN;w.key_commands[1]=tile_controls::STEP_UP;
    }else if(tile_controls::is_slider(mode)){
      make_slider(track,m.slider_h);
      if(mode=="volume"){panel_key(w,0,w.panel,m,m.key_h,m.key_h,false);panel_icon(w,0,icon_font);w.key_commands[0]=tile_controls::MEDIA_MUTE;}
    }else if(mode=="toggle"){
      panel_key(w,0,w.panel,m,m.toggle_w,m.toggle_h,false);lv_obj_set_style_radius(w.keys[0],LV_RADIUS_CIRCLE,0);
      w.knob=panel_obj(w.keys[0],false);lv_obj_set_size(w.knob,m.toggle_h-2*knob_pad,m.toggle_h-2*knob_pad);lv_obj_set_y(w.knob,knob_pad);
      lv_obj_set_style_radius(w.knob,LV_RADIUS_CIRCLE,0);lv_obj_set_style_bg_opa(w.knob,LV_OPA_COVER,0);lv_obj_add_style(w.knob,theme::style(theme::Paint::knob),0);
      w.key_commands[0]=tile_controls::TOGGLE;
    }else if(mode=="run"){
      const char *text=tile_controls::run_label(d);
      lv_point_t size;lv_text_get_size(&size,text,text_font,0,0,LV_COORD_MAX,LV_TEXT_FLAG_EXPAND);
      panel_key(w,0,w.panel,m,std::max(m.key_w*3/2,(int)size.x+2*m.run_pad),m.key_h,false);lv_obj_set_style_radius(w.keys[0],LV_RADIUS_CIRCLE,0);
      panel_icon(w,0,text_font);lv_label_set_text(w.key_icons[0],text);
      w.key_commands[0]=tile_controls::RUN;
    }else{end_panel(w);return 0;}
  }
  // Per-render contents: which keys, their icons and states; then the panel size and place.
  int panel_w=0,panel_h=m.key_h;uint32_t now=esphome::millis();
  auto set_checked=[&](unsigned n,bool checked){
    if(w.key_checked[n]==(int)checked)return;w.key_checked[n]=checked;
    if(checked)lv_obj_add_state(w.keys[n],LV_STATE_CHECKED);else lv_obj_remove_state(w.keys[n],LV_STATE_CHECKED);
    if(w.key_icons[n])lv_obj_set_style_text_color(w.key_icons[n],checked?theme::color(theme::ON_ACCENT):w.panel_text,0);
  };
  auto set_disabled=[&](unsigned n,bool disabled){if(disabled)lv_obj_add_state(w.keys[n],LV_STATE_DISABLED);else lv_obj_remove_state(w.keys[n],LV_STATE_DISABLED);};
  if(tile_controls::is_key_row(mode)){
    std::array<tile_controls::Key,3> keys;unsigned count=tile_controls::keys_for(t,keys,now);
    // With the volume above them, the keys stand centred under its slider, a row lower.
    const bool volume=pair_form==1&&(t.supported&tile_controls::feature::MEDIA_VOLUME_SET);
    const int row_w=count?count*key_w+(count-1)*m.gap:0;
    const int key_x=volume?(pair_w-row_w)/2:0,key_y=volume?m.slider_h+m.gap:0;
    for(unsigned n=0;n<3;++n){
      if(n>=count){lv_obj_add_flag(w.keys[n],LV_OBJ_FLAG_HIDDEN);w.key_commands[n]=tile_controls::NONE;continue;}
      lv_obj_remove_flag(w.keys[n],LV_OBJ_FLAG_HIDDEN);lv_obj_set_pos(w.keys[n],key_x+n*(key_w+m.gap),key_y);
      label(w.key_icons[n],keys[n].icon);center_icon(w.key_icons[n]);w.key_commands[n]=keys[n].command;w.key_args[n]=keys[n].arg;
      // The active mode key carries the accent; "off" stays neutral grey.
      if(keys[n].checked && w.key_checked[n]!=1)lv_obj_set_style_bg_color(w.keys[n],keys[n].arg=="off"?theme::color(theme::OFF):w.panel_accent,LV_STATE_CHECKED);
      set_checked(n,keys[n].checked);set_disabled(n,keys[n].disabled);
    }
    panel_w=row_w;
    if(pair_form==1&&w.control_slider){
      set_hidden(w.control_slider,!volume);
      if(volume){
        lv_obj_set_pos(w.control_slider,0,0);
        // Keep the dragged value while the command is under way; HA's report takes over afterwards.
        travel_look(w.control_slider,t,false,true);if(!lv_obj_has_state(w.control_slider,LV_STATE_PRESSED) && !(t.pending && !t.confirmed))lv_slider_set_value(w.control_slider,slider_value(t),LV_ANIM_OFF);
        panel_w=pair_w;panel_h=key_y+m.key_h;
      }
    }
#ifdef SD_MOD_LIGHT_PRESETS
  }else if(mode=="presets"||mode=="brightness_presets"){
    panel_w=preset_panel(w,t,m,taller,content_w,content_h,fill,panel_h);
#endif
  }else if(mode=="mode"){
    // A thermostat's modes (firmware 0.19.0): the bar under its -/+ in "Temperature and mode", with the same rule for
    // how many fit (climate_tile::bar_room) and the same modes (climate_bar_keys). Over the card's reach on a card of
    // more than one row or the whole page, a finger per segment beside the name on a card of one row.
    const auto cm=bar_metrics(m,large);
    const bool stretches=w.full||taller;
    const int reach=std::min(keys_room,ui::control_max_width());
    std::array<tile_controls::Key,climate_tile::SEGMENTS> modes;
    const int room=climate_tile::bar_room(cm,reach,(int)tile_controls::climate_bar_keys(t,modes));
    panel_w=climate_tile::bar_width(cm,reach,room,stretches);panel_h=cm.touch;
    if(panel_w)draw_mode_bar(w,t,w.panel,w.pill,w.segments.data(),{0,0,panel_w,panel_h},room,cm,large);
  }else if(mode=="setpoint"||mode=="stepper"){
    float shown=std::isfinite(t.edit_value)?t.edit_value:tile_controls::edit_target(t);
    std::string suffix=tile_controls::thermostat(t)?tile_controls::setpoint_suffix(t):screen_text::unit_suffix(t.unit);
    // A range: the chip says the chosen end (range_chip); the number keeps it too, which the tall form measures by.
    const float step=tile_controls::edit_step(t);
    label(w.pill_value,tile_controls::format_value(tile_controls::climate_range(t)?tile_controls::range_end(t,t.range_end):shown,step,suffix.c_str()));
    panel_w=fill;panel_h=m.key_h+2;
    if(!taller)stepper_keys(w,fill,panel_h,text_font,&t);
  }else if(tile_controls::is_slider(mode)){
    bool has_slider=mode!="volume" || (t.supported & tile_controls::feature::MEDIA_VOLUME_SET);
    if(has_slider){
      lv_obj_remove_flag(w.control_slider,LV_OBJ_FLAG_HIDDEN);lv_obj_set_pos(w.control_slider,0,(panel_h-m.slider_h)/2);
      // Keep the dragged value while the command is under way; HA's report takes over afterwards.
      travel_look(w.control_slider,t,false,true);if(!lv_obj_has_state(w.control_slider,LV_STATE_PRESSED) && !(t.pending && !t.confirmed))lv_slider_set_value(w.control_slider,slider_value(t),LV_ANIM_OFF);
      panel_w=track;
    }else lv_obj_add_flag(w.control_slider,LV_OBJ_FLAG_HIDDEN);
    if(mode=="volume"){
      bool has_mute=t.supported & tile_controls::feature::MEDIA_VOLUME_MUTE;
      if(has_mute){
        lv_obj_remove_flag(w.keys[0],LV_OBJ_FLAG_HIDDEN);lv_obj_set_pos(w.keys[0],panel_w?panel_w+m.gap:0,0);
        label(w.key_icons[0],t.muted?tile_controls::glyph::MUTED:tile_controls::glyph::VOLUME);
        if(t.muted && w.key_checked[0]!=1)lv_obj_set_style_bg_color(w.keys[0],w.panel_accent,LV_STATE_CHECKED);
        set_checked(0,t.muted);panel_w+=(panel_w?m.gap:0)+m.key_h;
      }else lv_obj_add_flag(w.keys[0],LV_OBJ_FLAG_HIDDEN);
    }
  }else if(mode=="toggle"){
    bool on=t.state=="on";
    if(on && w.key_checked[0]!=1)lv_obj_set_style_bg_color(w.keys[0],w.panel_accent,LV_STATE_CHECKED);
    set_checked(0,on);
    if(w.knob_on!=(int)on){w.knob_on=on;lv_obj_set_x(w.knob,on?m.toggle_w-m.toggle_h+knob_pad:knob_pad);}
    panel_w=m.toggle_w;panel_h=m.toggle_h;
  }else if(mode=="run"){
    // The requested width: a key created in this pass has no coordinates before LVGL's layout.
    panel_w=lv_obj_get_style_width(w.keys[0],LV_PART_MAIN);
  }
  (void)now;
  if(!panel_w){hide_panel(w);return 0;}
  // A panel shown again kept the colours of the card it last served.
  if(lv_obj_has_flag(w.panel,LV_OBJ_FLAG_HIDDEN)){lv_obj_remove_flag(w.panel,LV_OBJ_FLAG_HIDDEN);w.panel_dirty=true;}
  lv_obj_set_size(w.panel,panel_w,panel_h);
  if(w.full||taller)lv_obj_set_pos(w.panel,std::max(0,(content_w-panel_w)/2),std::max(0,content_h-panel_h));
  else lv_obj_set_pos(w.panel,content_w-panel_w,std::max(0,(content_h-panel_h)/2));
  w.panel_w=panel_w+m.text_gap;
  return w.panel_w;
}

}  // namespace runtime_tiles
