// The weather card: now, the next hours and the coming days.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the rules themselves, which are plain C++ without LVGL in weather_chart.h, weather_week.h.
// What proves it: web/wasm/test_weather_detail.mjs, tests/test_weather_week.cpp.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// ---- Weather card: now, the next hours and the coming days, with rain ----
// The colour of a condition's icon on a card: the sky of the one weather table (tile_controls::weather_sky), the same the
// chart beside it draws its marks in.
inline uint32_t weather_color_raw(const std::string &c) { return tile_controls::weather_sky(c); }
inline uint32_t weather_accent(const std::string &c) { return theme::foreground(weather_color_raw(c)); }
inline std::string degrees(float value){ if(!std::isfinite(value))return "--"; char b[16];snprintf(b,sizeof(b),"%.0f°",value);return b; }
// ---- The weather card (design study 10-09, weather_chart.h): what a tap on a weather tile opens ----
// Home Assistant's more-info dialog in its order: the weather now (its icon, the temperature, the condition, today's
// high and low, feels like), the attributes the entity has (humidity, wind with its direction, air pressure,
// visibility), and the forecast under a Daily | Hourly key, the days as columns in a light grid over one chart. The
// arrangement follows the forecast: the richest one that leaves the chart its highest tier (weather_week.h) wins, so a
// small glass drops the attributes to one line, then that line, then moves the key into the top card.
inline int weather_view=0;   // 0 daily, 1 hourly
inline uint32_t weather_page_shown(){return (uint32_t)weather_view;}
// The chart's faces, from the smallest step up: the look's fonts, never a size of the chart's own.
inline weather_chart::Fonts weather_fonts(){
  const lv_font_t *icon=widgets[0].icon_font?widgets[0].icon_font:mini_icon_font;
  const lv_font_t *small=small_font?small_font:detail_font,*mini=mini_icon_font?mini_icon_font:icon,*tiny=watch_icon_font?watch_icon_font:mini;
  const lv_font_t *bold=label_font?label_font:detail_font,*big_text=control_font?control_font:small;
  const lv_font_t *head=watch_font?watch_font:bold,*value=watch_value_font?watch_value_font:head;
  weather_chart::Fonts f;
  f.levels[0]={small,tiny,tiny,bold,small,small};
  f.levels[1]={small,mini,tiny,bold,small,small};
  f.levels[2]={big_text,icon,mini,head,big_text,small};
  f.levels[3]={head,big_icon_font?big_icon_font:icon,icon,value,head,big_text};
  f.marks={tiny,mini,icon};f.axis=small;
  return f;
}
// Today's weekday, Sunday 0, from the screen's clock; -1 while it is not set.
inline int weather_today(){
  const auto now=now_time?now_time():esphome::ESPTime{};
  return now.is_valid()&&now.day_of_week>=1&&now.day_of_week<=7?now.day_of_week-1:-1;
}
inline weather_chart::Chart weather_chart_of(const Tile &t,bool hourly){
  namespace ww=weather_week;
  const Extra &x=t.extra();
  weather_chart::Chart c;
  c.hourly=hourly;c.large=ui::large();c.fonts=weather_fonts();c.unit=x.rain_unit.empty()?"mm":x.rain_unit;
  c.fahrenheit=t.unit.find('F')!=std::string::npos;
  const int today=weather_today();
  c.today=today>=0?today:(x.forecast.size()&&x.forecast[0].weekday>=0?x.forecast[0].weekday:0);
  for(int k=0;k<7;++k)c.weekdays.push_back(tr(txt::date_weekdays_short+k));
  for(size_t k=0;k<x.forecast.size()&&k<(size_t)ww::DAYS;++k){
    const auto &f=x.forecast[k];ww::Day d;
    // The first day says Today when it is today (Home Assistant's word); the others their short name in the screen's
    // language; an older app sent only the two letters of the tile.
    if(f.weekday>=0)d.name=k==0&&f.weekday==c.today?tr(txt::ha_today):tr(txt::date_weekdays_short+f.weekday);else d.name=f.day;
    d.condition=f.condition;d.high=f.high;d.low=f.low;d.mm=f.mm;d.chance=f.rain;
    c.days.push_back(d);
  }
  // The hours count from today's midnight; an older app sends only their times, which run on past midnight.
  int day=0,last=-1;
  for(size_t i=0;i<x.hours.size()&&i<(size_t)ww::HOURS;++i){
    const auto &h=x.hours[i];ww::Hour o;
    if(h.at>=0)o.at=h.at;
    else{const int hour=atoi(h.time.c_str());if(last>=0&&hour<last)++day;last=hour;o.at=24*day+hour;}
    o.condition=h.condition;o.temp=h.temp;o.mm=h.mm;c.hours.push_back(o);
  }
  const auto now=now_time?now_time():esphome::ESPTime{};
  c.now=now.is_valid()?now.hour:(c.hours.empty()?0:c.hours.front().at);
  // The week's columns are the forecast's days: a list that starts tomorrow (or still yesterday) moves the hours and now
  // to its first day's midnight, so today's line is not drawn under tomorrow (GitHub #280). The hourly strip keeps today.
  const int shift=hourly?0:ww::first_day_from_today(x.forecast.empty()?-1:x.forecast[0].weekday,today);
  if(shift){
    for(auto &h:c.hours)h.at-=24*shift;
    c.now=std::max(0,c.now-24*shift);
    c.today=((c.today+shift)%7+7)%7;
  }
  return c;
}
inline lv_obj_t *weather_chart_object(lv_obj_t *parent,int x,int y,int w,int h,weather_chart::Chart &&chart){
  auto *o=weather_chart::create(parent);lv_obj_set_pos(o,x,y);lv_obj_set_size(o,std::max(1,w),std::max(1,h));
  weather_chart::set(o,std::move(chart));return o;
}
// "SW": the wind's bearing in Home Assistant's sixteen directions.
inline std::string wind_direction(float bearing){
  if(!std::isfinite(bearing))return "";
  const int k=((int)std::lround(bearing/22.5f)%16+16)%16;
  return tr(txt::ha_wind_direction_n+k);
}
struct WeatherAttribute{const char *icon;uint16_t caption;std::string value;};
inline std::vector<WeatherAttribute> weather_attributes(const Tile &t){
  const Extra &x=t.extra();std::vector<WeatherAttribute> a;char b[40];
  auto num=[&](float v){return screen_text::decimal(v,std::fabs(v)<10&&std::fabs(v-std::round(v))>=0.05f?1:0);};
  if(std::isfinite(t.humidity))a.push_back({"\U000F058E",txt::ha_weather_attribute_humidity,screen_text::percent((int)std::lround(t.humidity))});
  if(std::isfinite(x.wind)){
    std::string v=screen_text::with_unit(num(x.wind),x.wind_unit.empty()?"km/h":x.wind_unit);const std::string dir=wind_direction(x.bearing);
    a.push_back({"\U000F059D",txt::ha_weather_attribute_wind_speed,dir.empty()?v:v+" "+dir});
  }
  if(std::isfinite(x.pressure)){snprintf(b,sizeof(b),"%.0f",x.pressure);a.push_back({"\U000F029A",txt::ha_weather_attribute_air_pressure,screen_text::with_unit(x.pressure<100?num(x.pressure):std::string(b),x.pressure_unit)});}
  if(std::isfinite(x.visibility))a.push_back({"\U000F0208",txt::ha_weather_attribute_visibility,screen_text::with_unit(num(x.visibility),x.visibility_unit)});
  return a;
}
// The Daily | Hourly key: two halves of one grey pill, the chosen one white.
inline void weather_key_event(lv_event_t *e){
  const int view=(int)(intptr_t)lv_event_get_user_data(e);
  if(view==weather_view||detail_index>=model.count)return;
  weather_view=view;redraw_detail();
}
inline int weather_key_w(){
  const lv_font_t *f=label_font?label_font:detail_font;
  return 2*(std::max(text_width(tr(txt::ha_weather_view_daily),f),text_width(tr(txt::ha_weather_view_hourly),f))+ui::px(ui::large()?28:16));
}
inline int weather_key_h(){const lv_font_t *f=label_font?label_font:detail_font;return std::max(ui::touch_min(),line_of(f)+ui::px(12));}
inline void weather_key(lv_obj_t *parent,int x,int y,bool hours){
  const lv_font_t *f=label_font?label_font:detail_font;
  const int w=weather_key_w(),h=weather_key_h(),half=w/2,in=ui::px(3);
  auto *track=lv_obj_create(parent);lv_obj_remove_style_all(track);lv_obj_remove_flag(track,LV_OBJ_FLAG_SCROLLABLE);lv_obj_remove_flag(track,LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_pos(track,x,y);lv_obj_set_size(track,w,h);lv_obj_set_style_radius(track,LV_RADIUS_CIRCLE,0);
  lv_obj_set_style_bg_color(track,theme::color(theme::TRACK),0);lv_obj_set_style_bg_opa(track,LV_OPA_COVER,0);
  for(int side=0;side<2;++side){
    const bool chosen=side==(hours?1:0);
    auto *k=lv_obj_create(track);lv_obj_remove_style_all(k);lv_obj_remove_flag(k,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_pos(k,side?half:in,in);lv_obj_set_size(k,half-in,h-2*in);lv_obj_set_style_radius(k,LV_RADIUS_CIRCLE,0);
    lv_obj_set_style_bg_color(k,theme::color(chosen?theme::CARD:theme::TRACK),0);lv_obj_set_style_bg_opa(k,LV_OPA_COVER,0);
    lv_obj_set_style_bg_color(k,theme::color(theme::KEY_PRESSED),LV_STATE_PRESSED);
    auto *word=lv_label_create(k);lv_obj_set_style_text_font(word,f,0);lv_label_set_text(word,tr(side?txt::ha_weather_view_hourly:txt::ha_weather_view_daily));
    lv_obj_set_style_text_color(word,theme::color(chosen?theme::INK:theme::MUTED),0);lv_obj_center(word);lv_obj_remove_flag(word,LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_flag(k,LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(k,weather_key_event,LV_EVENT_CLICKED,(void*)(intptr_t)side);
  }
}
// A grey tile of one attribute: its icon and value on a line, Home Assistant's name for it under them.
inline int weather_chip_h(){const lv_font_t *f=label_font?label_font:detail_font,*s=small_font?small_font:detail_font;return 2*ui::px(ui::large()?8:5)+line_of(f)+line_of(s);}
inline void weather_chip(lv_obj_t *p,int x,int y,int w,const WeatherAttribute &a){
  const lv_font_t *f=label_font?label_font:detail_font,*s=small_font?small_font:detail_font,*ic=watch_icon_font?watch_icon_font:s;
  const int h=weather_chip_h(),in=ui::px(ui::large()?10:6),v=ui::px(ui::large()?8:5),iw=line_of(ic);
  auto *t=lv_obj_create(p);lv_obj_remove_style_all(t);lv_obj_remove_flag(t,LV_OBJ_FLAG_SCROLLABLE);lv_obj_remove_flag(t,LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_pos(t,x,y);lv_obj_set_size(t,w,h);lv_obj_set_style_radius(t,ui::px(ui::large()?12:8),0);
  lv_obj_set_style_bg_color(t,theme::color(theme::TRACK),0);lv_obj_set_style_bg_opa(t,LV_OPA_COVER,0);
  detail_text(t,a.icon,in,v+(line_of(f)-iw)/2,iw+2,ic,LV_TEXT_ALIGN_LEFT,theme::MUTED);
  detail_text(t,a.value,in+iw+ui::px(5),v,w-2*in-iw-ui::px(5),f,LV_TEXT_ALIGN_LEFT,theme::INK);
  detail_text(t,tr(a.caption),in,v+line_of(f),w-2*in,s,LV_TEXT_ALIGN_LEFT,theme::MUTED);
}
inline void render_weather_detail(const Tile &t,bool large,int width,int height,int){
  const Extra &x=t.extra();
  // The Daily | Hourly key is there only for a forecast that has hours, as Home Assistant's own card offers a kind of
  // forecast only where the entity has it (a provider with days alone: the key opened an empty chart, 2026-11-17).
  const bool by_hour=!x.hours.empty();
  if(!by_hour)weather_view=0;
  if(detail_status){lv_obj_add_flag(detail_status,LV_OBJ_FLAG_HIDDEN);detail_status=nullptr;}
  const int pad=overlay_card::pad(),gap=ui::px(large?12:6),gi=ui::px(large?12:6),card_pad=ui::px(large?16:8);
  const int top=detail_bar::bottom()+gap;
  const int area_w=width-2*pad,area_h=height-top-pad,inner=area_w-2*card_pad;
  const lv_font_t *hero_font=setpoint_font?setpoint_font:(watch_value_font?watch_value_font:detail_font);
  const lv_font_t *big_icon=big_icon_font?big_icon_font:widgets[0].icon_font;
  const lv_font_t *words_font=watch_font?watch_font:detail_font,*bold=label_font?label_font:detail_font;
  const lv_font_t *line_font=control_font?control_font:detail_font,*small=small_font?small_font:detail_font;
  const auto attrs=weather_attributes(t);const int n=attrs.size();
  char now[16];if(std::isfinite(t.current))snprintf(now,sizeof(now),"%.1f°",t.current);else snprintf(now,sizeof(now),"--");
  if(!face_covers(hero_font,now))hero_font=watch_value_font?watch_value_font:detail_font;
  const std::string cond=t.available()?weather_text(t.state):tr(txt::ha_unavailable);
  std::string hl;
  if(x.forecast.size())hl=degrees(x.forecast[0].high)+" / "+degrees(x.forecast[0].low);
  const std::string feels=std::isfinite(x.feels)?fill(txt::weather_feels_like,"n",(int)std::lround(x.feels)):"";
  const int hero=std::max(line_of(hero_font),line_of(big_icon));
  int widest=0;for(auto &a:attrs)widest=std::max(widest,text_width(a.value,bold));
  // The attributes: a row of tiles (two by two where one row is too narrow), one muted line, or none.
  int per_row=n,rows=n?1:0;
  while(per_row>1&&(inner-(per_row-1)*ui::px(6))/per_row<widest+line_of(watch_icon_font?watch_icon_font:small)+ui::px(30)){per_row=(per_row+1)/2;rows=(n+per_row-1)/per_row;}
  const int tiles_h=rows*weather_chip_h()+std::max(0,rows-1)*ui::px(6);
  // The line of attributes starts with feels like, which the card's top says only where it has a third line.
  std::string line=std::isfinite(x.feels)?fill(txt::weather_feels_like,"n",(int)std::lround(x.feels)):"";
  for(auto &a:attrs){std::string next=line+(line.empty()?"":" · ")+a.value;if(text_width(next,small)<=inner)line=next;}
  const int hero_w=line_of(big_icon)+gi+text_width(now,hero_font)+gi+std::max({text_width(cond,words_font),text_width(hl,line_font),text_width(feels,line_font)})+gi;
  const int beside_w=std::max(widest+line_of(watch_icon_font?watch_icon_font:small)+ui::px(30),text_width(tr(txt::ha_weather_attribute_air_pressure),small)+ui::px(24));
  const bool beside=n&&inner-hero_w>=n*beside_w+(n-1)*ui::px(6);
  struct Option{int extra;bool title,key_in_hero,beside;};
  // The key stands at the right of the card's top bar where the name centred there leaves it room, as Home
  // Assistant's dialog puts its keys in its header; else over the forecast, or in the top card on the smallest glass.
  // Its right edge is the top bar's (detail_bar): where the outer key at the right ends on every page.
  const auto edge=detail_bar::right_slot(detail_root);
  const int key_x=edge.x+edge.w-weather_key_w(),middle=detail_bar::glass_left(detail_root)+overlay_card::screen_width()/2;
  const lv_font_t *heading=watch_font?watch_font:detail_font;
  const bool key_top=by_hour&&middle+text_width(t.name,heading)/2+gap<=key_x;
  if(key_top)weather_key(detail_root,key_x,edge.y+(edge.h-weather_key_h())/2,weather_view==1);
  const bool title=by_hour&&!key_top;
  const Option options[]={{beside?std::max(0,weather_chip_h()-hero):-1,title,false,true},{n?gi+tiles_h:-1,title,false,false},
                          {line.empty()?-1:line_of(small)+ui::px(4),title,false,false},{0,title,false,false},{0,false,by_hour&&!key_top,false}};
  const auto chart_proto=weather_chart_of(t,false);
  // The richest arrangement whose forecast still reaches the rain row (or the most the forecast can reach at all);
  // where none shows anything, the one that leaves the forecast the most room.
  int tiers[5],rooms[5],most=-1;
  for(int i=0;i<5;++i){
    const auto &o=options[i];tiers[i]=-2;rooms[i]=-1;
    if(o.extra<0)continue;
    const int now_h=2*card_pad+hero+o.extra;rooms[i]=area_h-now_h-gap-2*card_pad-(o.title?weather_key_h()+gi:0);
    tiers[i]=weather_view?(rooms[i]>=weather_chart::hours_need(chart_proto.fonts)?3:-1):weather_chart::week_tier(chart_proto,inner,rooms[i]);
    most=std::max(most,tiers[i]);
  }
  Option best=options[4];
  if(most<0){int room=-1;for(int i=0;i<5;++i)if(rooms[i]>room){room=rooms[i];best=options[i];}}
  else for(int i=0;i<5;++i)if(tiers[i]>=std::min(3,most)){best=options[i];break;}
  // The weather now.
  const int now_h=2*card_pad+hero+best.extra;
  auto *card=detail_card(pad,top,area_w,now_h);
  int right=area_w-card_pad;
  if(best.key_in_hero){right-=weather_key_w();weather_key(card,right,card_pad+(hero-weather_key_h())/2,weather_view==1);right-=gi;}
  const int words_min=std::max(text_width(cond,bold),text_width(hl,line_font));
  bool with_icon=true;const lv_font_t *tf=hero_font;
  for(int step=0;step<3;++step){
    with_icon=step==0;tf=step<2?hero_font:(watch_value_font?watch_value_font:hero_font);
    if(right-card_pad-(with_icon?line_of(big_icon)+gi:0)-text_width(now,tf)-gi>=words_min)break;
  }
  const int hero_y=best.beside?(now_h-hero)/2-card_pad:0;
  int xx=card_pad;
  if(with_icon){
    const int ih=line_of(big_icon);
    auto *art=weather_chart::create(card);lv_obj_set_pos(art,xx,card_pad+hero_y+(hero-ih)/2);lv_obj_set_size(art,ih*5/4,ih);
    // The condition's two-tone picture, the one the chart draws for a day, in the largest face.
    weather_chart::Chart c;c.icon_only=true;c.fonts=weather_fonts();c.days.push_back({"",t.available()?t.state:"exceptional"});
    weather_chart::set(art,std::move(c));
    xx+=ih+gi;
  }
  const int tw=text_width(now,tf);
  detail_text(card,now,xx,card_pad+hero_y+(hero-line_of(tf))/2,tw+2,tf,LV_TEXT_ALIGN_LEFT,theme::INK);xx+=tw+gi;
  const int rw=best.beside?std::max(0,card_pad+hero_w-xx):right-xx;
  const lv_font_t *wf=text_width(cond,words_font)<=rw?words_font:bold;
  // Feels like once: in the line of attributes where the card has it, else as the top card's third line where it fits.
  const bool in_line=!best.beside&&best.extra>0&&best.extra!=gi+tiles_h;
  const bool show_feels=!in_line&&!feels.empty()&&text_width(feels,line_font)<=rw&&line_of(wf)+2*line_of(line_font)<=hero;
  const std::string hl_line=hl;
  const bool show_hl=!hl_line.empty()&&text_width(hl_line,line_font)<=rw;
  const int lines=line_of(wf)+(show_hl?line_of(line_font):0)+(show_feels?line_of(line_font):0);
  int ty=card_pad+hero_y+(hero-lines)/2;
  detail_text(card,cond,xx,ty,std::max(1,rw),wf,LV_TEXT_ALIGN_LEFT,theme::INK);ty+=line_of(wf);
  if(show_hl){detail_text(card,hl_line,xx,ty,rw,line_font,LV_TEXT_ALIGN_LEFT,theme::MUTED);ty+=line_of(line_font);}
  if(show_feels)detail_text(card,feels,xx,ty,rw,line_font,LV_TEXT_ALIGN_LEFT,theme::MUTED);
  if(best.beside){
    const int cw=std::min(ui::px(150),(inner-hero_w-(n-1)*ui::px(6))/n),x2=card_pad+inner-(n*cw+(n-1)*ui::px(6));
    for(int i=0;i<n;++i)weather_chip(card,x2+i*(cw+ui::px(6)),(now_h-weather_chip_h())/2,cw,attrs[i]);
  }else if(best.extra==gi+tiles_h&&n){
    const int cw=(inner-(per_row-1)*ui::px(6))/per_row;
    for(int i=0;i<n;++i)weather_chip(card,card_pad+(i%per_row)*(cw+ui::px(6)),card_pad+hero+gi+(i/per_row)*(weather_chip_h()+ui::px(6)),cw,attrs[i]);
  }else if(best.extra>0)detail_text(card,line,card_pad,card_pad+hero+ui::px(4),inner,small,LV_TEXT_ALIGN_LEFT,theme::MUTED);
  // The forecast.
  const int fy=top+now_h+gap,fh=area_h-now_h-gap;
  auto *days=detail_card(pad,fy,area_w,fh);
  int cy=card_pad;
  if(best.title){weather_key(days,card_pad,card_pad,weather_view==1);cy+=weather_key_h()+gi;}
  if(!x.forecast.size()&&!weather_view){detail_text(days,tr(txt::weather_no_forecast),card_pad,cy,inner,small,LV_TEXT_ALIGN_LEFT,theme::MUTED);}
  else weather_chart_object(days,card_pad,cy,inner,fh-cy-card_pad,weather_chart_of(t,weather_view==1));
  card_shaped(t,picture_card_shape);
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
