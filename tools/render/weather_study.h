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

struct Fonts {const lv_font_t *label,*note,*note_big,*headline,*value,*icon_watch,*icon_mini,*icon,*icon_big;};
struct Board {const char *name,*look; int width,height,dpi,cols,rows,top,footer,margin,gx,gy,radius,pad,circle; Fonts f;};
struct Rect {int x,y,w,h; int right()const{return x+w;} int bottom()const{return y+h;}};
struct Day {const char *name,*cond; float high,low,mm,pct;};
struct Hour {int hour; const char *cond; float temp,mm,pct;};
struct Scene {const char *key,*place,*cond,*words; float now; int hour; std::vector<Day> days; std::vector<Hour> hours;};

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
inline void icon(lv_obj_t *p,const std::string &c,int cx,int y,const lv_font_t *big,const lv_font_t *small,bool two_tone){
  const int b=H(big),s=H(small),x=cx-b/2;
  if(!two_tone){gl(p,glyph(c),x,y,big,theme::foreground(hue(c)));return;}
  namespace h=theme::ha;
  const char *CLOUD="\U000F0590",*SUN="\U000F0599",*MOON="\U000F0594",*DROP="\U000F058C",*FLAKE="\U000F0717",*BOLT="\U000F0241";
  if(c=="sunny"){gl(p,SUN,x,y,big,theme::foreground(h::SUNNY));return;}
  if(c=="clear-night"){gl(p,MOON,x,y,big,theme::foreground(h::NIGHT_SKY));return;}
  if(c=="fog"||c=="windy"||c=="exceptional"){gl(p,glyph(c),x,y,big,cloud_back());return;}
  // A cloud of the big face, lifted when something falls out of it.
  const bool falls=c!="partlycloudy"&&c!="cloudy";
  const int lift=falls?b/6:0;
  if(c=="partlycloudy")gl(p,SUN,x+b/2-s/8,y-s/10,small,theme::foreground(h::SUNNY));
  if(c=="cloudy")gl(p,CLOUD,x+b/2-s/6,y-s/12,small,cloud_back());
  gl(p,CLOUD,x,y+(c=="partlycloudy"||c=="cloudy"?b/12:0)-lift,big,cloud_front());
  if(!falls)return;
  // What falls: two marks (three when pouring) under the cloud's belly, half a small face each.
  const int below=y+b-lift-s*3/4+b/12;
  auto mark=[&](const char *g,uint32_t col,int dx){gl(p,g,cx-s/2+dx,below,small,col);};
  const int step=s*5/8;
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
  struct Cap {lv_area_t a; uint32_t top,bottom;}; std::vector<Cap> caps;   // a day's range, coloured high to low
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
  for(auto &k:c->caps){lv_draw_rect_dsc_t d;lv_draw_rect_dsc_init(&d);d.radius=LV_RADIUS_CIRCLE;d.bg_opa=LV_OPA_COVER;
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
    auto soft=[&](int i){static const float W[]={1,2,3,2,1};float sum=0,w=0;
      for(int j=-2;j<=2;++j){const int k=std::clamp(i+j,0,n-1);sum+=W[j+2]*s.hours[k].temp;w+=W[j+2];}return sum/w;};
    auto at=[&](float x){x=std::clamp(x,first,last);const int i=std::min(n-2,(int)(x-first));const float t=std::clamp(x-first-i,0.f,1.f),k=(1-std::cos(t*3.14159265f))/2;
      return soft(i)+(soft(i+1)-soft(i))*k;};
    if(h>=first&&h<=last)return at(h);
    if(h>last&&h<last+12){const float t=(h-last)/12,k=t*t*(3-2*t);return at(last)*(1-k)+v*k;}
  }
  return v;
}

// ---- the week: day columns over one chart
struct Level {const lv_font_t *name,*icon,*small,*high,*low,*rain;};
inline Level level(const Fonts &f,int n){
  if(n>=2)return {f.headline,f.icon_big,f.icon,f.value,f.headline,f.note_big};
  if(n==1)return {f.note_big,f.icon,f.icon_mini,f.headline,f.note_big,f.note};
  if(n==0)return {f.note,f.icon_mini,f.icon_watch,f.label,f.note,f.note};
  return {f.note,f.icon_watch,f.icon_watch,f.label,f.note,f.note};  // tight: the icon in the small face
}
// What a short card gives up, in this order: the chance, the rain bars, the amount (the icon still says rain).
struct WeekPlan {int level=-9,cols=0; bool rain=false,pct=false,bars=false;};
inline int gap_of(int n){return ui::px(n>=2?8:n>0?6:n==0?3:2);}
inline int bar_of(int n){return ui::px(n>=2?12:n>0?10:6);}
inline int week_fixed(const Level &l,const WeekPlan &p,int gap,int bar){
  return H(l.name)+gap+H(l.icon)+gap+H(l.high)+H(l.low)+(p.rain?gap+(p.bars?bar:0)+H(l.rain)+(p.pct?H(l.rain):0):0);
}
inline int curve_min(const Level &l){return std::max(ui::px(26),H(l.high));}
inline WeekPlan plan_week(const Scene &s,const Fonts &f,int w,int h,int variant){
  const bool B=variant!=0;
  // More days before bigger letters; the rain's words before bigger letters; then the largest face that fits.
  for(int cols=std::min<int>(7,s.days.size());cols>=std::min<int>(4,s.days.size());--cols)
  for(int drop=0;drop<4;++drop)
  for(int n=2;n>=-1;--n){
    const Level l=level(f,n);
    bool wet=false,pct=false;
    for(int k=0;k<cols;++k){wet|=s.days[k].mm>=0.1f;pct|=std::isfinite(s.days[k].pct);}
    WeekPlan p{n,cols,B?wet:true,pct,!B};
    if(drop>=1)p.pct=false;
    if(drop>=2)p.bars=false;
    if(drop>=3)p.rain=false;
        int cw=0;
    for(int k=0;k<cols;++k){const auto &d=s.days[k];
      cw=std::max({cw,width_of(k?d.name:"Today",l.name),width_of(deg(d.high,!B),l.high),width_of(deg(d.low,!B),l.low),H(l.icon)*5/4});
      if(p.rain&&(d.mm>=0.1f||!B))cw=std::max(cw,width_of(mm_text(d.mm),l.rain));
    }
    cw+=ui::px(n>0?10:6);
    if(cw*cols>w)continue;
    // A big face only where the chart keeps the larger share of the card.
    const int fixed=week_fixed(l,p,gap_of(n),bar_of(n));
    if(fixed+curve_min(l)>h)continue;
    if(n>0&&fixed>h*75/100)continue;
    return p;
  }
  return {};
}
inline void week(lv_obj_t *card,Rect r,const Scene &s,const Fonts &f,int variant){
  const WeekPlan p=plan_week(s,f,r.w,r.h,variant);
  if(p.level<-1){text(card,"Too small for the week",r.x,r.y,r.w,f.note,muted());return;}
  const Level l=level(f,p.level);const int gap=gap_of(p.level),bar=bar_of(p.level);
  const int fixed=week_fixed(l,p,gap,bar);
  // The curve takes the room left, up to two fifths of the card; what is left beyond it is air above and under.
  const int curve=std::min(r.h-fixed,std::max(curve_min(l),(p.level>=2?r.h*2/5:std::min(r.h*2/5,3*H(l.high)))));
  const int top=r.y+(r.h-fixed-curve)/2,cw=r.w/p.cols,x0=r.x+(r.w-cw*p.cols)/2;
  const bool B=variant!=0;
  auto *c=chart(card,{r.x,r.y,r.w,r.h});
  // Today on a pale pill (B), as the forecast tile has it: its padding comes out of the air, never past the card.
  if(B){const int y1=std::max(r.y,top-gap),y2=std::min(r.bottom(),top+fixed+curve+gap);
    auto *pill=box(card,{x0+ui::px(2),y1,cw-ui::px(4),y2-y1},theme::hex(theme::TRACK),ui::px(p.level>0?14:10));lv_obj_move_to_index(pill,0);}
  int y=top;
  const int name_y=y;y+=H(l.name)+gap;const int icon_y=y;y+=H(l.icon)+gap;const int high_y=y;y+=H(l.high);
  const int curve_y=y;y+=curve;const int low_y=y;y+=H(l.low);
  const int bar_y=y+gap;const int rain_y=bar_y+(p.bars?bar:0);
  // Column hairlines (A): from under the icons to the rain bars, the reference's frame.
  if(!B)for(int k=1;k<p.cols;++k)c->hairs.push_back({x0+k*cw-r.x,high_y-r.y-gap/2,(p.rain?bar_y+(p.bars?bar:0):low_y+H(l.low))-r.y,theme::hex(theme::LINE)});
  float most=10;for(int j=0;j<p.cols;++j)most=std::max(most,s.days[j].mm);
  for(int k=0;k<p.cols;++k){
    const auto &d=s.days[k];const int x=x0+k*cw;
    text(card,k==0?"Today":d.name,x,name_y,cw,l.name,B&&k!=0?muted():ink(),LV_TEXT_ALIGN_CENTER);
    icon(card,d.cond,x+cw/2,icon_y,l.icon,l.small,true);
    text(card,deg(d.high,!B),x,high_y,cw,l.high,ink(),LV_TEXT_ALIGN_CENTER);
    text(card,deg(d.low,!B),x,low_y,cw,l.low,B?muted():ink(),LV_TEXT_ALIGN_CENTER);
    if(!p.rain)continue;
    const float mm=std::isfinite(d.mm)?d.mm:0;
    if(B&&mm>=0.1f){
      // A drop and the amount, in the rain's blue, only on a day it rains.
      const std::string t=mm_text(mm);const int tw=width_of(t,l.rain),dw=tw+width_of("\U000F058C",f.icon_watch)<=cw-ui::px(4)?width_of("\U000F058C",f.icon_watch):0,x1=x+(cw-dw-tw)/2;
      if(dw)gl(card,"\U000F058C",x1,rain_y+(H(l.rain)-H(f.icon_watch))/2,f.icon_watch,rain());
      text(card,t,x1+dw,rain_y,tw,l.rain,rain());
    }
    if(!B)text(card,mm_text(mm),x,rain_y,cw,l.rain,ink(),LV_TEXT_ALIGN_CENTER);
    if(p.pct&&std::isfinite(d.pct)&&(!B||d.pct>=30))text(card,pct_text(d.pct),x,rain_y+H(l.rain),cw,l.rain,B?muted():ink(),LV_TEXT_ALIGN_CENTER);
    if(p.bars&&mm>=0.1f){
      // The reference's bar: hung from the frame's line, as long as the day is wet on one scale (10 mm at least).
      const int bw=cw-ui::px(8),bh=std::max(ui::px(3),(int)std::lround(bar*mm/most)),bx=x+(cw-bw)/2-r.x;
      c->bars.push_back({{bx,bar_y-r.y,bx+bw-1,bar_y-r.y+std::max(ui::px(3),bh*2/3)-1},ink(),ui::px(2)});
    }
  }
  // The range of the week on one scale.
  float lo=1e9,hi=-1e9;const int first_h=s.hour,last_h=24*p.cols;
  for(int hh=first_h;hh<=last_h;++hh){const float v=through(s,hh);lo=std::min(lo,v);hi=std::max(hi,v);}
  const float lw=std::max(1.5f,ui::px(p.level>0?5:4)/2.f),inset=lw+ui::px(3);
  const float span=std::max(1.f,hi-lo);
  auto yof=[&](float v){return curve_y-r.y+inset+(curve-2*inset)*(hi-v)/span;};
  const uint32_t line=theme::dark?ink():theme::hex(theme::INK);
  if(variant==3){
    // D: each day's range as a capsule on the week's scale, coloured from its high down to its low, over a faint
    // track for the whole scale; today carries the temperature now as a dot.
    const int capw=std::max(ui::px(6),std::min(ui::px(12),cw/6));
    for(int k=0;k<p.cols;++k){
      const auto &d=s.days[k];const int cx=x0+k*cw+cw/2-r.x;
      c->bars.push_back({{cx-capw/2,(int)(curve_y-r.y+inset-capw/2),cx-capw/2+capw-1,(int)(curve_y-r.y+curve-inset+capw/2)},theme::hex(theme::TRACK),LV_RADIUS_CIRCLE});
      c->caps.push_back({{cx-capw/2,(int)std::lround(yof(d.high)-capw/2),cx-capw/2+capw-1,(int)std::lround(yof(d.low)+capw/2)},
                         theme::foreground(theme::temperature(d.high)),theme::foreground(theme::temperature(d.low))});
      if(k==0){c->dot_x=cx-0.5f+capw%2*0.5f;c->dot_y=yof(s.now);c->dot_r=capw*3/4;c->dot_color=theme::hex(theme::CARD);}
    }
    if(c->dot_r){c->dot_color=line;}
    return;
  }
  // A and B: the temperature through the week, from now to the end of the last column.
  c->fx=(int)std::lround(x0-r.x+first_h*cw/24.f);
  const int end=x0-r.x+p.cols*cw;
  for(int x=c->fx;x<end;++x){
    const float v=through(s,(x-(x0-r.x))*24.f/cw);c->ys.push_back(yof(v));
    c->cols.push_back(B?theme::foreground(theme::temperature(v)):line);
  }
  c->lw=lw;c->fill=B;c->base=curve_y-r.y+curve;c->fill_opa=theme::dark?48:90;
  c->dot_x=c->fx;c->dot_y=c->ys.front();c->dot_r=ui::px(p.level>0?6:4);c->dot_color=c->cols.front();
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
    icon(card,h.cond,cx,icon_y,l.icon,l.small,true);
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
  int right=w;
  // The key: only on a card that gets the whole page and has the room beside the name.
  const int key_h=std::min(head,std::max(ui::touch_min(),H(f.label)+ui::px(12)));
  const int key_w=2*(std::max(width_of("Week",f.label),width_of("48 h",f.label))+ui::px(28));
  const bool key=big&&(variant==1||variant==2)&&w-key_w-head-gap>=ui::px(120);
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
  ui::configure(b.dpi,b.look);theme::set_dark(dark);
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
  card(root,main,b,s,variant,size=="full"||size=="detail");
  save(root,out+"/"+where+".ppm");
  lv_obj_delete(root);
  for(auto *c:charts)delete c;charts.clear();
}
}  // namespace weather_study
