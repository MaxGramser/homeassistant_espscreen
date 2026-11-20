// The media card: its layout, its cover and the colour read from it, and its parts.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the rules themselves, which are plain C++ without LVGL in media_card.h, media_library.h.
// What proves it: tests/test_media_card.cpp, tests/test_media_card.py.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// ---- The media card (firmware 0.2.64+) ----
// "Now playing" as a phone shows it: the album cover (app 0.2.77+ serves it, a Guition draws it; the CYD keeps the
// placeholder), the title, the artist and the album, a progress bar that runs while the track plays, round keys for
// previous, play or pause and next, and the volume row. media_card.h decides where everything goes for a tall card and
// a wide one; the same parts draw the card here and a tile over the whole page (render_media_full). The keys go
// through detail_command like every card's, the slider through commit_slider.
inline lv_obj_t *media_progress_fill=nullptr,*media_elapsed_label=nullptr;  // the card's, moved by tick() once a second
inline lv_obj_t *media_total_label=nullptr;
inline int media_bar_width=0;
inline media_card::Rect media_art_rect;  // where the card's cover goes once it is here
inline uint32_t media_accent(){return theme::foreground(theme::ha::LIGHT_BLUE);}
// The tile's icon font: the one the look gives every card's icon, fixed at boot by make_cells (packages/core.yaml), as
// every other font is. It used to be the first bound card that had one, so a card drawn while another page's cards
// were bound measured theirs (an empty meter ring on a 10.1 inch, 2026-11-15); the scan stays only for before boot.
inline const lv_font_t *cell_icon_font = nullptr;
inline const lv_font_t *tile_icon_font(){if(cell_icon_font)return cell_icon_font;for(auto &w:widgets)if(w.icon_font)return w.icon_font;return mini_icon_font?mini_icon_font:detail_font;}
// `duration`: the track's length, whose time is the widest beside the bar (firmware 0.46.0). A board that draws no
// pictures gets no place for a cover (media_card.h).
inline media_card::Metrics media_metrics(bool large,uint32_t duration=0){
  media_card::Metrics m;m.large=large;
  m.art=camera_supported();
  const lv_font_t *title=watch_font?watch_font:detail_font,*artist=control_font?control_font:detail_font,*small=small_font?small_font:detail_font;
  m.title_h=lv_font_get_line_height(title);m.artist_h=lv_font_get_line_height(artist);m.small_h=lv_font_get_line_height(small);
  if(duration){
    lv_point_t size;const std::string widest=media_card::clock_text(duration);
    lv_text_get_size(&size,widest.c_str(),small,0,0,LV_COORD_MAX,LV_TEXT_FLAG_NONE);
    m.clock_w=size.x+ui::px(2);
  }
  return m;
}
// What the keys do, on the card and on a tile over the whole page: 20 play or pause, 21 previous, 22 next, 23 mute,
// 24 turn on, 30 turn off.
// Play or pause, mute, shuffle and repeat show at once (docs/OPTIMISTIC.md); the track keys and power wait for the
// player, whose next track and state after power the screen cannot know.
inline void media_action(Tile &t,int cmd){
  using F=optimistic::Field;
  if(cmd==20){
    const auto a=tile_controls::media_play_action(t);
    const auto w=tile_controls::wanted(t,tile_controls::MEDIA_PLAY_PAUSE);
    if(a.valid()&&w.valid)wish(t,F::PLAYING,w.value,a.service,"","",media_entity(t));
    else action("media_player.media_play_pause",media_entity(t));
  }
  if(cmd==21)action("media_player.media_previous_track",media_entity(t));
  if(cmd==22)action("media_player.media_next_track",media_entity(t));
  if(cmd==23)wish(t,F::MUTED,t.muted?"0":"1","media_player.volume_mute","is_volume_muted",t.muted?"false":"true",media_entity(t));
  if(cmd==24)action("media_player.turn_on",media_entity(t));
  if(cmd==30)action("media_player.turn_off",media_entity(t));
  // Shuffle and repeat on the card (firmware 0.24.0+): the other way round, and repeat's next step.
  if(cmd==25)wish(t,F::SHUFFLE,t.extra().media_shuffle==1?"0":"1","media_player.shuffle_set","shuffle",t.extra().media_shuffle==1?"false":"true",media_entity(t));
  if(cmd==26){const std::string next=media_card::next_repeat(t.extra().media_repeat);wish(t,F::REPEAT,next,"media_player.repeat_set","repeat",next,media_entity(t));}
}
// An off or standby player shows one key: power, when the player can be turned on from here.
inline bool media_off(const Tile &t){return t.state=="off" || t.state=="standby";}
// A rounded box without a style of its own: the art's placeholder, the bar's track and its fill.
inline lv_obj_t *media_box(lv_obj_t *parent,lv_obj_t *existing,const media_card::Rect &r,uint32_t color,int radius){
  auto *o=existing;
  if(!o){o=lv_obj_create(parent);lv_obj_remove_style_all(o);lv_obj_set_style_bg_opa(o,LV_OPA_COVER,0);lv_obj_remove_flag(o,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(o,LV_OBJ_FLAG_SCROLLABLE);}
  lv_obj_set_pos(o,r.x,r.y);lv_obj_set_size(o,std::max(1,r.w),std::max(1,r.h));
  set_color(o,LV_STYLE_BG_COLOR,theme::rgb(color));set_number(o,LV_STYLE_RADIUS,radius);
  return o;
}
// A round key: a glyph on a grey circle, the play key on the accent, the mute key bare beside the slider. Faded while
// it cannot be used. `existing` keeps a tile's key across redraws; the card builds its keys anew each time.
inline lv_obj_t *media_key(lv_obj_t *parent,lv_obj_t *existing,const media_card::Rect &r,const char *glyph,const lv_font_t *font,bool accent,bool bare,bool enabled,lv_event_cb_t cb,void *user,
                           lv_event_code_t code=LV_EVENT_SHORT_CLICKED){
  auto *key=existing;
  if(!key){
    key=lv_obj_create(parent);lv_obj_remove_style_all(key);
    lv_obj_set_style_radius(key,LV_RADIUS_CIRCLE,0);lv_obj_set_style_bg_opa(key,bare?LV_OPA_TRANSP:LV_OPA_COVER,0);lv_obj_set_style_bg_opa(key,LV_OPA_COVER,LV_STATE_PRESSED);
    lv_obj_set_style_opa(key,LV_OPA_40,LV_STATE_DISABLED);
    lv_obj_add_flag(key,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(key,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_ext_click_area(key,bare?10:6);
    auto *icon=lv_label_create(key);lv_obj_remove_flag(icon,LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(key,cb,code,user);
  }
  lv_obj_set_pos(key,r.x,r.y);lv_obj_set_size(key,r.w,r.h);
  set_color(key,LV_STYLE_BG_COLOR,theme::color(accent?theme::ACCENT:theme::KEY));
  set_color(key,LV_STYLE_BG_COLOR,theme::color(accent?theme::ACCENT_PRESSED:theme::KEY_PRESSED),LV_STATE_PRESSED);
  auto *icon=lv_obj_get_child(key,0);
  if(font)set_font(icon,font);
  set_color(icon,LV_STYLE_TEXT_COLOR,theme::color(accent?theme::ON_ACCENT:theme::INK));
  label(icon,glyph);center_icon(icon);
  if(enabled)lv_obj_remove_state(key,LV_STATE_DISABLED);else lv_obj_add_state(key,LV_STATE_DISABLED);
  return key;
}
// The volume slider: the media colour on a pale track, a round white knob, the range every card slider has.
inline lv_obj_t *media_slider(lv_obj_t *parent,lv_obj_t *existing,const media_card::Rect &r,const Tile &t,bool large,bool enabled,void *user){
  auto *s=existing;
  if(!s){
    s=lv_slider_create(parent);lv_obj_remove_style_all(s);lv_slider_set_range(s,0,1000);
    lv_obj_set_style_bg_opa(s,LV_OPA_COVER,LV_PART_MAIN);lv_obj_set_style_bg_opa(s,LV_OPA_COVER,LV_PART_INDICATOR);lv_obj_set_style_bg_opa(s,LV_OPA_COVER,LV_PART_KNOB);
    lv_obj_set_style_radius(s,LV_RADIUS_CIRCLE,LV_PART_MAIN);lv_obj_set_style_radius(s,LV_RADIUS_CIRCLE,LV_PART_INDICATOR);lv_obj_set_style_radius(s,LV_RADIUS_CIRCLE,LV_PART_KNOB);
    lv_obj_set_style_pad_all(s,ui::px(large?4:3),LV_PART_KNOB);lv_obj_set_style_bg_opa(s,LV_OPA_80,(lv_style_selector_t)LV_PART_KNOB|(lv_style_selector_t)LV_STATE_PRESSED);
    lv_obj_set_style_opa(s,LV_OPA_40,LV_STATE_DISABLED);
    lv_obj_set_ext_click_area(s,ui::px(large?12:8));
    lv_obj_add_event_cb(s,slider_event,LV_EVENT_ALL,user);
  }
  lv_obj_set_pos(s,r.x,r.y);lv_obj_set_size(s,std::max(1,r.w),r.h);
  set_color(s,LV_STYLE_BG_COLOR,theme::rgb(theme::tint(theme::ha::LIGHT_BLUE,64)),LV_PART_MAIN);
  set_color(s,LV_STYLE_BG_COLOR,theme::rgb(t.muted?theme::hex(theme::OFF):media_accent()),LV_PART_INDICATOR);
  set_color(s,LV_STYLE_BG_COLOR,theme::color(theme::SLIDER_KNOB),LV_PART_KNOB);
  if(!lv_obj_has_state(s,LV_STATE_PRESSED) && lv_slider_get_value(s)!=slider_value(t))lv_slider_set_value(s,slider_value(t),LV_ANIM_OFF);
  if(enabled){lv_obj_remove_state(s,LV_STATE_DISABLED);lv_obj_add_flag(s,LV_OBJ_FLAG_CLICKABLE);}
  else{lv_obj_add_state(s,LV_STATE_DISABLED);lv_obj_remove_flag(s,LV_OBJ_FLAG_CLICKABLE);}
  return s;
}
// The cover over its placeholder: LVGL's image widget exists only on a board whose profile draws images.
inline lv_obj_t *media_picture_show(lv_obj_t *parent,lv_obj_t *existing,const media_card::Rect &r,lv_image_dsc_t *src){
#if LV_USE_IMAGE
  if(!src || !src->data)return existing;
  auto *p=existing;
  if(!p){p=lv_image_create(parent);lv_obj_remove_flag(p,LV_OBJ_FLAG_CLICKABLE);}
  lv_image_set_src(p,src);lv_obj_set_pos(p,r.x,r.y);lv_obj_set_size(p,r.w,r.h);lv_obj_invalidate(p);
  return p;
#else
  (void)parent;(void)r;(void)src;return existing;
#endif
}
// A media text that is wider than its line rolls by, round and round, and stands still when it fits (firmware 0.2.77+):
// LVGL's own circular scroll, at its own pace, where the dots of LV_LABEL_LONG_DOT cut a long title short.
inline void marquee(lv_obj_t *label,bool reading_pause=false,bool ready=true){
  if(!label)return;
  if(!ready){
    if(lv_label_get_long_mode(label)!=LV_LABEL_LONG_DOT)lv_label_set_long_mode(label,LV_LABEL_LONG_DOT);
    return;
  }
  if(lv_label_get_long_mode(label)==LV_LABEL_LONG_SCROLL_CIRCULAR)return;
  if(reading_pause){
    static const lv_anim_t timing=[](){lv_anim_t a;lv_anim_init(&a);lv_anim_set_delay(&a,1400);lv_anim_set_repeat_delay(&a,1800);lv_anim_set_repeat_count(&a,LV_ANIM_REPEAT_INFINITE);return a;}();
    lv_obj_set_style_anim(label,&timing,0);
    lv_obj_set_style_anim_duration(label,lv_anim_speed(ui::px(24)),0);
  }
  // LVGL cancels the old animation when long mode is assigned, even unchanged.
  lv_label_set_long_mode(label,LV_LABEL_LONG_SCROLL_CIRCULAR);
}
// The bar's fill and the elapsed time follow the track: once a second from tick(), without a redraw.
inline void media_progress(const Tile &t,lv_obj_t *fill,lv_obj_t *elapsed,int bar_w){
  const auto &x=t.extra();
  if(!fill || !x.media_duration)return;
  const bool play=media_card::playing(t.state);
  const int p=media_card::progress(x.media_position,x.media_position_at,now_epoch(),play,x.media_duration);
  const int h=lv_obj_get_style_height(fill,LV_PART_MAIN);
  const int w=std::max(h,bar_w*std::max(0,p)/1000);
  if(lv_obj_get_style_width(fill,LV_PART_MAIN)!=w)lv_obj_set_width(fill,w);
  if(elapsed)label(elapsed,media_card::clock_text(media_card::elapsed_seconds(x.media_position,x.media_position_at,now_epoch(),play,x.media_duration)));
}
// ---- The media card on its cover's ground (firmware 0.24.0+) ----
// The card is dark in both looks, the way a player's own "now playing" is: one dark colour read from the cover by the
// app (with the player's state, a few bytes), white words and keys on it. Everything is there before a picture is: a
// screen without pictures (the CYD) gets the same ground, and a cover only comes over its placeholder. Before the app
// has read a cover's colour, and for a cover without colour, and while nothing plays, the card is plain black
// (theme::MEDIA_GROUND). One flat colour (firmware 0.52.0): the card ran from one colour at the top to another at the
// bottom before, and the app has sent the same colour for both ends since GitHub #135.
inline uint32_t media_ground(const Tile &t){
  const auto &x=t.extra();
  return x.has_ground?x.ground:theme::hex(theme::MEDIA_GROUND);
}
inline uint32_t media_ink(){return theme::hex(theme::CAMERA_INK);}
// The second line, the times and what is faded: the ink, a quarter of the way into the ground.
inline uint32_t media_soft(uint32_t ground){return theme::mix(media_ink(),ground,190);}
// A key on the ground: a white key for the main one with the ground's own colour in it, a faint white circle for the
// others, none at all for a bare one (mute, shuffle, repeat), white icons.
inline void media_dark_key(lv_obj_t *key,bool primary,bool bare,uint32_t ground,uint32_t icon_color=0){
  if(!key)return;
  set_color(key,LV_STYLE_BG_COLOR,theme::rgb(media_ink()));
  set_color(key,LV_STYLE_BG_COLOR,theme::rgb(primary?theme::mix(media_ink(),ground,200):media_ink()),LV_STATE_PRESSED);
  set_number(key,LV_STYLE_BG_OPA,primary?LV_OPA_COVER:bare?LV_OPA_TRANSP:40);
  set_number(key,LV_STYLE_BG_OPA,primary?LV_OPA_COVER:90,LV_STATE_PRESSED);
  if(auto *icon=lv_obj_get_child(key,0))set_color(icon,LV_STYLE_TEXT_COLOR,theme::rgb(icon_color?icon_color:primary?ground:media_ink()));
}
// ---- What the card shows of its cover: the picture and the colour read from it (firmware 0.52.0, GitHub #177) ----
// A new track changes the words and the bar at once, as Home Assistant reports them, and the cover and the card's colour
// together, in one frame, once the new cover is here: until then the card keeps the old ones, as a phone's player does.
// Before, the card was built again on the new track's picture, on a black ground over an empty square, and once more
// when the app had read the new cover's colour: every key and the bar flashed twice, and the cover was gone for a second
// or two. Keeping the old cover costs no memory, the store keeps a picture while a card draws it (picture_store.h). A
// board that draws its cover from the download (no store) has it written over by the next one, so there the square
// shows its placeholder while the new cover loads, as before.
// The old face goes without a new one when the new cover has not come within MEDIA_FACE_WAIT_MS (Home Assistant had no
// picture), or when the player shows no picture (a radio station, a stop) for MEDIA_FACE_HOLD_MS: a player that passes
// through "idle" between two tracks keeps its face. A card that opens takes what there is, at once.
struct MediaFace {
  std::string key;               // the cover shown (cover_key), "" for the placeholder
  lv_image_dsc_t *src=nullptr;   // its picture
  uint32_t ground=0;             // the card's colour
  bool coloured=false;           // read from a cover, not the neutral black
  std::string wanted;            // what the player shows now: its cover's key, or its colour without one
  uint32_t since=0;              // since when it wants that
  uint32_t recheck=0;            // when a wait runs out and the face is worked out again (tick), 0 for none
  bool drawn=false;              // the card has shown a face since it opened
};
inline MediaFace media_face;
constexpr uint32_t MEDIA_FACE_WAIT_MS=8000,MEDIA_FACE_HOLD_MS=3000;
// The volume row's keys (firmware 0.39.0, GitHub #146), on the card and on a tile over the whole page, the keys the
// screensaver has: volume down and up step the player (Home Assistant's volume_down and volume_up), every clean tap
// counts and nothing waits for an answer, so a series of taps is a series of steps. Volume down held for a second and
// a half mutes the player where Home Assistant says it can be muted, and shows the muted speaker; the next tap on
// either key takes the mute off and changes nothing else.
constexpr uint32_t MEDIA_MUTE_HOLD_MS=1500;
inline uint32_t media_hold_at=0;    // when the finger came down on volume down; 0 once this hold has muted
inline bool media_hold_muted=false; // the hold muted: its own release is no step
// The tile the key belongs to: the open card's, or the tile over the whole page whose part the key is (asked of the
// key itself, never of a slot handed to LVGL: kept pages swap whole Widgets).
inline Tile *media_volume_tile(lv_obj_t *key,bool card){
  if(card)return detail_index<model.count?&model.tiles[detail_index]:nullptr;
  for(auto &w:widgets)if(w.extra_mode=="media"&&key&&(w.parts[11]==key||w.parts[13]==key))return w.index<model.count?&model.tiles[w.index]:nullptr;
  return nullptr;
}
// Muted or not shows at once on the card and the tiles (docs/OPTIMISTIC.md).
inline void media_mute(Tile &t,bool muted){
  if(muted==t.muted)return;
  wish(t,optimistic::Field::MUTED,muted?"1":"0","media_player.volume_mute","is_volume_muted",muted?"true":"false",media_entity(t));
}
inline void media_volume_event(lv_event_t *e){
  const intptr_t tag=(intptr_t)lv_event_get_user_data(e);
  const bool up=tag&1,card=tag&2;
  const auto code=lv_event_get_code(e);
  const uint32_t now=esphome::millis();
  auto *key=lv_event_get_current_target_obj(e);
  if(!enabled||!fresh()||lv_obj_has_state(key,LV_STATE_DISABLED))return;
  Tile *t=media_volume_tile(key,card);
  if(!t||!t->available())return;
  if(code==LV_EVENT_PRESSED){media_hold_at=now?now:1;media_hold_muted=false;return;}
  if(code==LV_EVENT_PRESSING){
    if(!media_hold_at||now-media_hold_at<MEDIA_MUTE_HOLD_MS||t->muted||!(t->supported&tile_controls::feature::MEDIA_VOLUME_MUTE))return;
    media_hold_at=0;media_hold_muted=true;
    media_mute(*t,true);
    return;
  }
  if(media_hold_muted){media_hold_muted=false;return;}
  if(!screen_input::touch_guard.accept_repeat(now,720+up))return;
  if(t->muted){media_mute(*t,false);return;}
  step_action(up?"media_player.volume_up":"media_player.volume_down",media_entity(*t));
}
// The card's volume row paints itself (docs/CARD_PARTS.md): volume down shows the muted speaker while muted, and the
// slider's fill goes faint; its track is the ink a little into the card's colour.
inline void media_minus_paint(lv_obj_t *key,const Tile &t,const CardPart &){
  paint_glyph(key,t.muted?tile_controls::glyph::MUTED:tile_controls::glyph::MINUS);
}
inline void media_volume_paint(lv_obj_t *slider,const Tile &t,const CardPart &){
  set_color(slider,LV_STYLE_BG_COLOR,theme::rgb(theme::mix(media_ink(),media_face.ground,70)),LV_PART_MAIN);
  set_color(slider,LV_STYLE_BG_COLOR,theme::rgb(t.muted?media_soft(media_face.ground):media_ink()),LV_PART_INDICATOR);
  if(!lv_obj_has_state(slider,LV_STATE_PRESSED)&&lv_slider_get_value(slider)!=slider_value(t))lv_slider_set_value(slider,slider_value(t),LV_ANIM_OFF);
}
// Volume down, the slider and volume up. `parts` keeps a tile's three across redraws (nullptr: the card makes them
// anew); on the card (`card`) they stand on its colour, a tile keeps the keys' own colours.
inline void media_volume_row(lv_obj_t *parent,lv_obj_t **parts,const media_card::Rect &minus,const media_card::Rect &volume,const media_card::Rect &plus,
                             const Tile &t,bool large,bool usable,void *slider_user,bool card,const lv_font_t *font){
  using namespace tile_controls;
  const uint32_t f=t.supported;auto can=[&](uint32_t bit){return usable&&(!f||(f&bit));};
  const bool step=can(feature::MEDIA_VOLUME_SET|feature::MEDIA_VOLUME_STEP)||(t.muted&&can(feature::MEDIA_VOLUME_MUTE));
  const intptr_t tag=card?2:0;
  lv_obj_t *made[3];
  const bool fresh_minus=!parts||!parts[0];
  made[0]=media_key(parent,parts?parts[0]:nullptr,minus,t.muted?glyph::MUTED:glyph::MINUS,font,false,false,step,media_volume_event,(void*)tag,LV_EVENT_CLICKED);
  if(fresh_minus){
    lv_obj_add_event_cb(made[0],media_volume_event,LV_EVENT_PRESSED,(void*)tag);
    lv_obj_add_event_cb(made[0],media_volume_event,LV_EVENT_PRESSING,(void*)tag);
  }
  made[1]=media_slider(parent,parts?parts[1]:nullptr,volume,t,large,can(feature::MEDIA_VOLUME_SET),slider_user);
  made[2]=media_key(parent,parts?parts[2]:nullptr,plus,glyph::PLUS,font,false,false,step,media_volume_event,(void*)(tag|1),LV_EVENT_CLICKED);
  if(card){
    media_dark_key(made[0],false,false,media_face.ground);media_dark_key(made[2],false,false,media_face.ground);
    set_color(made[1],LV_STYLE_BG_COLOR,theme::rgb(media_ink()),LV_PART_KNOB);
    card_bind(made[0],t,media_minus_paint);card_bind(made[1],t,media_volume_paint);
  }
  if(parts)for(int i=0;i<3;++i)parts[i]=made[i];
}
// The media card's seek (firmware 0.24.0+): a finger on the bar moves its knob, and the place it lets go of is sent.
// The bar then stands there until Home Assistant reports the player near it (media_card::Seek).
// A cover is asked for once the app has read its colour (the corners are cut over it), or after MEDIA_GROUND_WAIT_MS
// without it (an app from before): one download per track, not one for each colour.
inline std::string media_ground_waited;
inline uint32_t media_ground_since=0;
constexpr uint32_t MEDIA_GROUND_WAIT_MS=2500;
inline media_card::Seek media_seek;
inline std::string media_seek_entity;
inline lv_obj_t *media_knob=nullptr;
// The card's pill and library key (firmware 0.24.0+), for the render harness.
inline lv_obj_t *media_pill_obj=nullptr,*media_library_key=nullptr,*media_input_key=nullptr;
inline int media_bar_x=0,media_knob_size=0;
inline bool media_seeking=false;
// Where the track is now, as the card shows it: a seek just sent wins over Home Assistant's word until it agrees.
inline uint32_t media_elapsed(const Tile &t){
  const auto &x=t.extra();
  const bool play=media_card::playing(t.state);
  const uint32_t now=now_epoch();
  if(media_seek_entity==t.entity&&media_seek.holds(x.media_position,x.media_position_at,esphome::millis(),now,play,x.media_title)){
    uint32_t at=media_seek.seconds+(play&&now>media_seek.epoch?now-media_seek.epoch:0);
    return x.media_duration?std::min(at,x.media_duration):at;
  }
  return media_card::elapsed_seconds(x.media_position,x.media_position_at,now,play,x.media_duration);
}
// The fill and the knob at a number of seconds; at nought and 0:00 without a length (firmware 0.52.0).
inline void media_bar_at(uint32_t seconds,uint32_t duration,lv_obj_t *fill,lv_obj_t *elapsed,int bar_w){
  if(!fill)return;
  if(!duration)seconds=0;
  const int h=lv_obj_get_style_height(fill,LV_PART_MAIN);
  const int w=std::max(h,duration?(int)((uint64_t)bar_w*std::min(seconds,duration)/duration):0);
  if(lv_obj_get_style_width(fill,LV_PART_MAIN)!=w)lv_obj_set_width(fill,w);
  if(media_knob&&lv_obj_get_parent(media_knob)==lv_obj_get_parent(fill)&&lv_obj_get_style_x(media_knob,LV_PART_MAIN)!=media_bar_x+w-media_knob_size/2)lv_obj_set_x(media_knob,media_bar_x+w-media_knob_size/2);
  if(elapsed)label(elapsed,media_card::clock_text(seconds));
}
inline void media_seek_event(lv_event_t *e){
  const auto code=lv_event_get_code(e);
  if(detail_index>=model.count||!media_progress_fill)return;
  auto &t=model.tiles[detail_index];
  const auto &x=t.extra();
  if(!media_card::has_track(t.state)||!x.media_duration)return;
  lv_point_t point;lv_indev_get_point(lv_indev_active(),&point);
  lv_area_t area;lv_obj_get_coords(lv_obj_get_parent(media_progress_fill),&area);
  const int along=point.x-area.x1-media_bar_x;
  const uint32_t seconds=media_card::seek_seconds(along,media_bar_width,x.media_duration);
  // The seek bar is no LVGL slider: it says its own steps (touch_feedback.h), every 5 % of the track.
  if(code==LV_EVENT_PRESSED||code==LV_EVENT_PRESSING)touch_feedback::moved(media_progress_fill,(int)seconds,0,(int)x.media_duration);
  if(code==LV_EVENT_PRESSED||code==LV_EVENT_PRESSING){media_seeking=true;media_bar_at(seconds,x.media_duration,media_progress_fill,media_elapsed_label,media_bar_width);return;}
  if(code==LV_EVENT_PRESS_LOST){media_seeking=false;media_bar_at(media_elapsed(t),x.media_duration,media_progress_fill,media_elapsed_label,media_bar_width);return;}
  if(code!=LV_EVENT_RELEASED||!media_seeking)return;
  media_seeking=false;
  if(!fresh()||!t.available())return;
  media_seek.send(seconds,esphome::millis(),now_epoch(),x.media_title);media_seek_entity=t.entity;
  media_bar_at(seconds,x.media_duration,media_progress_fill,media_elapsed_label,media_bar_width);
  action("media_player.media_seek",media_entity(t),"seek_position",std::to_string(seconds));
}
// The card's top bar for a player (firmware 0.24.0+): the back key on the ground, the speaker it plays on as a pill
// in the middle where Home Assistant lists speakers (a tap opens the menu of them), and at the right the power key,
// where every other card has it (firmware 0.39.0, GitHub #146). A player without speakers keeps its name there. The
// library and the input keys stood at the right before; they close the volume row now (media_row_keys).
// The power key follows Home Assistant's dialog (computeMediaControls): turn off for a player that is on and can be
// turned off, and for a player whose state is only assumed both keys, whatever it reports. An off player's turn on is
// the big key in the middle of the card.
inline void media_top_bar(const Tile &t,lv_obj_t *back,lv_obj_t *heading){
  using namespace tile_controls;
  const auto &x=t.extra();
  // The top bar's keys are faint white circles, the same on any colour of the card.
  const uint32_t g=media_face.ground;
  media_dark_key(back,false,false,g);
  set_color(heading,LV_STYLE_TEXT_COLOR,theme::rgb(media_ink()));
  auto cb=[](lv_event_t *e){detail_command((intptr_t)lv_event_get_user_data(e));};
  const lv_font_t *icons=mini_icon_font?mini_icon_font:detail_font;
  const bool usable=fresh()&&t.available(),off=media_off(t);
  const bool power_off=usable&&(t.supported&feature::MEDIA_TURN_OFF)&&(!off||x.assumed);
  const bool power_on=usable&&(t.supported&feature::MEDIA_TURN_ON)&&!off&&x.assumed;
  int right=0;  // the keys at the right, in the top bar's places for them (detail_bar)
  for(int cmd:{30,24}){
    if(cmd==30?!power_off:!power_on)continue;
    const auto slot=detail_bar::right_slot(detail_root,right++);
    auto *key=media_key(detail_root,nullptr,{slot.x,slot.y,slot.w,slot.h},glyph::STANDBY,icons,false,false,true,cb,(void*)(intptr_t)cmd);
    media_dark_key(key,false,false,g);
  }
  media_pill_obj=nullptr;
  // Two keys at the right: the name keeps clear of both.
  detail_bar::place_title(heading,detail_root,right);
  if(x.media_sources.empty())return;
  lv_obj_add_flag(heading,LV_OBJ_FLAG_HIDDEN);
  // The pill: the speaker icon, the speaker's name (or "Choose a speaker"), the arrow of a menu.
  const lv_font_t *font=control_font?control_font:detail_font;
  const std::string name=x.media_source.empty()?std::string(tr(txt::media_choose_speaker)):x.media_source;
  const auto home=detail_bar::back_slot(detail_root),edge=detail_bar::right_slot(detail_root,std::max(0,right-1));
  const int bar=home.h,bar_y=home.y;
  const int h=bar*3/4,inset=ui::px(ui::large()?14:8),icon_w=lv_font_get_line_height(icons),gap=ui::px(ui::large()?6:4);
  // The room between the back key and the keys at the right; the pill stands in the middle of the glass where it fits
  // there, and in the middle of that room when two keys at the right leave too little (a speaker's name stays whole).
  const int lo=home.x+home.w+gap,hi=edge.x-gap,room=std::max(h,hi-lo);
  const int w=std::max(h,std::min(room,inset+icon_w+gap+text_width(name,font)+gap+icon_w+inset));
  const int mid=detail_bar::glass_left(detail_root)+overlay_card::screen_width()/2;
  const int centred=mid-w/2,px_left=centred>=lo&&centred+w<=hi?centred:lo+(room-w)/2;
  auto *pill=lv_obj_create(detail_root);lv_obj_remove_style_all(pill);
  lv_obj_set_pos(pill,px_left,bar_y+(bar-h)/2);lv_obj_set_size(pill,w,h);
  lv_obj_set_style_radius(pill,LV_RADIUS_CIRCLE,0);lv_obj_add_flag(pill,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(pill,LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_style_bg_color(pill,theme::rgb(media_ink()),0);lv_obj_set_style_bg_opa(pill,40,0);lv_obj_set_style_bg_opa(pill,90,LV_STATE_PRESSED);
  lv_obj_set_ext_click_area(pill,(bar-h)/2);
  lv_obj_add_event_cb(pill,cb,LV_EVENT_SHORT_CLICKED,(void*)(intptr_t)28);
  media_pill_obj=pill;
  auto glyph_at=[&](const char *glyph,int gx){
    auto *icon=lv_label_create(pill);lv_obj_remove_flag(icon,LV_OBJ_FLAG_CLICKABLE);set_font(icon,icons);
    lv_obj_set_style_text_color(icon,theme::rgb(media_ink()),0);lv_label_set_text(icon,glyph);
    lv_obj_set_pos(icon,gx,(h-lv_font_get_line_height(icons))/2);
  };
  glyph_at("\U000F04C3",inset);
  glyph_at("\U000F0140",w-inset-icon_w);
  auto *words=detail_text(pill,name,inset+icon_w+gap,(h-lv_font_get_line_height(font))/2,std::max(1,w-2*(inset+icon_w+gap)),font,LV_TEXT_ALIGN_CENTER,media_ink());
  lv_obj_remove_flag(words,LV_OBJ_FLAG_CLICKABLE);
}
// The card: everything under the top bar, from `top` down.
// ---- The media card's parts (docs/CARD_PARTS.md): each paints itself from the tile ----
inline bool media_usable(const Tile &t){return fresh()&&t.available();}
inline bool media_track(const Tile &t){return media_usable(t)&&media_card::has_track(t.state);}
inline bool media_at_rest(const Tile &t){
  const auto &x=t.extra();
  return media_usable(t)&&!media_track(t)&&!media_off(t)&&x.media_library&&media_library::available()&&
         !(t.supported&(tile_controls::feature::MEDIA_PLAY|tile_controls::feature::MEDIA_PAUSE));
}
// A stream (firmware 0.52.0): a track that plays without a length, a radio station. Home Assistant has no word for it:
// Sonos, Cast and Music Assistant report a station as a track without media_duration, and Home Assistant's own dialog
// leaves its bar out then. Music Assistant keeps the bar, without a knob and without a total; the card and a tile over
// the whole page keep it as well, empty, with "Live" where the time stands (the word a live camera's tile shows,
// screen.camera.live). A track counts as a stream once it has played MEDIA_LIVE_MS without a length, so a player that
// reports the length a moment after the title never shows "Live" in between. Between two tracks (no track) the bar
// stands at nought with 0:00 at its ends.
constexpr uint32_t MEDIA_LIVE_MS=1500;
struct MediaLiveMark { std::string entity; uint32_t since=0; };
inline std::array<MediaLiveMark,4> media_live_marks{};  // when each player began to play without a length
inline bool media_live(const Tile &t){
  const bool stream=media_track(t)&&!t.extra().media_duration;
  MediaLiveMark *mark=nullptr,*spare=&media_live_marks[0];
  for(auto &m:media_live_marks){if(m.entity==t.entity)mark=&m;else if(m.entity.empty())spare=&m;}
  if(!stream){if(mark)*mark=MediaLiveMark{};return false;}
  const uint32_t now=esphome::millis();
  if(!mark){mark=spare;*mark=MediaLiveMark{t.entity,now};}
  return now-mark->since>=MEDIA_LIVE_MS;
}
// The card's cover square as render_media_detail laid it out (0: none), the size its cover is asked for in.
inline int media_art_size=0;
// What the card shows of its cover now (MediaFace above). The card's own paint works it out first, in every paint of the
// card, so every part after it paints the same face.
inline void media_face_follow(const Tile &t){
  const auto &x=t.extra();
  const uint32_t now=esphome::millis(),ground=media_ground(t);
  // The one picture held outside LVGL: never handed on once the store has let it go (its card draws it, so it should
  // not, but a pointer to freed memory on the glass is no risk worth taking).
  if(media_face.src&&!picture_kept_here(media_face.src)){media_face.src=nullptr;media_face.key.clear();}
  const bool pictured=camera_supported()&&media_art_size>0&&media_track(t)&&!x.media_picture.empty();
  const std::string waited=t.entity+"|"+x.media_picture;
  if(waited!=media_ground_waited){media_ground_waited=waited;media_ground_since=now;}
  const bool pending=pictured&&!x.ground_known&&now-media_ground_since<MEDIA_GROUND_WAIT_MS;
  // The cover's corners are cut over the card's colour, so the colour is part of which cover it is.
  const std::string key=pictured?cover_key(t.entity,x.media_picture,media_art_size,ground):std::string();
  const std::string wanted=pictured?key:"-"+std::to_string(ground);
  if(wanted!=media_face.wanted){media_face.wanted=wanted;media_face.since=now;}
  uint32_t due=0;
  auto recheck=[&](uint32_t at){if(!due||static_cast<int32_t>(at-due)<0)due=at;};
  if(pending)recheck(media_ground_since+MEDIA_GROUND_WAIT_MS);
  // The cover goes to the loader with the next round (card_cover_want); what the store has of it is here at once.
  media_card_cover=pictured&&!pending?CoverAsk{t.entity,x.media_picture,media_art_size,ground}:CoverAsk{};
  lv_image_dsc_t *src=media_card_cover.valid()?picture_of(key):nullptr;
  media_face.recheck=0;
  // The new cover is here: it and its colour, together. The one it takes over from goes from the store once nothing
  // draws it (the loader forgets a cover its owner moved on from).
  if(src&&src->data){
    media_face.drawn=true;media_face.key=key;media_face.src=src;media_face.ground=ground;media_face.coloured=x.has_ground;return;
  }
  // A cover on the card stays while the next one is on its way, or while the player shows none for a moment. The
  // square without a cover keeps its colour too while a cover is on its way (a track without one, then one with):
  // the colour came a moment before its cover and the empty square showed on it. A card that opens takes what there is.
  if(media_face.src||(pictured&&media_face.drawn)){
    const uint32_t wait=pictured?MEDIA_FACE_WAIT_MS:MEDIA_FACE_HOLD_MS;
    if(now-media_face.since<wait){recheck(media_face.since+wait);media_face.recheck=due;return;}
  }
  // Nothing to keep: the placeholder on the player's colour, and its cover comes over it once it is here.
  media_face.drawn=true;
  media_face.key.clear();media_face.src=nullptr;media_face.ground=ground;media_face.coloured=x.has_ground;
  media_face.recheck=due;
}
// The card's colour behind everything, after the face for this paint is worked out.
inline void media_root_paint(lv_obj_t *root,const Tile &t,const CardPart &){
  media_face_follow(t);
  set_color(root,LV_STYLE_BG_COLOR,theme::rgb(media_face.ground));
}
inline void media_backdrop_paint(lv_obj_t *backdrop,const Tile &,const CardPart &){
  set_color(backdrop,LV_STYLE_BG_COLOR,theme::rgb(media_face.ground));
}
// The square under the cover: a darker one on a cover's colour, a faint white one on the plain black.
inline void media_frame_paint(lv_obj_t *frame,const Tile &,const CardPart &){
  set_color(frame,LV_STYLE_BG_COLOR,theme::rgb(media_face.coloured?theme::hex(theme::CAMERA_PAGE):media_ink()));
  set_number(frame,LV_STYLE_BG_OPA,media_face.coloured?60:24);
}
// The player's icon in the square (`value`: the library's, for a player at rest): the big icon where the square holds
// it, the tile's icon in a small one.
inline void media_placeholder_paint(lv_obj_t *icon,const Tile &t,const CardPart &part){
  set_color(icon,LV_STYLE_TEXT_COLOR,theme::rgb(theme::mix(media_ink(),media_face.ground,120)));
  const std::string glyph=part.value.empty()?std::string(icon_for(t)):part.value;
  if(glyph==lv_label_get_text(icon))return;
  set_font(icon,big_icon_font&&font_has(big_icon_font,glyph)&&lv_font_get_line_height(big_icon_font)<=media_art_rect.h?big_icon_font:tile_icon_font());
  lv_label_set_text(icon,glyph.c_str());center_icon(icon);
}
// The cover over the square, or nothing over it.
inline void media_picture_paint(lv_obj_t *picture,const Tile &,const CardPart &){
#if LV_USE_IMAGE
  lv_image_dsc_t *src=media_face.src&&media_face.src->data?media_face.src:nullptr;
  if(lv_image_get_src(picture)!=src){
    lv_image_set_src(picture,src);
    lv_obj_set_pos(picture,media_art_rect.x,media_art_rect.y);lv_obj_set_size(picture,media_art_rect.w,media_art_rect.h);
  }
  set_hidden(picture,!src);
#else
  (void)picture;
#endif
}
// The second line, the times: the ink a quarter of the way into the card's colour.
inline void media_soft_paint(lv_obj_t *text,const Tile &,const CardPart &){
  set_color(text,LV_STYLE_TEXT_COLOR,theme::rgb(media_soft(media_face.ground)));
}
// The title, or what the player does when nothing plays; a new text starts its roll again, the same one rolls on.
inline void media_title_paint(lv_obj_t *line,const Tile &t,const CardPart &){
  const auto &x=t.extra();
  label(line,media_track(t)&&!x.media_title.empty()?x.media_title:std::string(media_card::idle_text(media_usable(t)?t.state:"unavailable")));
}
inline void media_artist_paint(lv_obj_t *line,const Tile &t,const CardPart &part){
  const auto &x=t.extra();
  label(line,media_track(t)?media_card::subtitle(x.media_artist,x.media_album):media_at_rest(t)?std::string(tr(txt::media_library_hint)):std::string());
  media_soft_paint(line,t,part);
}
// The main key (play or pause, power on) is white with the card's colour in its icon.
inline void media_primary_paint(lv_obj_t *key,const Tile &,const CardPart &){media_dark_key(key,true,false,media_face.ground);}
inline void media_play_paint(lv_obj_t *key,const Tile &t,const CardPart &part){
  paint_glyph(key,media_card::playing(t.state)?tile_controls::glyph::PAUSE:tile_controls::glyph::PLAY);
  media_primary_paint(key,t,part);
}
// A player at rest has the Library key instead: white, its word in the card's colour.
inline void media_start_paint(lv_obj_t *start,const Tile &,const CardPart &){
  set_color(start,LV_STYLE_BG_COLOR,theme::rgb(theme::mix(media_ink(),media_face.ground,200)),LV_STATE_PRESSED);
  if(auto *words=lv_obj_get_child(start,0))set_color(words,LV_STYLE_TEXT_COLOR,theme::rgb(media_face.ground));
}
// Shuffle on is the accent, off a faded white; the dot under it shows while it is on.
inline void media_shuffle_paint(lv_obj_t *key,const Tile &t,const CardPart &){
  if(auto *icon=lv_obj_get_child(key,0))set_color(icon,LV_STYLE_TEXT_COLOR,theme::rgb(t.extra().media_shuffle==1?media_accent():media_soft(media_face.ground)));
}
inline void media_shuffle_dot_paint(lv_obj_t *dot,const Tile &t,const CardPart &){
  set_hidden(dot,t.extra().media_shuffle!=1);
}
// Repeat all and one the accent (one with its own glyph), off a faded white.
inline void media_repeat_paint(lv_obj_t *key,const Tile &t,const CardPart &){
  const auto &repeat=t.extra().media_repeat;
  paint_glyph(key,repeat=="one"?"\U000F0458":"\U000F0456");
  if(auto *icon=lv_obj_get_child(key,0))set_color(icon,LV_STYLE_TEXT_COLOR,theme::rgb(repeat!="off"?media_accent():media_soft(media_face.ground)));
}
// The bar as the card shows it now: where the track is, at nought without a track or a length, empty with "Live" for a
// stream (media_live). The times stand in the ink a quarter into the card's colour, "Live" in the ink itself.
inline void media_bar_now(const Tile &t){
  const bool live=media_live(t);
  const uint32_t duration=media_track(t)?t.extra().media_duration:0;
  if(media_progress_fill)set_hidden(media_progress_fill,live);
  if(media_knob)set_hidden(media_knob,live);
  if(live){if(media_elapsed_label)label(media_elapsed_label,tr(txt::camera_live));}
  else media_bar_at(duration?media_elapsed(t):0,duration,media_progress_fill,media_elapsed_label,media_bar_width);
  if(media_elapsed_label)set_color(media_elapsed_label,LV_STYLE_TEXT_COLOR,theme::rgb(live?media_ink():media_soft(media_face.ground)));
  if(media_total_label){
    label(media_total_label,live?std::string():media_card::clock_text(duration));
    set_color(media_total_label,LV_STYLE_TEXT_COLOR,theme::rgb(media_soft(media_face.ground)));
  }
}
// The bar stands where a pause left it and runs on from there (the bar's own second-by-second tick does the rest).
inline void media_bar_paint(lv_obj_t *,const Tile &t,const CardPart &){
  if(!media_seeking)media_bar_now(t);
}
inline void media_bar_track_paint(lv_obj_t *track,const Tile &,const CardPart &){
  set_color(track,LV_STYLE_BG_COLOR,theme::rgb(theme::mix(media_ink(),media_face.ground,70)));
}
// What decides the media card's parts: whether the player can be used, is at rest or off, the keys it has, the room the
// times need, the speakers and inputs. The words, play or pause, the bar and its times, mute, shuffle, repeat, the
// volume, the cover and the card's colour are painted, so a new track paints the card and never builds it again
// (firmware 0.52.0, GitHub #177).
inline uint32_t media_card_shape(const Tile &t){
  Fingerprint f;
  auto add=[&](const std::string &text){f.add(text);f.write('|');};
  const auto &x=t.extra();
  add(t.entity);f.write(media_usable(t));f.write(media_at_rest(t));f.write(media_off(t));
  add(std::to_string(t.supported));add(std::to_string(x.media_features));
  // The times beside the bar take more room for a track of an hour or more.
  add(std::to_string(media_metrics(ui::large(),x.media_duration).times_w()));
  add(std::to_string(x.media_library&&media_library::available()));add(std::to_string(x.media_inputs.size()));
  add(x.media_source);add(std::to_string(x.media_sources.size()));add(std::to_string(x.assumed));
  // Whether shuffle, repeat and the volume row are there at all.
  f.write(x.media_shuffle>=0);f.write(!x.media_repeat.empty());f.write(std::isfinite(t.volume));
  // Volume down works while muted on a player that cannot set its volume: then muting changes what the keys can do.
  if(!(t.supported&(tile_controls::feature::MEDIA_VOLUME_SET|tile_controls::feature::MEDIA_VOLUME_STEP)))f.write(t.muted);
  add(std::to_string(camera_supported()));
  return f.value;
}
inline void render_media_detail(Tile &t,unsigned index,bool large,int width,int height,int top){
  using namespace media_card;
  using namespace tile_controls;
  const auto &x=t.extra();
  const Metrics m=media_metrics(large,x.media_duration);
  // The volume row ends with the keys of what the player has besides: its inputs, and its library outermost.
  const bool library=x.media_library&&media_library::available(),inputs=!x.media_inputs.empty();
  const Layout l=layout(m,width,std::max(60,height-top-(ui::px(large?12:6))),library+inputs);
  auto at=[&](Rect r){r.y+=top;return r;};
  const bool usable=fresh()&&t.available();
  const uint32_t f=t.supported,had=f|x.media_features;auto can=[&](uint32_t bit){return usable&&(!f||(f&bit));};
  // A player at rest whose library opens, with nothing to play or pause (Spotify playing nowhere): the card says how
  // to start it, and its one key is the library.
  const bool rest=media_at_rest(t);
  // The card's colour and what it shows of its cover, worked out first in every paint (media_face_follow).
  media_art_rect=l.art.w?at(l.art):Rect{};media_art_size=l.art.w;media_detail_picture=nullptr;
  card_bind(detail_root,t,media_root_paint);
  card_bind(detail_backdrop,t,media_backdrop_paint);
  const uint32_t ink=media_ink(),soft=media_soft(media_face.ground);
  // The cover's square with the player's icon, and the cover over it once it is here. A board that draws no pictures
  // has neither (firmware 0.46.0): the layout gives the player that room.
  if(l.art.w){
    auto *frame=card_bind(media_box(detail_root,nullptr,media_art_rect,ink,l.art_radius),t,media_frame_paint);
    auto *icon=lv_label_create(frame);lv_obj_remove_flag(icon,LV_OBJ_FLAG_CLICKABLE);
    card_bind(icon,t,media_placeholder_paint,rest?std::string("\U000F04C7"):std::string());
#if LV_USE_IMAGE
    if(camera_supported()){
      media_detail_picture=lv_image_create(detail_root);lv_obj_remove_flag(media_detail_picture,LV_OBJ_FLAG_CLICKABLE);
      lv_obj_add_flag(media_detail_picture,LV_OBJ_FLAG_HIDDEN);
      card_bind(media_detail_picture,t,media_picture_paint);
    }
#endif
  }
  // Title, artist · album.
  const lv_font_t *title_font=watch_font?watch_font:detail_font,*artist_font=control_font?control_font:detail_font,*small=small_font?small_font:detail_font;
  const lv_text_align_t align=l.wide?LV_TEXT_ALIGN_LEFT:LV_TEXT_ALIGN_CENTER;
  // A title or artist line wider than the card rolls by, round and round (firmware 0.2.77+); a shorter one stands still.
  marquee(card_bind(detail_text(detail_root,"",l.title.x,l.title.y+top,l.title.w,title_font,align,ink),t,media_title_paint));
  if(l.artist)marquee(card_bind(detail_text(detail_root,"",l.artist_line.x,l.artist_line.y+top,l.artist_line.w,artist_font,align,soft),t,media_artist_paint));
  // The progress bar, under the words wherever the keys are: at nought with 0:00 at both ends without a track or a
  // length (a stream, the moment between two tracks), so the card keeps its shape while a player changes tracks
  // (firmware 0.52.0; it went and came back before, GitHub #177). The fill runs while the track plays. Where the player
  // seeks (firmware 0.24.0+) the bar has a knob, and a finger on it moves the track.
  const bool keyed=!rest&&!(usable&&media_off(t));
  media_progress_fill=nullptr;media_elapsed_label=nullptr;media_total_label=nullptr;media_knob=nullptr;media_bar_width=l.bar.w;media_bar_x=l.bar.x;
  if(keyed){
    const bool seek=can(feature::MEDIA_SEEK);
    if(seek){
      auto *area=lv_obj_create(detail_root);lv_obj_remove_style_all(area);
      lv_obj_set_pos(area,l.seek.x,l.seek.y+top);lv_obj_set_size(area,l.seek.w,l.seek.h);
      lv_obj_add_flag(area,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(area,LV_OBJ_FLAG_SCROLLABLE);
      lv_obj_remove_flag(area,LV_OBJ_FLAG_GESTURE_BUBBLE);
      overlay_card::touchable(area,l.seek.h);
      lv_obj_add_event_cb(area,media_seek_event,LV_EVENT_ALL,nullptr);
    }
    card_bind(media_box(detail_root,nullptr,at(l.bar),ink,LV_RADIUS_CIRCLE),t,media_bar_track_paint);
    Rect fill=at(l.bar);fill.w=l.bar.h;
    media_progress_fill=media_box(detail_root,nullptr,fill,ink,LV_RADIUS_CIRCLE);
    if(seek){
      media_knob_size=m.seek_knob_h();
      media_knob=media_box(detail_root,nullptr,Rect{fill.right()-media_knob_size/2,fill.cy()-media_knob_size/2,media_knob_size,media_knob_size},ink,LV_RADIUS_CIRCLE);
    }
    if(l.times){
      media_elapsed_label=detail_text(detail_root,"",l.elapsed.x,l.elapsed.y+top,l.elapsed.w,small,LV_TEXT_ALIGN_LEFT,soft);
      media_total_label=detail_text(detail_root,"",l.total.x,l.total.y+top,l.total.w,small,LV_TEXT_ALIGN_RIGHT,soft);
    }
    // The fill, the knob and both times paint as one (media_bar_now), here and from the second's tick.
    card_bind(media_progress_fill,t,media_bar_paint);
  }
  // The keys: previous, play or pause in white, next; shuffle and repeat at the ends where the row has room; under them
  // the volume row. An off player shows one power key instead, and no volume: it reports none. A player at rest with a
  // library shows the Library key.
  auto cb=[](lv_event_t *e){detail_command((intptr_t)lv_event_get_user_data(e));};
  const lv_font_t *key_font=mini_icon_font?mini_icon_font:detail_font;
  const uint32_t g=media_face.ground;
  std::vector<lv_obj_t *> keys;
  if(rest){
    // Where the keys would be: under the words on a tall card, in the column beside the cover on a wide one.
    const int w=std::min(std::max(l.next.right()-l.prev.x,ui::px(large?200:120)),l.title.w);
    auto *start=detail_button(tr(txt::media_library),l.play.cx()-w/2,l.play.y+top,w,l.play.h,27);
    lv_obj_set_style_radius(start,LV_RADIUS_CIRCLE,0);
    set_color(start,LV_STYLE_BG_COLOR,theme::rgb(ink));
    if(auto *words=lv_obj_get_child(start,0)){
      if(control_font){set_font(words,control_font);lv_obj_set_height(words,lv_font_get_line_height(control_font));}
      lv_obj_center(words);
    }
    card_bind(start,t,media_start_paint);
  }else if(usable && media_off(t)){
    if(can(feature::MEDIA_TURN_ON)){keys.push_back(media_key(detail_root,nullptr,at(l.play),glyph::STANDBY,tile_icon_font(),true,false,true,cb,(void*)(intptr_t)24));card_bind(keys.back(),t,media_primary_paint);}
  }else{
    keys={media_key(detail_root,nullptr,at(l.prev),glyph::PREVIOUS,key_font,false,false,can(feature::MEDIA_PREVIOUS),cb,(void*)(intptr_t)21),
          media_key(detail_root,nullptr,at(l.play),media_card::playing(t.state)?glyph::PAUSE:glyph::PLAY,tile_icon_font(),true,false,can(feature::MEDIA_PLAY|feature::MEDIA_PAUSE),cb,(void*)(intptr_t)20),
          media_key(detail_root,nullptr,at(l.next),glyph::NEXT,key_font,false,false,can(feature::MEDIA_NEXT),cb,(void*)(intptr_t)22)};
    media_dark_key(keys[0],false,false,g);media_dark_key(keys[2],false,false,g);
    card_bind(keys[1],t,media_play_paint);
    // Shuffle on is the accent with a dot under it, as on a phone; repeat all and one the accent, off a faded white.
    if(l.sides && x.media_shuffle>=0 && (had&feature::MEDIA_SHUFFLE)){
      keys.push_back(media_key(detail_root,nullptr,at(l.shuffle),"\U000F049F",key_font,false,true,can(feature::MEDIA_SHUFFLE),cb,(void*)(intptr_t)25));
      media_dark_key(keys.back(),false,true,g,soft);
      card_bind(keys.back(),t,media_shuffle_paint);
      const int d=ui::px(large?5:4);
      card_bind(media_box(detail_root,nullptr,Rect{at(l.shuffle).cx()-d/2,at(l.shuffle).bottom()+ui::px(2),d,d},media_accent(),LV_RADIUS_CIRCLE),t,media_shuffle_dot_paint);
    }
    if(l.sides && !x.media_repeat.empty() && (had&feature::MEDIA_REPEAT)){
      keys.push_back(media_key(detail_root,nullptr,at(l.repeat),x.media_repeat=="one"?"\U000F0458":"\U000F0456",key_font,false,true,can(feature::MEDIA_REPEAT),cb,(void*)(intptr_t)26));
      media_dark_key(keys.back(),false,true,g,soft);
      card_bind(keys.back(),t,media_repeat_paint);
    }
    if(std::isfinite(t.volume))media_volume_row(detail_root,nullptr,at(l.minus),at(l.volume),at(l.plus),t,large,usable,(void*)(uintptr_t)index,true,key_font);
  }
  // The player's own keys at the right end of the volume row, whatever it plays: the inputs (firmware 0.26.0+, Home
  // Assistant's source of a player whose sources are inputs, a Sonos's TV input or a TV's ports, with its icon) and the
  // library (firmware 0.24.0+).
  media_library_key=media_input_key=nullptr;
  int end=0;
  for(int cmd:{27,29}){
    if(cmd==27?!library:!inputs)continue;
    auto *key=media_key(detail_root,nullptr,at(l.ends[end++]),cmd==27?"\U000F0CB8":"\U000F0206",key_font,false,false,true,cb,(void*)(intptr_t)cmd);
    media_dark_key(key,false,false,g);
    (cmd==27?media_library_key:media_input_key)=key;
  }
  // Only the keys the player supports join the card's actions: tick() enables those again after a wait, and a key
  // the player lacks stays faded.
  for(auto *k:keys)if(!lv_obj_has_state(k,LV_STATE_DISABLED) && detail_action_count<32)detail_actions[detail_action_count++]=k;
  // From here on the card paints itself: a new track, its cover and its colour too.
  card_shaped(t,media_card_shape);
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
