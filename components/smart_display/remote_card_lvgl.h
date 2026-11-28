// A remote's card: on and off, its activities and its keypad, as Home Assistant's dialog has them.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the cover card, whose file it stood in.
// What proves it: web/wasm/test_remote_card.mjs, tests/test_remote_tiles.py.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// A remote's card (firmware 0.22.0+), what Home Assistant's dialog has for it (more-info-remote.ts): on and off, and its
// activities where it supports them (Harmony, Android TV Remote), each of which turns it on with that activity. The power
// key sits in the top bar across from the back key, where the light's and the thermostat's have theirs; the activities
// are the select card's rows. Home Assistant lists no commands, so a remote's keys are tiles of their own that perform
// remote.send_command.
// A remote's keypad (firmware 0.22.0+): a ring with four arrows round OK, as every TV remote has it, and beside it Back,
// Home and Play/Pause on the left and the volume on the right; on glass too narrow for those columns they stand in a row
// under the ring. Only the keys the remote's integration takes are drawn (catalogue/remote.yaml keypad).
inline void render_remote_keypad(const Tile &t,bool large,int width,int height,int top){
  const auto &keys=t.extra().keypad;
  auto has=[&](int k){return k<(int)keys.size()&&!keys[k].empty();};
  const lv_font_t *mini=mini_icon_font?mini_icon_font:detail_font,*text=control_font?control_font:detail_font;
  const lv_font_t *arrows=tile_icon_font()?tile_icon_font():mini;   // the ring's arrows a size up from the round keys
  // A remote in the hand: a ring of at most about eight centimetres, its round keys the card's own keys, growing with
  // the ring on large glass up to a thumb's width.
  const int pad=overlay_card::pad(),gap=ui::px(large?12:6),most=ui::mm(80),room=height-top-pad,span=width-2*pad;
  std::vector<int> lefts,rights;
  for(int k:{RK_BACK,RK_HOME,RK_PLAY})if(has(k))lefts.push_back(k);
  for(int k:{RK_VOLUME_UP,RK_MUTE,RK_VOLUME_DOWN})if(has(k))rights.push_back(k);
  // The glass decides where the keys stand, never the remote, so every remote on one screen looks alike with fewer keys
  // where it has fewer: a row of six under the ring, two rows of three under it (narrow glass standing up), or a column
  // of three on each side, whichever leaves the largest ring.
  int rows=0;bool below=false;
  auto fit=[&](int key){
    rows=6*key+5*gap<=span?1:3*key+2*gap<=span?2:0;
    const int under=rows?std::min({room-rows*(key+gap),span,most}):0,beside=std::min({room,span-2*(key+gap),most});
    below=under>=beside;
    return std::max(ui::touch_min()*3,below?under:beside);
  };
  int key=std::max(ui::touch_min(),ui::px(large?60:40)),ring=fit(key);
  const int grown=std::min(std::max(key,ring/5),ui::mm(14));
  if(grown>key){key=grown;ring=fit(key);}
  const int x=(width-ring)/2,y=top;
  auto *disc=lv_obj_create(detail_root);lv_obj_remove_style_all(disc);
  lv_obj_set_pos(disc,x,y);lv_obj_set_size(disc,ring,ring);lv_obj_set_style_radius(disc,LV_RADIUS_CIRCLE,0);
  lv_obj_set_style_bg_color(disc,theme::color(theme::KEY),0);lv_obj_set_style_bg_opa(disc,LV_OPA_COVER,0);
  lv_obj_remove_flag(disc,LV_OBJ_FLAG_SCROLLABLE);lv_obj_remove_flag(disc,LV_OBJ_FLAG_CLICKABLE);
  auto press=[](lv_event_t *e){detail_command((intptr_t)lv_event_get_user_data(e));};
  // The arrows: from the rim to OK's edge, a third of the ring wide, lit while a finger is on them.
  const int ok=ring*2/5,third=ring/3,deep=(ring-ok)/2;
  struct Zone{int k,x,y,w,h;const char *glyph;};
  const Zone zones[]={{RK_UP,third,0,third,deep,"\U000F0143"},{RK_DOWN,third,ring-deep,third,deep,"\U000F0140"},
                      {RK_LEFT,0,third,deep,third,"\U000F0141"},{RK_RIGHT,ring-deep,third,deep,third,"\U000F0142"}};
  for(const auto &z:zones){
    auto *zone=lv_obj_create(disc);lv_obj_remove_style_all(zone);lv_obj_set_pos(zone,z.x,z.y);lv_obj_set_size(zone,z.w,z.h);
    lv_obj_add_flag(zone,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(zone,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_radius(zone,ui::px(large?18:12),0);
    lv_obj_set_style_bg_color(zone,theme::color(theme::KEY_PRESSED),LV_STATE_PRESSED);lv_obj_set_style_bg_opa(zone,LV_OPA_COVER,LV_STATE_PRESSED);
    auto *glyph=lv_label_create(zone);lv_label_set_text(glyph,z.glyph);lv_obj_set_style_text_font(glyph,arrows,0);
    lv_obj_set_style_text_color(glyph,theme::color(theme::INK),0);lv_obj_center(glyph);
    lv_obj_add_event_cb(zone,press,LV_EVENT_SHORT_CLICKED,(void*)(intptr_t)(REMOTE_KEY_FIRST+z.k));
    if(detail_action_count<32)detail_actions[detail_action_count++]=zone;
  }
  // OK in the middle: the card's own white, as the key a thumb rests on.
  auto *centre=lv_obj_create(disc);lv_obj_remove_style_all(centre);lv_obj_set_pos(centre,(ring-ok)/2,(ring-ok)/2);lv_obj_set_size(centre,ok,ok);
  lv_obj_set_style_radius(centre,LV_RADIUS_CIRCLE,0);lv_obj_set_style_bg_color(centre,theme::color(theme::CARD),0);lv_obj_set_style_bg_opa(centre,LV_OPA_COVER,0);
  lv_obj_set_style_bg_color(centre,theme::color(theme::CARD_PRESSED),LV_STATE_PRESSED);
  lv_obj_add_flag(centre,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(centre,LV_OBJ_FLAG_SCROLLABLE);
  auto *word=lv_label_create(centre);lv_label_set_text(word,"OK");lv_obj_set_style_text_font(word,text,0);
  lv_obj_set_style_text_color(word,theme::color(theme::INK),0);lv_obj_center(word);
  lv_obj_add_event_cb(centre,press,LV_EVENT_SHORT_CLICKED,(void*)(intptr_t)(REMOTE_KEY_FIRST+RK_OK));
  if(detail_action_count<32)detail_actions[detail_action_count++]=centre;
  // The round keys: the remote's own, Back, Home and Play/Pause first, then the volume.
  auto glyph_of=[](int k){
    switch(k){case RK_BACK:return "\U000F17B3";case RK_HOME:return "\U000F02DC";case RK_PLAY:return "\U000F040E";
              case RK_VOLUME_UP:return "\U000F075D";case RK_VOLUME_DOWN:return "\U000F075E";default:return "\U000F075F";}
  };
  auto round_key=[&](int k,int kx,int ky){climate_round_key({kx,ky,key,key},glyph_of(k),mini,theme::KEY,theme::INK,REMOTE_KEY_FIRST+k);};
  auto row=[&](const std::vector<int> &list,int ky){
    const int n=(int)list.size(),step=key+gap,start=(width-(n-1)*step-key)/2;
    for(int i=0;i<n;++i)round_key(list[i],start+i*step,ky);
  };
  if(below&&rows==1){
    std::vector<int> all(lefts);all.insert(all.end(),rights.begin(),rights.end());
    row(all,y+ring+gap);
    return;
  }
  if(below){
    row(lefts,y+ring+gap);
    row(rights,y+ring+gap+(lefts.empty()?0:key+gap));
    return;
  }
  auto column=[&](const std::vector<int> &list,int kx){
    const int n=(int)list.size(),span=n*key+(n-1)*gap,start=y+(ring-span)/2;
    for(int i=0;i<n;++i)round_key(list[i],kx,start+i*(key+gap));
  };
  column(lefts,x-gap-key);
  column(rights,x+ring+gap);
}
inline void render_remote_detail(const Tile &t,bool large,int width,int height,int pad,int top,int bar,int bar_x,int bar_y){
  const bool on=t.state=="on";
  const auto fill=on?theme::ACCENT_TINT:theme::KEY,ink=on?theme::ACCENT_ICON:theme::ICON_OFF;
  if(!t.extra().keypad.empty()){
    // A remote whose keys Home Assistant's integration names: its keypad, the power key in the top bar.
    if(detail_status){lv_obj_add_flag(detail_status,LV_OBJ_FLAG_HIDDEN);detail_status=nullptr;}
    auto *power=card_bind(climate_round_key(bar_key(),tile_controls::glyph::POWER,
                                            mini_icon_font?mini_icon_font:detail_font,fill,ink,LIGHT_POWER),t,power_key_paint);
    lv_obj_move_to_index(power,2);
    render_remote_keypad(t,large,width,height,top);
    overlay_card::centre(detail_root,3);
    detail_placed=true;
    card_shaped(t,select_card_shape);
    return;
  }
  if(t.extra().options.empty()){
    // Nothing but on and off (a Broadlink, an Apple TV): one big power key in the middle, its state under it.
    const lv_font_t *icons=tile_icon_font();
    const int side=ui::px(large?120:76);
    card_bind(climate_round_key({(width-side)/2,top,side,side},tile_controls::glyph::POWER,icons?icons:detail_font,fill,ink,LIGHT_POWER),t,power_key_paint);
    if(detail_status)lv_obj_set_y(detail_status,top+side+ui::px(large?12:6));
    card_shaped(t,select_card_shape);
    return;
  }
  // The activities say what runs and the lit key that it is on, so the card draws no state line of its own. The key
  // stays in the top bar while the rows below it are centred.
  if(detail_status){lv_obj_add_flag(detail_status,LV_OBJ_FLAG_HIDDEN);detail_status=nullptr;}
  auto *key=card_bind(climate_round_key(bar_key(),tile_controls::glyph::POWER,
                                        mini_icon_font?mini_icon_font:detail_font,fill,ink,LIGHT_POWER),t,power_key_paint);
  lv_obj_move_to_index(key,2);
  render_select_detail(t,large,width,height,pad,top,on?t.extra().activity:std::string());
  overlay_card::centre(detail_root,3);
  detail_placed=true;
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
