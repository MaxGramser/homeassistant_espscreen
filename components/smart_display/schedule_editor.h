#pragma once
// Native LVGL editor. Home Assistant owns the schedule and executes its actions.
// Only the transport callback knows about ESPHome events. HA owns all timers.
#include "schedule_model.h"
#include "schedule_layout.h"
#include "overlay_card.h"
#include "screen_text.h"
#include "screen_input.h"
#include "theme.h"
#include "esphome/core/hal.h"
#include <functional>
#include <memory>

namespace schedule_editor {
using schedule_model::Heat;
using Programme = schedule_model::Programme<Heat>;
using screen_text::tr;
namespace txt = screen_text::txt;
using Rect = schedule_layout::Rect;
inline const char *DAYS[] = {"mon","tue","wed","thu","fri","sat","sun"};
inline constexpr const char *SAVE="\U000F0193", *BACK="\U000F004D", *PLUS="\U000F0419", *MINUS="\U000F0377";
inline constexpr const char *LEFT="\U000F0141", *RIGHT="\U000F0142", *VACATION="\U000F158C", *CALENDAR="\U000F0B66";
enum Command { BACK_CMD=1, SAVE_CMD, MENU, RELOAD, NEW, VACATION_CMD, ENABLED, ADD, REMOVE, PREVIOUS, NEXT,
               PAGE_PREV, PAGE_NEXT, KEEP, DISCARD, SAVE_LEAVE, PROGRAMME_FIRST=100, DAY_FIRST=200 };
struct Snapshot {
  std::string revision, nonce, warning;
  schedule_model::Heating caps;
  std::vector<Programme> programmes;
  bool ready=false, vacation=false;
  Programme vacation_programme;
};
struct Editor {
  std::string entity, name, error;
  Snapshot saved, incoming;
  Programme draft, original;
  schedule_model::Lifecycle life;
  bool vacation=false, vacation_view=false, received_begin=false, dragging=false, redraw=true, guard=false;
  unsigned selected=0, serial=0, expected=0;
  uint32_t rid=0, asked=0;
  int page=0, day=0, last_weekday=0, destination=0;
  int drag_anchor_x=0, drag_anchor_minute=0;
  const lv_font_t *font=nullptr,*small=nullptr,*icons=nullptr,*day_icons=nullptr,*day_text=nullptr,*handle_icons=nullptr;
  uint32_t background=0;
  bool transparent=false;
  lv_obj_t *root=nullptr,*value_label=nullptr,*save_button=nullptr;
  lv_obj_t *boundary_labels[2]{};
  lv_obj_t *boundary_handles[2]{};
  lv_obj_t *boundary_lines[2]{};
  std::vector<lv_obj_t*> segments;
  std::vector<lv_obj_t*> separators;
  schedule_layout::Layout layout{};
  Rect timeline{};
  std::function<void(const std::string&)> send;
};
inline std::unique_ptr<Editor> editor;
inline uint32_t next_request=0;
inline bool visible() { return editor && editor->root && !lv_obj_has_flag(editor->root,LV_OBJ_FLAG_HIDDEN); }
inline bool busy() { return visible() && editor->life.needs_guard(); }
inline void render();
inline void command(int code);
inline void request(const char *operation);
inline void close() {
  if (!editor) return;
  if (editor->root) lv_obj_delete(editor->root);
  editor.reset();
}
inline std::string number(float n) { char out[24]; snprintf(out,sizeof(out),"%.1f",double(n)); return screen_text::localize(out); }
inline std::string value_text(Heat value) { return value.off ? tr(txt::ha_off) : number(value.temperature)+"°C"; }
inline std::string clock(int minute) { char out[8]; snprintf(out,sizeof(out),"%02d:%02d",minute/60,minute%60); return out; }
inline std::string identity() { return editor->saved.nonce+"_"+std::to_string(++editor->serial); }
inline void changed() {
  auto &e=*editor;
  e.life.dirty = !(e.draft==e.original) || (e.vacation_view && e.vacation!=e.saved.vacation);
  e.redraw=true;
}
inline bool valid() {
  if(!editor || !editor->saved.ready) return false;
  auto &e=*editor;
  if(!schedule_model::valid(e.draft)) return false;
  for(const auto &s:e.draft.slots) if(!e.saved.caps.valid(s.value))return false;
  return true;
}
inline void select_day(int day) {
  auto &e=*editor;e.day=day;e.vacation_view=day==7;e.selected=0;
  if(day==7)e.draft=e.saved.vacation_programme;
  else {
    e.last_weekday=day;
    auto found=std::find_if(e.saved.programmes.begin(),e.saved.programmes.end(),[&](const Programme &p){return p.days&(1U<<day);});
    if(found!=e.saved.programmes.end())e.draft=*found;
    else e.draft={"day_"+std::string(DAYS[day]),tr(txt::schedule_title),1U<<day,true,{{identity(),0,1440,{}}}};
    e.draft.days=1U<<day;e.draft.enabled=true;
  }
  e.original=e.draft;e.life.dirty=false;
}
inline bool read_value(JsonObject o, Heat &v, const schedule_model::Heating &caps) {
  std::string mode=o["mode"]|"";
  if(mode=="off") { v={}; return true; }
  if(mode!="heat"||!o["temperature"].is<float>())return false;
  v={false,o["temperature"].as<float>()}; return caps.valid(v);
}
inline void write_value(JsonObject o,const Heat &v) {
  o["mode"]=v.off?"off":"heat"; if(!v.off)o["temperature"]=v.temperature;
}
inline bool read_programme(JsonObject o,Programme &p,const schedule_model::Heating &caps) {
  p.id=o["id"]|""; p.name=o["name"]|"";
  if(p.id.size()>64 || p.name.size()>320 || !o["enabled"].is<bool>() || !o["days"].is<JsonArray>() ||
     !o["slots"].is<JsonArray>() || !o["start_date"].isNull() || !o["end_date"].isNull())return false;
  p.enabled=o["enabled"];p.days=0;p.slots.clear();
  for(JsonVariant day:o["days"].as<JsonArray>()) {
    std::string name=day.as<std::string>(); int found=-1;
    for(int i=0;i<7;++i)if(name==DAYS[i])found=i;
    if(found<0||(p.days&(1U<<found)))return false;
    p.days|=1U<<found;
  }
  for(JsonObject row:o["slots"].as<JsonArray>()) {
    if(p.slots.size()==schedule_model::MAX_SLOTS || !row["start"].is<int>() || !row["end"].is<int>())return false;
    schedule_model::Slot<Heat> slot;slot.id=row["id"]|"";slot.start=row["start"];slot.end=row["end"];
    if(slot.id.size()>64 || !read_value(row["value"].as<JsonObject>(),slot.value,caps))return false;
    p.slots.push_back(slot);
  }
  return schedule_model::valid(p);
}
inline void write_programme(JsonObject o,const Programme &p) {
  o["id"]=p.id;o["name"]=p.name;o["enabled"]=p.enabled;
  auto days=o["days"].to<JsonArray>();for(int i=0;i<7;++i)if(p.days&(1U<<i))days.add(DAYS[i]);
  auto slots=o["slots"].to<JsonArray>();
  for(const auto &s:p.slots) { auto row=slots.add<JsonObject>();row["id"]=s.id;row["start"]=s.start;row["end"]=s.end;write_value(row["value"].to<JsonObject>(),s.value); }
}
inline void request(const char *operation) {
  auto &e=*editor;if(e.life.pending)return;
  JsonDocument doc;doc["v"]=1;doc["rid"]=e.rid=++next_request;if(!e.rid)doc["rid"]=e.rid=++next_request;
  doc["entity"]=e.entity;doc["op"]=operation;
  if(std::string(operation)!="load") {
    doc["revision"]=e.saved.revision;
    JsonDocument value;write_programme(value.to<JsonObject>(),e.draft);
    if(e.vacation_view) { auto v=doc["vacation"].to<JsonObject>();v["enabled"]=e.vacation;v["slots"]=value["slots"]; }
    else {doc["day"]=DAYS[e.day];doc["slots"]=value["slots"]; }
  }
  std::string payload;serializeJson(doc,payload);
  if(payload.size()>4096) { e.error=tr(txt::schedule_timeout);e.redraw=true;return; }
  e.life.pending=true;e.received_begin=false;e.asked=esphome::millis();e.error.clear();e.redraw=true;
  e.send(payload);
}
inline bool receive(JsonObject o) {
  if(!visible() || !editor->life.pending || o["entity"].as<std::string>()!=editor->entity || o["rid"].as<uint32_t>()!=editor->rid)return true;
  auto &e=*editor;std::string stage=o["stage"]|"";
  if(stage=="error") {
    e.error=o["message"]|"";e.life.pending=false;e.life.uncertain=true;e.redraw=true;return true;
  }
  if(stage=="begin") {
    e.incoming={};auto &s=e.incoming;
    s.revision=o["revision"]|"";s.nonce=o["nonce"]|"";s.warning=o["warning"]|"";s.ready=o["ready"]|false;
    auto c=o["capabilities"].as<JsonObject>();
    if(c["profile"].as<std::string>()!="heating" || c["unit"].as<std::string>()!="°C")return false;
    s.caps.minimum=c["min"]|0.f;s.caps.maximum=c["max"]|0.f;s.caps.step=c["step"]|0.f;
    if(!std::isfinite(s.caps.minimum)||!std::isfinite(s.caps.maximum)||!std::isfinite(s.caps.step)||s.caps.minimum<=0 ||
       s.caps.maximum>30||s.caps.maximum<s.caps.minimum||s.caps.step<=0||s.caps.positions()>1000)return false;
    e.expected=o["count"]|99U;
    if(e.expected>schedule_model::MAX_PROGRAMMES || s.revision.size()>64 || s.nonce.size()!=16)return false;
    auto vacation=o["vacation"].as<JsonObject>();s.vacation=vacation["enabled"]|false;
    JsonDocument value;auto p=value.to<JsonObject>();
    p["id"]="vacation";p["name"]=tr(txt::schedule_vacation);p["enabled"]=true;
    auto days=p["days"].to<JsonArray>();for(auto day:DAYS)days.add(day);
    if(vacation["slots"].is<JsonArray>())p["slots"]=vacation["slots"];
    else {auto slot=p["slots"].to<JsonArray>().add<JsonObject>();slot["id"]="vacation_all_day";slot["start"]=0;slot["end"]=1440;slot["value"]=vacation["value"];}
    if(!read_programme(p,s.vacation_programme,s.caps))return false;
    e.received_begin=true;return true;
  }
  if(stage=="programme") {
    if(!e.received_begin || e.incoming.programmes.size()>=e.expected || o["index"].as<unsigned>()!=e.incoming.programmes.size())return false;
    Programme p;if(!read_programme(o["programme"].as<JsonObject>(),p,e.incoming.caps))return false;
    for(const auto &old:e.incoming.programmes)if(old.id==p.id)return false;
    e.incoming.programmes.push_back(std::move(p));return true;
  }
  if(stage!="end"||!e.received_begin||e.incoming.programmes.size()!=e.expected)return false;
  bool first=e.saved.revision.empty();e.saved=std::move(e.incoming);e.life.confirmed();
  if(first&&!e.saved.warning.empty())e.error=e.saved.warning;
  e.vacation=e.saved.vacation;
  int day=first&&e.saved.vacation?7:e.day;
  if(day==7&&!e.saved.vacation&&!first)day=e.last_weekday;
  unsigned selected=e.selected;select_day(day);
  e.selected=std::min(selected,unsigned(e.draft.slots.size()-1));e.redraw=true;
  if(e.life.leave_after_save) {e.life.leave_after_save=false;command(DISCARD);}
  return true;
}
inline lv_obj_t *label(lv_obj_t *parent,const std::string &text,Rect r,const lv_font_t *font,theme::Role role=theme::INK) {
  auto *o=lv_label_create(parent);lv_obj_set_pos(o,r.x,r.y);lv_obj_set_size(o,r.w,r.h);
  lv_obj_set_style_text_font(o,font,0);lv_obj_set_style_text_color(o,theme::color(role),0);
  lv_label_set_long_mode(o,LV_LABEL_LONG_DOT);lv_label_set_text(o,text.c_str());lv_obj_set_style_text_align(o,LV_TEXT_ALIGN_CENTER,0);
  lv_obj_remove_flag(o,LV_OBJ_FLAG_CLICKABLE);return o;
}
inline lv_obj_t *box(lv_obj_t *parent,Rect r,theme::Role role,int radius=0) {
  auto *o=lv_obj_create(parent);lv_obj_remove_style_all(o);lv_obj_set_pos(o,r.x,r.y);lv_obj_set_size(o,r.w,r.h);
  lv_obj_remove_flag(o,LV_OBJ_FLAG_SCROLLABLE);lv_obj_set_style_bg_color(o,theme::color(role),0);lv_obj_set_style_bg_opa(o,LV_OPA_COVER,0);
  lv_obj_set_style_radius(o,radius,0);return o;
}
inline void clicked(lv_event_t *event) {
  const int code=int(intptr_t(lv_event_get_user_data(event)));
  if(!editor || !screen_input::touch_guard.accept(esphome::millis(),700+code))return;
  command(code);
}
inline lv_obj_t *button(const std::string &text,Rect r,int code,bool icon=false,bool on=false,bool enabled=true,bool transparent=false) {
  auto &e=*editor;
  auto *o=box(e.root,r,on&&enabled?theme::ACCENT:theme::KEY,r.h/2);
  lv_obj_set_user_data(o,(void*)(intptr_t)code);
  if(transparent)lv_obj_set_style_bg_opa(o,LV_OPA_TRANSP,0);
  const auto *font=icon?e.icons:e.small;
  auto *caption=label(o,text,{0,(r.h-lv_font_get_line_height(font))/2,r.w,lv_font_get_line_height(font)},font,
                     !enabled?theme::OFF:on?theme::ON_ACCENT:transparent?theme::ACCENT:theme::INK);
  (void)caption;
  if(!enabled || e.life.pending)lv_obj_add_state(o,LV_STATE_DISABLED);
  lv_obj_add_event_cb(o,clicked,LV_EVENT_SHORT_CLICKED,(void*)(intptr_t)code);return o;
}
inline void navigate(int code) {
  auto &e=*editor;
  e.guard=false;e.destination=0;e.error.clear();e.page=0;
  if(code==BACK_CMD) {close();return;}
  if(code==RELOAD) {e.life.confirmed();e.saved.revision.clear();request("load");return;}
  if(code>=DAY_FIRST&&code<DAY_FIRST+7) {
    e.vacation=e.saved.vacation;
    select_day(e.vacation?7:code-DAY_FIRST);
  }
  else if(code==VACATION_CMD) {select_day(7);e.vacation=true;changed();}
  e.redraw=true;
}
inline void command(int code) {
  if(!editor)return;auto &e=*editor;
  if(e.life.pending)return;
  if(code==KEEP) {e.guard=false;e.error.clear();e.redraw=true;return;}
  if(code==DISCARD) {int target=e.destination;e.life.dirty=false;navigate(target?target:BACK_CMD);return;}
  if(code==SAVE_CMD||code==SAVE_LEAVE) {
    if(e.life.can_save(valid())) {e.life.leave_after_save=code==SAVE_LEAVE;request(e.vacation_view?"vacation":"day");}
    return;
  }
  if(code>=DAY_FIRST&&code<DAY_FIRST+7&&(e.vacation||code-DAY_FIRST==e.day))return;
  bool navigation=code==BACK_CMD||code==RELOAD||
      (code>=DAY_FIRST&&code<DAY_FIRST+7)||
      (code==VACATION_CMD&&!e.vacation_view);
  if(navigation) {
    if(e.life.dirty && code!=RELOAD) {e.destination=code;e.guard=true;e.redraw=true;return;}
    navigate(code);return;
  }
  if(code==VACATION_CMD) {e.vacation=!e.vacation;changed();}
  else if(code==ADD) {if(schedule_model::split(e.draft,e.selected,identity()))changed();}
  else if(code==REMOVE) {if(schedule_model::merge(e.draft,e.selected)){e.selected=std::min(e.selected,unsigned(e.draft.slots.size()-1));changed();}}
  else if(code==PREVIOUS&&e.selected) --e.selected;
  else if(code==NEXT&&e.selected+1<e.draft.slots.size()) ++e.selected;
  else if(code==PAGE_PREV) {e.page=std::max(0,e.page-1);}
  else if(code==PAGE_NEXT) {e.page=std::min(2,e.page+1);}
  e.redraw=true;
}
inline Heat &active_value() {return editor->draft.slots[editor->selected].value;}
inline void slider_event(lv_event_t *event) {
  if(!editor || editor->life.pending)return;auto &e=*editor;auto code=lv_event_get_code(event);
  if(code==LV_EVENT_PRESSED)e.dragging=true;
  if(code==LV_EVENT_VALUE_CHANGED) {
    active_value()=e.saved.caps.value(lv_slider_get_value((lv_obj_t*)lv_event_get_target(event)));
    if(e.value_label)lv_label_set_text(e.value_label,value_text(active_value()).c_str());
    changed();
  }
  if(code==LV_EVENT_RELEASED||code==LV_EVENT_PRESS_LOST) {e.dragging=false;changed();}
}
inline Rect boundary_time_rect(int side,int y) {
  auto &e=*editor;auto l=e.layout;const auto &s=e.draft.slots[e.selected];
  int pill=std::max(ui::px(59),3*int(lv_font_get_line_height(e.day_text)));
  int left=std::clamp(e.timeline.x+e.timeline.w*s.start/1440-pill/2,e.timeline.x,e.timeline.x+e.timeline.w-2*pill-l.gap);
  int right=std::clamp(e.timeline.x+e.timeline.w*s.end/1440-pill/2,left+pill+l.gap,e.timeline.x+e.timeline.w-pill);
  return {side?right:left,y,pill,l.key};
}
inline int boundary_handle_x(int side) {
  auto &e=*editor;auto l=e.layout;const auto &s=e.draft.slots[e.selected];
  int first=e.timeline.x,last=e.timeline.x+e.timeline.w-l.key;
  int left=std::clamp(first+e.timeline.w*s.start/1440-l.key/2,first,last);
  int right=std::clamp(first+e.timeline.w*s.end/1440-l.key/2,first,last);
  // Keep both drag handles reachable when the selected interval is very short.
  int separation=std::min(l.key+l.gap,e.timeline.w-l.key);
  if(e.selected>0&&e.selected+1<e.draft.slots.size()&&right-left<separation) {
    left=std::clamp((left+right-separation)/2,first,last-separation);
    right=left+separation;
  }
  return side?right:left;
}
inline void timeline_event(lv_event_t *event) {
  if(!editor || editor->life.pending)return;
  auto &e=*editor;auto code=lv_event_get_code(event);
  int boundary=int(intptr_t(lv_event_get_user_data(event)));
  auto *input=lv_indev_active();if(!input)return;lv_point_t p;lv_indev_get_point(input,&p);
  int minute=std::clamp((int(p.x)-e.timeline.x)*1440/std::max(1,e.timeline.w),0,1440);
  if(boundary<0) {
    if(code==LV_EVENT_SHORT_CLICKED && screen_input::touch_guard.accept(esphome::millis(),750)) {
      for(unsigned i=0;i<e.draft.slots.size();++i)if(minute>=e.draft.slots[i].start&&minute<e.draft.slots[i].end)e.selected=i;
      e.redraw=true;
    }
    return;
  }
  if(code==LV_EVENT_PRESSED) {e.dragging=true;e.drag_anchor_x=p.x;e.drag_anchor_minute=e.draft.slots[boundary].start;}
  if(code==LV_EVENT_PRESSING) {
    minute=e.drag_anchor_minute+(int(p.x)-e.drag_anchor_x)*1440/std::max(1,e.timeline.w);
    schedule_model::boundary(e.draft,boundary,minute);changed();
    for(unsigned i=0;i<e.segments.size();++i) {
      const auto &s=e.draft.slots[i];int x=e.timeline.w*s.start/1440,w=e.timeline.w*s.end/1440-x;
      lv_obj_set_x(e.segments[i],x);lv_obj_set_width(e.segments[i],std::max(1,w));
      if(auto *caption=lv_obj_get_child(e.segments[i],0))lv_obj_set_width(caption,std::max(1,w));
    }
    for(unsigned i=0;i<e.separators.size();++i)
      lv_obj_set_x(e.separators[i],e.timeline.w*e.draft.slots[i+1].start/1440-ui::px(1));
    // Update the same timeline in place, keeping the pressed handle alive.
    const auto &s=e.draft.slots[e.selected];
    for(int n=0;n<2;++n) {
      if(e.boundary_labels[n]) {
        lv_label_set_text(e.boundary_labels[n],clock(n?s.end:s.start).c_str());
        lv_obj_set_x(lv_obj_get_parent(e.boundary_labels[n]),boundary_time_rect(n,0).x);
      }
      if(e.boundary_handles[n])lv_obj_set_x(e.boundary_handles[n],boundary_handle_x(n));
      if(e.boundary_lines[n])lv_obj_set_x(e.boundary_lines[n],e.timeline.x+e.timeline.w*(n?s.end:s.start)/1440-ui::px(1));
    }
  }
  if(code==LV_EVENT_RELEASED||code==LV_EVENT_PRESS_LOST) {e.dragging=false;changed();}
}
inline int draw_days(int y) {
  auto &e=*editor;auto l=e.layout;int cell=(l.body.w-(l.day_columns-1)*l.gap)/l.day_columns;
  for(int i=0;i<8;++i) {
    Rect r{l.pad+(i%l.day_columns)*(cell+l.gap),y+(i/l.day_columns)*(l.key+l.gap),cell,l.key};
    bool selected=i==7?e.vacation:i==e.day;
    bool enabled=i==7||!e.vacation;
    auto *key=button("",r,i==7?VACATION_CMD:DAY_FIRST+i,false,selected,enabled);
    lv_obj_set_style_radius(key,ui::px(10),0);
    auto ink=!enabled?theme::OFF:selected?theme::ON_ACCENT:theme::INK;
    int ih=lv_font_get_line_height(e.day_icons),th=lv_font_get_line_height(e.day_text);
    label(key,i==7?VACATION:CALENDAR,{0,(r.h-ih)/2,r.w,ih},e.day_icons,ink);
    if(i<7)label(key,tr(txt::date_weekdays_min+(i+1)%7),{0,(r.h-th)/2+ih/7,r.w,th},e.day_text,ink);
  }
  return y+l.day_rows*(l.key+l.gap);
}
inline int draw_timeline(int y,int available) {
  auto &e=*editor;auto l=e.layout;int fh=lv_font_get_line_height(e.small);
  int bar_h=std::max(fh+l.gap,std::min(ui::px(52),available-2*l.key-fh-3*l.gap));
  int bar_y=y+l.key+l.gap;
  int axis=bar_y+bar_h+l.gap;
  int inset=ui::px(8);e.timeline={l.pad+inset,bar_y,l.body.w-2*inset,bar_h};
  auto *card=box(e.root,{l.pad,y,l.body.w,axis+fh+l.gap-y},theme::CARD,ui::px(18));
  lv_obj_set_style_border_width(card,ui::px(1),0);lv_obj_set_style_border_color(card,theme::color(theme::LINE),0);
  lv_obj_remove_flag(card,LV_OBJ_FLAG_CLICKABLE);
  {
    auto *track=box(e.root,e.timeline,theme::TRACK);
    lv_obj_set_user_data(track,(void*)(intptr_t)-1);
    lv_obj_add_event_cb(track,timeline_event,LV_EVENT_SHORT_CLICKED,(void*)(intptr_t)-1);
    for(unsigned i=0;i<e.draft.slots.size();++i) {
      const auto &s=e.draft.slots[i];int x=e.timeline.w*s.start/1440,w=e.timeline.w*s.end/1440-x;
      auto *segment=box(track,{x,0,std::max(1,w),bar_h},s.value.off?theme::TRACK:theme::ACCENT_TINT);
      e.segments.push_back(segment);
      lv_obj_remove_flag(segment,LV_OBJ_FLAG_CLICKABLE);
      if(!s.value.off)lv_obj_set_style_bg_color(segment,theme::rgb(e.background?theme::surface(e.background):theme::hex(theme::ACCENT_TINT)),0);
      if(i==e.selected) {
        lv_obj_set_style_bg_color(segment,theme::rgb(theme::surface(e.background?e.background:theme::swatch("orange"))),0);
        lv_obj_set_style_border_width(segment,ui::px(2),0);lv_obj_set_style_border_color(segment,theme::rgb(theme::ha::DEEP_ORANGE),0);
      }
      if(w>2*fh)label(segment,value_text(s.value),{0,(bar_h-fh)/2,w,fh},e.small);
    }
    // Every slot needs a visible edge, including equal-colour unselected slots.
    for(unsigned i=1;i<e.draft.slots.size();++i) {
      auto *line=box(track,{e.timeline.w*e.draft.slots[i].start/1440-ui::px(1),0,ui::px(2),bar_h},theme::CARD);
      lv_obj_remove_flag(line,LV_OBJ_FLAG_CLICKABLE);e.separators.push_back(line);
    }
    const auto &s=e.draft.slots[e.selected];
    for(int n=0;n<2;++n) {
      int boundary=int(e.selected)+n;
      bool editable=boundary>0&&boundary<int(e.draft.slots.size());
      auto r=boundary_time_rect(n,y);
      // Display-only indicators, with the short rectangle from the wireframe.
      int th=lv_font_get_line_height(e.day_text),badge_h=std::max(th,ui::px(27));
      r.y+=(r.h-badge_h)/2;r.h=badge_h;
      auto *pill=box(e.root,r,editable?theme::ACCENT:theme::KEY,ui::px(6));
      lv_obj_remove_flag(pill,LV_OBJ_FLAG_CLICKABLE);
      e.boundary_labels[n]=label(pill,clock(n?s.end:s.start),{0,(r.h-th)/2,r.w,th},e.day_text,editable?theme::ON_ACCENT:theme::OFF);
      if(editable) {
        e.boundary_lines[n]=box(e.root,{e.timeline.x+e.timeline.w*(n?s.end:s.start)/1440-ui::px(1),r.y+r.h,
            ui::px(2),bar_y+bar_h-r.y-r.h},theme::CARD);
        lv_obj_remove_flag(e.boundary_lines[n],LV_OBJ_FLAG_CLICKABLE);
      }
    }
    // Only the handles adjust times; all boundaries snap to five minutes.
    for(int n=0;n<2;++n) {
      int boundary=int(e.selected)+n;if(boundary==0||boundary==int(e.draft.slots.size()))continue;
      auto *handle=box(e.root,{boundary_handle_x(n),bar_y+bar_h/2-l.key/2,l.key,l.key},theme::KNOB);
      lv_obj_set_style_bg_opa(handle,LV_OPA_TRANSP,0);
      int diameter=ui::px(28),offset=(l.key-diameter)/2;
      auto *knob=box(handle,{offset,offset,diameter,diameter},theme::KNOB,diameter/2);
      lv_obj_set_style_border_width(knob,ui::px(1),0);lv_obj_set_style_border_color(knob,theme::color(theme::LINE),0);
      lv_obj_remove_flag(knob,LV_OBJ_FLAG_CLICKABLE);
      e.boundary_handles[n]=handle;
      lv_obj_set_user_data(handle,(void*)(intptr_t)(300+boundary));
      int ih=lv_font_get_line_height(e.handle_icons);
      label(handle,LEFT,{(l.key-ih)/2-ui::px(5),(l.key-ih)/2,ih,ih},e.handle_icons,theme::SLATE);
      label(handle,RIGHT,{(l.key-ih)/2+ui::px(5),(l.key-ih)/2,ih,ih},e.handle_icons,theme::SLATE);
      lv_obj_add_event_cb(handle,timeline_event,LV_EVENT_ALL,(void*)(intptr_t)boundary);
    }
  }
  for(int i=0;i<=4;++i)label(e.root,clock(i*360),{e.timeline.x+std::clamp(e.timeline.w*i/4-2*fh,0,e.timeline.w-4*fh),axis,4*fh,fh},e.small,theme::SUBTLE);
  int tools=axis+fh+l.gap;
  {
    const int span=l.body.w-l.key;
    button(LEFT,{l.pad,tools,l.key,l.key},PREVIOUS,true,false,e.selected>0,true);
    button(PLUS,{l.pad+span/3,tools,l.key,l.key},ADD,true,false,e.draft.slots.size()<16&&e.draft.slots[e.selected].end-e.draft.slots[e.selected].start>=10,true);
    button(MINUS,{l.pad+2*span/3,tools,l.key,l.key},REMOVE,true,false,e.draft.slots.size()>1,true);
    button(RIGHT,{l.width-l.pad-l.key,tools,l.key,l.key},NEXT,true,false,e.selected+1<e.draft.slots.size(),true);
  }
  return tools+l.key+l.gap;
}
inline void draw_temperature(int y) {
  auto &e=*editor;auto l=e.layout;int fh=lv_font_get_line_height(e.small),value_w=4*fh;
  auto reach=overlay_card::reach(l.width,l.body.w);
  auto *card=box(e.root,{reach.x,y,reach.w,l.key},theme::CARD,ui::px(12));
  lv_obj_set_style_bg_color(card,theme::rgb(theme::surface(e.background)),0);
  if(e.transparent)lv_obj_set_style_bg_opa(card,LV_OPA_TRANSP,0);
  auto *slider=lv_slider_create(card);lv_obj_remove_style_all(slider);
  lv_obj_set_user_data(slider,(void*)(intptr_t)-2);
  int x=l.key/2,w=reach.w-value_w-l.key;
  lv_obj_set_pos(slider,x,l.key/2-ui::px(3));lv_obj_set_size(slider,w,ui::px(6));
  lv_slider_set_range(slider,0,e.saved.caps.positions());lv_slider_set_value(slider,e.saved.caps.position(active_value()),LV_ANIM_OFF);
  lv_obj_set_style_bg_color(slider,theme::color(theme::TRACK),LV_PART_MAIN);lv_obj_set_style_bg_opa(slider,LV_OPA_COVER,LV_PART_MAIN);
  lv_obj_set_style_bg_color(slider,theme::color(theme::ACCENT),LV_PART_INDICATOR);lv_obj_set_style_bg_opa(slider,LV_OPA_COVER,LV_PART_INDICATOR);
  lv_obj_set_style_bg_color(slider,theme::color(theme::SLIDER_KNOB),LV_PART_KNOB);lv_obj_set_style_bg_opa(slider,LV_OPA_COVER,LV_PART_KNOB);
  lv_obj_set_style_pad_all(slider,ui::px(8),LV_PART_KNOB);lv_obj_set_style_radius(slider,LV_RADIUS_CIRCLE,LV_PART_KNOB);
  overlay_card::touchable(slider,ui::px(6));lv_obj_add_event_cb(slider,slider_event,LV_EVENT_ALL,nullptr);
  if(e.life.pending||!e.saved.ready)lv_obj_add_state(slider,LV_STATE_DISABLED);
  e.value_label=label(card,value_text(active_value()),{reach.w-value_w,(l.key-fh)/2,value_w,fh},e.small);
}
inline void render() {
  if(!visible())return;auto &e=*editor;auto *root=e.root;
  lv_obj_clean(root);e.value_label=nullptr;e.redraw=false;e.segments.clear();e.separators.clear();
  e.boundary_labels[0]=e.boundary_labels[1]=e.boundary_handles[0]=e.boundary_handles[1]=nullptr;
  e.boundary_lines[0]=e.boundary_lines[1]=nullptr;
  overlay_card::frame(root,overlay_card::graph);
  int fh=lv_font_get_line_height(e.small);e.layout=schedule_layout::place(overlay_card::screen_width(),overlay_card::screen_height(),fh);
  auto l=e.layout;lv_obj_set_style_bg_color(root,theme::color(theme::PAGE),0);
  button(BACK,l.back,BACK_CMD,true);
  e.save_button=button(SAVE,l.save,SAVE_CMD,true,e.life.can_save(valid()),e.life.can_save(valid()));
  auto *caption=label(root,e.vacation_view?std::string(tr(txt::schedule_vacation))+" "+tr(e.vacation?txt::ha_on:txt::ha_off):tr(txt::schedule_title),
                      {l.title.x,l.title.y+(l.title.h-fh)/2,l.title.w,fh},e.small,theme::ACCENT);
  if(e.guard) {
    label(root,tr(txt::schedule_unsaved),{l.pad,l.header,l.body.w,fh*2},e.small);
    int y=l.header+fh*2;
    button(tr(txt::schedule_keep),{l.pad,y,l.body.w,l.key},KEEP);
    button(tr(txt::schedule_discard),{l.pad,y+l.key+l.gap,l.body.w,l.key},DISCARD);
    button(tr(txt::schedule_save_leave),{l.pad,y+2*(l.key+l.gap),l.body.w,l.key},SAVE_LEAVE,false,true,e.life.can_save(valid()));return;
  }
  if(!e.error.empty() || (!e.saved.ready&&!e.saved.revision.empty())) {
    std::string message=e.error.empty()?e.saved.warning:e.error;
    label(root,message,{l.pad,l.header,l.body.w,std::max(fh,l.body.h-2*l.key-l.gap)},e.small);
    button(tr(txt::schedule_reload),{l.pad,l.body_bottom-2*l.key-l.gap,l.body.w,l.key},RELOAD);
    if(e.saved.ready)button(tr(txt::schedule_keep),{l.pad,l.body_bottom-l.key,l.body.w,l.key},KEEP);return;
  }
  if(e.saved.revision.empty()) {label(root,tr(txt::schedule_loading),{l.pad,l.header,l.body.w,fh*2},e.font);return;}
  int y=l.header;
  if(!l.paged||e.page==0)y=draw_days(y)+l.gap;
  if(!l.paged||e.page==1)y=draw_timeline(y,l.paged?l.body.h:l.body_bottom-y-2*l.key)+l.gap;
  if(!l.paged||e.page==2)draw_temperature(y);
  if(l.paged) {
    button(LEFT,{l.pad,l.pager.y,l.key,l.key},PAGE_PREV,true,false,e.page>0);
    label(root,std::to_string(e.page+1)+" / 3",{l.pad+l.key,l.pager.y+(l.key-fh)/2,l.body.w-2*l.key,fh},e.small,theme::MUTED);
    button(RIGHT,{l.width-l.pad-l.key,l.pager.y,l.key,l.key},PAGE_NEXT,true,false,e.page<2);
  }
  if(e.life.pending)lv_label_set_text(caption,tr(txt::schedule_saving));
}
inline void palette(uint32_t background,bool transparent) {
  if(!editor || (editor->background==background&&editor->transparent==transparent))return;
  editor->background=background;editor->transparent=transparent;editor->redraw=true;
}
inline void open(const std::string &entity,const std::string &name,const lv_font_t *font,const lv_font_t *small,const lv_font_t *icons,
                 const lv_font_t *day_icons,const lv_font_t *day_text,const lv_font_t *handle_icons,uint32_t background,bool transparent,std::function<void(const std::string&)> send) {
  if(visible()&&editor->entity==entity)return;
  close();editor=std::make_unique<Editor>();auto &e=*editor;
  e.entity=entity;e.name=name;e.font=font;e.small=small;e.icons=icons;e.send=std::move(send);
  e.day_icons=day_icons;e.day_text=day_text;e.background=background;e.transparent=transparent;
  e.handle_icons=handle_icons;
  e.root=box(lv_screen_active(),{0,0,overlay_card::screen_width(),overlay_card::screen_height()},theme::PAGE);
  lv_obj_move_foreground(e.root);request("load");render();
}
inline void tick() {
  if(!visible())return;auto &e=*editor;
  if(e.life.pending && uint32_t(esphome::millis()-e.asked)>15000) {
    e.life.pending=false;e.life.uncertain=true;e.error=tr(txt::schedule_timeout);e.redraw=true;
  }
  if(e.redraw&&!e.dragging)render();
}
inline void restyle() {if(editor)editor->redraw=true;}
}  // namespace schedule_editor
