// The history card: numbers as a line with axes, states as a timeline.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the rules themselves, which are plain C++ without LVGL in history_view.h.
// What proves it: tests/test_history_view.cpp, tests/test_history_card.py.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// ---- History card (firmware 0.2.51+): numbers as a line with axes, states as a timeline ----
// Sensors, numbers, switches, binary sensors and people. The card asks the manager for the chosen range when it
// opens (an hour, a day or a week; always 24 averages or 96 slots) and draws what comes back. A finger on the
// graph shows the value or state and its time at the top, until it lifts.
inline bool history_card(const Tile &t){
  auto d=t.domain();
  return d=="sensor"||d=="binary_sensor"||d=="switch"||d=="input_boolean"||d=="person"||d=="number"||d=="input_number";
}
// Before the history arrives: a line for numbers, a timeline for the rest.
inline bool history_line_guess(const Tile &t){
  auto d=t.domain();
  if(d=="number"||d=="input_number")return true;
  if(d!="sensor"||t.device_class=="enum"||t.device_class=="timestamp"||t.device_class=="date")return false;
  if(!t.unit.empty())return true;
  char *end=nullptr;std::strtof(t.state.c_str(),&end);return end!=t.state.c_str();
}
// The open card's parts that a finger changes, and the plot: x, y, w, h on the screen.
struct HistoryChart {
  lv_obj_t *value=nullptr,*first=nullptr,*second=nullptr,*area=nullptr,*status=nullptr;
  int x=0,y=0,w=0,h=0;
  float bottom=0,top=1;
  // The highest and lowest moment the card shows: the history's, or the value now when it goes beyond them.
  float high=NAN,low=NAN;
  uint32_t high_at=0,low_at=0;
  bool line=true,ready=false;
  uint32_t accent=theme::ha::BLUE;
  std::string value_text,first_text,second_text;
  lv_point_precise_t *points=nullptr;unsigned count=0;
};
inline HistoryChart history_chart;
inline void history_forget(){
  auto &c=history_chart;c.value=c.first=c.second=c.area=c.status=nullptr;c.count=0;c.ready=false;c.high=c.low=NAN;
}
inline float history_y(float value){
  const auto &c=history_chart;
  return c.y+c.h-(std::clamp(value,c.bottom,c.top)-c.bottom)/(c.top-c.bottom)*c.h;
}
// Where a moment of the range lies across the plot, from its left edge.
inline float history_x(uint32_t at){
  const auto &h=history;const auto &c=history_chart;
  return float(std::clamp(at,h.start,h.end)-h.start)/float(std::max<uint32_t>(1,h.end-h.start))*(c.w-1);
}
// The history holds the open card's entity and range, and is new: the answer to this opening, or less than a
// minute old (a card opened again shows it at once while it asks).
inline bool history_fits(const Tile &t){
  return history.entity==t.entity&&history.hours==history_hours&&
    (history_answered||esphome::millis()-history_received_at<60000);
}
// Home Assistant's word for the state now: from this entity's history words, else the card's own. The history can
// still be the previous card's while this one waits for its answer.
inline std::string history_words(const Tile &t){
  if(!t.available())return tr(txt::ha_unavailable);
  if(history.entity==t.entity)for(const auto &pair:history.words)if(pair.first==t.state)return pair.second;
  return detail_state(t);
}
inline std::string history_clock(uint32_t epoch,bool weekday){
  return history_view::clock(epoch,history.offset,screen_settings::current.clock_24h!=0,weekday);
}
// The soft area under the line: two triangles per segment down to the plot's bottom, no layer buffer.
inline void history_fill(lv_event_t *e){
  const auto &c=history_chart;if(!c.line||c.count<2||!c.area)return;
  auto *layer=lv_event_get_layer(e);lv_area_t area;lv_obj_get_coords(c.area,&area);
  lv_draw_triangle_dsc_t dsc;lv_draw_triangle_dsc_init(&dsc);dsc.color=lv_color_hex(c.accent);dsc.opa=theme::fill_opacity();
  const lv_value_precise_t ox=area.x1,oy=area.y1,base=area.y2+1;
  for(unsigned i=0;i+1<c.count;++i){
    const auto &a=c.points[i],&b=c.points[i+1];
    dsc.p[0]={ox+a.x,oy+a.y};dsc.p[1]={ox+b.x,oy+b.y};dsc.p[2]={ox+b.x,base};lv_draw_triangle(layer,&dsc);
    dsc.p[1]=dsc.p[2];dsc.p[2]={ox+a.x,base};lv_draw_triangle(layer,&dsc);
  }
}
// The timeline: one rectangle per run, drawn in the bar's own draw event instead of an object each.
inline void history_bar(lv_event_t *e){
  const auto &h=history;if(h.line||!h.slots)return;
  auto *obj=lv_event_get_current_target_obj(e);auto *layer=lv_event_get_layer(e);
  lv_area_t area;lv_obj_get_coords(obj,&area);const int w=lv_area_get_width(&area);
  lv_draw_rect_dsc_t dsc;lv_draw_rect_dsc_init(&dsc);dsc.bg_opa=LV_OPA_COVER;
  for(size_t i=0;i<h.runs.size();++i){
    const int state=h.runs[i].state;
    const int x1=area.x1+w*h.runs[i].slot/h.slots,x2=area.x1+w*history_view::run_end(h.runs,h.slots,i)/h.slots-1;
    dsc.bg_color=lv_color_hex(state<0||state>=static_cast<int>(h.states.size())?theme::hex(theme::TRACK):theme::state(h.states[state].color));
    lv_area_t piece{x1,area.y1,std::max(x1,x2),area.y2};lv_draw_rect(layer,&dsc,&piece);
  }
}
inline void history_restore(){
  auto &c=history_chart;
  if(c.value){label(c.value,c.value_text);lv_obj_set_style_text_color(c.value,theme::color(theme::INK),0);}
  if(c.first)label(c.first,c.first_text);
  if(c.second)label(c.second,c.second_text);
}
// A finger on the graph: the value (or state) of the moment under it, and when, at the top of the card. The graph
// itself stays as it is.
inline void history_scrub(lv_event_t *e){
  auto &c=history_chart;const auto &h=history;auto code=lv_event_get_code(e);
  if(code==LV_EVENT_RELEASED||code==LV_EVENT_PRESS_LOST){history_restore();return;}
  if((code!=LV_EVENT_PRESSED&&code!=LV_EVENT_PRESSING)||!c.ready||!c.value||!lv_indev_active())return;
  lv_point_t point;lv_indev_get_point(lv_indev_active(),&point);
  // A finger's point is the screen's; the plot's own x is the card's, and a card that does not fill the
  // glass stands in the middle of it. Reading the two against each other put the whole graph a card's
  // left edge too far left: on a ten-inch screen the middle of the glass already read "now" and the
  // card's own left half read the start of the range (firmware 0.2.82).
  const float fraction=std::clamp(float(point.x-detail_screen_x(c.x))/float(std::max(1,c.w)),0.0f,1.0f);
  const bool week=h.hours==168;
  if(c.line){
    // A part without a value (before the sensor existed, while it was unavailable) says so.
    const int i=history_view::part_at(fraction);
    const uint64_t span=h.end-h.start;
    const uint32_t begin=h.start+static_cast<uint32_t>(span*i/history_view::PARTS),finish=h.start+static_cast<uint32_t>(span*(i+1)/history_view::PARTS);
    label(c.value,h.has[i]?history_view::number(h.values[i],h.decimals,h.unit):std::string(tr(txt::history_no_data)));
    lv_obj_set_style_text_color(c.value,lv_color_hex(h.has[i]?theme::foreground(c.accent):theme::hex(theme::SUBTLE)),0);
    if(c.first)label(c.first,history_clock(begin,week)+" \u2013 "+history_clock(finish,false));
    if(c.second)label(c.second,!h.has[i]?std::string():h.hours==1?std::string(tr(txt::history_average)):fill(txt::history_average_of,"duration",history_view::duration(finish-begin)));
  }else{
    // A run reads the real times of its state, not the slots it covers: a door open for 5 minutes says 5 min.
    const int r=history_view::run_at(h.runs,h.slots,fraction);if(r<0)return;
    const auto &run=h.runs[r];
    const uint32_t begin=h.start+run.begin,finish=h.start+run.end;
    label(c.value,run.state<0||run.state>=static_cast<int>(h.states.size())?std::string(tr(txt::history_no_data)):h.states[run.state].label);
    if(c.first)label(c.first,history_clock(begin,week)+" \u2013 "+history_clock(finish,week&&finish-begin>=43200));
    if(c.second)label(c.second,history_view::duration(run.seconds));
  }
}
// The transparent area a finger scrubs, over the graph and a little around it; it keeps the finger while it drags.
inline void history_touch(int x,int y,int w,int h){
  auto *area=lv_obj_create(detail_root);lv_obj_remove_style_all(area);lv_obj_set_pos(area,x,y);lv_obj_set_size(area,w,h);
  lv_obj_add_flag(area,LV_OBJ_FLAG_CLICKABLE);lv_obj_add_flag(area,LV_OBJ_FLAG_PRESS_LOCK);
  lv_obj_remove_flag(area,LV_OBJ_FLAG_SCROLLABLE);lv_obj_remove_flag(area,LV_OBJ_FLAG_GESTURE_BUBBLE);
  lv_obj_add_event_cb(area,history_scrub,LV_EVENT_ALL,nullptr);
}
// Times below the graph: round clock times (weekdays for a week) where they fit, and "Now" at the end.
inline void history_times(int x,int w,int y,const lv_font_t *font,bool large){
  const auto &h=history;
  const lv_font_t *bold=detail_font?detail_font:font;
  const int now_w=text_width(tr(txt::history_now),bold),gap=ui::px(large?10:6);
  detail_text(detail_root,tr(txt::history_now),x+w-now_w,y,now_w+2,bold,LV_TEXT_ALIGN_LEFT,theme::INK);
  int last=x-1000;
  for(uint32_t at:h.times){
    if(at<=h.start||at>=h.end)continue;
    const std::string words=h.hours==168?history_view::clock(at,h.offset,true,true).substr(0,3)
      :history_view::axis_clock(at,h.offset,screen_settings::current.clock_24h!=0);
    const int tw=text_width(words,font),cx=x+static_cast<int>(std::lround(float(at-h.start)/float(h.end-h.start)*w));
    const int left=std::max(x-(ui::px(large?8:4)),cx-tw/2);
    if(left<=last+gap||left+tw>x+w-now_w-gap)continue;
    detail_shape(detail_root,cx,y-(ui::px(large?7:4)),1,ui::px(large?5:3),theme::TICK,0);
    detail_text(detail_root,words,left,y,tw+2,font,LV_TEXT_ALIGN_LEFT,theme::SUBTLE);
    last=left+tw;
  }
}
inline void render_history_line(bool large,int card_x,int card_y,int card_w,int card_h,const lv_font_t *small,float current){
  auto &c=history_chart;const auto &h=history;
  // The value now can lie outside the history (the last hour is not in the statistics yet): the plot makes room.
  c.bottom=h.bottom;c.top=h.top;
  if(std::isfinite(current)&&(current<c.bottom||current>c.top)){
    const float margin=(std::max(c.top,current)-std::min(c.bottom,current))*0.06f;
    if(current<c.bottom)c.bottom=current-margin;else c.top=current+margin;
  }
  const int label_h=lv_font_get_line_height(small),edge=ui::px(large?14:8);
  int label_w=0;for(const auto &tick:h.ticks)label_w=std::max(label_w,text_width(tick.second,small));
  c.x=card_x+edge+label_w+(label_w?(ui::px(large?10:5)):0);c.w=card_x+card_w-(ui::px(large?18:10))-c.x;
  c.y=card_y+(ui::px(large?22:10));c.h=card_y+card_h-(label_h+(ui::px(large?16:8)))-c.y;
  if(c.w<40||c.h<24)return;
  for(const auto &tick:h.ticks){
    const int ty=static_cast<int>(std::lround(history_y(tick.first)));
    detail_shape(detail_root,c.x,ty,c.w,1,theme::GRID,0);
    detail_text(detail_root,tick.second,card_x+edge,ty-label_h/2,label_w+2,small,LV_TEXT_ALIGN_RIGHT,theme::SUBTLE);
  }
  // Through the middle of each part, from the left edge when the range begins with a value, to "Now" at the right
  // (the value now); a curve that never overshoots them, so the axis and the highest and lowest moment stay true.
  // The averages only reach the highest and lowest moment in their hour, so the line also runs through those two
  // moments: its peak and its valley are where the rings are.
  float xs[history_view::PARTS+4],ys[history_view::PARTS+4];unsigned n=0;
  for(int i=0;i<history_view::PARTS;++i){
    if(!h.has[i])continue;
    const float y=history_y(h.values[i])-c.y;
    if(i==0){xs[n]=0;ys[n++]=y;}
    xs[n]=history_view::part_middle(i)*(c.w-1);ys[n++]=y;
  }
  if(n&&std::isfinite(current)){xs[n]=float(c.w-1);ys[n++]=history_y(current)-c.y;}
  // A moment takes the place of its part's point, so the curve stays smooth; its ring goes where the point is.
  float high_x=history_x(c.high_at),low_x=history_x(c.low_at);
  if(n){
    const float snap=(c.w-1)/float(2*history_view::PARTS);
    int kept=-1;
    if(std::isfinite(c.high)&&(kept=history_view::through(xs,ys,n,history_view::PARTS+4,high_x,history_y(c.high)-c.y,snap))>=0)high_x=xs[kept];
    if(std::isfinite(c.low)){
      const int at=history_view::through(xs,ys,n,history_view::PARTS+4,low_x,history_y(c.low)-c.y,snap,kept);
      if(at>=0)low_x=xs[at];
    }
  }
  if(!c.points)c.points=new_points();
  c.count=n>=2?history_view::monotone(xs,ys,n,4,c.points,POINT_BUFFER):0;
  c.area=lv_obj_create(detail_root);lv_obj_remove_style_all(c.area);lv_obj_set_pos(c.area,c.x,c.y);lv_obj_set_size(c.area,c.w,c.h);
  lv_obj_remove_flag(c.area,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(c.area,LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_add_event_cb(c.area,history_fill,LV_EVENT_DRAW_MAIN,nullptr);
  if(c.count>=2){
    auto *stroke=lv_line_create(detail_root);lv_obj_remove_flag(stroke,LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_style_line_rounded(stroke,true,0);lv_obj_set_style_line_width(stroke,ui::px(large?3:2),0);
    lv_obj_set_style_line_color(stroke,lv_color_hex(c.accent),0);
    lv_line_set_points(stroke,c.points,c.count);lv_obj_set_pos(stroke,c.x,c.y);
  }
  // The highest and lowest moment as rings; the Guition writes their values beside them.
  const int ring=ui::px(large?12:8);
  auto marker=[&](float value,float at_x,bool high){
    const int mx=c.x+static_cast<int>(std::lround(at_x));
    const int my=static_cast<int>(std::lround(history_y(value)));
    auto *o=detail_shape(detail_root,mx-ring/2,my-ring/2,ring,ring,theme::CARD,ring/2);
    lv_obj_set_style_border_width(o,ui::px(large?3:2),0);lv_obj_set_style_border_color(o,lv_color_hex(c.accent),0);
    if(!large)return;
    const std::string words=history_view::number(value,h.decimals,"");
    const int lh=lv_font_get_line_height(detail_font),tw=text_width(words,detail_font)+2;
    int ly=high?my-ring/2-lh-2:my+ring/2+2;
    if(ly<card_y+4)ly=my+ring/2+2;
    if(ly+lh>c.y+c.h+6)ly=my-ring/2-lh-2;
    const int lx=std::max(c.x,std::min(mx-tw/2,c.x+c.w-tw));
    detail_text(detail_root,words,lx,ly,tw,detail_font,LV_TEXT_ALIGN_CENTER,theme::INK);
  };
  if(std::isfinite(c.high))marker(c.high,high_x,true);
  if(std::isfinite(c.low)&&c.low!=c.high)marker(c.low,low_x,false);
  if(std::isfinite(current)){
    const int size=ui::px(large?12:8);
    auto *o=detail_shape(detail_root,c.x+c.w-1-size/2,static_cast<int>(std::lround(history_y(current)))-size/2,size,size,c.accent,size/2);
    lv_obj_set_style_border_width(o,2,0);lv_obj_set_style_border_color(o,theme::color(theme::CARD),0);
  }
  history_times(c.x,c.w,c.y+c.h+(ui::px(large?8:4)),small,large);
  history_touch(c.x-(ui::px(large?14:8)),card_y,c.w+(ui::px(large?28:16)),card_h);
}
inline void render_history_timeline(bool large,int card_x,int card_y,int card_w,int card_h,const lv_font_t *small){
  auto &c=history_chart;const auto &h=history;
  const int edge=ui::px(large?16:8),label_h=lv_font_get_line_height(small),times_gap=ui::px(large?8:4),legend_gap=ui::px(large?16:6);
  const int row_h=label_h+(ui::px(large?10:3)),square=ui::px(large?14:8);
  c.x=card_x+edge;c.w=card_w-2*edge;c.h=ui::px(large?56:24);
  // Bar, times and legend as one block in the middle of the card; a legend that does not fit loses its last rows.
  const int above=c.h+times_gap+label_h+legend_gap;
  const int rows=std::max(1,std::min(static_cast<int>((h.states.size()+1)/2),(card_h-2*edge-above+row_h-label_h)/row_h));
  const int block=above+rows*row_h-(row_h-label_h);
  c.y=card_y+std::max(edge,(card_h-block)/2);
  auto *bar=lv_obj_create(detail_root);lv_obj_remove_style_all(bar);lv_obj_set_pos(bar,c.x,c.y);lv_obj_set_size(bar,c.w,c.h);
  lv_obj_remove_flag(bar,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(bar,LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_add_event_cb(bar,history_bar,LV_EVENT_DRAW_MAIN,nullptr);
  history_times(c.x,c.w,c.y+c.h+times_gap,small,large);
  // Every state with its colour and its time, in two columns. The bar is the graph and takes the glass; the
  // legend is read, so it keeps a hand's width in the middle, where a time at the far edge would be lost.
  const auto list=overlay_card::reach(card_w,c.w);
  const int top=c.y+above,col_w=list.w/2,list_x=card_x+list.x;
  const size_t shown=std::min<size_t>(h.states.size(),static_cast<size_t>(rows)*2);
  for(size_t i=0;i<shown;++i){
    const int lx=list_x+static_cast<int>(i%2)*col_w,ly=top+static_cast<int>(i/2)*row_h;
    detail_shape(detail_root,lx,ly+(label_h-square)/2,square,square,theme::state(h.states[i].color),ui::px(large?4:2));
    const std::string time=history_view::duration(h.states[i].seconds);
    const int tw=text_width(time,small)+2,words_x=lx+square+(ui::px(large?10:5)),time_x=lx+col_w-(ui::px(large?14:8))-tw;
    detail_text(detail_root,h.states[i].label,words_x,ly,std::max(8,time_x-words_x-6),small,LV_TEXT_ALIGN_LEFT,theme::INK);
    detail_text(detail_root,time,time_x,ly,tw,small,LV_TEXT_ALIGN_LEFT,theme::SUBTLE);
  }
  history_touch(c.x-(ui::px(large?14:8)),card_y,c.w+(ui::px(large?28:16)),c.y+c.h+(ui::px(large?24:12))-card_y);
}
// The range: an hour, a day or a week, as one segmented row. It asks the manager, not Home Assistant, so
// waiting for a command does not lock it. However thin the row is drawn, each key keeps a finger's worth
// of touch area (overlay_card::touchable), as the other segmented rows do, and the strip under the row down to the
// glass's edge (detail_reach_down, `bottom`).
inline void history_ranges(int x,int y,int w,int h,int bottom){
  static const uint32_t hours[]={1,24,168};
  const char *const words[]={tr(txt::history_range_hour),tr(txt::history_range_day),tr(txt::history_range_week)};
  const lv_font_t *font=control_font?control_font:detail_font;
  auto *track=detail_shape(detail_root,x,y,w,h,theme::CARD,h/2);
  lv_obj_set_style_border_width(track,1,0);lv_obj_set_style_border_color(track,theme::color(theme::LINE),0);
  const int inset=std::max(3,h/10),sw=(w-2*inset)/3;
  for(int i=0;i<3;++i){
    const bool selected=history_hours==hours[i];
    const int segment_w=i==2?w-2*inset-2*sw:sw;
    auto *segment=detail_button(words[i],x+inset+i*sw,y+inset,segment_w,h-2*inset,160+i);
    lv_obj_set_style_radius(segment,(h-2*inset)/2,0);
    lv_obj_set_style_bg_color(segment,theme::color(theme::ACCENT),0);
    lv_obj_set_style_bg_opa(segment,selected?LV_OPA_COVER:LV_OPA_TRANSP,0);
    lv_obj_set_style_bg_opa(segment,LV_OPA_COVER,LV_STATE_PRESSED);
    if(!selected)lv_obj_set_style_bg_color(segment,theme::color(theme::ACCENT_TINT),LV_STATE_PRESSED);
    button_words(segment,font,theme::hex(selected?theme::ON_ACCENT:theme::INK),segment_w-6);
    overlay_card::touchable(segment,h-2*inset);
    if(detail_action_count&&detail_actions[detail_action_count-1]==segment)--detail_action_count;
    detail_reach_down(segment,160+i,bottom);
  }
}
inline void render_history_detail(const Tile &t,bool large,int width,int height,int pad){
  auto &c=history_chart;const auto &h=history;auto d=t.domain();
  history_forget();
  // Asked once per opening and range; again after 30 s without an answer (see tick).
  if(history_asked_entity!=t.entity||history_asked_hours!=history_hours||(!history_fits(t)&&esphome::millis()-history_asked_at>30000))
    history_request(t.entity,history_hours);
  c.ready=history_fits(t);
  const bool line=c.ready?h.line:history_line_guess(t);
  c.line=line;c.accent=tile_controls::accent(t);
  const lv_font_t *big=watch_value_font?watch_value_font:(watch_font?watch_font:detail_font);
  const lv_font_t *text=control_font?control_font:detail_font;
  const lv_font_t *small=small_font?small_font:detail_font;
  // The header: the value now (or the state), and at the right what the history says about it.
  char *end=nullptr;const float parsed=std::strtof(t.state.c_str(),&end);
  const bool numeric=end!=t.state.c_str()&&std::isfinite(parsed)&&t.available();
  const float current=numeric?parsed:NAN;
  c.first_text.clear();c.second_text.clear();
  if(line){
    int decimals=0;const auto dot=t.state.find('.');if(dot!=std::string::npos)decimals=static_cast<int>(std::min<size_t>(4,t.state.size()-dot-1));
    if(c.ready)decimals=h.decimals;
    // Home Assistant's own words for a value where it has them (a duration in hours and minutes, firmware 0.56.0+).
    c.value_text=!t.available()?std::string(tr(txt::ha_unavailable)):numeric&&!t.extra().state_word.empty()?t.extra().state_word
                :numeric?history_view::number(current,decimals,t.unit):t.state;
    if(c.ready){
      // The value now counts too: it can lie beyond the history (the running hour is not in the statistics yet).
      if(h.has_high){c.high=h.high;c.high_at=h.high_at;}
      if(h.has_low){c.low=h.low;c.low_at=h.low_at;}
      if(std::isfinite(current)&&std::isfinite(c.high)&&current>c.high){c.high=current;c.high_at=h.end;}
      if(std::isfinite(current)&&std::isfinite(c.low)&&current<c.low){c.low=current;c.low_at=h.end;}
    }
    if(std::isfinite(c.high))c.first_text=fill(txt::history_high,"value",history_view::number(c.high,h.decimals,h.unit))+" \u00B7 "+history_clock(c.high_at,h.hours==168);
    if(std::isfinite(c.low))c.second_text=fill(txt::history_low,"value",history_view::number(c.low,h.decimals,h.unit))+" \u00B7 "+history_clock(c.low_at,h.hours==168);
  }else{
    c.value_text=history_words(t);
    if(c.ready&&h.active>=0){
      c.first_text=h.states[h.active].label+" \u00B7 "+history_view::duration(h.states[h.active].seconds);
      c.second_text=h.began?plural(txt::history_times,h.began):"";
    }
  }
  const int row=ui::px(large?84:50),row_h=lv_font_get_line_height(big),text_h=lv_font_get_line_height(text);
  int right=width-pad-(ui::px(large?8:4));
  if(t.is_switch()){
    const int sw=ui::px(large?84:52),sh=ui::px(large?46:28);
    detail_switch=lv_switch_create(detail_root);
    lv_obj_set_size(detail_switch,sw,sh);lv_obj_set_pos(detail_switch,right-sw,row+(row_h-sh)/2);
    lv_obj_set_style_bg_color(detail_switch,theme::color(theme::SWITCH_OFF),LV_PART_MAIN);
    lv_obj_set_style_bg_color(detail_switch,lv_color_hex(theme::ha::SWITCH_ON),static_cast<lv_style_selector_t>(LV_PART_INDICATOR)|LV_STATE_CHECKED);
    lv_obj_set_style_bg_color(detail_switch,theme::color(theme::KNOB),LV_PART_KNOB);
    lv_obj_set_style_opa(detail_switch,LV_OPA_50,LV_STATE_DISABLED);
    if(t.state=="on")lv_obj_add_state(detail_switch,LV_STATE_CHECKED);
    lv_obj_add_event_cb(detail_switch,[](lv_event_t *e){
      if(detail_index>=model.count)return;
      auto &tile=model.tiles[detail_index];auto *control=lv_event_get_target_obj(e);
      bool allowed=fresh() && tile.available() && !tile.waiting(esphome::millis()) &&
        screen_input::touch_guard.accept(esphome::millis(),350);
      bool requested_on=lv_obj_has_state(control,LV_STATE_CHECKED);
      // A tap that may not act leaves the switch where the tile is; one that may is a wish (docs/OPTIMISTIC.md).
      if(allowed && requested_on!=(tile.state=="on")){toggle_wish(tile);return;}
      if(tile.state=="on")lv_obj_add_state(control,LV_STATE_CHECKED);else lv_obj_remove_state(control,LV_STATE_CHECKED);
    },LV_EVENT_VALUE_CHANGED,nullptr);
    if(detail_action_count<32)detail_actions[detail_action_count++]=detail_switch;
    right-=sw+(ui::px(large?14:8));
  }
  // The value column fits the widest text a finger can show there, so a readout never runs into the texts beside it.
  int widest=text_width(c.value_text,big);
  if(c.ready)widest=std::max(widest,text_width(tr(txt::history_no_data),big));
  if(c.ready&&line){for(int i=0;i<history_view::PARTS;++i)if(h.has[i])widest=std::max(widest,text_width(history_view::number(h.values[i],h.decimals,h.unit),big));}
  else if(c.ready){for(const auto &s:h.states)widest=std::max(widest,text_width(s.label,big));}
  const int value_x=pad+(ui::px(large?8:4)),value_w=std::min(widest+6,(width-2*pad)*11/20);
  c.value=detail_text(detail_root,c.value_text,value_x,row,value_w,big,LV_TEXT_ALIGN_LEFT,theme::INK);
  const int words_x=value_x+value_w+(ui::px(large?12:6)),words_w=std::max(20,right-words_x),words_y=row+(row_h-2*text_h)/2;
  c.first=detail_text(detail_root,c.first_text,words_x,words_y,words_w,text,LV_TEXT_ALIGN_RIGHT,theme::MUTED);
  c.second=detail_text(detail_root,c.second_text,words_x,words_y+text_h,words_w,text,LV_TEXT_ALIGN_RIGHT,theme::MUTED);
  int top=row+std::max(row_h,2*text_h)+(ui::px(large?10:4));
  if(d=="number"||d=="input_number"){
    const int slider_h=ui::px(large?24:14);
    // A slider is dragged, so it keeps a hand's width however wide the card's graph is.
    const auto bar=overlay_card::reach(width,width-2*pad-(ui::px(large?28:20)));
    auto *slider=lv_slider_create(detail_root);lv_obj_set_pos(slider,bar.x,top+(ui::px(large?10:5)));
    lv_obj_set_size(slider,bar.w,slider_h);lv_slider_set_range(slider,0,1000);
    lv_slider_set_value(slider,slider_value(t),LV_ANIM_OFF);lv_obj_set_style_bg_color(slider,theme::color(theme::SLIDER_KNOB),LV_PART_KNOB);
    lv_obj_add_event_cb(slider,slider_event,LV_EVENT_ALL,(void*)(uintptr_t)detail_index);
    top+=slider_h+(ui::px(large?22:12));
  }
  const int range_h=ui::px(large?48:28),bottom=height-(ui::px(large?16:6)),range_y=bottom-range_h,card_h=range_y-(ui::px(large?10:5))-top;
  detail_card(pad,top,width-2*pad,card_h);
  const bool empty=c.ready&&(line?std::none_of(h.has,h.has+history_view::PARTS,[](bool v){return v;}):h.states.empty());
  if(!c.ready||empty){
    c.status=detail_text(detail_root,tr(!c.ready?txt::history_loading:txt::history_empty),pad,top+(card_h-text_h)/2,width-2*pad,text,LV_TEXT_ALIGN_CENTER,theme::SUBTLE);
  }else if(line){
    render_history_line(large,pad,top,width-2*pad,card_h,small,current);
  }else{
    render_history_timeline(large,pad,top,width-2*pad,card_h,small);
  }
  // The graph took the glass; the keys under it keep a hand's width and stand in the middle of the card.
  const auto keys=overlay_card::reach(width,width-2*pad);
  history_ranges(keys.x,range_y,keys.w,range_h,height);
  card_shaped(t,picture_card_shape);
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
