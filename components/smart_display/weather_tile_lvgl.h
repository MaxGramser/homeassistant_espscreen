// The weather tile: its forecast and its week.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the rules themselves, which are plain C++ without LVGL in forecast_tile.h, weather_week.h.
// What proves it: tests/test_forecast_tile.cpp, tests/test_weather_week.cpp.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// ---- The weather tile's forecast (firmware 0.3.3): forecast_tile.h decides where, this draws ----
// Today among the forecast's days: the day's short name as the manager wrote it (screen.date.weekdays_min) against
// the screen's own clock in the same words. -1 while the clock is not set, or when the two speak another language.
inline int forecast_today(const Tile &t){
  const auto now=now_time?now_time():esphome::ESPTime{};
  if(!now.is_valid()||now.day_of_week<1||now.day_of_week>7)return -1;
  const std::string name=tr(txt::date_weekdays_min+now.day_of_week-1);
  const auto &days=t.extra().forecast;
  for(size_t k=0;k<days.size()&&k<(size_t)forecast_tile::DAYS;++k)if(days[k].day==name)return (int)k;
  return -1;
}
// A rounded bar with a second one inside it: the week's range as the track, one day's range as the fill.
inline lv_obj_t *part_bar(Widgets &w,unsigned i,int x,int y,int width,int height){
  auto *&p=w.parts[i];
  if(!p){
    p=lv_obj_create(w.extra);
    for(auto *o:{p,lv_obj_create(p)}){
      lv_obj_remove_style_all(o);lv_obj_set_style_bg_opa(o,LV_OPA_COVER,0);lv_obj_set_style_radius(o,LV_RADIUS_CIRCLE,0);
      lv_obj_remove_flag(o,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(o,LV_OBJ_FLAG_SCROLLABLE);
    }
    lv_obj_set_style_bg_grad_dir(lv_obj_get_child(p,0),LV_GRAD_DIR_HOR,0);
  }
  lv_obj_set_pos(p,x,y);lv_obj_set_size(p,std::max(1,width),std::max(1,height));return p;
}
// ---- The weather tile's week (design study 10-09): a card of two rows or more, or a whole page ----
// The card's head row as every card has it (its circle and icon, its name, the condition, the temperature large at the
// end), the week under it in the same light grid as the card a tap opens. A wide, low card (a 4x2) puts the weather
// now in a column at the left, a light line, and the week over the full height at the right, where it reaches a higher
// tier. Every colour is set on every render, as render_forecast does. False when the week fits in no tier here: the
// card then keeps the forecast's own forms.
inline bool render_week(Widgets &w,const Tile &t,bool large,int width,int height){
  const Extra &x=t.extra();
  const lv_font_t *bold=w.title_font?w.title_font:lv_obj_get_style_text_font(w.title,LV_PART_MAIN),*text=w.value_font;
  const lv_font_t *temp_font=watch_value_font?watch_value_font:bold,*hero_font=setpoint_font?setpoint_font:temp_font;
  const lv_font_t *line_font=control_font?control_font:text;
  const int circle=w.base_circle>0?w.base_circle:ui::px(large?54:36),gap=ui::px(large?10:6);
  const uint32_t ink=theme::hex(theme::INK),muted=theme::hex(theme::MUTED);
  const uint32_t sky=t.available()?weather_color_raw(t.state):theme::STATE_OFF;
  char now[16];if(std::isfinite(t.current))snprintf(now,sizeof(now),"%.0f°",t.current);else snprintf(now,sizeof(now),"--");
  const std::string cond=t.available()?weather_text(t.state):tr(txt::ha_unavailable);
  const std::string feels=std::isfinite(x.feels)?fill(txt::weather_feels_like,"n",(int)std::lround(x.feels)):"";
  auto chart=weather_chart_of(t,false);
  const bool wide=width>=height*12/5;
  // Where the week goes, and whether it fits there at all.
  int cx=0,cy=0,cw=width,ch=height,col=0;
  std::string hl;if(x.forecast.size())hl=degrees(x.forecast[0].high)+" / "+degrees(x.forecast[0].low);
  const lv_font_t *tf=hero_font;
  // A card of one row: the circle with the temperature and the condition beside it, as the forecast has always had it.
  const bool low=wide&&height<circle+gap+line_of(temp_font)+line_of(line_font);
  if(low){
    // The largest face that leaves the condition its line under it, as the forecast has always had it; else the largest
    // that fits alone.
    tf=nullptr;
    for(const lv_font_t *f:{hero_font,temp_font,watch_font})if(f&&face_covers(f,now)&&line_of(f)+line_of(text)<=height){tf=f;break;}
    if(!tf)for(const lv_font_t *f:{hero_font,temp_font,watch_font})if(f&&face_covers(f,now)&&line_of(f)<=height){tf=f;break;}
    if(!tf)tf=bold;
    const bool line=line_of(tf)+line_of(text)<=height;
    col=std::min(circle,height)+gap+std::max(text_width(now,tf),line?text_width(cond,text):0)+gap;
    cx=col+gap+1+gap;cw=width-cx;
  }else if(wide){
    if(!face_covers(tf,now)||circle+gap+line_of(tf)+line_of(line_font)>height)tf=temp_font;
    col=std::max({circle+gap+std::max(text_width(t.name,bold),text_width(cond,text)),text_width(now,tf),text_width(hl,line_font)})+gap;
    cx=col+gap+1+gap;cw=width-cx;
  }else{cy=circle+gap;ch=height-cy;}
  const int tier=weather_chart::week_tier(chart,cw,ch);
  // A card of two rows or more shows the line at least; one of a single row the days.
  if(tier<0||(!low&&tier<1))return false;
  begin_extra(w,"week",width,height);
  for(auto *p:w.parts)if(p)lv_obj_add_flag(p,LV_OBJ_FLAG_HIDDEN);
  auto show=[](lv_obj_t *p){lv_obj_remove_flag(p,LV_OBJ_FLAG_HIDDEN);return p;};
  auto words=[&](unsigned i,const lv_font_t *font,int px,int py,int pw,lv_text_align_t align,const std::string &s,uint32_t color){
    auto *p=show(part_label(w,i,font,px,py,pw,align,s));
    if(lv_label_get_long_mode(p)!=LV_LABEL_LONG_DOT)lv_label_set_long_mode(p,LV_LABEL_LONG_DOT);
    set_color(p,LV_STYLE_TEXT_COLOR,lv_color_hex(color));return p;
  };
  // The head: the circle in the condition's colour with its icon, as on every other card.
  const int disc_y=low?(height-std::min(circle,height))/2:0;
  auto *disc=show(part_dot(w,0,0,disc_y,std::min(circle,height)));
  set_color(disc,LV_STYLE_BG_COLOR,lv_color_hex(t.available()?theme::tint(sky,38):theme::hex(theme::TRACK)));
  const int gh=line_of(w.icon_font);
  words(1,w.icon_font,0,disc_y+(std::min(circle,height)-gh)/2,std::min(circle,height),LV_TEXT_ALIGN_CENTER,t.available()?weather_icon(t.state):"\U000F0595",t.available()?theme::icon(sky):theme::hex(theme::OFF));
  const int th=line_of(bold),nh=line_of(text),hy=(circle-th-nh)/2;
  if(low){
    const int c0=std::min(circle,height)+gap,tfh=line_of(tf);
    const bool line=tfh+nh<=height;
    const int ty=(height-tfh-(line?nh:0))/2;
    words(4,tf,c0,ty,col-c0,LV_TEXT_ALIGN_LEFT,now,ink);
    if(line)words(3,text,c0,ty+tfh,col-c0,LV_TEXT_ALIGN_LEFT,cond,muted);
    auto *rule=show(part_dot(w,6,col+gap,ui::px(4),1));
    lv_obj_set_size(rule,1,height-ui::px(8));lv_obj_set_style_radius(rule,0,0);
    set_color(rule,LV_STYLE_BG_COLOR,theme::color(theme::dark?theme::RAISED_LINE:theme::LINE));
  }else if(wide){
    words(2,bold,circle+gap,hy,col-circle-gap,LV_TEXT_ALIGN_LEFT,t.name,ink);
    words(3,text,circle+gap,hy+th,col-circle-gap,LV_TEXT_ALIGN_LEFT,cond,muted);
    const int ty=circle+(height-circle-line_of(tf)-line_of(line_font))/2;
    words(4,tf,0,ty,col,LV_TEXT_ALIGN_LEFT,now,ink);
    if(!hl.empty())words(7,line_font,0,ty+line_of(tf),col,LV_TEXT_ALIGN_LEFT,hl,muted);
    auto *rule=show(part_dot(w,6,col+gap,ui::px(4),1));
    lv_obj_set_size(rule,1,height-ui::px(8));lv_obj_set_style_radius(rule,0,0);
    set_color(rule,LV_STYLE_BG_COLOR,theme::color(theme::dark?theme::RAISED_LINE:theme::LINE));
  }else{
    // The temperature large at the end of the row where it fits beside the name; the line under the name says the
    // condition, and feels like where there is room for it.
    int right=width;
    const int nw=text_width(now,temp_font);
    if(line_of(temp_font)<=circle+ui::px(6)&&width-nw-circle-gap>=ui::px(large?110:70)){
      words(4,temp_font,width-nw-2,(circle-line_of(temp_font))/2,nw+2,LV_TEXT_ALIGN_RIGHT,now,ink);right=width-nw-gap;
    }
    const int room=right-circle-gap;
    std::string line=cond;
    if(!feels.empty()&&text_width(cond+" · "+feels,text)<=room)line=cond+" · "+feels;
    words(2,bold,circle+gap,hy,room,LV_TEXT_ALIGN_LEFT,t.name,ink);
    words(3,text,circle+gap,hy+th,room,LV_TEXT_ALIGN_LEFT,line,muted);
  }
  // The week: one object that owns what it draws (weather_chart.h).
  auto *&p=w.parts[5];
  if(!p)p=weather_chart::create(w.extra);
  show(p);lv_obj_set_pos(p,cx,cy);lv_obj_set_size(p,cw,ch);
  weather_chart::set(p,std::move(chart));
  return true;
}
// The weather now (the condition in its circle, the temperature, the word) and the coming days, in the form the
// card's cell holds: days as columns beside it on a card of one row, as rows under it with the week's range as bars
// on a taller one. Every colour is set here on every render, because each day has its own: the palette pass that
// colours the other custom cards leaves these parts alone.
inline void render_forecast(Widgets &w,const Tile &t,bool large,int width,int height) {
  namespace ft=forecast_tile;
  // The week (render_week) on every card it fits; the forms below where it fits nowhere.
  if(render_week(w,t,large,width,height))return;
  const auto &x=t.extra();const auto &days=x.forecast;
  const lv_font_t *bold=w.title_font?w.title_font:lv_obj_get_style_text_font(w.title,LV_PART_MAIN),*text=w.value_font;
  const lv_font_t *mini=mini_icon_font?mini_icon_font:w.icon_font;
  const lv_font_t *faces[ft::FACES]={setpoint_font,watch_value_font,watch_font};
  char now_text[16];
  if(std::isfinite(t.current))snprintf(now_text,sizeof(now_text),"%.0f°",t.current);else snprintf(now_text,sizeof(now_text),"--");
  ft::Metrics m;m.large=large;
  for(int f=0;f<ft::FACES;++f){
    const bool usable=faces[f]&&face_covers(faces[f],now_text);
    m.face_h[f]=usable?lv_font_get_line_height(faces[f]):0;m.face_w[f]=usable?text_width(now_text,faces[f])+2:0;
  }
  m.text_h=lv_font_get_line_height(text);m.bold_h=lv_font_get_line_height(bold);m.icon_h=lv_font_get_line_height(mini);
  m.circle=w.base_circle>0?w.base_circle:ui::px(large?54:36);
  const std::string cond=t.available()?weather_text(t.state):tr(txt::ha_unavailable);
  std::string line=cond;
  if(std::isfinite(x.feels))line+=" · "+fill(txt::weather_feels_like,"n",(int)std::lround(x.feels));
  m.cond_w=text_width(cond,text)+2;m.line_w=text_width(line,text)+2;
  const int n=(int)std::min<size_t>(days.size(),ft::DAYS),space=ui::px(large?4:2);
  float lowest=INFINITY,highest=-INFINITY;
  for(int k=0;k<n;++k){
    const auto &f=days[k];
    const int hw=text_width(degrees(f.high),bold),lw=text_width(degrees(f.low),text);
    m.temps_w=std::max(m.temps_w,hw+space+lw);m.high_w=std::max(m.high_w,hw+2);m.low_w=std::max(m.low_w,lw+2);
    m.name_w=std::max(m.name_w,text_width(f.day,text)+2);m.row_name_w=std::max(m.row_name_w,text_width(f.day,bold)+2);
    if(std::isfinite(f.rain)&&f.rain>=30){m.rain=true;m.rain_w=std::max(m.rain_w,text_width(screen_text::percent((int)std::lround(f.rain)),text)+2);}
    if(std::isfinite(f.low))lowest=std::min(lowest,f.low);
    if(std::isfinite(f.high))highest=std::max(highest,f.high);
  }
  const bool tall=t.row_span()>1||w.full;
  const auto l=ft::layout(m,width,height,n,forecast_today(t),tall);
  const bool rows=l.form==ft::Form::rows;
  begin_extra(w,rows?"forecast_rows":"forecast",width,height);
  for(auto *p:w.parts)if(p)lv_obj_add_flag(p,LV_OBJ_FLAG_HIDDEN);
  auto show=[](lv_obj_t *p){lv_obj_remove_flag(p,LV_OBJ_FLAG_HIDDEN);return p;};
  auto paint=[](lv_obj_t *p,uint32_t color){set_color(p,LV_STYLE_TEXT_COLOR,lv_color_hex(color));};
  auto words=[&](unsigned i,const lv_font_t *font,ft::Rect r,lv_text_align_t align,const std::string &s,uint32_t color){
    auto *p=show(part_label(w,i,font,r.x,r.y,r.w,align,s));
    if(lv_label_get_long_mode(p)!=LV_LABEL_LONG_DOT)lv_label_set_long_mode(p,LV_LABEL_LONG_DOT);
    paint(p,color);return p;
  };
  const uint32_t ink=theme::hex(theme::INK),muted=theme::hex(theme::MUTED),rain=theme::foreground(theme::ha::RAIN);
  // The weather now. The circle is the look's, in the condition's colour, the icon in it as on every other card.
  const uint32_t sky=t.available()?weather_color_raw(t.state):theme::STATE_OFF;
  if(!l.circle.empty()){
    auto *disc=show(part_dot(w,0,l.circle.x,l.circle.y,l.circle.w));
    set_color(disc,LV_STYLE_BG_COLOR,lv_color_hex(t.available()?theme::tint(sky,38):theme::hex(theme::TRACK)));
    const lv_font_t *glyph=l.circle.w>=m.circle||!mini_icon_font?w.icon_font:mini_icon_font;
    const int gh=lv_font_get_line_height(glyph);
    paint(show(part_label(w,1,glyph,l.circle.x,l.circle.y+(l.circle.h-gh)/2,l.circle.w,LV_TEXT_ALIGN_CENTER,t.available()?weather_icon(t.state):"\U000F0595")),
          t.available()?theme::icon(sky):theme::hex(theme::OFF));
  }
  if(l.face>=0){
    words(2,faces[l.face],l.temp,LV_TEXT_ALIGN_LEFT,now_text,ink);
    if(!l.line.empty())words(3,text,l.line,LV_TEXT_ALIGN_LEFT,l.long_line?line:cond,muted);
  }
  // The high in the title font and the low beside it in the value font, on one baseline.
  const int low_drop=(bold->line_height-bold->base_line)-(text->line_height-text->base_line);
  if(rows){
    const float span=highest>lowest?highest-lowest:1.0f;
    const bool fahrenheit=t.unit.find('F')!=std::string::npos;
    auto celsius=[&](float v){return fahrenheit?(v-32)*5/9:v;};
    for(int k=0;k<l.days;++k){
      const auto &f=days[k];const auto &r=l.rows[k];const unsigned base=4+k*6;
      words(base,bold,r.name,LV_TEXT_ALIGN_LEFT,f.day,ink);
      words(base+1,mini,r.icon,LV_TEXT_ALIGN_CENTER,weather_icon(f.condition),weather_accent(f.condition));
      if(!r.rain.empty()&&std::isfinite(f.rain)&&f.rain>=30)words(base+2,text,r.rain,LV_TEXT_ALIGN_LEFT,screen_text::percent((int)std::lround(f.rain)),rain);
      words(base+3,text,{r.low.x,r.low.y,r.low.w,r.low.h},LV_TEXT_ALIGN_RIGHT,degrees(f.low),muted);
      auto *track=show(part_bar(w,base+4,r.bar.x,r.bar.y,r.bar.w,r.bar.h));
      set_color(track,LV_STYLE_BG_COLOR,theme::color(theme::TRACK));
      auto *fill_bar=lv_obj_get_child(track,0);
      if(std::isfinite(f.low)&&std::isfinite(f.high)&&std::isfinite(lowest)){
        const int from=(int)std::lround((f.low-lowest)/span*r.bar.w),to=(int)std::lround((f.high-lowest)/span*r.bar.w);
        lv_obj_remove_flag(fill_bar,LV_OBJ_FLAG_HIDDEN);
        lv_obj_set_pos(fill_bar,std::min(from,r.bar.w-r.bar.h),0);lv_obj_set_size(fill_bar,std::max(r.bar.h,to-from),r.bar.h);
        set_color(fill_bar,LV_STYLE_BG_COLOR,lv_color_hex(theme::temperature(celsius(f.low))));
        set_color(fill_bar,LV_STYLE_BG_GRAD_COLOR,lv_color_hex(theme::temperature(celsius(f.high))));
      }else lv_obj_add_flag(fill_bar,LV_OBJ_FLAG_HIDDEN);
      words(base+5,bold,r.high,LV_TEXT_ALIGN_RIGHT,degrees(f.high),ink);
    }
    return;
  }
  // Today's pill, below everything else it stands behind.
  if(!l.pill.empty()){
    auto *pill=show(part_dot(w,4,l.pill.x,l.pill.y,0));
    lv_obj_set_size(pill,l.pill.w,l.pill.h);lv_obj_set_style_radius(pill,std::min(ui::px(large?14:9),l.pill.h/2),0);
    set_color(pill,LV_STYLE_BG_COLOR,theme::color(theme::TRACK));
    if(lv_obj_get_index(pill)!=0)lv_obj_move_to_index(pill,0);
  }
  for(int k=0;k<l.days;++k){
    const auto &f=days[k];const auto &c=l.columns[k];const unsigned base=5+k*5;
    const bool beside=!c.name.empty()&&c.name.y>c.icon.y;
    if(!c.name.empty())words(base,text,c.name,beside?LV_TEXT_ALIGN_LEFT:LV_TEXT_ALIGN_CENTER,f.day,muted);
    words(base+1,mini,c.icon,LV_TEXT_ALIGN_CENTER,weather_icon(f.condition),weather_accent(f.condition));
    const std::string hi=degrees(f.high),lo=degrees(f.low);
    const int hw=text_width(hi,bold),lw=text_width(lo,text),x0=c.temps.x+(c.temps.w-(hw+space+lw))/2;
    words(base+2,bold,{x0,c.temps.y,hw+2,c.temps.h},LV_TEXT_ALIGN_LEFT,hi,ink);
    words(base+3,text,{x0+hw+space,c.temps.y+low_drop,lw+2,m.text_h},LV_TEXT_ALIGN_LEFT,lo,muted);
    if(!c.rain.empty()&&std::isfinite(f.rain)&&f.rain>=30)words(base+4,text,c.rain,LV_TEXT_ALIGN_CENTER,screen_text::percent((int)std::lround(f.rain)),rain);
  }
}
// Smoothed trend of the manager's 24 history samples with a soft fill beneath.
inline void render_graph(Widgets &w,const Tile &t,bool large,int x,int y,int width,int height) {
  begin_extra(w,"graph",x+width,y+height);
  float minimum=INFINITY,maximum=-INFINITY;for(float v:t.history)if(std::isfinite(v)){minimum=std::min(minimum,v);maximum=std::max(maximum,v);}
  lv_point_precise_t raw[24];unsigned n=0;int stroke=ui::px(large?3:2),top=stroke;
  for(unsigned i=0;i<t.history.size() && i<24;++i){
    if(!std::isfinite(t.history[i]))continue;
    float level=maximum>minimum?(t.history[i]-minimum)/(maximum-minimum):0.5f;
    raw[n++]={(lv_value_precise_t)(stroke/2+i*(width-stroke-1)/23),(lv_value_precise_t)(height-stroke/2-1-level*(height-stroke-1-top))};
  }
  if(n==1){raw[1]=raw[0];raw[1].x=(lv_value_precise_t)(width-1);n=2;}
  unsigned count=smooth(raw,n,w.points,POINT_BUFFER,width,height);
  part_line(w,0,w.points,count,stroke,x,y);
  w.fill_points=w.points;w.fill_count=count;w.fill_x=x;w.fill_y=y;w.fill_base=height;w.fill_opa=theme::fill_opacity();
}
// Sun path: horizon, an arc from sunrise to sunset and the sun at the current
// position (or below the horizon at night). Wide cards only.
inline void render_sunpath(Widgets &w,const Tile &t,bool large,int width,int height) {
  begin_extra(w,"sunpath",width,height);
  const lv_font_t *title_font=w.title_font;  // the card's own, as in render_clock
  int title_h=lv_font_get_line_height(title_font),text_h=lv_font_get_line_height(w.value_font);
  // The sun's glow is the widest thing on the path: the path keeps half of it from either side of the card, so the sun at
  // rise or set (and clamped there at night) stays inside it (firmware 0.2.104; the standard look's glow is 30 px against
  // a 14 px margin, and stuck out a pixel).
  const int size=ui::px(large?18:10),glow=size+(ui::px(large?12:6));
  int horizon=height-text_h-(ui::px(large?4:2)),top=title_h+(ui::px(large?4:2)),x0=std::max(ui::px(large?14:8),(glow+1)/2),x1=width-x0;
  part_label(w,0,title_font,0,0,width,LV_TEXT_ALIGN_LEFT,t.name.empty()?std::string(tr(txt::sun_name)):t.name);
  part_label(w,1,w.value_font,0,horizon+(ui::px(large?3:1)),width/2,LV_TEXT_ALIGN_LEFT,fill(txt::sun_rise,"time",screen_text::clock_text(t.extra().sunrise,screen_settings::current.clock_24h!=0,true)));
  part_label(w,2,w.value_font,width/2,horizon+(ui::px(large?3:1)),width/2,LV_TEXT_ALIGN_RIGHT,fill(txt::sun_set,"time",screen_text::clock_text(t.extra().sunset,screen_settings::current.clock_24h!=0,true)));
  auto now=now_time?now_time():esphome::ESPTime{};
  int rise=minutes_of(t.extra().sunrise),set=minutes_of(t.extra().sunset),minute=now.is_valid()?now.hour*60+now.minute:-1;
  bool day=t.state=="above_horizon";float fraction=0.5f;
  if(rise>=0 && set>=0 && minute>=0){
    if(day){int span=(set-rise+1440)%1440;if(!span)span=1;fraction=std::clamp(float((minute-rise+1440)%1440)/span,0.0f,1.0f);}
    else{int span=(rise-set+1440)%1440;if(!span)span=1;fraction=std::clamp(float((minute-set+1440)%1440)/span,0.0f,1.0f);}
  }
  const unsigned segments=40;float amplitude=day?float(horizon-top):float(height-text_h-horizon-(ui::px(large?2:1)));
  auto *arc=w.points,*travelled=w.points+segments+1,*line=w.points+2*segments+3;
  for(unsigned i=0;i<=segments;++i){
    float a=3.14159265f*i/segments;
    arc[i]={(lv_value_precise_t)(x0+(x1-x0)*float(i)/segments),(lv_value_precise_t)(day?horizon-sinf(a)*amplitude:horizon+sinf(a)*amplitude)};
  }
  unsigned filled=std::min(segments,unsigned(fraction*segments));
  for(unsigned i=0;i<=filled;++i)travelled[i]=arc[i];
  float sa=3.14159265f*fraction;
  lv_point_precise_t sun={(lv_value_precise_t)(x0+(x1-x0)*fraction),(lv_value_precise_t)(day?horizon-sinf(sa)*amplitude:horizon+sinf(sa)*amplitude)};
  travelled[filled+1]=sun;
  line[0]={(lv_value_precise_t)0,(lv_value_precise_t)horizon};line[1]={(lv_value_precise_t)(width-1),(lv_value_precise_t)horizon};
  const uint32_t path=theme::hex(theme::SUN_PATH), accent=day?theme::ha::ORANGE:theme::foreground(theme::ha::NIGHT_SKY), disc=day?theme::ha::SUNNY:theme::hex(theme::MOON);
  lv_obj_set_style_line_color(part_line(w,3,line,2,2),lv_color_hex(path),0);
  lv_obj_set_style_line_color(part_line(w,4,arc,segments+1,ui::px(large?2:1)),lv_color_hex(path),0);
  lv_obj_set_style_line_color(part_line(w,5,travelled,filled+2,ui::px(large?4:3)),lv_color_hex(accent),0);
  auto *halo=part_dot(w,6,int(sun.x)-glow/2,int(sun.y)-glow/2,glow);lv_obj_set_style_bg_color(halo,lv_color_hex(disc),0);lv_obj_set_style_bg_opa(halo,LV_OPA_30,0);
  lv_obj_set_style_bg_color(part_dot(w,7,int(sun.x)-size/2,int(sun.y)-size/2,size),lv_color_hex(disc),0);
  if(day){w.fill_points=travelled;w.fill_count=filled+2;w.fill_x=0;w.fill_y=0;w.fill_base=horizon;w.fill_color=lv_color_hex(theme::ha::SUNNY);w.fill_opa=theme::fill_opacity();}
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
