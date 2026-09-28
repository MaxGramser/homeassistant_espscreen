// Native LVGL media views. No browser-specific rendering.
#include "runtime_tiles.h"
#if LV_USE_IMAGE
#include "src/misc/cache/instance/lv_image_cache.h"
#endif
namespace runtime_tiles {
// The card: everything under the top bar, from `top` down.
void render_media_detail(Tile &t,unsigned index,bool large,int width,int height,int top){
  using namespace media_card;
  using namespace tile_controls;
  const auto &x=t.extra();
  const Metrics m=media_metrics(large);
  const Layout l=layout(m,width,std::max(60,height-top-(ui::px(large?12:6))));
  auto at=[&](Rect r){r.y+=top;return r;};
  const bool usable=fresh()&&t.available(),track=usable&&has_track(t.state),play=media_card::playing(t.state);
  const uint32_t f=t.supported;auto can=[&](uint32_t bit){return usable&&(!f||(f&bit));};
  // The cover, or its placeholder with the player's icon; the cover comes over it once the app served it.
  auto *frame=media_box(detail_root,nullptr,at(l.art),theme::tint(theme::ha::LIGHT_BLUE,51),l.art_radius);
  const std::string glyph=icon_for(t);
  const lv_font_t *placeholder_font=big_icon_font&&font_has(big_icon_font,glyph)?big_icon_font:tile_icon_font();
  auto *icon=lv_label_create(frame);lv_obj_remove_flag(icon,LV_OBJ_FLAG_CLICKABLE);lv_obj_set_style_text_font(icon,placeholder_font,0);
  lv_obj_set_style_text_color(icon,theme::rgb(theme::icon(theme::ha::LIGHT_BLUE)),0);lv_label_set_text(icon,glyph.c_str());center_icon(icon);
  media_art_rect=at(l.art);media_detail_picture=nullptr;
  const uint32_t ground=theme::hex(theme::PAGE);
  if(camera_supported()&&track&&!x.media_picture.empty()){
    cover_want(t.entity,x.media_picture,l.art.w,ground,CoverOwner::DETAIL,0);
    media_detail_picture=media_picture_show(detail_root,nullptr,media_art_rect,cover_ready(t.entity,x.media_picture,l.art.w,ground));
  }
  // Title, artist · album.
  const lv_font_t *title_font=watch_font?watch_font:detail_font,*artist_font=control_font?control_font:detail_font,*small=small_font?small_font:detail_font;
  const lv_text_align_t align=l.wide?LV_TEXT_ALIGN_LEFT:LV_TEXT_ALIGN_CENTER;
  // A title or artist line wider than the card rolls by, round and round (firmware 0.2.77+); a shorter one stands still.
  marquee(detail_text(detail_root,track&&!x.media_title.empty()?x.media_title:std::string(idle_text(usable?t.state:"unavailable")),l.title.x,l.title.y+top,l.title.w,title_font,align,theme::INK));
  if(l.artist)marquee(detail_text(detail_root,track?subtitle(x.media_artist,x.media_album):std::string(),l.artist_line.x,l.artist_line.y+top,l.artist_line.w,artist_font,align,theme::MUTED));
  // The progress bar: the fill runs while the track plays; a stream without a length has no bar to show.
  media_progress_fill=nullptr;media_elapsed_label=nullptr;media_bar_width=l.bar.w;
  if(track && x.media_duration){
    media_progress_fill=media_timeline(detail_root,nullptr,at(l.bar),t,large,index);
    if(l.times){
      media_elapsed_label=detail_text(detail_root,clock_text(elapsed_seconds(x.media_position,x.media_position_at,now_epoch(),play,x.media_duration)),l.elapsed.x,l.elapsed.y+top,l.elapsed.w,small,LV_TEXT_ALIGN_LEFT,theme::SUBTLE);
      detail_text(detail_root,clock_text(x.media_duration),l.total.x,l.total.y+top,l.total.w,small,LV_TEXT_ALIGN_RIGHT,theme::SUBTLE);
    }
  }
  // The keys: previous, play or pause on the accent, next; the mute key bare at the start of the volume row. An off
  // player shows one power key instead, and no volume row: it reports no volume.
  auto cb=[](lv_event_t *e){detail_command((intptr_t)lv_event_get_user_data(e));};
  const lv_font_t *key_font=mini_icon_font?mini_icon_font:detail_font;
  std::vector<lv_obj_t *> keys;
  if(usable && media_off(t)){
    if(can(feature::MEDIA_TURN_ON))keys.push_back(media_key(detail_root,nullptr,at(l.play),glyph::POWER,tile_icon_font(),true,false,true,cb,(void*)(intptr_t)24));
  }else{
    keys={media_key(detail_root,nullptr,at(l.prev),glyph::PREVIOUS,key_font,false,false,can(feature::MEDIA_PREVIOUS),cb,(void*)(intptr_t)21),
          media_key(detail_root,nullptr,at(l.play),play?glyph::PAUSE:glyph::PLAY,tile_icon_font(),true,false,can(feature::MEDIA_PLAY|feature::MEDIA_PAUSE),cb,(void*)(intptr_t)20),
          media_key(detail_root,nullptr,at(l.next),glyph::NEXT,key_font,false,false,can(feature::MEDIA_NEXT),cb,(void*)(intptr_t)22)};
    if(std::isfinite(t.volume)){
      auto *mute=media_key(detail_root,nullptr,at(l.mute),t.muted?glyph::MUTED:glyph::VOLUME,key_font,false,true,can(feature::MEDIA_VOLUME_MUTE),cb,(void*)(intptr_t)23);
      lv_obj_add_event_cb(mute,[](lv_event_t *){media_speakers_open(detail_index);},LV_EVENT_LONG_PRESSED,nullptr);
      keys.push_back(mute);
      media_slider(detail_root,nullptr,at(l.volume),t,large,can(feature::MEDIA_VOLUME_SET),(void*)(uintptr_t)index);
      detail_text(detail_root,media_volume_text(t),l.percent.x,l.percent.y+top,l.percent.w,small,LV_TEXT_ALIGN_RIGHT,theme::MUTED);
    }
  }
  // Only the keys the player supports join the card's actions: tick() enables those again after a wait, and a key
  // the player lacks stays faded.
  for(auto *k:keys)if(!lv_obj_has_state(k,LV_STATE_DISABLED) && detail_action_count<32)detail_actions[detail_action_count++]=k;
}

inline uint32_t media_speakers_asked=0,media_speakers_opened=0;
inline bool media_speakers_stale=true,media_speakers_timeout=false;
inline lv_obj_t *media_group_dropdown=nullptr;
inline std::string media_zoom_mark;
inline lv_image_dsc_t media_zoom_source{};
inline void *media_zoom_pixels=nullptr;
inline size_t media_zoom_capacity=0;
inline std::vector<MediaGroup> media_group_choices,media_group_pending,media_group_options;
inline unsigned media_group_next_page=0;
inline bool media_group_more=false;
constexpr unsigned MEDIA_GROUP_LIMIT=64;
inline std::string media_speaker_held_entity;
inline group_page::Held media_speaker_held;
inline lv_obj_t *media_speaker_drag=nullptr;
inline bool media_speaker_changed=false;

bool media_touching(){
  for(auto *i=lv_indev_get_next(nullptr);i;i=lv_indev_get_next(i))if(lv_indev_get_state(i)==LV_INDEV_STATE_PRESSED)return true;
  return false;
}
inline bool media_speakers_fresh(){return fresh()&&media_speakers_received&&esphome::millis()-media_speakers_received<7000;}
inline int media_speaker_row_height(){
  const auto m=effects_page::screen_metrics();
  return std::max<int>(ui::px(ui::large()?72:42),lv_font_get_line_height(effects_page::row_font)+2*m.gap+ui::px(ui::large()?8:5));
}
inline int media_speakers_count(){
  const auto m=effects_page::screen_metrics();
  const int top=m.bar_y+m.bar+m.gap+m.row_h+m.gap;
  const int row=media_speaker_row_height();
  return std::clamp((m.height-top-m.bar-m.gap)/(row+m.gap),1,4);
}
inline void media_speakers_request(){
  if(!media_speakers_root||inbox.empty()||!fresh())return;
  esphome::api::HomeassistantActionRequest request;
  request.service=esphome::StringRef("esphome.screen_media_groups");request.is_event=true;
  const std::string keys[]={"inbox","entity","group","schema","page","gp","count","session","rev","view"};
  const std::string values[]={inbox,media_speakers.source,media_speakers.group,"1",std::to_string(media_speakers.page),
    std::to_string(media_group_more?media_group_next_page:0),std::to_string(media_speakers_count()),protocol_key(transfer.lease),layout_rev,std::to_string(++media_speakers_view)};
  request.data.init(10);
  for(unsigned i=0;i<10;++i){esphome::api::HomeassistantServiceMap item;item.key=esphome::StringRef(keys[i]);item.value=esphome::StringRef(values[i]);request.data.push_back(item);}
  esphome::api::global_api_server->send_homeassistant_action(request);
  media_speakers_asked=esphome::millis();
  media_group_more=false;
}
void media_speakers_accept(MediaSpeakers next){
  // Gather bounded packets into the native dropdown's scrollable option list.
  // Keep the displayed options stable while the next snapshot is arriving.
  if(!next.group_page)media_group_pending.clear();
  for(const auto &group:next.groups){
    if(media_group_pending.size()>=MEDIA_GROUP_LIMIT)break;
    if(std::none_of(media_group_pending.begin(),media_group_pending.end(),[&](const MediaGroup &g){return g.entity==group.entity;}))media_group_pending.push_back(group);
  }
  media_group_next_page=next.group_page+1;
  media_group_more=media_group_next_page<next.group_pages&&media_group_pending.size()<MEDIA_GROUP_LIMIT;
  if(!media_group_more){media_group_choices=std::move(media_group_pending);media_group_pending.clear();}
  media_speakers=std::move(next);media_speakers_received=std::max<uint32_t>(1,esphome::millis());media_speakers_dirty=true;
}
void media_speakers_close(){
  if(media_speakers_root){lv_obj_delete(media_speakers_root);media_speakers_root=nullptr;}
  media_group_dropdown=nullptr;
  media_group_choices.clear();media_group_pending.clear();media_group_options.clear();media_group_more=false;
  media_speakers={};media_speakers_received=0;media_speakers_dirty=false;
  media_speaker_drag=nullptr;media_speaker_changed=false;media_speaker_held={};media_speaker_held_entity.clear();
  ++media_speakers_view;
}
void media_zoom_close(){
  if(media_zoom_root){lv_obj_delete(media_zoom_root);media_zoom_root=nullptr;}
  media_zoom_picture=nullptr;
#if LV_USE_IMAGE
  if(media_zoom_pixels)lv_image_cache_drop(&media_zoom_source);
#endif
  kept_free(media_zoom_pixels);media_zoom_pixels=nullptr;media_zoom_capacity=0;media_zoom_source={};
  media_zoom_entity.clear();
  media_zoom_mark.clear();
  if(cover_wish.owner==CoverOwner::ZOOM)cover_drop();
}
void media_zoom_show(lv_image_dsc_t *src){
#if LV_USE_IMAGE
  if(media_zoom_entity.empty()||!src||!src->data||!src->header.w||!src->header.h)return;
  // Own the displayed pixels: the shared download buffer may be released or
  // overwritten while the next track's artwork is still arriving.
  void *pixels=media_zoom_pixels;
  if(src->data_size>media_zoom_capacity){pixels=kept_allocate(src->data_size);if(!pixels)return;}
  lv_image_cache_drop(&media_zoom_source);
  if(pixels!=media_zoom_pixels){kept_free(media_zoom_pixels);media_zoom_pixels=pixels;media_zoom_capacity=src->data_size;}
  std::memcpy(media_zoom_pixels,src->data,src->data_size);media_zoom_source=*src;
  media_zoom_source.data=static_cast<const uint8_t *>(media_zoom_pixels);
  if(!media_zoom_root){
    media_zoom_root=effects_page::plain(lv_screen_active(),0,0,overlay_card::screen_width(),overlay_card::screen_height());
    lv_obj_add_flag(media_zoom_root,LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_style_bg_opa(media_zoom_root,LV_OPA_COVER,0);lv_obj_set_style_bg_color(media_zoom_root,theme::color(theme::CAMERA_PAGE),0);
    lv_obj_add_event_cb(media_zoom_root,[](lv_event_t *){
      if(allowed(esphome::millis(),1901,"close album art"))lv_async_call([](void *){media_zoom_close();refresh_all();refresh_detail(detail_index);},nullptr);
    },LV_EVENT_SHORT_CLICKED,nullptr);
  }
  if(!media_zoom_picture){media_zoom_picture=lv_image_create(media_zoom_root);lv_obj_remove_flag(media_zoom_picture,LV_OBJ_FLAG_CLICKABLE);}
  lv_image_set_src(media_zoom_picture,&media_zoom_source);
  const int scale=std::min(overlay_card::screen_width()*256/(int)src->header.w,overlay_card::screen_height()*256/(int)src->header.h);
  lv_image_set_scale(media_zoom_picture,scale);lv_obj_center(media_zoom_picture);lv_obj_invalidate(media_zoom_picture);
  lv_obj_move_foreground(media_zoom_root);
#else
  (void)src;
#endif
}
inline void media_zoom_request(const Tile &tile){
  media_zoom_mark=tile.extra().media_picture;
  const int size=std::clamp(std::min(overlay_card::screen_width(),overlay_card::screen_height()),48,1024);
  cover_want(tile.entity,media_zoom_mark,size,theme::hex(theme::CAMERA_PAGE),CoverOwner::ZOOM,0);
  if(auto *full=cover_ready(tile.entity,media_zoom_mark,size,theme::hex(theme::CAMERA_PAGE),true))media_zoom_show(full);
}
void media_zoom_tick(){
  if(media_zoom_entity.empty())return;
  for(size_t i=0;i<model.count;++i){
    const auto &tile=model.tiles[i];if(tile.entity!=media_zoom_entity)continue;
    if(!tile.extra().media_picture.empty()&&tile.extra().media_picture!=media_zoom_mark)media_zoom_request(tile);
    return;
  }
  media_zoom_close();
}
void media_views_foreground(){
  if(media_speakers_root)lv_obj_move_foreground(media_speakers_root);
  // LVGL reparents its open list to the screen. It must stay above our page.
  if(media_group_dropdown&&lv_dropdown_is_open(media_group_dropdown))lv_obj_move_foreground(lv_dropdown_get_list(media_group_dropdown));
  if(media_zoom_root)lv_obj_move_foreground(media_zoom_root);
}
void media_art_event(lv_event_t *event){
#if LV_USE_IMAGE
  auto *target=lv_event_get_target_obj(event);
  if(!target||!allowed(esphome::millis(),1900,"album art"))return;
  auto *src=static_cast<const lv_image_dsc_t *>(lv_image_get_src(target));
  if(!src||!src->data||!src->header.w||!src->header.h)return;
  const Tile *tile=nullptr;
  if(lv_obj_get_parent(target)==detail_root&&detail_index<model.count)tile=&model.tiles[detail_index];
  else for(auto &w:widgets)if(w.parts[MEDIA_PICTURE]==target&&w.index<model.count){tile=&model.tiles[w.index];break;}
  if(!tile)return;
  if(media_zoom_entity==tile->entity){media_zoom_close();return;}
  media_zoom_close();
  media_zoom_entity=tile->entity;
  // Stay on the player until the full-size image is ready, then switch once.
  media_zoom_request(*tile);
#else
  (void)event;
#endif
}
inline void media_speaker_slider(lv_event_t *event){
  auto *slider=lv_event_get_target_obj(event);
  const unsigned row=(uintptr_t)lv_event_get_user_data(event);
  const auto code=lv_event_get_code(event);
  if(code==LV_EVENT_PRESSED){media_speaker_drag=slider;media_speaker_changed=false;return;}
  if(code==LV_EVENT_PRESS_LOST){media_speaker_drag=nullptr;media_speaker_changed=false;media_speakers_dirty=true;return;}
  if(code==LV_EVENT_VALUE_CHANGED&&media_speaker_drag==slider){
    media_speaker_changed=true;
    auto *label=lv_obj_get_child(lv_obj_get_parent(slider),1);
    runtime_tiles::label(label,screen_text::percent(lv_slider_get_value(slider)/10));
    return;
  }
  if(code!=LV_EVENT_RELEASED||media_speaker_drag!=slider)return;
  media_speaker_drag=nullptr;
  if(!media_speaker_changed||row>=media_speakers.speakers.size()||!media_speakers_fresh())return;
  media_speaker_changed=false;
  const auto &speaker=media_speakers.speakers[row];
  if(!speaker.enabled||!screen_input::touch_guard.accept_slider(esphome::millis(),1910+row))return;
  const int volume=lv_slider_get_value(slider)/10;
  media_speaker_held_entity=speaker.entity;media_speaker_held.send(volume,esphome::millis());
  action("media_player.volume_set",speaker.entity,"volume_level",std::to_string(volume/100.0f));
  media_speakers_dirty=true;
  // Refresh soon after release, but do not issue commands while a finger drags.
  media_speakers_asked=esphome::millis()-1600;
}
inline void media_speakers_choose(lv_event_t *event){
  const unsigned row=lv_dropdown_get_selected(lv_event_get_target_obj(event));
  if(row>=media_group_options.size()||!media_speakers_fresh()||!allowed(esphome::millis(),1920+row,"speaker group"))return;
  media_speakers.group=media_group_options[row].entity;media_speakers.name=media_group_options[row].name;
  media_speakers.page=0;media_speakers.speakers.clear();media_speakers_received=0;
  media_speakers_opened=esphome::millis();
  media_group_more=false;media_speakers_dirty=true;media_speakers_request();
}
inline void media_speakers_page(int step){
  if(!allowed(esphome::millis(),1930+step,"speaker page"))return;
  auto &page=media_speakers.page;
  const unsigned pages=media_speakers.pages;
  if((step<0&&!page)||(step>0&&page+1>=pages))return;
  page+=step;media_speakers_received=0;media_speakers_dirty=true;media_speakers_request();
}
inline void media_speakers_draw(){
  if(!media_speakers_root)return;
  lv_obj_clean(media_speakers_root);
  media_group_dropdown=nullptr;
  const auto m=effects_page::screen_metrics();
  effects_page::top_bar(media_speakers_root,m,tr(txt::media_speakers),[](lv_event_t *){
    if(allowed(esphome::millis(),1940,"speaker back"))lv_async_call([](void *){media_speakers_close();},nullptr);
  });
  const int width=m.width-2*m.pad,dropdown_y=m.bar_y+m.bar+m.gap;
  auto *dropdown=media_group_dropdown=lv_dropdown_create(media_speakers_root);
  lv_obj_set_pos(dropdown,m.pad,dropdown_y);lv_obj_set_size(dropdown,width,m.row_h);
  lv_obj_set_style_text_font(dropdown,effects_page::row_font,LV_PART_MAIN);
  lv_obj_set_style_text_font(dropdown,effects_page::icon_font,LV_PART_INDICATOR);
  lv_obj_set_style_text_color(dropdown,theme::color(theme::INK),LV_PART_MAIN);
  lv_obj_set_style_text_color(dropdown,theme::color(theme::INK),LV_PART_INDICATOR);
  lv_obj_set_style_bg_color(dropdown,theme::color(theme::RAISED),LV_PART_MAIN);
  lv_obj_set_style_border_color(dropdown,theme::color(theme::LINE),LV_PART_MAIN);
  lv_obj_set_style_radius(dropdown,m.radius,LV_PART_MAIN);
  lv_obj_set_style_pad_hor(dropdown,m.inset,LV_PART_MAIN);
  lv_dropdown_set_symbol(dropdown,"\U000F0140");
  lv_dropdown_set_dir(dropdown,LV_DIR_BOTTOM);
  media_group_options=media_group_choices;
  std::string options;unsigned selected=0;
  for(unsigned i=0;i<media_group_options.size();++i){
    if(i)options+='\n';options+=media_group_options[i].name;
    if(media_group_options[i].entity==media_speakers.group)selected=i;
  }
  lv_dropdown_set_options(dropdown,options.empty()?tr(txt::media_loading):options.c_str());
  lv_dropdown_set_selected(dropdown,selected);
  lv_dropdown_set_text(dropdown,media_speakers.name.empty()?tr(txt::media_loading):media_speakers.name.c_str());
  if(media_group_options.empty()||!media_speakers_fresh())lv_obj_add_state(dropdown,LV_STATE_DISABLED);
  auto *list=lv_dropdown_get_list(dropdown);
  lv_obj_set_style_text_font(list,effects_page::row_font,LV_PART_MAIN);
  lv_obj_set_style_text_line_space(list,m.gap,LV_PART_MAIN);
  lv_obj_set_style_text_color(list,theme::color(theme::INK),LV_PART_MAIN);
  lv_obj_set_style_bg_color(list,theme::color(theme::RAISED),LV_PART_MAIN);
  lv_obj_set_style_border_color(list,theme::color(theme::LINE),LV_PART_MAIN);
  lv_obj_set_style_radius(list,m.radius,LV_PART_MAIN);
  lv_obj_set_style_pad_hor(list,m.inset,LV_PART_MAIN);
  lv_obj_set_style_bg_color(list,theme::color(theme::KEY),LV_PART_SELECTED);
  lv_obj_set_style_text_color(list,theme::color(theme::INK),LV_PART_SELECTED);
  lv_obj_set_style_max_height(list,m.height-dropdown_y-m.row_h-m.gap,LV_PART_MAIN);
  auto *options_label=lv_obj_get_child(list,0);
  lv_obj_set_style_text_font(options_label,effects_page::row_font,LV_PART_MAIN);
  lv_obj_set_style_text_line_space(options_label,m.gap,LV_PART_MAIN);
  lv_obj_add_event_cb(dropdown,media_speakers_choose,LV_EVENT_VALUE_CHANGED,nullptr);
  lv_obj_add_event_cb(dropdown,[](lv_event_t *event){
    const auto code=lv_event_get_code(event);
    if(code==LV_EVENT_READY)lv_dropdown_set_symbol(lv_event_get_target_obj(event),"\U000F0143");
    if(code==LV_EVENT_CANCEL){lv_dropdown_set_symbol(lv_event_get_target_obj(event),"\U000F0140");media_speakers_dirty=true;}
  },LV_EVENT_ALL,nullptr);
  const int top=dropdown_y+m.row_h+m.gap,row_h=media_speaker_row_height();
  const bool ready=media_speakers_fresh();media_speakers_stale=!ready;
  media_speakers_timeout=!ready&&esphome::millis()-media_speakers_opened>6000;
  if(!ready){
    detail_text(media_speakers_root,tr(media_speakers_timeout?txt::ha_unavailable:txt::media_loading),m.pad,top+m.gap,width,effects_page::row_font,LV_TEXT_ALIGN_CENTER,theme::MUTED);
  }else if(media_speakers.speakers.empty()){
    detail_text(media_speakers_root,tr(txt::media_no_groups),m.pad,top+m.gap,width,effects_page::row_font,LV_TEXT_ALIGN_CENTER,theme::MUTED);
  }else for(unsigned i=0;i<media_speakers.speakers.size();++i){
    auto &speaker=media_speakers.speakers[i];
    auto *card=effects_page::card(media_speakers_root,m.pad,top+i*(row_h+m.gap),width,row_h,m.radius);
    int volume=speaker.volume;
    if(media_speaker_held_entity==speaker.entity)volume=media_speaker_held.show(volume,esphome::millis());
    const int text_h=lv_font_get_line_height(effects_page::row_font),value_w=ui::px(ui::large()?90:65);
    auto *label=effects_page::text(card,speaker.name,effects_page::row_font,theme::INK);
    lv_obj_set_pos(label,m.inset,m.gap/2);lv_obj_set_width(label,width-2*m.inset-value_w);
    auto *value=effects_page::text(card,speaker.muted?tr(txt::media_muted):volume<0?tr(txt::ha_unavailable):screen_text::percent(volume),effects_page::row_font,theme::MUTED,LV_TEXT_ALIGN_RIGHT);
    lv_obj_set_pos(value,width-m.inset-value_w,m.gap/2);lv_obj_set_width(value,value_w);
    Tile temporary;temporary.entity=speaker.entity;temporary.volume=std::max(0,volume)/100.0f;temporary.muted=speaker.muted;
    const int h=ui::px(ui::large()?8:5),y=text_h+m.gap+(row_h-text_h-m.gap-h)/2;
    auto *slider=media_slider(card,nullptr,{m.inset,y,width-2*m.inset,h},temporary,ui::large(),speaker.enabled,nullptr);
    lv_obj_remove_event_cb(slider,slider_event);
    lv_obj_add_event_cb(slider,media_speaker_slider,LV_EVENT_ALL,(void*)(uintptr_t)i);
  }
  const unsigned page=media_speakers.page,pages=media_speakers.pages;
  if(pages>1){
    const int y=m.height-m.bar-m.gap/2;
    auto *prev=effects_page::round_key(media_speakers_root,m.pad,y,m.bar,"\U000F0141",[](lv_event_t *){media_speakers_page(-1);});
    auto *next=effects_page::round_key(media_speakers_root,m.width-m.pad-m.bar,y,m.bar,"\U000F0142",[](lv_event_t *){media_speakers_page(1);});
    if(!page)lv_obj_add_state(prev,LV_STATE_DISABLED);if(page+1>=pages)lv_obj_add_state(next,LV_STATE_DISABLED);
    detail_text(media_speakers_root,std::to_string(page+1)+" / "+std::to_string(pages),m.pad+m.bar,y+(m.bar-lv_font_get_line_height(effects_page::row_font))/2,width-2*m.bar,effects_page::row_font,LV_TEXT_ALIGN_CENTER,theme::MUTED);
  }
}
void media_speakers_open(unsigned index){
  if(index>=model.count||!fresh()||!model.tiles[index].available()||!(model.tiles[index].supported&MEDIA_GROUPING))return;
  if(!allowed(esphome::millis(),1950,"speaker controls"))return;
  media_speakers_close();media_speakers.source=model.tiles[index].entity;
  media_speakers_root=effects_page::page_root();media_speakers_opened=media_speakers_asked=esphome::millis();
  media_speakers_draw();media_speakers_request();
  // Opening on the long press consumes its release, even if the overlay covers the key.
  for(auto *i=lv_indev_get_next(nullptr);i;i=lv_indev_get_next(i))lv_indev_wait_release(i);
}
void media_speakers_tick(){
  if(!media_speakers_root||media_touching())return;
  const uint32_t now=esphome::millis();
  if(media_group_more||now-media_speakers_asked>=2000)media_speakers_request();
  if(media_speakers_stale==media_speakers_fresh())media_speakers_dirty=true;
  if(media_speakers_timeout!=(!media_speakers_fresh()&&now-media_speakers_opened>6000))media_speakers_dirty=true;
  // LVGL owns opening, scrolling, selection and closing. Keep the native list
  // intact while open, even when a background snapshot arrives.
  if(media_speakers_dirty&&(!media_group_dropdown||!lv_dropdown_is_open(media_group_dropdown)||!media_speakers_fresh())){media_speakers_dirty=false;media_speakers_draw();}
  media_views_foreground();
}
}  // namespace runtime_tiles
