#pragma once
// Optional cover controls use measured space and physical touch sizes. Returning
// no layout leaves the primary controls intact and tilt in the detail view.
#include "tall_tile.h"
#include <cmath>
namespace cover_tile {
using tall_tile::Rect;
// The slats of a tilt slider, seen from the side at their angle (firmware 0.57.0): fully open (100) they lie flat and
// the light passes between them, closed (0) they stand nearly upright and overlap into one surface. A standing slider
// stacks them; a lying one puts them side by side, turned a quarter. They are drawn behind the slider's handle, in a
// pale tint, so the handle stays what the eye takes first. `step` is the least distance between two slats (3 mm).
struct Slat { float x1=0,y1=0,x2=0,y2=0; };
struct Slats { std::array<Slat,16> slat{}; int count=0; int width=0; };
inline float slat_angle(float tilt) {
  if(!std::isfinite(tilt))tilt=50;
  tilt=std::max(0.0f,std::min(100.0f,tilt));
  return (1.0f-tilt/100.0f)*72.0f*3.14159265f/180.0f;
}
inline Slats slats(int w,int h,float tilt,int step,int thickness) {
  Slats out;
  if(w<=0||h<=0||step<=0)return out;
  const bool lying=w>h;
  const int across=lying?h:w,along=lying?w:h;
  const int pitch=std::max(step,std::min(across*42/100,along/9));
  const float half=std::max(1.0f,std::min({across*0.30f,pitch*0.78f,(along-thickness)/2.0f}));
  const int n=std::max(1,std::min(16,(along-2*(int)half-thickness)/pitch+1));
  const float a=slat_angle(tilt),c=std::cos(a)*half,s=std::sin(a)*half;
  const float first=(along-(n-1)*pitch)/2.0f,middle=across/2.0f;
  for(int i=0;i<n;++i){
    const float at=first+i*pitch;
    out.slat[i]=lying?Slat{at-s,middle-c,at+s,middle+c}:Slat{middle-c,at-s,middle+c,at+s};
  }
  out.count=n;out.width=thickness;return out;
}
// What a cover card draws beside its heading, from the room it has (firmware 0.57.0). Group 0 is the chosen primary
// control (the position slider or open/stop/close), group 1 the slats (their slider or their keys), group 2 the
// open/stop/close a positional blind gets beside its sliders where there is room for them too. The richest that fits:
//   COLUMNS_KEYS   the sliders standing side by side, the keys in a row under them
//   COLUMNS_SIDE   the sliders standing, the keys stacked beside them (a card wider than tall)
//   COLUMNS        the sliders (or key stacks) standing side by side, a caption under each
//   ROWS           each group lying in a row of its own, a slider as a bar (Home Assistant's tile features stacked)
//   SWAP           one row and a key that turns it from the primary control to the slats and back
// A bar or a key may be drawn at `bar` (85 % of a finger, the size of the tile's own bars) where a whole finger does
// not fit; a standing slider needs `slider_min`. A card one row high lays its groups only (`standing` false): two
// thin standing sliders beside a name read worse than two bars. Nothing fits: no layout, and the card keeps its primary.
enum Tier { NONE=0, SWAP, ROWS, COLUMNS, COLUMNS_SIDE, COLUMNS_KEYS };
struct Group { Rect area, control, caption; int keys=0; bool slider=false,horizontal=false,lying=false; };
struct Layout { bool fits=false; Tier tier=NONE; std::array<Group,3> groups{}; Rect swap{}; };
inline int bar_height(int touch){return touch*85/100;}
inline Layout layout(Rect body,int touch,int gap,int caption,int slider_min,
                     bool position,int primary_keys,bool tilt,int tilt_keys,int extra_keys=0,bool standing=true) {
  Layout out;
  if(touch<=0||gap<0||caption<=0||(!tilt&&!tilt_keys&&!position&&!primary_keys))return out;
  const bool primary=position||primary_keys;
  const bool has[2]={primary,tilt||tilt_keys>0};
  const int bar=bar_height(touch);
  const int n[3]={primary_keys,tilt_keys,extra_keys};
  const bool slider[2]={position,tilt};
  // ---- standing: the groups side by side, each with its caption under it
  auto columns=[&](int keys_under,bool keys_beside)->Layout{
    Layout l;
    const int columns=has[0]+has[1],column_gap=2*gap;
    const int control_h=body.h-caption-gap-(keys_under?bar+gap:0);
    if(control_h<bar)return l;
    if((position||tilt)&&control_h<slider_min)return l;
    std::array<int,2> widths{};std::array<bool,2> horizontal{};
    const int beside=keys_beside?touch+column_gap:0;
    const int preferred=std::min((body.w-beside-column_gap*(columns-1))/columns,2*touch);
    if(keys_beside&&preferred<touch*3/2)return l;
    // A stack of keys stands as long as each key keeps a bar's height; else the keys lie in a row, as high as the room.
    std::array<int,2> key{};
    for(int i=0;i<2;++i){
      if(!has[i])continue;
      horizontal[i]=n[i]&&(control_h-(n[i]-1)*gap)/n[i]<bar;
      key[i]=n[i]?std::min(touch,horizontal[i]?control_h:(control_h-(n[i]-1)*gap)/n[i]):0;
      widths[i]=horizontal[i]?n[i]*key[i]+(n[i]-1)*gap:preferred;
      if(widths[i]<touch&&!(horizontal[i]&&widths[i]>=n[i]*bar))return l;
    }
    const int total=widths[0]+widths[1]+(has[0]&&has[1]?column_gap:0)+beside;
    if(total>body.w)return l;
    if(keys_beside&&body.h<3*bar+2*gap)return l;
    if(keys_under&&body.w<3*bar+2*gap)return l;
    int x=body.x+(body.w-total)/2;
    for(int i=0;i<2;++i){
      if(!has[i])continue;
      auto &g=l.groups[i];g.slider=slider[i];g.keys=g.slider?0:n[i];
      g.horizontal=horizontal[i];
      const int h=g.slider?control_h:g.horizontal?key[i]:g.keys*key[i]+(g.keys-1)*gap;
      g.area={x,body.y,widths[i],control_h+gap+caption};
      g.control={x,body.y+(control_h-h)/2,widths[i],h};
      g.caption={x,body.y+control_h+gap,widths[i],caption};
      x+=widths[i]+column_gap;
    }
    if(keys_beside){
      auto &g=l.groups[2];g.keys=extra_keys;
      const int key=std::min(touch,(body.h-2*gap)/3),h=3*key+2*gap;
      g.area=g.control={x,body.y+(control_h+gap+caption-h)/2,touch,h};
    }
    if(keys_under){
      auto &g=l.groups[2];g.keys=extra_keys;g.horizontal=true;
      const int w=std::min(body.w,3*std::max(bar,std::min(touch*3/2,(body.w-2*gap)/3))+2*gap);
      g.area=g.control={body.x+(body.w-w)/2,body.bottom()-bar,w,bar};
    }
    l.tier=keys_under?COLUMNS_KEYS:keys_beside?COLUMNS_SIDE:COLUMNS;l.fits=true;return l;
  };
  // ---- lying: each group a row of its own, a slider as a bar across the row
  auto rows=[&](bool swap)->Layout{
    Layout l;
    const int count=swap?1:has[0]+has[1],row=std::min(touch,(body.h-(count-1)*gap)/count);
    if(row<bar)return l;
    const int width=body.w;
    for(int i=0;i<2;++i){
      if(!has[i])continue;
      const int keys=slider[i]?0:n[i],need=keys?keys*row+(keys-1)*gap:2*touch;
      if(need+(swap?row+gap:0)>width)return l;
    }
    int y=body.y+(body.h-count*row-(count-1)*gap)/2;
    for(int i=0;i<2;++i){
      if(!has[i])continue;
      auto &g=l.groups[i];g.slider=slider[i];g.lying=g.slider;g.keys=g.slider?0:n[i];g.horizontal=true;
      const int w=(swap?width-row-gap:width);
      const int cw=g.slider?w:std::min(w,g.keys*std::max(row,std::min(touch*3/2,(w-(g.keys-1)*gap)/g.keys))+(g.keys-1)*gap);
      g.area={body.x,y,w,row};
      g.control={body.x+(w-cw)/2,y,cw,row};
      if(!swap)y+=row+gap;
    }
    if(swap)l.swap={body.right()-row,y,row,row};
    l.tier=swap?SWAP:ROWS;l.fits=true;return l;
  };
  const bool lying_body=body.w>=2*body.h;
  for(Layout l:{standing&&extra_keys&&position&&!lying_body?columns(extra_keys,false):Layout{},
                standing&&extra_keys&&position&&body.w>body.h?columns(0,true):Layout{},
                !standing||lying_body?Layout{}:columns(0,false),
                rows(false),
                standing&&lying_body?columns(0,false):Layout{},
                has[0]&&has[1]?rows(true):Layout{}}){
    if(l.fits)return l;
  }
  return out;
}
}
