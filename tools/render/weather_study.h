#pragma once
// Host-only design study of a week forecast card (10-09). No device firmware includes this file.
// Every size comes from the board's own fonts, grid, density and the room a card gets; nothing is drawn for one board.
//
// Three directions on the same data:
//   A  the reference card 1:1: day columns, hairlines between them, one ink curve, rain bars, mm and chance.
//   B  the same chart in the screens' own language: no hairlines, today on a pale pill, the curve coloured by
//      Home Assistant's temperature hues with a soft fill, rain only where it falls, two-tone icons.
//   C  the next 48 hours from Home Assistant's hourly forecast in B's language, the other half of a Week | 48 h key.
#include "esphome/components/lvgl/lvgl_esphome.h"
#include "../../components/smart_display/ui_scale.h"
#include "../../components/smart_display/theme.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>
namespace weather_study {

struct Fonts {const lv_font_t *label,*note,*note_big,*headline,*value,*icon_watch,*icon_mini,*icon,*icon_big,*hero;};
struct Board {const char *name,*look; int width,height,dpi,cols,rows,top,footer,margin,gx,gy,radius,pad,circle; Fonts f;};
struct Rect {int x,y,w,h; int right()const{return x+w;} int bottom()const{return y+h;}};
struct Day {const char *name,*cond; float high,low,mm,pct;};
struct Hour {int hour; const char *cond; float temp,mm,pct;};
struct Scene {const char *key,*place,*cond,*words; float now; int hour; std::vector<Day> days; std::vector<Hour> hours; float hum,wind,bearing,pressure,vis,feels;};

inline int cuts=0;
inline std::string where;

// ---- small LVGL helpers, as in tall_concepts.h
inline lv_obj_t *box(lv_obj_t *parent,Rect r,uint32_t color,int radius=0) {
  assert(r.w>0 && r.h>0);
  auto *o=lv_obj_create(parent);lv_obj_remove_style_all(o);lv_obj_remove_flag(o,LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_pos(o,r.x,r.y);lv_obj_set_size(o,r.w,r.h);
  lv_obj_set_style_bg_color(o,lv_color_hex(color),0);lv_obj_set_style_bg_opa(o,LV_OPA_COVER,0);
  lv_obj_set_style_radius(o,radius,0);return o;
}
inline int width_of(const std::string &s,const lv_font_t *f){
  lv_point_t size;lv_text_get_size(&size,s.c_str(),f,0,0,LV_COORD_MAX,LV_TEXT_FLAG_NONE);return size.x;
}
inline int H(const lv_font_t *f){return lv_font_get_line_height(f);}
// A line of text; one that does not fit its width is counted (the study allows none) and ends in dots.
inline lv_obj_t *text(lv_obj_t *p,const std::string &s,int x,int y,int w,const lv_font_t *f,uint32_t color,
                      lv_text_align_t align=LV_TEXT_ALIGN_LEFT){
  if(width_of(s,f)>w){++cuts;fprintf(stderr,"CUT %s \"%s\" %d>%d\n",where.c_str(),s.c_str(),width_of(s,f),w);}
  auto *o=lv_label_create(p);lv_obj_remove_style_all(o);lv_label_set_text(o,s.c_str());
  lv_obj_set_style_text_font(o,f,0);lv_obj_set_style_text_color(o,lv_color_hex(color),0);
  lv_label_set_long_mode(o,LV_LABEL_LONG_DOT);lv_obj_set_style_text_align(o,align,0);
  lv_obj_set_pos(o,x,y);lv_obj_set_size(o,std::max(1,w),H(f));return o;
}
inline uint32_t ink(){return theme::hex(theme::INK);}
inline uint32_t muted(){return theme::hex(theme::MUTED);}
inline uint32_t subtle(){return theme::hex(theme::SUBTLE);}
inline uint32_t rain(){return theme::foreground(theme::ha::RAIN);}
inline std::string deg(float v,bool decimal=false){
  char b[16];if(!std::isfinite(v))return "--";
  if(decimal && std::fabs(v-std::round(v))>0.05f)snprintf(b,sizeof(b),"%.1f°",v);else snprintf(b,sizeof(b),"%.0f°",v);
  std::string s=b;if(s.rfind("-0°",0)==0)s="0°";return s;
}
inline std::string mm_text(float v){char b[16];if(v<10)snprintf(b,sizeof(b),"%.1f mm",v);else snprintf(b,sizeof(b),"%.0f mm",v);
  std::string s=b;if(s.size()>5&&s.compare(s.size()-5,5,".0 mm")==0)s=s.substr(0,s.size()-5)+" mm";return s;}
inline std::string pct_text(float v){char b[8];snprintf(b,sizeof(b),"%.0f%%",v);return b;}
inline const char *words(const std::string &c){
  if(c=="sunny")return "Sunny";if(c=="clear-night")return "Clear, night";if(c=="cloudy")return "Cloudy";
  if(c=="partlycloudy")return "Partly cloudy";if(c=="rainy")return "Rainy";if(c=="pouring")return "Pouring";
  if(c=="snowy")return "Snowy";if(c=="snowy-rainy")return "Snowy, rainy";if(c=="fog")return "Fog";
  if(c=="lightning")return "Lightning";if(c=="lightning-rainy")return "Lightning, rainy";if(c=="hail")return "Hail";
  if(c=="windy")return "Windy";return "Exceptional";
}
// The single glyph the tile wears today (runtime_tiles.h weather_icon) and its colour.
inline const char *glyph(const std::string &c){
  if(c=="sunny")return "\U000F0599";if(c=="clear-night")return "\U000F0594";if(c=="cloudy")return "\U000F0590";
  if(c=="partlycloudy")return "\U000F0595";if(c=="rainy")return "\U000F0597";if(c=="pouring")return "\U000F0596";
  if(c=="snowy")return "\U000F0598";if(c=="snowy-rainy")return "\U000F067F";if(c=="fog")return "\U000F0591";
  if(c=="hail")return "\U000F0592";if(c=="lightning"||c=="lightning-rainy")return "\U000F0593";if(c=="windy")return "\U000F059D";
  return "\U000F05D6";
}
inline uint32_t hue(const std::string &c){
  namespace h=theme::ha;
  if(c=="sunny")return h::SUNNY;if(c=="clear-night")return h::NIGHT_SKY;if(c=="partlycloudy")return h::PARTLY_CLOUDY;
  if(c=="rainy"||c=="pouring")return h::RAIN;if(c=="snowy"||c=="snowy-rainy"||c=="hail")return h::SNOW;
  if(c=="lightning"||c=="lightning-rainy")return h::LIGHTNING;return h::CLOUDY;
}

// ---- two-tone icons: one condition from a few MDI glyphs (cloud, sun, moon, drop, flake, bolt), like Home
// Assistant's own weather pictures, in fonts every board already has.
inline uint32_t cloud_front(){return theme::dark?0xCFD8DC:0xB0BEC5;}
inline uint32_t cloud_back(){return theme::dark?0x78909C:0x90A4AE;}
inline lv_obj_t *gl(lv_obj_t *p,const char *s,int x,int y,const lv_font_t *f,uint32_t c){
  auto *o=lv_label_create(p);lv_obj_remove_style_all(o);lv_label_set_text(o,s);lv_obj_set_style_text_font(o,f,0);
  lv_obj_set_style_text_color(o,lv_color_hex(c),0);lv_obj_set_pos(o,x,y);return o;
}
// The icon fills a box of `big`'s line height, centred on cx. `small` draws the sun behind a cloud, drops, flakes.
inline const Fonts *icon_fonts=nullptr;
// What falls out of a cloud (drops, flakes, a bolt) in the largest icon face at most ~42 % of the cloud's;
// nullptr when the board has none that small.
inline const lv_font_t *mark_font(const lv_font_t *big){
  const lv_font_t *best=nullptr;if(!icon_fonts)return best;
  for(auto *f:{icon_fonts->icon_watch,icon_fonts->icon_mini,icon_fonts->icon})if(H(f)*100<=H(big)*42&&(!best||H(f)>H(best)))best=f;
  return best;
}
inline void icon(lv_obj_t *p,const std::string &c,int cx,int y,const lv_font_t *big,const lv_font_t *small,bool two_tone){
  const bool falls=c!="partlycloudy"&&c!="cloudy"&&c!="sunny"&&c!="clear-night"&&c!="fog"&&c!="windy"&&c!="exceptional";
  const lv_font_t *mf=mark_font(big);
  if(falls&&!mf)two_tone=false;
  const int b=H(big),s=H(small),x=cx-b/2;
  if(!two_tone){gl(p,glyph(c),x,y,big,theme::foreground(hue(c)));return;}
  namespace h=theme::ha;
  const char *CLOUD="\U000F0590",*SUN="\U000F0599",*MOON="\U000F0594",*DROP="\U000F058C",*FLAKE="\U000F0717",*BOLT="\U000F0241";
  if(c=="sunny"){gl(p,SUN,x,y,big,theme::foreground(h::SUNNY));return;}
  if(c=="clear-night"){gl(p,MOON,x,y,big,theme::foreground(h::NIGHT_SKY));return;}
  if(c=="fog"||c=="windy"||c=="exceptional"){gl(p,glyph(c),x,y,big,cloud_back());return;}
  // A cloud of the big face, lifted when something falls out of it.
  const int m=falls?H(mf):0,lift=falls?m*2/3:0;
  if(c=="partlycloudy")gl(p,SUN,x+b/2-s/8,y-s/10,small,theme::foreground(h::SUNNY));
  if(c=="cloudy")gl(p,CLOUD,x+b/2-s/6,y-s/12,small,cloud_back());
  gl(p,CLOUD,x,y+(c=="partlycloudy"||c=="cloudy"?b/12:0)-lift,big,cloud_front());
  if(!falls)return;
  // What falls: two marks (three when pouring) under the cloud's belly, half a small face each.
  const int below=y+b-lift-m/2;
  auto mark=[&](const char *g,uint32_t col,int dx){gl(p,g,cx-m/2+dx,below,mf,col);};
  const int step=m*3/4;
  if(c=="lightning"||c=="lightning-rainy"){mark(BOLT,theme::foreground(h::LIGHTNING),c=="lightning"?0:-step/2);if(c!="lightning")mark(DROP,rain(),step/2+step/4);return;}
  const uint32_t r=rain(),sn=theme::foreground(h::SNOW);
  if(c=="pouring"){mark(DROP,r,-step);mark(DROP,r,0);mark(DROP,r,step);return;}
  if(c=="snowy"){mark(FLAKE,sn,-step/2);mark(FLAKE,sn,step/2);return;}
  if(c=="snowy-rainy"){mark(DROP,r,-step/2);mark(FLAKE,sn,step/2);return;}
  if(c=="hail"){mark(FLAKE,sn,-step/2);mark(DROP,r,step/2);return;}
  mark(DROP,r,-step/2);mark(DROP,r,step/2);
}

// ---- the chart layer, drawn in one draw event (one object, no buffer)
// The curve is a function of x, so it is drawn a pixel column at a time: the line's exact top and bottom in that
// column (its thickness measured across the slope), the two edge pixels at the share of them it covers. That is
// sub-pixel exact and anti-aliased with integer coordinates, has no joints, and lets the colour run on per column.
// The soft area under it is one column too: a vertical fade from the line's colour to nothing at the base.
struct Chart {
  int fx=0; std::vector<float> ys; std::vector<uint32_t> cols; float lw=2; bool fill=false; int base=0; uint8_t fill_opa=60;
  struct Bar {lv_area_t a; uint32_t color; int radius;}; std::vector<Bar> bars;
  struct Cap {lv_area_t a; uint32_t top,bottom; int radius=LV_RADIUS_CIRCLE;}; std::vector<Cap> caps;   // a day's range, coloured high to low
  struct Hair {int x,y1,y2; uint32_t color;}; std::vector<Hair> hairs;
  float dot_x=-1,dot_y=0; uint32_t dot_color=0; int dot_r=0;
};
inline std::vector<Chart*> charts;
inline void px_rect(lv_layer_t *layer,int x,int y1,int y2,uint32_t c,lv_opa_t opa){
  if(y2<y1||opa<2)return;lv_draw_rect_dsc_t d;lv_draw_rect_dsc_init(&d);d.bg_color=lv_color_hex(c);d.bg_opa=opa;
  lv_area_t a{x,y1,x,y2};lv_draw_rect(layer,&d,&a);
}
inline void chart_draw(lv_event_t *e){
  auto *c=static_cast<Chart*>(lv_event_get_user_data(e));auto *layer=lv_event_get_layer(e);
  lv_area_t a;lv_obj_get_coords(static_cast<lv_obj_t*>(lv_event_get_current_target(e)),&a);
  const int ox=a.x1,oy=a.y1;
  for(auto &h:c->hairs)px_rect(layer,ox+h.x,oy+h.y1,oy+h.y2,h.color,LV_OPA_COVER);
  for(auto &b:c->bars){lv_draw_rect_dsc_t d;lv_draw_rect_dsc_init(&d);d.bg_color=lv_color_hex(b.color);d.bg_opa=LV_OPA_COVER;d.radius=b.radius;
    lv_area_t r=b.a;r.x1+=ox;r.x2+=ox;r.y1+=oy;r.y2+=oy;lv_draw_rect(layer,&d,&r);}
  for(auto &k:c->caps){lv_draw_rect_dsc_t d;lv_draw_rect_dsc_init(&d);d.radius=k.radius;d.bg_opa=LV_OPA_COVER;
    lv_color_t cs[2]={lv_color_hex(k.top),lv_color_hex(k.bottom)};lv_grad_init_stops(&d.bg_grad,cs,nullptr,nullptr,2);lv_grad_vertical_init(&d.bg_grad);
    lv_area_t r=k.a;r.x1+=ox;r.x2+=ox;r.y1+=oy;r.y2+=oy;lv_draw_rect(layer,&d,&r);}
  const int n=c->ys.size();
  for(int i=0;i<n;++i){
    const float y=c->ys[i],slope=(c->ys[std::min(n-1,i+1)]-c->ys[std::max(0,i-1)])/2;
    const float half=c->lw/2*std::sqrt(1+slope*slope);
    // the slope's own run inside this column: a steep stretch covers more rows than its thickness alone
    const float top=std::min(y,y-std::fabs(slope)/2)-half,bot=std::max(y,y+std::fabs(slope)/2)+half;
    const uint32_t col=c->cols[i];const int x=ox+c->fx+i;
    if(c->fill){
      const int y1=oy+(int)std::ceil(bot)-1,y2=oy+c->base;
      if(y2>=y1){lv_draw_rect_dsc_t d;lv_draw_rect_dsc_init(&d);d.bg_opa=LV_OPA_COVER;
        lv_color_t cs[2]={lv_color_hex(col),lv_color_hex(col)};lv_opa_t op[2]={c->fill_opa,0};
        lv_grad_init_stops(&d.bg_grad,cs,op,nullptr,2);lv_grad_vertical_init(&d.bg_grad);
        lv_area_t r{x,y1,x,y2};lv_draw_rect(layer,&d,&r);}
    }
    const int r1=(int)std::floor(top),r2=(int)std::ceil(bot)-1;
    for(int row=r1;row<=r2;++row){
      const float cov=std::min<float>(row+1,bot)-std::max<float>(row,top);
      px_rect(layer,x,oy+row,oy+row,col,(lv_opa_t)std::clamp(cov*255.f,0.f,255.f));
    }
  }
  if(c->dot_x>=0){
    lv_draw_rect_dsc_t r;lv_draw_rect_dsc_init(&r);r.bg_color=lv_color_hex(c->dot_color);r.radius=LV_RADIUS_CIRCLE;
    r.border_color=lv_color_hex(theme::hex(theme::CARD));r.border_width=std::max(2,c->dot_r/2);
    const int cx=ox+(int)std::lround(c->dot_x),cy=oy+(int)std::lround(c->dot_y);
    lv_area_t q{cx-c->dot_r,cy-c->dot_r,cx+c->dot_r,cy+c->dot_r};lv_draw_rect(layer,&r,&q);
  }
}
inline Chart *chart(lv_obj_t *p,Rect r){
  auto *c=new Chart();charts.push_back(c);
  auto *o=lv_obj_create(p);lv_obj_remove_style_all(o);lv_obj_remove_flag(o,LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_pos(o,r.x,r.y);lv_obj_set_size(o,r.w,r.h);lv_obj_add_event_cb(o,chart_draw,LV_EVENT_DRAW_MAIN,c);return c;
}

// ---- the temperature through the week: Home Assistant's hourly forecast where it has one, else a day's low at
// five in the morning and its high at three in the afternoon, joined by half cosines (the shape of a real day).
inline float through(const Scene &s,float h){
  std::vector<std::pair<float,float>> a;
  for(size_t k=0;k<s.days.size();++k){a.push_back({24.f*k+5,s.days[k].low});a.push_back({24.f*k+15,s.days[k].high});}
  a.push_back({24.f*s.days.size()+5,s.days.back().low});  // the last night falls to that day's low
  float v=a.front().second;
  if(h>=a.back().first)v=a.back().second;
  for(size_t i=0;i+1<a.size();++i)if(h>=a[i].first&&h<a[i+1].first){
    const float t=(h-a[i].first)/(a[i+1].first-a[i].first),k=(1-std::cos(t*3.14159265f))/2;v=a[i].second+(a[i+1].second-a[i].second)*k;}
  if(!s.hours.empty()){
    // The hourly forecast, softened over five hours (a provider's whole degrees read as steps) and eased between
    // hours; past its end it hands over to the days over twelve hours.
    const int n=s.hours.size();const float first=s.hours.front().hour,last=s.hours.back().hour;
    auto soft=[&](int i){float sum=0,w=0;for(int j=-3;j<=3;++j){const int k=std::clamp(i+j,0,n-1);const float wt=4-std::abs(j);sum+=wt*s.hours[k].temp;w+=wt;}return sum/w;};
    auto at=[&](float x){x=std::clamp(x,first,last);const float u=(x-first)/3;const int i=std::min((n-1)/3-1,(int)u);
      const float t=std::clamp(u-i,0.f,1.f),k=(1-std::cos(t*3.14159265f))/2;return soft(3*i)+(soft(std::min(n-1,3*i+3))-soft(3*i))*k;};
    if(h>=first&&h<=last)return at(h);
    if(h>last&&h<last+12){const float t=(h-last)/12,k=t*t*(3-2*t);return at(last)*(1-k)+v*k;}
  }
  return v;
}

// ---- the week: day columns over one chart. B1 (variant 1) draws the reference's grid, B2 (variant 3) lines
// between the rows and today on a pill.
//
// What a card shows follows its room, in fixed tiers; a bigger card shows more, never the same things larger first:
//   1  the days: name, icon, high, low
//   2  + the temperature as a line through the week
//   3  + the rain as a second chart (a bar per day and the amount), with lines between the parts
//   4  + the chance of rain, where the provider gives one
// The highest tier that fits at the smallest face wins, then the largest face that keeps it. Every day the forecast
// has (up to seven) before either: a narrow card drops days only when even the smallest face cannot hold them.
struct Level {const lv_font_t *name,*icon,*small,*high,*low,*rain;};
inline Level level(const Fonts &f,int n){
  if(n>=2)return {f.headline,f.icon_big,f.icon,f.value,f.headline,f.note_big};
  if(n==1)return {f.note_big,f.icon,f.icon_mini,f.headline,f.note_big,f.note};
  if(n==0)return {f.note,f.icon_mini,f.icon_watch,f.label,f.note,f.note};
  return {f.note,f.icon_watch,f.icon_watch,f.label,f.note,f.note};
}
struct WeekPlan {int level=-9,cols=0,tier=0; bool pct=false;};
struct WeekRows {int pp,g,rs,bar,curve_min;};
inline WeekRows rows_of(int n){
  return {ui::px(n>0?8:4),ui::px(n>=2?8:n>0?5:3),ui::px(n>0?8:3),ui::px(n>=2?24:n>0?18:12),0};
}
inline int curve_min(const Level &l){return std::max(ui::px(ui::large()?30:22),H(l.high)*3/2);}
// The height of everything but the curve's and the bars' growth.
inline bool grid_lines=true;   // B1: the light grid on every tier
inline int week_fixed(const Level &l,const WeekPlan &p,const WeekRows &w){
  int h=2*w.pp+H(l.name)+w.g+H(l.icon)+H(l.high)+H(l.low);
  h+=p.tier>=3||grid_lines?2*w.rs+1:w.g;           // under the icons: a line with room, or a plain gap
  if(p.tier>=2)h+=curve_min(l);
  if(p.tier>=3)h+=w.rs+1+w.bar+w.g+H(l.rain);      // a line, the bars hanging from it, the amount
  if(p.tier>=4&&p.pct)h+=H(l.rain);
  return h;
}
inline int col_need(const Scene &s,const Level &l,int cols,int tier,int n){
  int cw=0;
  for(int k=0;k<cols;++k){const auto &d=s.days[k];
    cw=std::max({cw,width_of(k?d.name:"Today",l.name),width_of(deg(d.high),l.high),width_of(deg(d.low),l.low),H(l.icon)*5/4});
    if(tier>=3&&d.mm>=0.1f)cw=std::max(cw,width_of(mm_text(d.mm),l.rain));
  }
  return cw+2*ui::px(n>0?8:5);   // the pill's side padding, on every column alike
}
inline WeekPlan plan_week(const Scene &s,const Fonts &f,int w,int h){
  bool wet=false,pct=false;
  int cols=std::min<int>(7,s.days.size());
  while(cols>4&&col_need(s,level(f,0),cols,3,0)*cols>w)--cols;
  for(int k=0;k<cols;++k){wet|=s.days[k].mm>=0.1f;pct|=std::isfinite(s.days[k].pct);}
  for(int tier=4;tier>=1;--tier){
    if(tier>=3&&!wet&&!pct)continue;            // a dry week has no rain row to show
    for(int n=2;n>=(tier==1?-1:0);--n){
      WeekPlan p{n,cols,tier,pct&&tier>=4};
      const Level l=level(f,n);
      if(col_need(s,l,cols,tier,n)*cols>w)continue;
      const int fixed=week_fixed(l,p,rows_of(n));
      if(fixed>h)continue;
      if(n>0&&fixed>h*3/4)continue;              // a larger face only where the card keeps air around it
      return p;
    }
  }
  return {};
}
// A two-tone icon only where its small marks stay small beside the cloud; else the single glyph in its colour.
inline bool falls(const std::string &c){return c!="partlycloudy"&&c!="cloudy"&&c!="sunny"&&c!="clear-night"&&c!="fog"&&c!="windy"&&c!="exceptional";}
// One style per row: two-tone only when every condition shown can be drawn two-tone at this size.
inline bool row_two_tone(const Scene &s,int cols,const lv_font_t *big){
  for(int k=0;k<cols;++k)if(falls(s.days[k].cond)&&!mark_font(big))return false;
  return true;
}
inline bool two_tone_row=true;
inline void day_icon(lv_obj_t *p,const std::string &c,int cx,int y,const Level &l){
  icon(p,c,cx,y,l.icon,l.small,two_tone_row);
}
inline void week(lv_obj_t *card,Rect r,const Scene &s,const Fonts &f,int variant){
  grid_lines=variant!=3;
  const WeekPlan p=plan_week(s,f,r.w,r.h);
  if(p.level<-1){text(card,"Too small for the week",r.x,r.y,r.w,f.note,muted());return;}
  const bool grid=variant!=3;
  const Level l=level(f,p.level);WeekRows w=rows_of(p.level);
  int fixed=week_fixed(l,p,w),left=r.h-fixed;
  // The room left goes to the curve first (up to two fifths of the card), then to the rain bars (up to twice their
  // least height); what is still left is air above and under the whole.
  int curve=p.tier>=2?curve_min(l):0;
  if(p.tier>=2){const int more=std::max(0,std::min({left,r.h*3/10-curve,3*H(l.high)-curve}));curve+=more;left-=more;}
  const int cw=r.w/p.cols,x0=r.x+(r.w-cw*p.cols)/2,x1=x0+cw*p.cols;
  const int top=r.y+left/2;
  int y=top+w.pp;
  const int name_y=y;y+=H(l.name)+w.g;
  const int icon_y=y;y+=H(l.icon);
  int rule1=-1;if(p.tier>=3||grid){rule1=y+w.rs;y+=2*w.rs+1;}else y+=w.g;
  const int high_y=y;y+=H(l.high);
  const int curve_y=y;y+=curve;
  const int low_y=y;y+=H(l.low);
  int rule2=-1,bar_y=0,mm_y=0;
  if(p.tier>=3){rule2=y+w.rs;y+=w.rs+1;bar_y=y;y+=w.bar+w.g;mm_y=y;y+=H(l.rain);}
  const int pct_y=y;if(p.pct)y+=H(l.rain);
  const int bottom=y+w.pp;
  two_tone_row=row_two_tone(s,p.cols,l.icon);
  auto *c=chart(card,{r.x,r.y,r.w,r.h});
  const uint32_t rule=theme::hex(theme::dark?theme::RAISED_LINE:theme::LINE);
  const int inset=ui::px(p.level>0?8:5);
  if(!grid){const int pw=std::min(cw-ui::px(4),col_need(s,l,p.cols,p.tier,p.level));auto *pill=box(card,{x0+(cw-pw)/2,top,pw,bottom-top},theme::hex(theme::TRACK),ui::px(p.level>0?14:10));lv_obj_move_to_index(pill,0);}
  // The lines stop short of the card's sides; B1's lines between the days run from the first line to the bars' foot.
  if(rule1>=0)c->bars.push_back({{x0+inset-r.x,rule1-r.y,x1-inset-1-r.x,rule1-r.y},rule,0});
  if(rule2>=0)c->bars.push_back({{x0+inset-r.x,rule2-r.y,x1-inset-1-r.x,rule2-r.y},rule,0});
  if(grid&&rule1>=0)for(int k=1;k<p.cols;++k)c->hairs.push_back({x0+k*cw-r.x,rule1-r.y,(p.tier>=3?bar_y+w.bar:low_y+H(l.low))-r.y,rule});
  float most=10;for(int j=0;j<p.cols;++j)most=std::max(most,s.days[j].mm);
  for(int k=0;k<p.cols;++k){
    const auto &d=s.days[k];const int x=x0+k*cw;
    text(card,k==0?"Today":d.name,x,name_y,cw,l.name,k?muted():ink(),LV_TEXT_ALIGN_CENTER);
    day_icon(card,d.cond,x+cw/2,icon_y,l);
    text(card,deg(d.high),x,high_y,cw,l.high,ink(),LV_TEXT_ALIGN_CENTER);
    text(card,deg(d.low),x,low_y,cw,l.low,muted(),LV_TEXT_ALIGN_CENTER);
    if(p.tier<3)continue;
    const float mm=std::isfinite(d.mm)?d.mm:0;
    if(mm>=0.1f){
      // The reference's bar: flat, hung from the line, nearly the column's width, as long as the day is wet on one
      // scale for the week (10 mm at least), never thinner than a stroke. The amount under it in ink.
      const int bw=(grid?cw:std::min(cw-ui::px(4),col_need(s,l,p.cols,p.tier,p.level)))-2*ui::px(p.level>0?6:4),bx=x+(cw-bw)/2-r.x;
      const int bh=std::max(ui::px(3),(int)std::lround(w.bar*mm/most));
      c->bars.push_back({{bx,bar_y-r.y,bx+bw-1,bar_y-r.y+bh-1},rain(),0});
      text(card,mm_text(mm),x,mm_y,cw,l.rain,ink(),LV_TEXT_ALIGN_CENTER);
    }
    if(p.pct&&std::isfinite(d.pct))text(card,pct_text(d.pct),x,pct_y,cw,l.rain,muted(),LV_TEXT_ALIGN_CENTER);
  }
  if(p.tier<2)return;
  // The temperature through the week on one scale, from now to the end of the last column.
  float lo=1e9,hi=-1e9;const int first_h=s.hour,last_h=24*p.cols;
  for(int hh=first_h;hh<=last_h;++hh){const float v=through(s,hh);lo=std::min(lo,v);hi=std::max(hi,v);}
  const float lw=std::max(1.5f,ui::px(p.level>0?5:4)/2.f),in=lw+ui::px(4);
  const float span=std::max(1.f,hi-lo);
  auto yof=[&](float v){return curve_y-r.y+in+(curve-2*in)*(hi-v)/span;};
  c->fx=(int)std::ceil(x0-r.x+first_h*cw/24.f);
  for(int x=c->fx;x<x1-r.x;++x){
    const float v=through(s,std::max<float>(first_h,(x-(x0-r.x))*24.f/cw));c->ys.push_back(yof(v));
    c->cols.push_back(theme::foreground(theme::temperature(v)));
  }
  c->lw=lw;c->fill=true;c->base=curve_y-r.y+curve;c->fill_opa=theme::dark?48:90;
  c->dot_x=c->fx;c->dot_y=c->ys.front();c->dot_r=ui::px(p.level>0?5:4);c->dot_color=c->cols.front();
}

// ---- the next 48 hours: one curve, the condition and temperature every few clock hours, rain per hour, a time axis
inline void hours(lv_obj_t *card,Rect r,const Scene &s,const Fonts &f){
  if(s.hours.empty()){text(card,"No hourly forecast",r.x,r.y,r.w,f.note,muted());return;}
  const int n=std::min<int>(48,s.hours.size());
  const float slot=float(r.w)/n;
  const int gap=ui::px(4);
  // The largest face whose labels fit their stretch of hours; marks on whole clock hours (00, 03, 06 ...).
  int lv=1,step=3;Level l=level(f,1);
  for(lv=1;lv>=0;--lv){
    l=level(f,lv);bool ok=false;
    for(int k:{3,4,6,12}){const int need=std::max({width_of("00:00",f.note),width_of("-12°",l.high),H(l.icon)*5/4})+ui::px(8);
      if(slot*k>=need){step=k;ok=true;break;}}
    if(ok&&H(l.icon)+H(l.high)+ui::px(12)+H(f.note)+4*gap+curve_min(l)<=r.h)break;
  }
  if(lv<0)lv=0;
  l=level(f,lv);
  const int bar=ui::px(lv?12:8),axis=H(f.note);
  const int curve=r.h-(H(l.icon)+H(l.high)+gap+bar+gap+axis+gap);
  auto *c=chart(card,r);
  const int icon_y=r.y,high_y=icon_y+H(l.icon),curve_y=high_y+H(l.high)+gap,bar_y=curve_y+curve+gap,axis_y=bar_y+bar+gap;
  // A light three-hour mean: a provider's whole degrees read as steps.
  std::vector<float> t(n);
  for(int i=0;i<n;++i){static const float W[]={1,2,3,2,1};float sum=0,w=0;for(int j=-2;j<=2;++j){const int k=std::clamp(i+j,0,n-1);sum+=W[j+2]*s.hours[k].temp;w+=W[j+2];}t[i]=sum/w;}
  float lo=1e9,hi=-1e9,most=2;
  for(int i=0;i<n;++i){lo=std::min(lo,t[i]);hi=std::max(hi,t[i]);most=std::max(most,s.hours[i].mm);}
  const float lw=std::max(1.5f,ui::px(lv>0?5:4)/2.f),inset=lw+ui::px(3);const float span=std::max(1.f,hi-lo);
  c->fx=(int)std::lround(slot/2);
  for(int x=c->fx;x<=(int)std::lround(slot*(n-0.5f));++x){
    const float u=x/slot-0.5f;const int i=std::clamp((int)u,0,n-2);const float f=std::clamp(u-i,0.f,1.f),k=(1-std::cos(f*3.14159265f))/2;
    const float v=t[i]+(t[i+1]-t[i])*k;
    c->ys.push_back(curve_y-r.y+inset+(curve-2*inset)*(hi-v)/span);c->cols.push_back(theme::foreground(theme::temperature(v)));
  }
  c->fill=true;c->lw=lw;c->base=curve_y-r.y+curve;c->fill_opa=theme::dark?48:90;
  c->dot_x=c->fx;c->dot_y=c->ys.front();c->dot_r=ui::px(lv?6:4);c->dot_color=c->cols.front();
  bool hours_two_tone=true;for(int i=0;i<n;++i)if(falls(s.hours[i].cond)&&!mark_font(l.icon))hours_two_tone=false;
  static const char *WD[]={"Sun","Mon","Tue","Wed","Thu","Fri","Sat"};
  int today=0;for(int i=0;i<7;++i)if(!s.days.empty()&&std::string(s.days[0].name)==WD[i])today=i;
  for(int i=0;i<n;++i){
    const auto &h=s.hours[i];const int x=r.x+int(slot*i);
    if(h.mm>=0.05f){const int bh=std::max(ui::px(2),(int)std::lround(bar*h.mm/most)),bw=std::max(2,int(slot)-ui::px(2));
      c->bars.push_back({{x-r.x+(int(slot)-bw)/2,bar_y-r.y+bar-bh,x-r.x+(int(slot)-bw)/2+bw-1,bar_y-r.y+bar-1},rain(),ui::px(1)});}
    const int hour=h.hour%24;
    if(hour==0)c->hairs.push_back({x-r.x,curve_y-r.y,bar_y+bar-r.y,theme::hex(theme::TICK)});
    if(hour%step||i==0)continue;
    const int cw=int(slot*step),cx=x+int(slot/2),lx=std::clamp(cx-cw/2,r.x,r.right()-cw);
    if(cx-H(l.icon)/2<r.x||cx+H(l.icon)/2>r.right())continue;
    icon(card,h.cond,cx,icon_y,l.icon,l.small,hours_two_tone);
    text(card,deg(t[i]),lx,high_y,cw,l.high,ink(),LV_TEXT_ALIGN_CENTER);
    char b[8];snprintf(b,sizeof(b),"%02d:00",hour);
    text(card,hour==0?WD[(today+h.hour/24)%7]:b,lx,axis_y,cw,f.note,hour==0?ink():muted(),LV_TEXT_ALIGN_CENTER);
  }
}

// ---- the card around it: the screens' head row (round icon, name, condition) and, where there is room, a
// Week | 48 h key at its end and the temperature now in a large face.
struct Variant {int v; bool hours;};
inline void segmented(lv_obj_t *p,Rect r,const Fonts &f,bool hours_chosen){
  auto *track=box(p,r,theme::hex(theme::TRACK),LV_RADIUS_CIRCLE);
  const int half=r.w/2,in=ui::px(3);
  box(track,{hours_chosen?half:in,in,half-in,r.h-2*in},theme::hex(theme::CARD),LV_RADIUS_CIRCLE);
  text(track,"Week",0,(r.h-H(f.label))/2,half,f.label,hours_chosen?muted():ink(),LV_TEXT_ALIGN_CENTER);
  text(track,"48 h",half,(r.h-H(f.label))/2,half,f.label,hours_chosen?ink():muted(),LV_TEXT_ALIGN_CENTER);
}
inline void card(lv_obj_t *root,Rect r,const Board &b,const Scene &s,int variant,bool big){
  const Fonts &f=b.f;
  auto *o=box(root,r,theme::hex(theme::CARD),b.radius);
  lv_obj_set_style_border_width(o,1,0);lv_obj_set_style_border_color(o,theme::color(theme::LINE),0);
  const int pad=b.pad,w=r.w-2*pad;
  auto *p=box(o,{pad,pad,w,r.h-2*pad},theme::hex(theme::CARD));lv_obj_set_style_bg_opa(p,LV_OPA_TRANSP,0);
  const int head=b.circle;
  auto *badge=box(p,{0,0,head,head},theme::tint(hue(s.cond),40),LV_RADIUS_CIRCLE);
  const int ih=H(f.icon);
  auto *g=gl(badge,glyph(s.cond),(head-ih)/2,(head-ih)/2,f.icon,theme::icon(hue(s.cond)));(void)g;
  const int gap=ui::px(ui::large()?10:6);
  const int inner_h=r.h-2*pad;
  if(!big&&w>=inner_h*12/5){
    // A wide, low tile: the weather now in a column at the left (the tile's own head, the temperature large, today's
    // high and low), a line, and the week over the full height at the right, where it reaches a higher tier.
    char hl[40];snprintf(hl,sizeof(hl),"%s / %s",deg(s.days[0].high).c_str(),deg(s.days[0].low).c_str());
    const std::string now=deg(s.now,true);
    const lv_font_t *tf=f.hero;
    if(head+gap+H(tf)+H(f.note_big)>inner_h)tf=f.value;
    const int th=H(f.label),nh=H(f.note);
    const int col=std::max({head+gap+std::max(width_of(s.place,f.label),width_of(words(s.cond),f.note)),width_of(now,tf),width_of(hl,f.note_big)})+gap;
    text(p,s.place,head+gap,(head-th-nh)/2,col-head-gap,f.label,ink());
    text(p,words(s.cond),head+gap,(head-th-nh)/2+th,col-head-gap,f.note,muted());
    const int ty=head+(inner_h-head-H(tf)-H(f.note_big))/2;
    text(p,now,0,ty,col,tf,ink());
    text(p,hl,0,ty+H(tf),col,f.note_big,muted());
    const int sep=col+gap;
    box(p,{sep,ui::px(4),1,inner_h-ui::px(8)},theme::hex(theme::dark?theme::RAISED_LINE:theme::LINE));
    week(p,{sep+1+gap,0,w-sep-1-gap,inner_h},s,f,variant);
    return;
  }
  int right=w;
  // The key: only on a card that gets the whole page and has the room beside the name.
  const int key_h=std::min(head,std::max(ui::touch_min(),H(f.label)+ui::px(12)));
  const int key_w=2*(std::max(width_of("Week",f.label),width_of("48 h",f.label))+ui::px(28));
  const bool key=big&&variant>0&&w-key_w-head-gap>=ui::px(120);
  if(key){right=w-key_w;segmented(p,{right,(head-key_h)/2,key_w,key_h},f,variant==2);right-=gap;}
  // The temperature now in a large light face at the end of the head row (B, C), where it fits.
  std::string now=deg(s.now,variant==0);
  const lv_font_t *nf=f.value;
  if(variant>0&&!key&&H(nf)<=head+ui::px(6)&&w-width_of(now,nf)-head-gap>=ui::px(110)){
    const int nw=width_of(now,nf);text(p,now,w-nw,(head-H(nf))/2,nw,nf,ink(),LV_TEXT_ALIGN_RIGHT);right=w-nw-gap;
  }
  const int th=H(f.label),nh=H(f.note);const int hy=(head-th-nh)/2;
  text(p,s.place,head+gap,hy,right-head-gap,f.label,ink());
  std::string line=std::string(words(s.cond))+(variant==0||key||right==w?std::string(" · ")+deg(s.now,true):std::string());
  if(width_of(line,f.note)>right-head-gap)line=words(s.cond);
  text(p,line,head+gap,hy+th,right-head-gap,f.note,muted());
  const int top=head+ui::px(ui::large()?10:6);
  Rect area{0,top,w,r.h-2*pad-top};
  if(variant==2)hours(p,area,s,f);else week(p,area,s,f,variant);
}

// ---- the detail view: what a tap on the weather tile opens. Home Assistant's more-info dialog in order: the
// weather now (temperature, condition, today's high and low, feels like), its attributes (humidity, wind with its
// direction, air pressure, visibility: only those the entity has), then the forecast with its Week | 48 h key.
// Wide glass puts the weather now in a column beside the forecast; other glass stacks them.
inline std::string compass(float b){static const char *N[]={"N","NE","E","SE","S","SW","W","NW"};return N[((int)std::lround(b/45.f))%8];}
struct Attr {const char *icon,*caption; std::string value;};
inline std::vector<Attr> attrs(const Scene &s){
  std::vector<Attr> a;char b[32];
  if(std::isfinite(s.hum)){snprintf(b,sizeof(b),"%.0f%%",s.hum);a.push_back({"\U000F058E","Humidity",b});}
  if(std::isfinite(s.wind)){snprintf(b,sizeof(b),"%.0f km/h",s.wind);a.push_back({"\U000F059D","Wind",std::string(b)+(std::isfinite(s.bearing)?" "+compass(s.bearing):"")});}
  if(std::isfinite(s.pressure)){snprintf(b,sizeof(b),"%.0f hPa",s.pressure);a.push_back({"\U000F029A","Air pressure",b});}
  if(std::isfinite(s.vis)){snprintf(b,sizeof(b),"%.0f km",s.vis);a.push_back({"\U000F06D0","Visibility",b});}
  return a;
}
inline lv_obj_t *panel(lv_obj_t *root,Rect r,const Board &b){
  auto *o=box(root,r,theme::hex(theme::CARD),b.radius);
  lv_obj_set_style_border_width(o,1,0);lv_obj_set_style_border_color(o,theme::color(theme::LINE),0);return o;
}
inline int key_h(const Fonts &f){return std::max(ui::touch_min(),H(f.label)+ui::px(12));}
inline int key_w(const Fonts &f){return 2*(std::max(width_of("Week",f.label),width_of("48 h",f.label))+ui::px(28));}
inline int title_room(const Fonts &f){return key_h(f)+ui::px(ui::large()?10:6);}
// The forecast card: its title and the key on one row (where it has them), the week or the hours under it.
inline void forecast_card(lv_obj_t *root,Rect r,const Board &b,const Scene &s,int variant,bool title){
  const Fonts &f=b.f;auto *o=panel(root,r,b);const int pad=b.pad,w=r.w-2*pad;
  int y=pad;
  if(title){
    text(o,variant==2?"Next 48 hours":(std::to_string(std::min<int>(7,s.days.size()))+" days"),pad,pad+(key_h(f)-H(f.label))/2,w-key_w(f)-pad,f.label,ink());
    segmented(o,{pad+w-key_w(f),pad,key_w(f),key_h(f)},f,variant==2);y+=title_room(f);
  }
  Rect area{pad,y,w,r.h-y-pad};
  if(variant==2)hours(o,area,s,f);else week(o,area,s,f,variant);
}
inline int chip_h(const Fonts &f){return 2*ui::px(ui::large()?8:5)+H(f.label)+H(f.note);}
inline void chip(lv_obj_t *p,Rect r,const Fonts &f,const Attr &a){
  auto *t=box(p,r,theme::hex(theme::TRACK),ui::px(ui::large()?12:8));const int in=ui::px(ui::large()?10:6),v=ui::px(ui::large()?8:5),iw=H(f.icon_watch);
  gl(t,a.icon,in,v+(H(f.label)-iw)/2,f.icon_watch,muted());
  text(t,a.value,in+iw+ui::px(5),v,r.w-2*in-iw-ui::px(5),f.label,ink());
  text(t,a.caption,in,v+H(f.label),r.w-2*in,f.note,muted());
}
inline int forecast_tier(const Scene &s,const Fonts &f,int w,int h){return plan_week(s,f,w,h).tier;}
inline void detail(lv_obj_t *root,Rect area,const Board &b,const Scene &s,int variant){
  grid_lines=variant!=3;
  const Fonts &f=b.f;const int gap=b.gx,pad=b.pad;
  const auto list=attrs(s);const int n=list.size();
  char hl[40];snprintf(hl,sizeof(hl),"%s / %s",deg(s.days[0].high).c_str(),deg(s.days[0].low).c_str());
  const std::string feels=std::isfinite(s.feels)?"Feels like "+deg(s.feels):"",now=deg(s.now,true);
  const uint32_t rule=theme::hex(theme::dark?theme::RAISED_LINE:theme::LINE);
  int widest=0;for(auto &a:list)widest=std::max(widest,width_of(a.value,f.label));
  // Stacked: the weather now in one card, the forecast in a second under it. Which parts the now card carries
  // follows the forecast: the richest arrangement that leaves the forecast its highest tier wins.
  const int hero=std::max(H(f.hero),H(f.icon_big)),gi=ui::px(ui::large()?12:6),inner=area.w-2*pad;
  int per_row=n,rows=n?1:0;
  while(per_row>1&&(inner-(per_row-1)*ui::px(6))/per_row<widest+H(f.icon_watch)+ui::px(30)){per_row=(per_row+1)/2;rows=(n+per_row-1)/per_row;}
  const int tiles_h=rows*chip_h(f)+std::max(0,rows-1)*ui::px(6);
  std::string line;for(auto &a:list){std::string next=line+(line.empty()?"":" · ")+a.value;if(width_of(next,f.note)<=inner)line=next;}
  struct Option {int extra; bool title,key_in_hero,beside=false;};
  // Beside: on wide glass the attributes stand in the hero's row, right of the words, one tile each.
  const int hero_w=H(f.icon_big)+gi+width_of(now,f.hero)+gi+std::max({width_of(words(s.cond),f.headline),width_of(hl,f.note_big),width_of(feels,f.note_big)})+2*gi;
  const int beside_w=std::max(widest+H(f.icon_watch)+ui::px(30),width_of("Air pressure",f.note)+ui::px(24));
  const bool beside=n&&inner-hero_w>=n*beside_w+(n-1)*ui::px(6)&&chip_h(f)<=std::max(hero,chip_h(f));
  const Option options[]={{beside?std::max(0,chip_h(f)-hero):-1,true,false,true},{n?gi+tiles_h:-1,true,false},{line.empty()?-1:H(f.note)+ui::px(4),true,false},{0,true,false},{0,false,true}};
  Option best=options[3];int best_tier=-1,best_fh=-1;
  const int hours_need=H(f.icon_mini)+H(f.label)+H(f.note)+ui::px(8)+4*ui::px(4)+ui::px(40);
  for(auto &o:options){
    if(o.extra<0)continue;
    const int now_h=2*pad+hero+o.extra,fh=area.h-now_h-gap-2*pad-(o.title?title_room(f):0);
    const int t=variant==2?(fh>=hours_need?4:0):forecast_tier(s,f,inner,fh);
    // the richest arrangement at the highest tier; when nothing fits, the one that leaves the forecast most room
    if(t>best_tier||(t==0&&best_tier==0&&fh>best_fh)){best_tier=t;best=o;best_fh=fh;}
  }
  const int now_h=2*pad+hero+best.extra;
  auto *o=panel(root,{area.x,area.y,area.w,now_h},b);
  const int hero_y=best.beside?(now_h-hero)/2-pad:0;
  int right=area.w-pad;
  if(best.key_in_hero){right-=key_w(f);segmented(o,{right,pad+(hero-key_h(f))/2,key_w(f),key_h(f)},f,variant==2);right-=gi;}
  // The temperature in the hero face beside the icon; where the words then have no room, the icon goes first
  // (the words say the condition), then the face steps down.
  const int words_min=std::max(width_of(words(s.cond),f.label),width_of(hl,f.note_big));
  bool with_icon=true;const lv_font_t *tf=f.hero;const int ih=H(f.icon_big);
  for(int step=0;step<3;++step){
    with_icon=step==0;tf=step<2?f.hero:f.value;
    if(right-pad-(with_icon?ih+gi:0)-width_of(now,tf)-gi>=words_min)break;
  }
  int x=pad;
  if(with_icon){icon(o,s.cond,x+ih/2,hero_y+pad+(hero-ih)/2,f.icon_big,f.icon,true);x+=ih+gi;}
  const int tw=width_of(now,tf);text(o,now,x,hero_y+pad+(hero-H(tf))/2,tw,tf,ink());x+=tw+gi;
  const int rw=best.beside?std::max(0,pad+hero_w-x):right-x;
  // The words beside the temperature, as many lines as the hero's height and width hold.
  const lv_font_t *wf=width_of(words(s.cond),f.headline)<=rw?f.headline:f.label;
  const bool show_feels=!feels.empty()&&width_of(feels,f.note_big)<=rw&&H(wf)+2*H(f.note_big)<=hero;
  const int lines=H(wf)+H(f.note_big)+(show_feels?H(f.note_big):0);
  int ty=hero_y+pad+(hero-lines)/2;
  text(o,words(s.cond),x,ty,rw,wf,ink());ty+=H(wf);
  text(o,hl,x,ty,rw,f.note_big,muted());ty+=H(f.note_big);
  if(show_feels)text(o,feels,x,ty,rw,f.note_big,muted());
  if(best.beside){
    const int cw=std::min(ui::px(150),(inner-hero_w-(n-1)*ui::px(6))/n),x2=pad+inner-(n*cw+(n-1)*ui::px(6));
    const int hh=std::max(hero,chip_h(f));
    for(int i=0;i<n;++i)chip(o,{x2+i*(cw+ui::px(6)),pad+(hh-chip_h(f))/2,cw,chip_h(f)},f,list[i]);
  } else if(best.extra==gi+tiles_h&&n){
    const int cw=(inner-(per_row-1)*ui::px(6))/per_row;
    for(int i=0;i<n;++i)chip(o,{pad+(i%per_row)*(cw+ui::px(6)),pad+hero+gi+(i/per_row)*(chip_h(f)+ui::px(6)),cw,chip_h(f)},f,list[i]);
  } else if(best.extra>0)text(o,line,pad,pad+hero+ui::px(4),inner,f.note,muted());
  forecast_card(root,{area.x,area.y+now_h+gap,area.w,area.h-now_h-gap},b,s,variant,best.title);
}

// ---- a page with the card in its cells, the rest of the grid as plain neighbours
inline int check_bounds(lv_obj_t *parent){
  int count=0;lv_area_t p;lv_obj_get_coords(parent,&p);
  for(unsigned i=0;i<lv_obj_get_child_count(parent);++i){auto *o=lv_obj_get_child(parent,i);lv_area_t r;lv_obj_get_coords(o,&r);
    if(lv_obj_check_type(o,&lv_label_class)){} else
    if(r.x1<p.x1||r.y1<p.y1||r.x2>p.x2||r.y2>p.y2){fprintf(stderr,"OVERFLOW %s parent %d,%d..%d,%d child %d,%d..%d,%d\n",where.c_str(),p.x1,p.y1,p.x2,p.y2,r.x1,r.y1,r.x2,r.y2);++cuts;}
    count+=1+check_bounds(o);}
  return count;
}
inline void save(lv_obj_t *root,const std::string &path){
  lv_obj_update_layout(root);check_bounds(root);
  auto *buf=lv_snapshot_take(root,LV_COLOR_FORMAT_RGB888);assert(buf);
  FILE *fp=fopen(path.c_str(),"wb");assert(fp);fprintf(fp,"P6\n%d %d\n255\n",int(buf->header.w),int(buf->header.h));
  for(int y=0;y<int(buf->header.h);++y)for(int x=0;x<int(buf->header.w);++x){const auto *q=buf->data+y*buf->header.stride+3*x;uint8_t rgb[]={q[2],q[1],q[0]};fwrite(rgb,1,3,fp);}
  fclose(fp);lv_draw_buf_destroy(buf);
}
// size: "CxR" in cells, "full" for the whole grid, "detail" for the card opened from a tile (header row, no page bar).
inline void render(const Board &b,const std::string &out,const Scene &s,const std::string &size,int variant,bool dark){
  ui::configure(b.dpi,b.look);theme::set_dark(dark);icon_fonts=&b.f;
  where=std::string(b.name)+"-"+s.key+"-"+size+"-"+"ABCD"[variant]+(dark?"-dark":"");
  auto *root=box(lv_screen_active(),{0,0,b.width,b.height},theme::hex(theme::PAGE));
  const int head_h=H(b.f.headline);
  const int cw=(b.width-2*b.margin-(b.cols-1)*b.gx)/b.cols,ch=(b.height-b.top-b.footer-(b.rows-1)*b.gy)/b.rows;
  Rect main;int span_c=b.cols,span_r=b.rows;
  if(size=="detail"){
    const int iw=H(b.f.icon_mini);
    gl(root,"\U000F0141",b.margin,(b.top-iw)/2,b.f.icon_mini,ink());
    text(root,s.place,b.margin+iw+ui::px(8),(b.top-head_h)/2,b.width/2,b.f.headline,ink());
    text(root,"10:08",b.width-b.margin-ui::px(80),(b.top-H(b.f.headline))/2,ui::px(80),b.f.headline,muted(),LV_TEXT_ALIGN_RIGHT);
    main={b.margin,b.top,b.width-2*b.margin,b.height-b.top-b.margin};
  } else {
    text(root,"Home",b.margin,(b.top-head_h)/2,b.width-2*b.margin,b.f.headline,ink());
    if(size!="full"){span_c=size[0]-'0';span_r=size[2]-'0';}
    main={b.margin,b.top,span_c*cw+(span_c-1)*b.gx,span_r*ch+(span_r-1)*b.gy};
    for(int row=0;row<b.rows;++row)for(int col=0;col<b.cols;++col){
      if(row<span_r&&col<span_c)continue;
      auto *o=box(root,{b.margin+col*(cw+b.gx),b.top+row*(ch+b.gy),cw,ch},theme::hex(theme::CARD),b.radius);
      lv_obj_set_style_border_width(o,1,0);lv_obj_set_style_border_color(o,theme::color(theme::LINE),0);
      const int c=std::min(b.circle,ch-2*b.pad);
      if(c>ui::px(20)&&cw>c+ui::px(60)){
        box(o,{b.pad,(ch-c)/2,c,c},theme::tint((row+col)%2?theme::ha::AMBER:theme::ha::DEEP_ORANGE,40),LV_RADIUS_CIRCLE);
        const int tx=b.pad+c+ui::px(8);
        auto *t=lv_label_create(o);lv_obj_remove_style_all(t);lv_label_set_text(t,(row+col)%2?"Kitchen":"Living room");
        lv_obj_set_style_text_font(t,b.f.label,0);lv_obj_set_style_text_color(t,lv_color_hex(ink()),0);lv_label_set_long_mode(t,LV_LABEL_LONG_DOT);
        lv_obj_set_pos(t,tx,ch/2-H(b.f.label));lv_obj_set_size(t,cw-tx-b.pad,H(b.f.label));
        auto *u=lv_label_create(o);lv_obj_remove_style_all(u);lv_label_set_text(u,(row+col)%2?"Off":"21.5 °C");
        lv_obj_set_style_text_font(u,b.f.note,0);lv_obj_set_style_text_color(u,lv_color_hex(muted()),0);
        lv_obj_set_pos(u,tx,ch/2);lv_obj_set_size(u,cw-tx-b.pad,H(b.f.note));
      }
    }
    const int dot=ui::px(6),dg=ui::px(10),y=b.height-b.footer/2;
    for(int i=0;i<3;++i)box(root,{b.width/2+(i-1)*(dot+dg)-dot/2,y-dot/2,dot,dot},theme::hex(i==0?theme::INK:theme::TICK),LV_RADIUS_CIRCLE);
  }
  if(size=="detail")detail(root,main,b,s,variant);else card(root,main,b,s,variant,size=="full");
  save(root,out+"/"+where+".ppm");
  lv_obj_delete(root);
  for(auto *c:charts)delete c;charts.clear();
}
}  // namespace weather_study
