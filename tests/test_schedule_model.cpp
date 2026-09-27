#include "components/smart_display/schedule_model.h"
#include "components/smart_display/schedule_layout.h"
#include <cassert>

int main() {
  using namespace schedule_model;
  Programme<int> brightness{"weekdays", "Light", 31, true, {{"one",0,1440,70}}};
  assert(valid(brightness));
  assert(split(brightness,0,"two"));
  assert(brightness.slots[1].value==70);
  assert(boundary(brightness,1,1439));
  assert(brightness.slots[0].end==1435);
  assert(!split(brightness,1,"three"));
  assert(!merge(brightness,9));
  brightness.slots[1].value=25;
  assert(merge(brightness,0));
  assert(brightness.slots[0].value==25 && brightness.slots[0].start==0);
  assert(!merge(brightness,0));
  assert(valid(brightness));
  assert(!boundary(brightness,0,720));
  brightness.days=0; assert(!valid(brightness));
  Heating h;
  assert(h.value(0).off && h.position(Heat{})==0);
  assert(h.value(1).temperature==5);
  assert(h.value(h.positions()).temperature==30);
  for(int i=0;i<=h.positions();++i) assert(h.position(h.value(i))==i);
  assert(!h.valid({false,0}) && !h.valid({false,20.25f}));
  Lifecycle life; life.dirty=true;
  assert(life.can_save(true) && life.needs_guard());
  life.pending=true; assert(!life.can_save(true));
  life.pending=false; life.uncertain=true; assert(!life.can_save(true));
  life.confirmed(); assert(!life.dirty && !life.pending && !life.uncertain);
  struct Shape {int w,h,dpi; const char* look;};
  for(auto s:{Shape{320,240,143,"compact"},Shape{240,320,143,"compact"},
              Shape{480,480,170,"standard"},Shape{720,720,254,"standard"},
              Shape{800,480,217,"standard"},Shape{1024,600,127,"standard"}}) {
    ui::configure(s.dpi,s.look);
    auto l=schedule_layout::place(s.w,s.h,ui::px(ui::large()?25:13));
    for(auto r:{l.back,l.save,l.title,l.body,l.pager}) {
      assert(r.x>=0 && r.y>=0 && r.w>0 && r.h>0);
      assert(r.x+r.w<=s.w && r.y+r.h<=s.h);
    }
    assert(l.back.w>=ui::touch_min() && l.save.h>=ui::touch_min());
    assert(l.body.y>=l.back.y+l.back.h);
    if(l.paged) assert(l.body.y+l.body.h<=l.pager.y);
  }
}
