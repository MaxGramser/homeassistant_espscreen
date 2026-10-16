#include "../components/smart_display/tall_tile.h"
#include "../components/smart_display/cover_tile.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdio>
using namespace tall_tile;
static bool inside(Rect r,int w,int h){return r.x>=0&&r.y>=0&&r.right()<=w&&r.bottom()<=h;}
int main(){
  // Physical density, available area and selected group count vary independently.
  // This catches negative body space, overlap and touch shrinkage, rather than
  // pinning coordinates to one board or repeating the layout implementation.
  unsigned checked=0;
  for(int touch:{28,39,47,60,84})for(int width=touch*2;width<900;width+=17)
  for(int height=20;height<650;height+=19)for(int groups=0;groups<=2;++groups){
    Metrics m{width,height,16,14,54,8,touch,400,{touch,touch},groups};
    auto l=layout(m);
    if(!l.fits){assert(height<16+groups*(touch+8));continue;}
    assert(inside(l.header,width,height));assert(l.header.h>=16);
    assert(inside(l.body,width,height));assert(l.body.y>=l.header.bottom());
    int end=l.body.bottom();
    for(int i=0;i<groups;++i){
      auto row=l.rows[i];assert(inside(row,width,height));assert(row.h>=touch);assert(row.y>=end);end=row.bottom();
      auto buttons=keys(row,3,touch+12,touch,8);
      if(buttons[0].empty()){assert(row.w<3*touch+16);continue;}
      for(int j=0;j<3;++j){assert(inside(buttons[j],width,height));assert(buttons[j].w>=touch&&buttons[j].h>=touch);if(j)assert(buttons[j-1].right()<=buttons[j].x);}
    }
    if(groups)assert(end==height);
    ++checked;
  }
  // A switch always has horizontal travel and a full-height touch target.
  for(int touch:{28,39,47,60,84})for(int width=1;width<500;++width){
    const auto track=toggle(width,touch);
    if(track.empty()){assert(width<touch+touch/2);continue;}
    assert(track.w<=width&&track.h==touch&&track.w>=touch+touch/2);
  }
  // Centre an action's icon and text within the actual available card area.
  for(int width:{40,80,131,218,300,500})for(int height=20;height<600;height+=7){
    auto a=action(width,height,54,28,16,14,8);
    if(!a.fits)continue;
    assert(inside(a.icon,width,height)&&inside(a.title,width,height)&&inside(a.state,width,height));
    assert(a.title.y>=a.icon.bottom()+8&&a.state.y>=a.title.bottom());
    assert(std::abs(2*a.icon.x+a.icon.w-width)<=1);
    assert(a.title.w==width&&a.state.w==width);
    assert(std::abs(a.icon.y-(height-a.state.bottom()))<=1);
  }
  // An on/off card: the same stack with its switch under it, the switch never shrunk, the whole group centred.
  for(int width:{40,80,131,218,300,500})for(int height=20;height<600;height+=7){
    auto a=action(width,height,54,28,16,14,8,78,39);
    if(!a.fits){assert(width<78||height<28+8+16+16+39);continue;}
    assert(inside(a.icon,width,height)&&inside(a.title,width,height)&&inside(a.control,width,height));
    assert(a.control.w==78&&a.control.h==39&&a.control.y>=a.state.bottom()+16);
    assert(std::abs(2*a.control.x+a.control.w-width)<=1);
    assert(std::abs(a.icon.y-(height-a.control.bottom()))<=1);
  }
  assert(action(300,400,54,28,16,14,8).control.empty());
  // Extended covers never overlap groups, leave the card or squeeze a control below what its kind needs: a standing
  // slider its slider height, a bar or a key 85 % of a finger (cover_tile::bar_height). Sweep independent dimensions,
  // densities and partial capability sets, with and without open/stop/close beside a positional blind.
  unsigned covers=0,tiers[6]{};
  for(int touch:{28,39,48,60})for(int width=20;width<800;width+=31)
  for(int height=20;height<600;height+=23)for(int keys=0;keys<4;++keys)
  for(int tilt_keys=0;tilt_keys<4;++tilt_keys)for(int extra:{0,3}){
    const int bar=cover_tile::bar_height(touch);
    const auto c=cover_tile::layout({0,0,width,height},touch,6,16,2*touch,keys==0,keys,tilt_keys==0,tilt_keys,keys==0?extra:0);
    if(!c.fits){assert(c.tier==cover_tile::NONE);continue;}
    ++tiers[c.tier];
    for(int i=0;i<3;++i){
      const auto &g=c.groups[i];
      if(g.area.empty())continue;
      assert(inside(g.control,width,height)&&inside(g.area,width,height));
      if(!g.caption.empty()){assert(inside(g.caption,width,height));assert(g.control.bottom()<g.caption.y);}
      if(g.slider&&!g.lying)assert(g.control.h>=2*touch);
      if(g.slider&&g.lying)assert(g.control.h>=bar&&g.control.w>=2*touch);
      if(g.keys&&g.horizontal)assert(g.control.h>=bar&&g.control.w>=g.keys*bar+(g.keys-1)*6);
      if(g.keys&&!g.horizontal)assert(g.control.w>=touch&&g.control.h>=g.keys*std::min(bar,touch)+(g.keys-1)*6);
      for(int j=i+1;j<3;++j){
        const auto &o=c.groups[j];
        if(o.area.empty()||(c.tier==cover_tile::SWAP&&i<2&&j<2))continue;
        assert(g.control.right()<=o.control.x||o.control.right()<=g.control.x||g.control.bottom()<=o.control.y||o.control.bottom()<=g.control.y);
      }
    }
    if(c.tier==cover_tile::SWAP){assert(!c.swap.empty()&&inside(c.swap,width,height)&&c.swap.w>=bar);
      assert(c.groups[0].control.right()<=c.swap.x);}
    ++covers;
  }
  assert(covers>1000);
  for(int t=1;t<6;++t)assert(tiers[t]>0);
  assert(cover_tile::layout({0,0,131,60},39,4,13,91,true,0,true,0).tier==cover_tile::SWAP);
  assert(!cover_tile::layout({0,0,100,30},39,4,13,91,true,0,true,0).fits);
  assert(cover_tile::layout({0,0,204,180},48,8,19,150,true,0,true,0).fits);
  // A Guition 1x2 stands its sliders, a CYD 1x2 shares one row and swaps, a lying 2x1 lays them in rows.
  assert(cover_tile::layout({0,0,194,150},48,8,16,96,true,0,true,0,3).tier==cover_tile::COLUMNS);
  assert(cover_tile::layout({0,0,132,50},40,4,13,80,true,0,true,0,3).tier==cover_tile::SWAP);
  assert(cover_tile::layout({0,0,208,94},48,8,16,96,true,0,true,0,3).tier==cover_tile::ROWS);
  assert(cover_tile::layout({0,0,424,180},48,8,16,96,true,0,true,0,3).tier==cover_tile::COLUMNS_SIDE);
  // The slats: within the slider, as many as fit at their pitch, flat when open and steep when closed.
  for(int w:{30,60,96,180})for(int h:{30,80,240,500})for(float tilt:{0.0f,45.0f,100.0f}){
    const auto s=cover_tile::slats(w,h,tilt,12,6);
    assert(s.count>=1&&s.count<=16);if(h>=80&&w<=h)assert(s.count>=3);
    for(int i=0;i<s.count;++i){const auto &l=s.slat[i];
      assert(std::min(l.x1,l.x2)>=-1&&std::max(l.x1,l.x2)<=w+1&&std::min(l.y1,l.y2)>=-1&&std::max(l.y1,l.y2)<=h+1);}
    const auto &m=s.slat[0];const float dx=std::abs(m.x2-m.x1),dy=std::abs(m.y2-m.y1);
    if(w<=h&&tilt==100.0f)assert(dy<0.5f);
    if(w<=h&&tilt==0.0f)assert(dy>dx);
  }
  // A CYD-sized cell accepts one row, but cannot promise two physical rows.
  Metrics compact{131,92,13,13,28,4,39,280,{39,39},1};
  assert(layout(compact).fits);compact.row_count=2;assert(!layout(compact).fits);
  Metrics spacious{424,204,21,19,54,8,47,400,{47,47},2};
  assert(layout(spacious).fits);
  assert(fits_text({0,0,80,40},79,39));assert(!fits_text({0,0,80,40},81,39));
  std::printf("tall tile geometry: %u valid arrangements checked\n",checked);
}
