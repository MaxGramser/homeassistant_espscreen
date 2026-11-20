// The alarm panel, its code pad and its animations.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the rules themselves, which are plain C++ without LVGL in alarm_panel.h.
// What proves it: tests/test_alarm_panel.cpp, tests/test_alarm_panel.py.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// ---- Alarm panel (firmware 0.3.3+): Home Assistant's alarm dialog and its code dialog in this look ----
// alarm_panel.h decides (the modes, when a code is asked for, the lock after wrong codes, where the parts go); this
// draws it. The card: the shield on a white card with a key per mode, or one big Disarm key while the alarm counts
// down or goes off. A mode that needs a code opens the keypad in the card's place: the dots, a line of words and
// twelve keys. The code goes to Home Assistant with the action and is wiped here as soon as it is sent. The screen
// never logs it, stores it or puts it in an event.
inline constexpr int ALARM_MODE_FIRST=600,ALARM_DIGIT_FIRST=610,ALARM_CLEAR=620,ALARM_OK=621;
// What the keypad of the open card holds. It lives outside the card's widgets, so a new state (the card is drawn
// again) keeps what was typed.
struct AlarmPad {
  bool open=false;
  unsigned mode=0;
  std::string code, entity;
  uint16_t note=0;      // a line in place of "Enter code" (Wrong code, Nothing changed), 0 for none
  uint32_t note_at=0, shake_at=0;
};
inline AlarmPad alarm_pad;
inline alarm_panel::Attempt alarm_attempt;
inline std::string alarm_attempt_entity;
inline alarm_panel::Lockout alarm_lock;
inline uint16_t alarm_card_note=0;   // a line in place of the card's state (a code with letters)
inline uint32_t alarm_card_note_at=0;
inline esphome::ESPPreferenceObject alarm_preference;
struct AlarmSaved { uint32_t failures=0, seconds=0; };
inline lv_obj_t *alarm_dots=nullptr,*alarm_line=nullptr,*alarm_ring=nullptr,*alarm_keys[12]{};
inline unsigned alarm_dots_shown=0;
// Set by packages/core.yaml: wake the screen as a touch does (the backlight, the dim overlay, open cards closed).
inline std::function<void()> alarm_wake;

// The card is about to be drawn again from nothing: what pointed into the last one points nowhere now.
inline void alarm_forget_widgets(){alarm_dots=alarm_line=alarm_ring=nullptr;for(auto *&k:alarm_keys)k=nullptr;}
inline alarm_panel::Codes alarm_codes(const Tile &t){
  alarm_panel::Codes c;c.format=t.extra().code_format;c.arm_required=!t.extra().arm_code_free;c.saved=t.extra().code_saved;return c;
}
inline bool alarm_keypad_first(const Tile &t){
  return t.domain()=="alarm_control_panel"&&t.available()&&alarm_panel::keypad_first(t.state,alarm_codes(t));
}
inline const char *alarm_state_text(const std::string &state){
  using namespace screen_text;
  if(state=="disarmed")return tr(txt::ha_alarm_disarmed);
  if(state=="armed_home")return tr(txt::ha_alarm_armed_home);
  if(state=="armed_away")return tr(txt::ha_alarm_armed_away);
  if(state=="armed_night")return tr(txt::ha_alarm_armed_night);
  if(state=="armed_vacation")return tr(txt::ha_alarm_armed_vacation);
  if(state=="armed_custom_bypass")return tr(txt::ha_alarm_armed_custom_bypass);
  if(state=="pending")return tr(txt::ha_alarm_pending);
  if(state=="arming")return tr(txt::ha_alarm_arming);
  if(state=="disarming")return tr(txt::ha_alarm_disarming);
  if(state=="triggered")return tr(txt::ha_alarm_triggered);
  return state.c_str();
}
inline const char *alarm_mode_text(unsigned mode){
  static const uint16_t words[]={txt::ha_alarm_mode_armed_home,txt::ha_alarm_mode_armed_away,txt::ha_alarm_mode_armed_night,
                                 txt::ha_alarm_mode_armed_vacation,txt::ha_alarm_mode_armed_custom_bypass,txt::ha_alarm_mode_disarmed};
  return tr(words[mode<alarm_panel::MODE_COUNT?mode:alarm_panel::DISARM]);
}
// The keypad's title, as Home Assistant's code dialog names it: Disarm, or the mode that arms.
inline const char *alarm_action_text(unsigned mode){
  static const uint16_t words[]={txt::ha_alarm_action_arm_home,txt::ha_alarm_action_arm_away,txt::ha_alarm_action_arm_night,
                                 txt::ha_alarm_action_arm_vacation,txt::ha_alarm_action_arm_custom_bypass,txt::ha_alarm_action_disarm};
  return tr(words[mode<alarm_panel::MODE_COUNT?mode:alarm_panel::DISARM]);
}
// Seconds left of the exit or entry delay, where the integration says how long it is.
inline uint32_t alarm_left(const Tile &t){
  return (t.state=="arming"||t.state=="pending")?alarm_panel::seconds_left(t.extra().alarm_end,now_epoch()):0;
}
// The line under the name on the tile and on the card: Home Assistant's word, the time the delay has left, and on
// the card who changed it last where Home Assistant says so.
inline std::string alarm_status(const Tile &t,bool card){
  if(!t.available())return tr(txt::ha_unavailable);
  std::string text=!t.extra().state_word.empty()?t.extra().state_word:std::string(alarm_state_text(t.state));
  if(const uint32_t left=alarm_left(t))text+=" · "+countdown(left);
  if(card&&!t.extra().changed_by.empty()&&!alarm_panel::urgent(t.state))text+=" · "+t.extra().changed_by;
  return text;
}
// The card's line under the name: the state, or for a moment why a mode did nothing (a code with letters).
inline std::string alarm_card_line(const Tile &t){
  if(alarm_card_note&&esphome::millis()-alarm_card_note_at<6000)return tr(alarm_card_note);
  return alarm_status(t,true);
}
inline bool alarm_pad_open(){return alarm_pad.open&&detail_index<model.count&&model.tiles[detail_index].entity==alarm_pad.entity;}
// The open card's send_after (the tile's option): how many digits send the code by themselves, 0 for the OK key.
// Only an alarm panel's tile has it; a lock's keypad keeps its OK key.
inline unsigned alarm_send_after(){
  if(detail_index>=model.count)return 0;
  const auto &t=model.tiles[detail_index];
  return t.domain()=="alarm_control_panel"?alarm_panel::send_after(t.send_after):0;
}
// The keypad stands on red while the panel goes off or counts someone in (alarm_panel::keypad_first): set by the card
// as it is drawn.
inline bool alarm_red=false;
// Whether the card of this panel is its keypad at once, and back closes the card rather than going to the card.
inline bool alarm_keypad_first(const Tile &t);
// A code leaves no copy behind: the bytes are overwritten before the string lets them go.
inline void alarm_wipe(std::string &code){for(char &c:code)c='\0';code.clear();}
inline void alarm_close_pad(){alarm_wipe(alarm_pad.code);alarm_pad.open=false;alarm_pad.note=0;}
inline void alarm_save_lock(){
  AlarmSaved saved{alarm_lock.failures,alarm_lock.remaining_s(esphome::millis())};
  alarm_preference.save(&saved);
}
inline void alarm_load_lock(){
  alarm_preference=esphome::global_preferences->make_preference<AlarmSaved>(0x414C4D31);
  AlarmSaved saved;
  if(alarm_preference.load(&saved)&&saved.failures<1000)alarm_lock.resume(saved.failures,saved.seconds,esphome::millis());
}
// Home Assistant hears of every wrong code (an event, like the manual alarm's manual_alarm_bad_code_attempt), with
// the panel, how many in a row and how long the keypad is locked; never the code.
inline void alarm_refused_event(const std::string &entity,uint32_t locked){
  esphome::api::HomeassistantActionRequest request;
  // A lock's keypad has an event of its own (firmware 0.5.0+).
  request.service=api_text::of(entity.compare(0,5,"lock.")==0?"esphome.screen_lock_code_refused":"esphome.screen_alarm_code_refused");
  request.is_event=true;
  const std::string failures=std::to_string(alarm_lock.failures),seconds=std::to_string(locked);
  const std::string keys[]={"entity_id","failures","locked"},values[]={entity,failures,seconds};
  request.data.init(3);
  for(int i=0;i<3;++i){esphome::api::HomeassistantServiceMap entry;entry.key=api_text::of(keys[i]);entry.value=api_text::of(values[i]);request.data.push_back(entry);}
  esphome::api::global_api_server->send_homeassistant_action(request);
}
inline void redraw_detail();
// The end of an attempt with a code: accepted closes the keypad and opens the lock again; failed counts, may lock the
// keypad, tells Home Assistant and shakes the dots.
inline void alarm_settled(alarm_panel::Outcome outcome,bool silent){
  using alarm_panel::Outcome;
  if(outcome==Outcome::WAITING)return;
  const uint32_t now=esphome::millis();
  if(outcome==Outcome::ACCEPTED){
    if(alarm_attempt.with_code&&alarm_lock.failures){alarm_lock.success();alarm_save_lock();}
    if(alarm_pad.open)alarm_close_pad();
    ESP_LOGI(alarm_attempt_entity.compare(0,5,"lock.")==0?"lock":"alarm","%s accepted",alarm_attempt_entity.c_str());
  }else{
    if(!alarm_attempt.with_code)return;
    const uint32_t locked=alarm_lock.fail(now);
    alarm_save_lock();
    alarm_refused_event(alarm_attempt_entity,locked);
    alarm_pad.note=silent?txt::alarm_nothing_changed:txt::alarm_wrong_code;alarm_pad.note_at=now;alarm_pad.shake_at=now;
    ESP_LOGW(alarm_attempt_entity.compare(0,5,"lock.")==0?"lock":"alarm","%s: code not accepted (%s), %u in a row, keypad locked for %u s",alarm_attempt_entity.c_str(),
             silent?"ignored":"refused",(unsigned)alarm_lock.failures,(unsigned)locked);
  }
  redraw_detail();
}
// Home Assistant refused an action (watch_call): an attempt with a code on its way failed.
inline void alarm_refused(const std::string &entity){
  if(alarm_attempt.active&&entity==alarm_attempt_entity)alarm_settled(alarm_attempt.refused(),false);
}
// A mode key: straight to Home Assistant when no code is needed, else the keypad.
inline void alarm_choose(Tile &t,unsigned mode){
  using namespace alarm_panel;
  if(mode>=MODE_COUNT||t.state==MODES[mode].state)return;
  const Codes codes=alarm_codes(t);
  if(needs_code(codes,mode)){
    if(!code_typable(codes)){alarm_card_note=txt::alarm_letters;alarm_card_note_at=esphome::millis();redraw_detail();return;}
    alarm_wipe(alarm_pad.code);alarm_pad.open=true;alarm_pad.mode=mode;alarm_pad.note=0;alarm_pad.entity=t.entity;
    redraw_detail();
    return;
  }
  alarm_attempt.begin(mode,false,esphome::millis());alarm_attempt_entity=t.entity;
  action(MODES[mode].service,t.entity);
}
inline void alarm_send(Tile &t){
  using namespace alarm_panel;
  const uint32_t now=esphome::millis();
  if(alarm_pad.code.empty()||alarm_lock.locked(now)||alarm_attempt.active)return;
  alarm_attempt.begin(alarm_pad.mode,true,now);alarm_attempt_entity=t.entity;
  alarm_pad.note=0;
  // The one place the code leaves the screen: the action's `code`, as Home Assistant's own dialogs send it.
  action(t.domain()=="lock"?lock_panel::service((lock_panel::Act)alarm_pad.mode):MODES[alarm_pad.mode].service,t.entity,"code",alarm_pad.code);
  alarm_wipe(alarm_pad.code);
  redraw_detail();
}

// ---- The animations: they show what the alarm does, never how a card opens, and only inside the shield's circle ----
// A ring that grows out of the circle and fades (a heartbeat: slow while arming, fast while someone is inside, in Home
// Assistant's one-second rhythm while it goes off), a ring that closes round the shield when it arms, and a short
// spring of the circle when it arms or disarms. They run on the circle only, so the CYD redraws a small square.
enum AlarmLook : uint8_t { LOOK_NONE, LOOK_ARMING, LOOK_PENDING, LOOK_TRIGGERED };
inline AlarmLook alarm_look(const Tile &t){
  if(!t.available())return LOOK_NONE;
  if(t.state=="triggered")return LOOK_TRIGGERED;
  if(t.state=="pending")return LOOK_PENDING;
  if(t.state=="arming")return LOOK_ARMING;
  return LOOK_NONE;
}
inline void alarm_beat_exec(lv_anim_t *a,int32_t v){
  auto *o=static_cast<lv_obj_t *>(a->var);const int reach=(int)(intptr_t)lv_anim_get_user_data(a);
  lv_obj_set_style_outline_width(o,reach*v/255,0);
  lv_obj_set_style_outline_opa(o,(lv_opa_t)(150*(255-v)/255),0);
}
// The spring grows the circle by a few pixels on every side: transform_width and _height draw it bigger in place,
// without the layer a scale or a rotation would give it (tests/test_layer_free.py).
inline void alarm_spring_exec(void *o,int32_t v){
  auto *obj=static_cast<lv_obj_t *>(o);lv_obj_set_style_transform_width(obj,v,0);lv_obj_set_style_transform_height(obj,v,0);
}
inline void alarm_still(lv_obj_t *o){
  if(!o)return;
  lv_anim_delete(o,nullptr);
  lv_obj_set_style_outline_width(o,0,0);lv_obj_set_style_outline_opa(o,LV_OPA_TRANSP,0);
  lv_obj_set_style_transform_width(o,0,0);lv_obj_set_style_transform_height(o,0,0);
}
// A heartbeat of `period` ms, forever, or once.
inline void alarm_beat(lv_obj_t *o,uint32_t colour,uint32_t period,int reach,bool once){
  lv_obj_set_style_outline_color(o,lv_color_hex(colour),0);lv_obj_set_style_outline_pad(o,0,0);
  lv_anim_t a;lv_anim_init(&a);lv_anim_set_var(&a,o);lv_anim_set_values(&a,0,255);lv_anim_set_duration(&a,period);
  lv_anim_set_custom_exec_cb(&a,alarm_beat_exec);lv_anim_set_user_data(&a,(void *)(intptr_t)reach);lv_anim_set_path_cb(&a,lv_anim_path_ease_out);
  lv_anim_set_repeat_count(&a,once?1:LV_ANIM_REPEAT_INFINITE);
  lv_anim_start(&a);
}
inline void alarm_spring(lv_obj_t *o,uint32_t delay){
  lv_obj_set_style_radius(o,LV_RADIUS_CIRCLE,0);
  const int32_t grow=std::max<int32_t>(2,lv_obj_get_width(o)/24);
  lv_anim_t a;lv_anim_init(&a);lv_anim_set_var(&a,o);lv_anim_set_values(&a,0,grow);lv_anim_set_duration(&a,150);
  lv_anim_set_reverse_duration(&a,200);lv_anim_set_delay(&a,delay);lv_anim_set_exec_cb(&a,alarm_spring_exec);
  lv_anim_set_path_cb(&a,lv_anim_path_ease_out);
  lv_anim_start(&a);
}
// How long after a change of state the arrival is still shown: a card drawn later (opened a minute after arming)
// shows the shield standing still.
constexpr uint32_t ALARM_ARRIVAL_MS=1500;
inline bool alarm_arrived(const Tile &t){return t.changed_at&&esphome::millis()-t.changed_at<ALARM_ARRIVAL_MS;}
// The tile's circle, after every render of its slot and once a second from tick(): the heartbeat of the state while
// the screen is awake, the arrival once.
// A lock's heartbeat: slow while it moves, quicker while its tile waits for the second tap (lock section below).
inline AlarmLook lock_look(const Tile &t);
inline uint32_t lock_accent(const Tile &t);
inline void alarm_tile_look(size_t slot,const Tile *t){
  if(slot>=widgets.size()||!widgets[slot].circle)return;
  auto &w=widgets[slot];
  CardScope scope(w);  // tick() paints the ring outside render_slot: in the card's look (docs/THEME.md "A card's look")
  // A key of a bedside clock is its circle (render_slot): the ring grows out of the round card, since the card cuts off
  // what its children draw past its edge, and a circle as large as the card has no room inside it.
  lv_obj_t *circle=widgets[slot].key?widgets[slot].tile:widgets[slot].circle;
  // A lock's circle moves the same way (firmware 0.5.0+): it beats while the lock moves or waits for its second tap,
  // and beats once and springs when it locks.
  const bool lock=t&&t->domain()=="lock";
  const bool alarm=t&&(t->domain()=="alarm_control_panel"||lock);
  // The slot shows another tile now: its circle stands still.
  if(!alarm){
    if(w.alarm_look||w.alarm_mark)alarm_still(circle);
    w.alarm_look=LOOK_NONE;w.alarm_mark=0;
    return;
  }
  const AlarmLook want=alarm&&awake()&&fresh()?(lock?lock_look(*t):alarm_look(*t)):LOOK_NONE;
  const bool large=ui::large();
  if(alarm&&want==LOOK_NONE&&alarm_arrived(*t)&&w.alarm_mark!=t->changed_at&&awake()){
    w.alarm_mark=t->changed_at;alarm_still(circle);w.alarm_look=LOOK_NONE;
    const bool closed=lock?t->state=="locked":alarm_panel::armed(t->state);
    if(closed)alarm_beat(circle,theme::state(alarm_panel::GREEN),600,ui::px(large?10:5),true);
    alarm_spring(circle,closed?120:0);
    return;
  }
  if(want==w.alarm_look)return;
  w.alarm_look=want;alarm_still(circle);
  if(want==LOOK_NONE)return;
  const uint32_t colour=theme::state(lock?lock_accent(*t):alarm_panel::color(t->state));
  alarm_beat(circle,colour,want==LOOK_ARMING?1600:want==LOOK_PENDING?600:1000,ui::px(large?10:5),false);
}
// The bell rings while the alarm goes off: it shakes a few pixels either way, then stands still, once a second (a
// shift, not a rotation, which would need a layer of its own).
inline void alarm_swing_exec(lv_anim_t *a,int32_t v){
  const int reach=(int)(intptr_t)lv_anim_get_user_data(a);
  lv_obj_set_style_translate_x(static_cast<lv_obj_t *>(a->var),v<500?(int32_t)lv_trigo_sin((int16_t)(v*1440/500))*reach*(500-v)/500/32767:0,0);
}
#if LV_USE_ARC
inline void alarm_ring_turn(void *o,int32_t v){lv_arc_set_rotation(static_cast<lv_obj_t *>(o),v);}
inline void alarm_ring_close(void *o,int32_t v){lv_arc_set_angles(static_cast<lv_obj_t *>(o),0,v);}
#endif
// The ring round the card's shield: the exit delay running out where its length is known, a short arc going round
// where it is not, and the ring closing when the alarm arms.
inline void alarm_card_ring(const Tile &t,int cx,int cy,int size,int width){
  alarm_ring=nullptr;
#if LV_USE_ARC
  const bool closing=alarm_panel::armed(t.state)&&alarm_arrived(t);
  if(t.state!="arming"&&!closing)return;
  const uint32_t colour=theme::state(alarm_panel::color(t.state));
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
  const uint32_t delay=t.extra().alarm_delay,left=alarm_left(t);
  if(delay&&left){
    // The part still to run, from the top clockwise; tick() takes a second off it each second.
    lv_arc_set_range(arc,0,(int32_t)delay);lv_arc_set_mode(arc,LV_ARC_MODE_REVERSE);lv_arc_set_value(arc,(int32_t)std::min(left,delay));
    alarm_ring=arc;
    return;
  }
  lv_arc_set_angles(arc,0,70);
  lv_anim_set_values(&a,270,630);lv_anim_set_duration(&a,1600);lv_anim_set_exec_cb(&a,alarm_ring_turn);
  lv_anim_set_repeat_count(&a,LV_ANIM_REPEAT_INFINITE);lv_anim_start(&a);
#else
  (void)t;(void)cx;(void)cy;(void)size;(void)width;
#endif
}
// The dots of the keypad: one filled per digit typed, and empty ones up to four, like a PIN field.
inline void alarm_draw_dots(const alarm_panel::KeypadLayout &l){
  if(!alarm_dots)return;
  lv_obj_clean(alarm_dots);
  const unsigned n=alarm_pad.code.size(),shown=alarm_panel::dots_shown(alarm_send_after(),n);
  alarm_dots_shown=shown;
  const int gap=alarm_panel::dot_gap(l.dot),row=(int)shown*l.dot+((int)shown-1)*gap;
  lv_obj_set_size(alarm_dots,std::max(row,l.dots.w),l.dot);
  lv_obj_set_x(alarm_dots,l.dots.x+(l.dots.w-row)/2-(std::max(row,l.dots.w)-l.dots.w)/2);
  const bool bad=alarm_pad.note==txt::alarm_wrong_code||alarm_pad.note==txt::alarm_nothing_changed;
  for(unsigned i=0;i<shown;++i){
    // On red the dots are white: filled for a digit, a ring for one still to come.
    const uint32_t empty=alarm_red?theme::state(alarm_panel::RED):theme::hex(theme::CARD);
    const uint32_t full=alarm_red?theme::hex(theme::ON_ACCENT):bad?theme::state(alarm_panel::RED):theme::hex(theme::INK);
    auto *dot=detail_shape(alarm_dots,(std::max(row,l.dots.w)-row)/2+(int)i*(l.dot+gap),0,l.dot,l.dot,i<n?full:empty,l.dot/2);
    if(i>=n){lv_obj_set_style_border_width(dot,std::max(1,l.dot/7),0);lv_obj_set_style_border_color(dot,theme::color(alarm_red?theme::ON_ACCENT:theme::TICK),0);}
  }
}
inline alarm_panel::KeypadLayout alarm_keypad_layout;
inline void alarm_shake_exec(void *o,int32_t v){
  const int reach=alarm_keypad_layout.dot;
  lv_obj_set_style_translate_x(static_cast<lv_obj_t *>(o),v<320?(int32_t)lv_trigo_sin((int16_t)(v*1080/320))*reach*(320-v)/320/32767:0,0);
}
inline std::string alarm_line_text(){
  const uint32_t now=esphome::millis();
  if(alarm_lock.locked(now))return fill(txt::alarm_try_again,"time",countdown(alarm_lock.remaining_s(now)));
  if(alarm_attempt.active)return tr(txt::tile_command_sent);
  if(alarm_pad.note&&now-alarm_pad.note_at<4000)return tr(alarm_pad.note);
  // On red the line says what is going on and how long is left: Triggered, Pending · 0:24.
  if(alarm_red&&detail_index<model.count)return alarm_status(model.tiles[detail_index],false);
  return tr(txt::ha_alarm_action_enter_code);
}
// What the keypad's keys may do now: nothing while the lock holds or a code is on its way, and Clear and OK only with
// a digit to act on.
inline void alarm_keys_state(){
  const uint32_t now=esphome::millis();
  const bool held=alarm_lock.locked(now)||alarm_attempt.active||!fresh();
  for(int i=0;i<12;++i){
    if(!alarm_keys[i])continue;
    // The keys beside 0 (delete, OK) need a digit to act on; a digit needs room for one more.
    const bool side=i==9||i==11;
    const bool off=held||(side&&alarm_pad.code.empty())||(!side&&alarm_pad.code.size()>=alarm_panel::CODE_MAX);
    if(off)lv_obj_add_state(alarm_keys[i],LV_STATE_DISABLED);else lv_obj_remove_state(alarm_keys[i],LV_STATE_DISABLED);
  }
  if(alarm_line){
    label(alarm_line,alarm_line_text());
    const bool bad=!alarm_lock.locked(now)&&alarm_pad.note&&now-alarm_pad.note_at<4000;
    lv_obj_set_style_text_color(alarm_line,alarm_red?theme::color(theme::ON_ACCENT):bad?lv_color_hex(theme::foreground(alarm_panel::RED)):theme::color(theme::MUTED),0);
  }
}
// A key with an icon and a word side by side, centred: the mode keys and the Disarm key.
inline void alarm_key_face(lv_obj_t *key,const char *icon,const std::string &word,const lv_font_t *icons,const lv_font_t *text,lv_color_t ink,int w,int h){
  auto *words=lv_obj_get_child(key,0);
  lv_obj_set_align(words,LV_ALIGN_TOP_LEFT);   // detail_button centred it; this face places it itself
  lv_obj_set_style_text_font(words,text,0);lv_label_set_text(words,word.c_str());lv_obj_set_style_text_color(words,ink,0);
  const int icon_w=icons?lv_font_get_line_height(icons):0,room=std::max(1,w-icon_w-ui::px(8)-2*ui::px(10));
  // A word that does not fit whole leaves the key to its icon, which says the same thing, rather than to "Vac…".
  const bool word_fits=text_width(word,text)<=room||!icons;
  if(!word_fits)lv_obj_add_flag(words,LV_OBJ_FLAG_HIDDEN);
  const int gap=word_fits?ui::px(8):0,word_w=word_fits?std::min(room,text_width(word,text)):0;
  lv_obj_set_size(words,std::max(1,word_w),lv_font_get_line_height(text));
  const int x=(w-icon_w-gap-word_w)/2;
  lv_obj_set_pos(words,x+icon_w+gap,(h-lv_font_get_line_height(text))/2);lv_obj_set_style_text_align(words,LV_TEXT_ALIGN_LEFT,0);
  if(icons){
    auto *glyph=lv_label_create(key);lv_label_set_text(glyph,icon);lv_obj_set_style_text_font(glyph,icons,0);lv_obj_set_style_text_color(glyph,ink,0);
    lv_obj_set_pos(glyph,x,(h-icon_w)/2);lv_obj_remove_flag(glyph,LV_OBJ_FLAG_CLICKABLE);
  }
}
inline const lv_font_t *largest_digits(const char *text,int width,int height);
// The keypad: the dots, a line of words and twelve keys, in the card's place. The alarm panel's and a lock's.
// `top` is right under the card's bar: the keypad's title is the bar's name (Disarm), so the state line gives way and
// the keys take its room. `red`: the panel goes off or counts someone in, and the whole glass behind it turns red.
inline void render_code_pad(const alarm_panel::Metrics &m,int width,int top,int bottom,const lv_font_t *text,const lv_font_t *icons,const lv_font_t *mini,
                            bool red=false,lv_obj_t *heading=nullptr){
  using namespace alarm_panel;
  alarm_red=red;
  if(detail_status)lv_obj_add_flag(detail_status,LV_OBJ_FLAG_HIDDEN);
  if(red){
    // The card's own ground turns red, behind the bar too, so the red reaches every edge of the glass; show_detail
    // gives it back its page colour with the next card. The name on it turns white.
    lv_obj_set_style_bg_color(detail_root,lv_color_hex(theme::state(alarm_panel::RED)),0);
    if(heading)lv_obj_set_style_text_color(heading,theme::color(theme::ON_ACCENT),0);
  }
  const unsigned send_after=alarm_send_after();
  const auto l=keypad_layout(m,width,top,bottom,dots_shown(send_after,(unsigned)alarm_pad.code.size()));
  alarm_keypad_layout=l;
  alarm_dots=lv_obj_create(detail_root);lv_obj_remove_style_all(alarm_dots);lv_obj_set_pos(alarm_dots,l.dots.x,l.dots.y);
  lv_obj_remove_flag(alarm_dots,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(alarm_dots,LV_OBJ_FLAG_SCROLLABLE);
  alarm_draw_dots(l);
  if(alarm_pad.shake_at&&esphome::millis()-alarm_pad.shake_at<400){
    alarm_pad.shake_at=0;
    lv_anim_t a;lv_anim_init(&a);lv_anim_set_var(&a,alarm_dots);lv_anim_set_values(&a,0,320);lv_anim_set_duration(&a,320);
    lv_anim_set_exec_cb(&a,alarm_shake_exec);lv_anim_start(&a);
  }
  alarm_line=detail_text(detail_root,alarm_line_text(),l.line.x,l.line.y,l.line.w,text,LV_TEXT_ALIGN_CENTER,theme::MUTED);
  // The words wrap within their room instead of ending in dots after the first one (keypad_layout gives it the lines).
  lv_label_set_long_mode(alarm_line,LV_LABEL_LONG_WRAP);lv_obj_set_height(alarm_line,l.line.h);
  // The digits take the largest digit step that fits a key (looks/shared/digits.yaml), else the card's own.
  const Rect &cell=l.keys[0];
  const lv_font_t *digits=largest_digits("8",cell.w*6/10,cell.h*55/100);
  if(!digits)digits=watch_font?watch_font:detail_font;
  const lv_font_t *glyphs=icons&&lv_font_get_line_height(icons)<=cell.h-ui::px(6)?icons:mini;
  const int radius=std::min(m.radius(),cell.h/3);
  const unsigned before=detail_action_count;
  for(int i=0;i<12;++i){
    const Rect &r=l.keys[i];
    // The keys beside 0: delete and OK, or nothing and delete when the code sends itself (alarm_panel::Side).
    const Side side=i==9?left_of_zero(send_after):i==11?right_of_zero(send_after):Side::NONE;
    if((i==9||i==11)&&side==Side::NONE)continue;
    const bool ok=side==Side::OK,erase=side==Side::DELETE;
    const int digit=i<9?i+1:0;
    auto *key=detail_button("",r.x,r.y,r.w,r.h,ok?ALARM_OK:erase?ALARM_CLEAR:ALARM_DIGIT_FIRST+digit);
    lv_obj_set_style_radius(key,radius,0);
    // On red the OK key is the dark key of the card's Disarm, as blue on red would clash.
    const theme::Role ok_bg=red?theme::BUTTON_DARK:theme::ACCENT,ok_down=red?theme::BUTTON_DARK_PRESSED:theme::ACCENT_PRESSED;
    lv_obj_set_style_bg_color(key,theme::color(ok?ok_bg:theme::CARD),0);
    lv_obj_set_style_bg_color(key,theme::color(ok?ok_down:theme::KEY),LV_STATE_PRESSED);
    lv_obj_set_style_border_width(key,ok||red?0:1,0);lv_obj_set_style_border_color(key,theme::color(theme::LINE),0);
    auto *face=lv_obj_get_child(key,0);
    lv_obj_set_style_text_font(face,ok||erase?glyphs:digits,0);
    lv_label_set_text(face,ok?glyph::CHECK:erase?glyph::ERASE:std::to_string(digit).c_str());
    lv_obj_set_style_text_color(face,theme::color(ok?theme::ON_ACCENT:theme::INK),0);
    lv_obj_set_size(face,LV_SIZE_CONTENT,LV_SIZE_CONTENT);lv_obj_center(face);
    alarm_keys[i]=key;
  }
  // The keypad keeps its own states (alarm_keys_state), not the card's "wait for Home Assistant" ones.
  detail_action_count=before;
  alarm_keys_state();
}
inline uint32_t security_card_shape(const Tile &t);
inline void render_alarm_detail(Tile &t,bool large,int width,int height,lv_obj_t *heading){
  using namespace alarm_panel;
  detail_placed=true;
  if(alarm_pad.entity!=t.entity){alarm_close_pad();alarm_pad.entity=t.entity;}
  // A keypad to disarm closes when the panel is disarmed another way.
  if(alarm_pad.open&&(!t.available()||(alarm_pad.mode==DISARM&&t.state=="disarmed")))alarm_close_pad();
  // Going off or counting someone in, a panel that asks a code is its keypad at once (design B): no card with one
  // Disarm key first. A keypad open to arm turns into the one to disarm.
  const bool keypad_first=alarm_keypad_first(t);
  if(keypad_first&&(!alarm_pad.open||alarm_pad.mode!=DISARM)){
    alarm_wipe(alarm_pad.code);alarm_pad.open=true;alarm_pad.mode=DISARM;alarm_pad.note=0;alarm_pad.entity=t.entity;
  }
  alarm_red=false;
  alarm_forget_widgets();
  card_shaped(t,security_card_shape);
  const lv_font_t *text=large?detail_font:(control_font?control_font:detail_font);
  const lv_font_t *icons=tile_icon_font();
  const lv_font_t *mini=mini_icon_font?mini_icon_font:detail_font;
  Metrics m;m.large=large;m.touch=ui::touch_min();m.text_h=lv_font_get_line_height(text);
  m.icon_h=icons?lv_font_get_line_height(icons):m.text_h;m.side=overlay_card::pad();
  const int top=ui::px(large?80:50)+lv_font_get_line_height(detail_font)+m.gap(),bottom=height-ui::px(large?18:8);
  const bool on=t.active(),available=t.available();
  const uint32_t colour=on?color(t.state):theme::STATE_OFF;
  if(alarm_pad.open){
    // The keypad in the card's place, titled as Home Assistant's code dialog: Disarm, Arm away. It starts right under
    // the bar and takes the glass to its bottom edge.
    if(heading)label(heading,alarm_action_text(alarm_pad.mode));
    render_code_pad(m,width,detail_bar::bottom()+m.gap(),height-m.gap(),text,icons,mini,keypad_first,heading);
    return;
  }
  // The card: the shield on its white card, and the modes or the one Disarm key.
  const bool urgent_card=urgent(t.state)&&available;
  const auto offered=modes(t.supported);
  const auto l=card_layout(m,width,top,bottom,urgent_card?0:(unsigned)offered.size(),urgent_card);
  detail_card(l.hero.x,l.hero.y,l.hero.w,l.hero.h);
  const int icon_h=m.icon_h,ring_w=ui::px(large?8:5),ring_gap=ui::px(large?8:5);
  int d=std::min(std::min(l.hero.w,l.hero.h)-2*(ring_w+ring_gap)-ui::px(large?10:6),icon_h*5/2);
  d=std::max(d,icon_h+ui::px(8));
  const int cx=l.hero.cx(),cy=l.hero.cy();
  auto *circle=detail_shape(detail_root,cx-d/2,cy-d/2,d,d,available?theme::tint(theme::state(colour),38):theme::hex(theme::TRACK),d/2);
  if(icons){
    auto *icon=detail_text(circle,t.icon.empty()?alarm_panel::icon(t.state):t.icon.c_str(),0,(d-icon_h)/2,d,icons,LV_TEXT_ALIGN_CENTER,
                           available?theme::icon(theme::state(colour)):theme::hex(theme::OFF));
    if(t.state=="triggered"&&awake()){
      lv_anim_t a;lv_anim_init(&a);lv_anim_set_var(&a,icon);lv_anim_set_values(&a,0,1000);lv_anim_set_duration(&a,1000);
      lv_anim_set_custom_exec_cb(&a,alarm_swing_exec);lv_anim_set_user_data(&a,(void *)(intptr_t)std::max(2,icon_h/10));
      lv_anim_set_repeat_count(&a,LV_ANIM_REPEAT_INFINITE);lv_anim_start(&a);
    }
  }
  alarm_card_ring(t,cx,cy,d+2*(ring_w+ring_gap),ring_w);
  if(awake()&&available){
    const AlarmLook look=alarm_look(t);
    if(look==LOOK_PENDING||look==LOOK_TRIGGERED)alarm_beat(circle,theme::state(colour),look==LOOK_PENDING?600:1000,ui::px(large?28:14),false);
    else if(look==LOOK_NONE&&alarm_arrived(t))alarm_spring(circle,armed(t.state)?450:0);
  }
  if(urgent_card){
    auto *key=detail_button("",l.disarm.x,l.disarm.y,l.disarm.w,l.disarm.h,ALARM_MODE_FIRST+DISARM);
    lv_obj_set_style_radius(key,l.disarm.h/2,0);
    lv_obj_set_style_bg_color(key,theme::color(theme::BUTTON_DARK),0);lv_obj_set_style_bg_color(key,theme::color(theme::BUTTON_DARK_PRESSED),LV_STATE_PRESSED);
    alarm_key_face(key,glyph::SHIELD_OFF,alarm_action_text(DISARM),icons&&lv_font_get_line_height(icons)<=l.disarm.h-ui::px(8)?icons:mini,
                   watch_font?watch_font:text,theme::color(theme::ON_ACCENT),l.disarm.w,l.disarm.h);
    return;
  }
  const lv_font_t *key_icons=icons&&lv_font_get_line_height(icons)<=(l.key_count?l.keys[0].h:0)-ui::px(10)?icons:mini;
  for(unsigned i=0;i<l.key_count;++i){
    const unsigned mode=offered[i];
    const Rect &r=l.keys[i];
    const bool current=t.state==MODES[mode].state;
    auto *key=detail_button("",r.x,r.y,r.w,r.h,ALARM_MODE_FIRST+(int)mode);
    lv_obj_set_style_radius(key,r.h/2,0);
    const uint32_t mode_colour=mode==DISARM?theme::STATE_OFF:GREEN;
    lv_obj_set_style_bg_color(key,current?lv_color_hex(theme::state(mode_colour)):theme::color(theme::CARD),0);
    lv_obj_set_style_bg_color(key,theme::color(theme::KEY),LV_STATE_PRESSED);
    lv_obj_set_style_border_width(key,current?0:1,0);lv_obj_set_style_border_color(key,theme::color(theme::LINE),0);
    alarm_key_face(key,MODES[mode].icon,alarm_mode_text(mode),key_icons,text,
                   current?theme::color(theme::ON_ACCENT):theme::color(theme::INK),r.w,r.h);
    // The icon in the mode's colour on a white key, as Home Assistant colours its choices.
    if(!current&&lv_obj_get_child_count(key)>1)lv_obj_set_style_text_color(lv_obj_get_child(key,1),mode==DISARM?theme::color(theme::SLATE):lv_color_hex(theme::foreground(GREEN)),0);
  }
}
// A new state of an alarm panel arrived (page_receiver): an attempt may be settled by it, and someone coming in or
// the alarm going off wakes the screen with the card open, and the keypad when disarming asks for a code.
inline void alarm_state_arrived(unsigned index,const std::string &before){
  if(index>=model.count)return;
  auto &t=model.tiles[index];
  if(alarm_attempt.active&&t.entity==alarm_attempt_entity)alarm_settled(alarm_attempt.settle(t.state,esphome::millis()),true);
  if(!alarm_panel::calls_for_attention(t.state)||alarm_panel::calls_for_attention(before)||!t.available())return;
  if(!enabled||!model.ready())return;
  // A screen left out on the Events page (the app's alarm_screens) stays quiet: every tile of the panel says so.
  if(t.alarm_quiet)return;
  // A panel on several tiles gets a state message per tile: the first of them wakes the screen, once.
  for(size_t i=0;i<index;++i)if(model.tiles[i].entity==t.entity)return;
  ESP_LOGI("alarm","%s is %s: the screen wakes with its card",t.entity.c_str(),t.state.c_str());
  if(alarm_wake)alarm_wake();
  settings_screen::close();
  const auto codes=alarm_codes(t);
  if(alarm_pad.entity!=t.entity)alarm_close_pad();
  alarm_pad.entity=t.entity;
  if(alarm_panel::needs_code(codes,alarm_panel::DISARM)&&alarm_panel::code_typable(codes)&&!alarm_pad.open){
    alarm_pad.open=true;alarm_pad.mode=alarm_panel::DISARM;alarm_pad.note=0;alarm_wipe(alarm_pad.code);
  }
  active_index=(int)index;
  show_detail(index);
}
// Once a second and on every tick (tick()): an attempt nothing answered runs out, the keypad's lock counts down, the
// exit delay's ring and the tiles' heartbeats follow the screen's clock and whether it is awake.
inline void alarm_tick(){
  const uint32_t now=esphome::millis();
  if(alarm_attempt.active){
    std::string state;
    for(size_t i=0;i<model.count;++i)if(model.tiles[i].entity==alarm_attempt_entity){state=model.tiles[i].state;break;}
    // A lock's attempt heads for a lock's state (lock_panel::reached).
    const bool lock=alarm_attempt_entity.compare(0,5,"lock.")==0;
    alarm_settled(lock?alarm_attempt.settle_if(lock_panel::reached(state,(lock_panel::Act)alarm_attempt.mode),now):alarm_attempt.settle(state,now),true);
  }
  if(alarm_keys[0])alarm_keys_state();
  // A lock that ran out while nobody looked: the count stays, the keypad opens.
  static bool was_locked=false;
  const bool locked=alarm_lock.locked(now);
  if(was_locked&&!locked)alarm_save_lock();
  was_locked=locked;
#if LV_USE_ARC
  if(alarm_ring&&detail_index<model.count){
    const auto &t=model.tiles[detail_index];
    lv_arc_set_value(alarm_ring,(int32_t)std::min(alarm_left(t),t.extra().alarm_delay));
  }
#endif
}
inline void alarm_command(int cmd){
  if(detail_index>=model.count)return;
  auto &t=model.tiles[detail_index];
  // The keypad is a lock's too (firmware 0.5.0+); the mode keys are the alarm's own.
  if(t.domain()!="alarm_control_panel"&&!(t.domain()=="lock"&&cmd>=ALARM_DIGIT_FIRST))return;
  const uint32_t now=esphome::millis();
  if(cmd>=ALARM_DIGIT_FIRST&&cmd<ALARM_DIGIT_FIRST+10){
    if(!alarm_pad.open||alarm_lock.locked(now)||alarm_attempt.active||alarm_pad.code.size()>=alarm_panel::CODE_MAX)return;
    if(!screen_input::touch_guard.accept_repeat(now,300+cmd))return;
    alarm_pad.code+=(char)('0'+cmd-ALARM_DIGIT_FIRST);alarm_pad.note=0;
    // The dots follow the finger at once; a fifth digit makes the row longer, so it is drawn again.
    alarm_draw_dots(alarm_keypad_layout);
    alarm_keys_state();
    // The last digit of a code whose length the tile gives sends it, as OK would (alarm_panel::sends_now).
    if(alarm_panel::sends_now(alarm_send_after(),(unsigned)alarm_pad.code.size())&&fresh()&&t.available())alarm_send(t);
    return;
  }
  if(cmd==ALARM_CLEAR){
    // Delete takes the last digit back, as a phone's keypad does.
    if(!screen_input::touch_guard.accept_repeat(now,300+cmd))return;
    if(!alarm_pad.code.empty()){alarm_pad.code.back()='\0';alarm_pad.code.pop_back();}
    alarm_pad.note=0;alarm_draw_dots(alarm_keypad_layout);alarm_keys_state();
    return;
  }
  if(!fresh()||!allowed(now,300+cmd,"alarm:"+t.entity)||!t.available())return;
  if(cmd==ALARM_OK){alarm_send(t);return;}
  if(cmd>=ALARM_MODE_FIRST&&cmd<ALARM_MODE_FIRST+(int)alarm_panel::MODE_COUNT){
    if(t.waiting(now))return;
    alarm_choose(t,(unsigned)(cmd-ALARM_MODE_FIRST));
  }
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
