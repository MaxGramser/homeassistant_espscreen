// The lock: its dialog and the tile that locks with one tap.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the rules themselves, which are plain C++ without LVGL in lock_panel.h.
// What proves it: tests/test_lock_panel.cpp, tests/test_lock_panel.py.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// ---- Lock (firmware 0.5.0+): Home Assistant's lock dialog in this look, and a tile that locks with one tap ----
// lock_panel.h decides (what may happen, which keys, when a code is asked for); this draws it. A tap on the tile locks
// what is not locked at once. A locked lock asks first: the tile turns orange, and its circle
// beats and says "Confirm", and a second tap within five seconds unlocks. The card (hold the tile) has the key that changes the state,
// both keys while the lock is jammed, and Open door where the lock has one; Unlock and Open door ask for a second tap
// on the same key. A lock with a code opens the alarm panel's keypad instead, with its lock after wrong codes: typing
// the code is the second tap. The animations are the alarm panel's: a heartbeat while the lock moves or waits for its
// second tap, a ring going round while it moves, and a ring that closes round the lock when it locks.
inline constexpr int LOCK_KEY_FIRST=700;   // 700 lock, 701 unlock, 702 open
// The "tap again" a tile waits for lives on the tile (Tile::ask_act, firmware 0.16.0+); one tile waits at a time, and
// `lock_waits` says whether any does, so lock_tick has nothing to look at otherwise.
inline bool lock_waits=false;
inline lock_panel::Confirm lock_ask_of(const Tile &t){
  lock_panel::Confirm c;if(t.ask_act>=0){c.act=(lock_panel::Act)t.ask_act;c.since=t.ask_since;}return c;
}
inline void lock_keep_ask(Tile &t,const lock_panel::Confirm &c){t.ask_act=c.act==lock_panel::NONE?-1:(int8_t)c.act;t.ask_since=c.since;}
inline lv_obj_t *lock_ring=nullptr;
inline lock_panel::Lock lock_of(const Tile &t){
  lock_panel::Lock l;l.state=t.state;l.supported=t.supported;l.assumed=t.extra().assumed;l.available=t.available()&&fresh();return l;
}
inline lock_panel::Guard lock_guard(const Tile &t){return lock_panel::guard_of(t.guard);}
inline bool lock_noting(const Tile &t){return t.noted_at&&esphome::millis()-t.noted_at<3000;}
inline bool lock_asking(const Tile &t,bool card,lock_panel::Act a=lock_panel::NONE){
  if(t.ask_act<0||t.ask_card!=card)return false;
  const uint32_t now=esphome::millis();const auto c=lock_ask_of(t);
  return a==lock_panel::NONE?c.any(now):c.waiting(a,now);
}
// Ends the "tap again" of every tile but `keep`: each shows its state again at once, on its tile or its open card.
inline void lock_end_asks(size_t keep=SIZE_MAX){
  for(size_t i=0;i<model.count;++i){
    auto &t=model.tiles[i];
    if(i==keep||t.ask_act<0)continue;
    t.ask_act=-1;
    if(!t.ask_card)refresh_tile(i,redraw_log::TileWhy::tick);
    else if(detail_index==i&&detail_root&&!lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN))redraw_detail();
  }
}
inline const char *lock_state_text(const std::string &state){
  using namespace screen_text;
  if(state=="locked")return tr(txt::ha_lock_locked);
  if(state=="unlocked")return tr(txt::ha_lock_unlocked);
  if(state=="locking")return tr(txt::ha_lock_locking);
  if(state=="unlocking")return tr(txt::ha_lock_unlocking);
  if(state=="open")return tr(txt::ha_lock_open);
  if(state=="opening")return tr(txt::ha_lock_opening);
  if(state=="jammed")return tr(txt::ha_lock_jammed);
  return state.c_str();
}
// A key's word, as Home Assistant's dialog names it; the keypad's title too.
inline const char *lock_action_text(unsigned act){
  if(act==lock_panel::LOCK)return tr(txt::ha_lock_action_lock);
  if(act==lock_panel::UNLOCK)return tr(txt::ha_lock_action_unlock);
  return tr(txt::ha_lock_action_open_door);
}
// The tile's icon: the open lock while it waits for the second tap that unlocks it. A chosen icon stays.
inline const char *lock_icon(const Tile &t){return lock_panel::icon(t.state);}
// The line under the name: the second tap it waits for, a lock-only tile's word, or Home Assistant's word for the
// state, and on the card who changed it last.
inline std::string lock_status(const Tile &t,bool card){
  if(!t.available())return tr(txt::ha_unavailable);
  if(!card&&lock_asking(t,false))return tr(txt::lock_confirm);
  if(!card&&lock_noting(t))return tr(txt::lock_lock_only);
  std::string text=!t.extra().state_word.empty()?t.extra().state_word:std::string(lock_state_text(t.state));
  if(card&&!t.extra().changed_by.empty()&&!lock_panel::moving(t.state))text+=" · "+t.extra().changed_by;
  return text;
}
inline std::string lock_card_line(const Tile &t){
  if(alarm_card_note&&esphome::millis()-alarm_card_note_at<6000)return tr(alarm_card_note);
  return lock_status(t,true);
}
// The tile's colour: orange while it waits for the second tap, else Home Assistant's for the state.
inline uint32_t lock_accent(const Tile &t){
  return lock_asking(t,false)?lock_panel::ORANGE:lock_panel::color(t.state);
}
// What a tap or a key asks for: lock, unlock or open. A code opens the keypad; Unlock and Open door wait for a second
// tap on the same tile or key; the rest goes to Home Assistant at once.
inline void lock_do(unsigned index,lock_panel::Act act,bool card){
  using namespace lock_panel;
  if(index>=model.count)return;
  auto &t=model.tiles[index];
  const uint32_t now=esphome::millis();
  if(!can(lock_of(t),act,lock_guard(t))||t.waiting(now))return;
  const auto &x=t.extra();
  if(needs_code(x.code_format,x.code_saved)){
    t.ask_act=-1;
    if(!code_typable(x.code_format)){alarm_card_note=txt::alarm_letters;alarm_card_note_at=now;}
    else{alarm_wipe(alarm_pad.code);alarm_pad.open=true;alarm_pad.mode=act;alarm_pad.note=0;alarm_pad.entity=t.entity;}
    if(card)redraw_detail();else{active_index=(int)index;show_detail(index);}
    return;
  }
  if(confirms(act)){
    // One tile waits at a time: a first tap here ends another tile's wait, and the card's wait is not the tile's.
    lock_end_asks(index);
    if(t.ask_card!=card)t.ask_act=-1;
    t.ask_card=card;
    auto c=lock_ask_of(t);
    const bool second=c.press(act,now);
    lock_keep_ask(t,c);
    if(!second){
      lock_waits=true;
      ESP_LOGI("lock","%s: tap again to %s",t.entity.c_str(),act==OPEN?"open":"unlock");
      if(card)redraw_detail();else refresh_tile(index,redraw_log::TileWhy::finger);
      return;
    }
  }
  t.ask_act=-1;
  alarm_attempt.begin(act,false,now);alarm_attempt_entity=t.entity;
  action(service(act),t.entity);
  if(card)redraw_detail();else refresh_tile(index,redraw_log::TileWhy::finger);
}
// A finger on the tile (tile_controls::TapRoute::LOCK).
inline void lock_tap(unsigned index){
  if(index>=model.count)return;
  auto &t=model.tiles[index];
  const auto act=lock_panel::tap(lock_of(t),lock_guard(t));
  if(act==lock_panel::NONE){
    if(t.state=="locked"&&lock_guard(t)==lock_panel::Guard::LOCK_ONLY){t.noted_at=std::max<uint32_t>(1,esphome::millis());refresh_tile(index,redraw_log::TileWhy::finger);}
    return;
  }
  lock_do(index,act,false);
}
// The ring round the card's lock: a short arc going round while it moves, and a ring closing when it locks.
inline void lock_card_ring(const Tile &t,int cx,int cy,int size,int width){
  lock_ring=nullptr;
#if LV_USE_ARC
  const bool closing=t.state=="locked"&&alarm_arrived(t);
  if(!lock_panel::moving(t.state)&&!closing)return;
  const uint32_t colour=theme::state(lock_panel::color(t.state));
  auto *arc=lv_arc_create(detail_root);
  lv_obj_remove_style_all(arc);lv_obj_set_size(arc,size,size);lv_obj_set_pos(arc,cx-size/2,cy-size/2);
  lv_obj_remove_flag(arc,LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_arc_width(arc,width,LV_PART_MAIN);lv_obj_set_style_arc_width(arc,width,LV_PART_INDICATOR);
  lv_obj_set_style_arc_rounded(arc,true,LV_PART_INDICATOR);
  lv_obj_set_style_arc_color(arc,lv_color_hex(theme::tint(colour,38)),LV_PART_MAIN);lv_obj_set_style_arc_opa(arc,closing?LV_OPA_TRANSP:LV_OPA_COVER,LV_PART_MAIN);
  lv_obj_set_style_arc_color(arc,lv_color_hex(colour),LV_PART_INDICATOR);lv_obj_set_style_arc_opa(arc,LV_OPA_COVER,LV_PART_INDICATOR);
  lv_arc_set_rotation(arc,270);lv_arc_set_bg_angles(arc,0,360);
  lv_anim_t a;lv_anim_init(&a);lv_anim_set_var(&a,arc);
  if(closing){
    lv_arc_set_angles(arc,0,0);
    lv_anim_set_values(&a,0,360);lv_anim_set_duration(&a,500);lv_anim_set_exec_cb(&a,alarm_ring_close);lv_anim_set_path_cb(&a,lv_anim_path_ease_out);
    lv_anim_set_completed_cb(&a,[](lv_anim_t *done){lv_obj_add_flag(static_cast<lv_obj_t *>(done->var),LV_OBJ_FLAG_HIDDEN);});
    lv_anim_start(&a);
    return;
  }
  lv_arc_set_angles(arc,0,70);
  lv_anim_set_values(&a,270,630);lv_anim_set_duration(&a,1600);lv_anim_set_exec_cb(&a,alarm_ring_turn);
  lv_anim_set_repeat_count(&a,LV_ANIM_REPEAT_INFINITE);lv_anim_start(&a);
  lock_ring=arc;
#else
  (void)t;(void)cx;(void)cy;(void)size;(void)width;
#endif
}
// The lock and alarm cards (docs/CARD_PARTS.md, "Security cards"): every state, every step of a code, every attempt,
// a second tap asked for and a lockout are their shape, so each of those builds the card as it always did, with its
// animations. Only their status line paints itself (who locked it, a note that runs out).
inline uint32_t security_card_shape(const Tile &t){
  Fingerprint f;auto add=[&](const std::string &text){f.add(text);f.write('|');};
  auto number=[&](uint32_t v){add(std::to_string(v));};
  const uint32_t now=esphome::millis();
  const auto &x=t.extra();
  const auto codes=alarm_codes(t);
  add(t.entity);add(t.state);add(t.icon);add(t.guard);number(t.send_after);number(t.supported);f.write(t.available());f.write(fresh());
  add(codes.format);f.write(codes.arm_required);f.write(codes.saved);f.write(x.assumed);number(x.alarm_end);number(x.alarm_delay);
  f.write(alarm_pad.open);number(alarm_pad.mode);number(alarm_pad.code.size());add(alarm_pad.entity);
  number(alarm_pad.note);f.write(alarm_pad.note&&now-alarm_pad.note_at<4000);number(alarm_pad.shake_at);
  f.write(alarm_attempt.active);add(alarm_attempt_entity);f.write(alarm_lock.locked(now));number(alarm_lock.remaining_s(now));
  number(alarm_left(t));f.write(alarm_arrived(t));f.write(awake());
  for(auto act:{lock_panel::LOCK,lock_panel::UNLOCK,lock_panel::OPEN})f.write(lock_asking(t,true,act));
  f.write(lock_asking(t,false));f.write(lock_noting(t));number((uint32_t)(int32_t)t.ask_act);f.write(t.ask_card);number(t.ask_since);
  f.write(t.loading(now));f.write(t.refused_at!=0);
  return f.value;
}
inline void render_lock_detail(Tile &t,bool large,int width,int height,lv_obj_t *heading){
  using namespace alarm_panel;
  detail_placed=true;
  if(alarm_pad.entity!=t.entity){alarm_close_pad();alarm_pad.entity=t.entity;}
  if(alarm_pad.open&&!t.available())alarm_close_pad();
  alarm_red=false;
  alarm_forget_widgets();lock_ring=nullptr;
  card_shaped(t,security_card_shape);
  const lv_font_t *text=large?detail_font:(control_font?control_font:detail_font);
  const lv_font_t *icons=tile_icon_font();
  const lv_font_t *mini=mini_icon_font?mini_icon_font:detail_font;
  Metrics m;m.large=large;m.touch=ui::touch_min();m.text_h=lv_font_get_line_height(text);
  m.icon_h=icons?lv_font_get_line_height(icons):m.text_h;m.side=overlay_card::pad();
  const int top=ui::px(large?80:50)+lv_font_get_line_height(detail_font)+m.gap(),bottom=height-ui::px(large?18:8);
  if(alarm_pad.open){
    // The keypad in the card's place, titled as the key that asked for it: Unlock, Lock, Open door.
    if(heading)label(heading,lock_action_text(alarm_pad.mode));
    render_code_pad(m,width,detail_bar::bottom()+m.gap(),height-m.gap(),text,icons,mini);
    return;
  }
  const auto lock=lock_of(t);
  const auto guard=lock_guard(t);
  const auto primary=lock_panel::primary(lock,guard);
  const auto keys=lock_panel::secondary(lock,guard);
  const bool available=t.available();
  const bool asking=lock_asking(t,true);
  // The lock's hero is its control, so it takes the height the alarm's shield leaves to its keys.
  m.hero_cap=ui::px(large?300:190);
  const auto l=card_layout(m,width,top,bottom,keys.count,false);
  detail_card(l.hero.x,l.hero.y,l.hero.w,l.hero.h);
  // The lock itself is the big key, as Apple's Home and Home Assistant's own lock dialog make the lock the control:
  // a round key in its state's colour, and under it the word of what a tap does (Lock, Unlock, Confirm).
  const int icon_h=m.icon_h,ring_w=ui::px(large?8:5),ring_gap=ui::px(large?8:5),word_h=m.text_h,inner=ui::px(large?10:6);
  const int room_h=l.hero.h-2*inner-word_h-ui::px(large?8:4);
  int d=std::min({room_h-2*(ring_w+ring_gap),l.hero.w*11/20,icon_h*4});
  d=std::max(d,std::max(icon_h+ui::px(8),m.least_key()));
  const int block=d+2*(ring_w+ring_gap)+ui::px(large?8:4)+word_h;
  const int cx=l.hero.cx(),cy=l.hero.y+(l.hero.h-block)/2+ring_w+ring_gap+d/2;
  const bool waits_open=lock_asking(t,true,lock_panel::OPEN);
  const uint32_t colour=asking&&!waits_open?lock_panel::ORANGE:lock_panel::color(t.state);
  auto *big=detail_button("",cx-d/2,cy-d/2,d,d,LOCK_KEY_FIRST+(int)(primary==lock_panel::NONE?lock_panel::LOCK:primary));
  lv_obj_set_style_radius(big,LV_RADIUS_CIRCLE,0);lv_obj_set_style_border_width(big,0,0);
  const uint32_t ground=available?theme::tint(theme::state(colour),38):theme::hex(theme::TRACK);
  lv_obj_set_style_bg_color(big,lv_color_hex(ground),0);
  lv_obj_set_style_bg_color(big,lv_color_hex(theme::pressed(ground)),LV_STATE_PRESSED);
  lv_obj_set_style_bg_color(big,lv_color_hex(ground),LV_STATE_DISABLED);lv_obj_set_style_bg_opa(big,LV_OPA_COVER,LV_STATE_DISABLED);
  if(icons){
    auto *face=lv_obj_get_child(big,0);
    const char *glyph=asking&&!waits_open?lock_panel::glyph::LOCK_OPEN:(t.icon.empty()?lock_panel::icon(t.state):t.icon.c_str());
    // The large icon face where the key has room for it and it carries the glyph.
    const lv_font_t *face_font=big_icon_font&&font_has(big_icon_font,glyph)&&lv_font_get_line_height(big_icon_font)<=d*3/5?big_icon_font:icons;
    lv_obj_set_style_text_font(face,face_font,0);lv_label_set_text(face,glyph);
    lv_obj_set_style_text_color(face,lv_color_hex(available?theme::icon(theme::state(colour)):theme::hex(theme::OFF)),0);
    lv_obj_set_style_text_color(face,lv_color_hex(available?theme::icon(theme::state(colour)):theme::hex(theme::OFF)),LV_STATE_DISABLED);
    lv_obj_set_size(face,LV_SIZE_CONTENT,LV_SIZE_CONTENT);lv_obj_center(face);
  }
  if(primary==lock_panel::NONE||!lock_panel::can(lock,primary,guard))lv_obj_add_state(big,LV_STATE_DISABLED);
  // The word under the key: what a tap does, "Confirm" in orange while it waits, the state while it moves, and why a
  // lock-only tile's locked lock does nothing.
  std::string word;uint32_t ink=theme::hex(theme::INK);
  if(!available)word=tr(txt::ha_unavailable);
  else if(asking&&!waits_open){word=tr(txt::lock_confirm);ink=theme::foreground(lock_panel::ORANGE);}
  else if(lock_panel::moving(t.state))word=lock_state_text(t.state);
  else if(primary==lock_panel::NONE&&guard==lock_panel::Guard::LOCK_ONLY)word=tr(txt::lock_lock_only);
  else if(primary!=lock_panel::NONE)word=lock_action_text(primary);
  const int word_y=cy+d/2+ring_w+ring_gap+ui::px(large?8:4);
  auto *caption=detail_text(detail_root,word,l.hero.x+inner,word_y,l.hero.w-2*inner,text,LV_TEXT_ALIGN_CENTER,ink);
  lv_label_set_long_mode(caption,LV_LABEL_LONG_DOT);
  lock_card_ring(t,cx,cy,d+2*(ring_w+ring_gap),ring_w);
  if(awake()&&available){
    if(asking&&!waits_open)alarm_beat(big,theme::state(colour),1000,ui::px(large?28:14),false);
    else if(lock_panel::moving(t.state))alarm_beat(big,theme::state(colour),1600,ui::px(large?28:14),false);
    else if(alarm_arrived(t)){
      if(t.state=="locked")alarm_beat(big,theme::state(colour),600,ui::px(large?28:14),true);
      alarm_spring(big,t.state=="locked"?450:0);
    }
  }
  const lv_font_t *key_icons=icons&&lv_font_get_line_height(icons)<=(l.key_count?l.keys[0].h:0)-ui::px(10)?icons:mini;
  for(unsigned i=0;i<l.key_count;++i){
    const auto act=keys.act[i];
    const Rect &r=l.keys[i];
    const bool waiting=lock_asking(t,true,act);
    auto *key=detail_button("",r.x,r.y,r.w,r.h,LOCK_KEY_FIRST+(int)act);
    lv_obj_set_style_radius(key,r.h/2,0);
    // A key that waits for its second tap turns orange and asks, as Home Assistant's Open door key does.
    const uint32_t ask=theme::state(lock_panel::ORANGE);
    lv_obj_set_style_bg_color(key,waiting?lv_color_hex(ask):theme::color(theme::CARD),0);
    lv_obj_set_style_bg_color(key,waiting?lv_color_hex(theme::pressed(ask)):theme::color(theme::KEY),LV_STATE_PRESSED);
    lv_obj_set_style_border_width(key,waiting?0:1,0);lv_obj_set_style_border_color(key,theme::color(theme::LINE),0);
    const char *glyph=act==lock_panel::UNLOCK?lock_panel::glyph::LOCK_OPEN:lock_panel::glyph::DOOR_OPEN;
    const std::string label_text=waiting?(act==lock_panel::OPEN?tr(txt::ha_lock_action_open_door_confirm):tr(txt::lock_really_unlock)):lock_action_text(act);
    // Neutral keys, as Home Assistant's dialog draws them: the colour belongs to the lock, not to what a key does.
    alarm_key_face(key,glyph,label_text,key_icons,text,waiting?theme::color(theme::ON_ACCENT):theme::color(theme::INK),r.w,r.h);
    if(!lock_panel::can(lock,act,guard))lv_obj_add_state(key,LV_STATE_DISABLED);
  }
}
// A new state of a lock arrived (page_receiver): an attempt may be settled by it, and a "tap again" for it ends.
inline void lock_state_arrived(unsigned index,const std::string &before){
  if(index>=model.count)return;
  auto &t=model.tiles[index];
  if(alarm_attempt.active&&t.entity==alarm_attempt_entity)
    alarm_settled(alarm_attempt.settle_if(lock_panel::reached(t.state,(lock_panel::Act)alarm_attempt.mode),esphome::millis()),true);
  if(before!=t.state)t.ask_act=-1;
}
// Every tick (tick()): a "tap again" that ran out, or a screen that went to sleep, puts the tile or the card back.
inline void lock_tick(){
  if(!lock_waits)return;
  const uint32_t now=esphome::millis();
  bool waiting=false;
  for(size_t i=0;i<model.count;++i){
    auto &t=model.tiles[i];
    if(t.ask_act<0)continue;
    if(awake()&&lock_ask_of(t).any(now)){waiting=true;continue;}
    t.ask_act=-1;
    if(!t.ask_card)refresh_tile(i,redraw_log::TileWhy::tick);
    else if(detail_index==i&&detail_root&&!lv_obj_has_flag(detail_root,LV_OBJ_FLAG_HIDDEN))redraw_detail();
  }
  lock_waits=waiting;
}
inline void lock_command(int cmd){
  if(detail_index>=model.count)return;
  auto &t=model.tiles[detail_index];
  if(t.domain()!="lock"||!fresh()||!t.available())return;
  if(!allowed(esphome::millis(),300+cmd,"lock:"+t.entity))return;
  const int act=cmd-LOCK_KEY_FIRST;
  if(act<0||act>=(int)lock_panel::NONE)return;
  lock_do((unsigned)detail_index,(lock_panel::Act)act,true);
}
inline AlarmLook lock_look(const Tile &t){
  if(!t.available())return LOOK_NONE;
  if(lock_asking(t,false))return LOOK_TRIGGERED;
  if(lock_panel::moving(t.state))return LOOK_ARMING;
  return LOOK_NONE;
}
// A card that closes forgets the second tap its keys waited for.
inline void lock_card_closed(){if(detail_index<model.count&&model.tiles[detail_index].ask_card)model.tiles[detail_index].ask_act=-1;}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
