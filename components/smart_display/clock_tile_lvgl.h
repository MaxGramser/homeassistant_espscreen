// The clock on a tile: its faces and the bedside clock.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What proves it: tests/test_screen_saver.py.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
inline std::string time_text(esphome::ESPTime now) {
  if (!now.is_valid()) return "--:--";
  if (screen_settings::current.clock_24h) return hhmm(now);
  char b[8]; snprintf(b, sizeof(b), "%d:%02d", now.hour % 12 ? now.hour % 12 : 12, now.minute);
  return b;
}
// Digital: big time over the date. Analog: index strokes (numerals at 12/3/6/9 on
// large cards) with hour and minute hands. A single card adds a calendar block
// beside the dial (weekday, big day number, short month); a wide card adds the
// digital time and the date instead. Parts: 0-11 marks, 12-13 hands, 14 centre,
// 15-17 text, 18 the second hand (points 28-29), shown while the screen is awake.
inline void second_hand(Widgets &w,const esphome::ESPTime &now) {
  float a=(now.is_valid()?now.second:0)*3.14159265f/30;
  w.points[28]={(lv_value_precise_t)(w.hand_cx-w.hand_r*0.2f*sinf(a)),(lv_value_precise_t)(w.hand_cy+w.hand_r*0.2f*cosf(a))};
  w.points[29]={(lv_value_precise_t)(w.hand_cx+w.hand_r*0.92f*sinf(a)),(lv_value_precise_t)(w.hand_cy-w.hand_r*0.92f*cosf(a))};
  auto *p=part_line(w,18,w.points+28,2,w.hand_width);
  set_hidden(p,!(awake() && now.is_valid()));
}
// ---- Clock faces beside the digital clock and the classic dial (firmware 0.3.6+) ----
// "dial": a calm face, a filled disc with four strokes and eight dots and no numerals, so it reads at any size.
// "flip": hours and minutes on two blocks, like a flip clock. Both take the card's shape: wide cards put the time
// or the blocks at the left with the time and date beside them, tall cards stack, a full page centres.
// Digits are placed by the box their glyphs fill, not by the font's line box: a line box carries room above and
// below the digits, and centring that left the digits of the old wide clock visibly low.
inline void digit_box(const lv_font_t *font,int &top,int &height){
  lv_font_glyph_dsc_t g;
  if(font && lv_font_get_glyph_dsc(font,&g,'0',0) && g.box_h>0){
    height=g.box_h;top=lv_font_get_line_height(font)-font->base_line-g.box_h-g.ofs_y;return;
  }
  const int line=font?lv_font_get_line_height(font):10;height=line*7/10;top=(line-height)/2;
}
// AM or PM in the screen's language ("p. m." in Spanish) when it shows 12 hours, else nothing.
inline std::string am_pm(const esphome::ESPTime &now){
  if(screen_settings::current.clock_24h || !now.is_valid())return "";
  return tr(now.hour<12?txt::time_am:txt::time_pm);
}
inline lv_obj_t *part_rect(Widgets &w,unsigned i,int x,int y,int width,int height,int radius){
  auto *&p=w.parts[i];
  if(!p){p=lv_obj_create(w.extra);lv_obj_remove_style_all(p);lv_obj_set_style_bg_opa(p,LV_OPA_COVER,0);lv_obj_remove_flag(p,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(p,LV_OBJ_FLAG_SCROLLABLE);}
  lv_obj_set_style_radius(p,radius,0);lv_obj_set_pos(p,x,y);lv_obj_set_size(p,std::max(1,width),std::max(1,height));return p;
}
// A label whose digits start at `digits_top`: its box is moved up by the room the font keeps above them.
inline lv_obj_t *digit_label(Widgets &w,unsigned i,const lv_font_t *font,int x,int digits_top,int width,lv_text_align_t align,const std::string &text){
  int top,h;digit_box(font,top,h);
  return part_label(w,i,font,x,digits_top-top,width,align,text);
}
// The time column beside or under a dial: the time (with AM/PM after it) over the date. The largest font that fits
// the room, with the date if it fits too; the long date first, then the short one.
struct ClockText{const lv_font_t *font=nullptr;std::string date;int width=0,height=0,digits=0,gap=0;};
inline ClockText face_text(Widgets &w,const esphome::ESPTime &now,bool large,int room_w,int room_h,bool want_date=true){
  const lv_font_t *fonts[]={clock_font,watch_value_font,watch_font,w.value_font};
  const lv_font_t *small=w.value_font;
  const std::string time=time_text(now),ampm=am_pm(now);
  int small_top,small_h;digit_box(small,small_top,small_h);
  const std::string dates[]={date_text(now),fill(fill(txt::date_day_month,"day",now.is_valid()?std::to_string(now.day_of_month):"--"),"month",month_short(now))};
  const int line_gap=ui::px(large?9:5);
  // A date under a small time looks lost: it only comes with a time at least twice its own height.
  for(int with=want_date?1:0;with>=0;--with)for(auto *f:fonts){
    if(!f)continue;
    int top,dh;digit_box(f,top,dh);
    if(with && dh<2*small_h)continue;
    const int tw=text_width(time,f)+(ampm.empty()?0:ui::px(4)+text_width(ampm,small));
    const int h=dh+(with?line_gap+small_h:0);
    // The date's letters below the line (y, p) must fit too.
    if(h+(with?small->base_line:0)>room_h || tw>room_w)continue;
    if(!with)return ClockText{f,"",tw,h,dh,line_gap};
    for(const auto &date:dates){const int dw=text_width(date,small);if(dw<=room_w)return ClockText{f,date,std::max(tw,dw),h,dh,line_gap};}
  }
  return ClockText{};
}
// Place a ClockText with its left edge (align left) or its middle (centred) at x, its top at y.
inline void place_face_text(Widgets &w,const ClockText &c,const esphome::ESPTime &now,int x,int y,int room_w,bool centred){
  const lv_font_t *small=w.value_font;
  const std::string time=time_text(now),ampm=am_pm(now);
  const int tw=text_width(time,c.font),aw=ampm.empty()?0:ui::px(4)+text_width(ampm,small);
  const int tx=centred?x+(room_w-(tw+aw))/2:x;
  digit_label(w,15,c.font,tx,y,tw+2,LV_TEXT_ALIGN_LEFT,time);
  set_hidden(w.parts[15],false);
  int stop,sh;digit_box(small,stop,sh);
  // AM/PM sits on the time's baseline.
  digit_label(w,17,small,tx+tw+ui::px(4),y+c.digits-sh,std::max(1,aw),LV_TEXT_ALIGN_LEFT,ampm);
  set_hidden(w.parts[17],ampm.empty());
  const int dw=c.date.empty()?1:text_width(c.date,small)+2;
  digit_label(w,16,small,centred?x+(room_w-dw)/2:x,y+c.digits+c.gap,dw,LV_TEXT_ALIGN_LEFT,c.date);
  set_hidden(w.parts[16],c.date.empty());
}
inline void hide_face_text(Widgets &w){for(unsigned q=15;q<18;++q)if(w.parts[q])set_hidden(w.parts[q],true);}
inline void render_calm_dial(Widgets &w,const Tile &t,bool large,int width,int height){
  begin_extra(w,"calm",width,height);
  auto now=now_time?now_time():esphome::ESPTime{};
  const int gap=ui::px(large?16:8);
  // The disc goes first, so everything else is drawn over it.
  part_dot(w,19,0,0,1);
  // Where the dial goes, always inside the card's padding like the content of every other card (firmware 0.44.0;
  // before, a one-row card's dial reached into the padding and stood against the card's edge): beside the time on a
  // card wider than tall, above the time on a tall card or a page, alone when neither leaves room. A card of more rows
  // takes whichever of the two draws the time larger, and of two equal times the larger dial: a near-square card
  // (2x3 on the 10.1-inch) put a dial as tall as the card beside a time in the smallest step. On a card of more rows or
  // a page the padding is small beside the dial, so the dial keeps an eighth of its size as air as well; a one-row
  // card's padding is air enough.
  const int side=std::min(width,height);
  const bool big=w.full || t.row_span()>1;
  auto airy=[&](int d){return big?d*7/8:d;};
  struct Plan{ClockText text;int dial=0,cx=0,cy=0,tx=0,ty=0,room=0;bool centred=false;};
  auto beside=[&]{
    Plan p;const int d=airy(height);p.text=face_text(w,now,large,width-d-gap,height);
    if(!p.text.font)return p;
    p.dial=d;p.cx=d/2;p.cy=height/2;p.tx=d+gap;p.ty=(height-p.text.height)/2;p.room=width-p.tx;
    // What is left beside the time is shared: the dial and the text move in together as one group.
    const int spare=std::min(std::max(0,p.room-p.text.width)/2,gap);p.cx+=spare;p.tx+=2*spare;p.room-=2*spare;
    return p;
  };
  auto above=[&]{
    Plan p;p.text=face_text(w,now,large,width,height-side*60/100-gap);
    if(!p.text.font)return p;
    // Under the dial the date's letters below the line count too, or they touch the card's edge.
    const int below=p.text.date.empty()?0:w.value_font->base_line;
    p.dial=airy(std::min(width,height-p.text.height-below-gap));
    const int top=(height-p.dial-gap-p.text.height-below)/2;
    p.cx=width/2;p.cy=top+p.dial/2;p.ty=top+p.dial+gap;p.room=width;p.centred=true;
    return p;
  };
  Plan plan;
  if(w.full || height>width*9/10)plan=above();
  else if(t.row_span()<=1){plan=beside();if(!plan.text.font)plan=above();}
  else{
    const Plan a=beside(),b=above();
    const bool first=a.text.font && (!b.text.font || a.text.digits>b.text.digits || (a.text.digits==b.text.digits && a.dial>=b.dial));
    plan=first?a:b;
  }
  int dial=plan.dial,cx=plan.cx,cy=plan.cy;
  if(!plan.text.font){dial=airy(side);cx=width/2;cy=height/2;hide_face_text(w);}
  else place_face_text(w,plan.text,now,plan.tx,plan.ty,plan.room,plan.centred);
  const float R=dial/2.0f-1;
  lv_obj_set_pos(w.parts[19],cx-int(R),cy-int(R));lv_obj_set_size(w.parts[19],int(R)*2,int(R)*2);
  // Four strokes at 12, 3, 6 and 9 and a dot at every other hour, all inside the disc.
  const float inset=std::max(2.0f,R*0.09f),stroke=std::max(3.0f,R*0.22f);
  const int stroke_w=std::max(2,int(R*0.08f+0.5f)),dot=std::max(2,int(R*0.075f+0.5f));
  for(int i=0;i<12;++i){
    const float a=i*3.14159265f/6;
    if(i%3==0){
      if(w.parts[i] && !lv_obj_check_type(w.parts[i],&lv_line_class)){lv_obj_delete(w.parts[i]);w.parts[i]=nullptr;}
      auto *p=w.points+4+2*i;
      p[0]={(lv_value_precise_t)(cx+(R-inset)*sinf(a)),(lv_value_precise_t)(cy-(R-inset)*cosf(a))};
      p[1]={(lv_value_precise_t)(cx+(R-inset-stroke)*sinf(a)),(lv_value_precise_t)(cy-(R-inset-stroke)*cosf(a))};
      part_line(w,i,p,2,stroke_w);
    }else{
      const float r=R-inset-stroke*0.3f;
      part_dot(w,i,int(cx+r*sinf(a)+0.5f)-dot/2,int(cy-r*cosf(a)+0.5f)-dot/2,dot);
    }
  }
  float hour=((now.is_valid()?now.hour%12:0)+(now.is_valid()?now.minute:0)/60.0f)*3.14159265f/6, minute=(now.is_valid()?now.minute:0)*3.14159265f/30;
  w.points[0]={(lv_value_precise_t)cx,(lv_value_precise_t)cy};w.points[1]={(lv_value_precise_t)(cx+R*0.5f*sinf(hour)),(lv_value_precise_t)(cy-R*0.5f*cosf(hour))};
  w.points[2]={(lv_value_precise_t)cx,(lv_value_precise_t)cy};w.points[3]={(lv_value_precise_t)(cx+R*0.78f*sinf(minute)),(lv_value_precise_t)(cy-R*0.78f*cosf(minute))};
  part_line(w,12,w.points,2,std::max(3,int(R*0.16f+0.5f)));part_line(w,13,w.points+2,2,std::max(2,int(R*0.11f+0.5f)));
  const int center=std::max(5,int(R*0.26f+0.5f));part_dot(w,14,cx-center/2,cy-center/2,center);
  w.hand_cx=cx;w.hand_cy=cy;w.hand_r=int(R*0.9f);w.hand_width=std::max(1,int(R*0.045f+0.5f));
  const bool new_hand=!w.parts[18];
  second_hand(w,now);
  if(new_hand)lv_obj_move_to_index(w.parts[18],lv_obj_get_index(w.parts[14]));
}
// The digit steps, largest first (packages/looks/shared/digits.yaml): the display step, the setpoint's and the clock
// card's. A card takes the largest one that fits (largest_digits) and never brings a size of its own
// (tests/test_font_set.py).
inline std::array<const lv_font_t *,3> digit_steps(){return {display_font,setpoint_font,clock_font};}
// The largest digit step whose digits are at most `height` tall and whose `text` is at most `width` wide; null if none.
inline const lv_font_t *largest_digits(const char *text,int width,int height){
  for(const lv_font_t *f:digit_steps()){
    if(!f)continue;int top,h;digit_box(f,top,h);
    if(h<=height && text_width(text,f)<=width)return f;
  }
  return nullptr;
}
// The bedside clock's digits: its own step where the board has one (a page a fifth larger than the display step), else
// the display step; the 8 px place holder a board without its own step keeps is never drawn.
inline const lv_font_t *bedside_digits(){
  if(bedside_font && (!display_font || lv_font_get_line_height(bedside_font)>lv_font_get_line_height(display_font)))return bedside_font;
  return display_font?display_font:setpoint_font?setpoint_font:clock_font;
}
// A card that only switches (a lamp, a switch, a fan) or only runs (a script, a scene, a button), with no other control
// chosen: two rows tall, one column or two, it is one big key (firmware 0.17.0+), as the same card over a whole page is.
inline bool big_key(const Tile &t){
  const auto d=t.domain();
  return (d=="light"||d=="switch"||d=="input_boolean"||d=="fan"||d=="script"||d=="scene"||d=="button"||d=="input_button") && t.inline_control!="slider" &&
         (t.controls.empty()||t.controls=="toggle"||t.controls=="run"||t.controls=="none"||t.controls=="auto");
}
inline void render_flip(Widgets &w,const Tile &t,bool large,int width,int height){
  begin_extra(w,"flip",width,height);
  auto now=now_time?now_time():esphome::ESPTime{};
  char hh[4]="--",mm[4]="--";
  if(now.is_valid()){
    if(screen_settings::current.clock_24h)snprintf(hh,sizeof(hh),"%02d",now.hour);else snprintf(hh,sizeof(hh),"%d",now.hour%12?now.hour%12:12);
    snprintf(mm,sizeof(mm),"%02d",now.minute);
  }
  const std::string ampm=am_pm(now);
  const lv_font_t *small=w.value_font,*bold=w.title_font?w.title_font:w.value_font;
  const lv_font_t *fonts[]={setpoint_font,clock_font,watch_value_font,watch_font,w.value_font};
  int stop,sh;digit_box(small,stop,sh);
  const int aw=ampm.empty()?0:text_width(ampm,small);
  // A card as wide as two columns and two rows or more, or a whole page (firmware 0.17.0+): the two blocks share its
  // width, and one line under them carries the day at the left and AM or PM at the right. The digits are the board's
  // display step (looks/shared/digits.yaml), else the largest digit step that fits a block.
  if(w.full || (w.wide && t.row_span()>=2)){
    // The blocks keep room above them and under the day's line, so on a low card (a compact look) they never touch its
    // edge: at least 6 px, a twentieth of the card on a taller one.
    const int line_gap=ui::px(large?12:6),gb=std::max(ui::px(6),width/36),bw=(width-gb)/2,air=std::max(ui::px(6),height/20);
    const int bh=std::min(height-2*air-line_gap-sh,bw*92/100);
    const lv_font_t *font=largest_digits("88",bw*88/100,bh*72/100);int dh=0;
    if(font){int top;digit_box(font,top,dh);}
    for(unsigned q=0;q<7;++q)if(w.parts[q])set_hidden(w.parts[q],!font);
    if(!font){hide_face_text(w);return;}
    const int radius=std::max(ui::px(4),bh/12),seam=std::max(1,bh/60);
    const int by=(height-(bh+line_gap+sh))/2;
    for(int b=0;b<2;++b){
      const int x=b*(bw+gb);
      part_rect(w,b,x,by,bw,bh,radius);
      digit_label(w,2+b,font,x,by+(bh-dh)/2,bw,LV_TEXT_ALIGN_CENTER,b?mm:hh);
      part_rect(w,4+b,x,by+bh/2-seam/2,bw,seam,0);
    }
    const std::string day=weekday_text(now)+" "+fill(fill(txt::date_day_month,"day",now.is_valid()?std::to_string(now.day_of_month):"--"),"month",month_short(now));
    digit_label(w,16,small,0,by+bh+line_gap,std::max(1,width-aw-ui::px(8)),LV_TEXT_ALIGN_LEFT,day);set_hidden(w.parts[16],false);
    digit_label(w,6,small,width-aw-2,by+bh+line_gap,aw+2,LV_TEXT_ALIGN_RIGHT,ampm);set_hidden(w.parts[6],ampm.empty());
    if(w.parts[15])set_hidden(w.parts[15],true);if(w.parts[17])set_hidden(w.parts[17],true);
    return;
  }
  // The blocks: the largest digits whose blocks fit. A block is as tall as the room allows (a one-row card: the
  // card, into its padding; a page: a bit over half of it) and a little wider than tall. A card that is not a page
  // takes the two blocks side by side or one over the other, whichever gives the bigger blocks.
  struct Blocks{const lv_font_t *font=nullptr;int bh=0,bw=0,gb=0;};
  const int reach=face_reach(w,t);
  auto fit=[&](bool stack)->Blocks{
    const int want_h=stack?height:w.full?height*55/100:height+2*reach,grow=stack?0:reach;
    for(auto *f:fonts){
      if(!f)continue;
      int top,dh;digit_box(f,top,dh);
      int h=std::min(want_h,dh*100/62);
      const int g=std::max(ui::px(3),h/12);
      if(stack)h=std::min(h,(height-g)/2);
      if(dh>h*72/100)continue;
      const int bwid=std::max(text_width("88",f)+dh*6/10,h*108/100);
      const int need=(stack?bwid:2*bwid+g)+(aw?ui::px(6)+aw:0)-2*grow;
      if(need>width)continue;
      return Blocks{f,h,bwid,g};
    }
    return Blocks{};
  };
  Blocks row=fit(false),column=w.full?Blocks{}:fit(true);
  const bool stacked=column.font && column.bh>row.bh*11/10;
  const Blocks &chosen=stacked?column:row;
  const lv_font_t *font=chosen.font;const int bh=chosen.bh,bw=chosen.bw,gb=chosen.gb;
  const int reach_used=stacked?0:reach;
  for(unsigned q=0;q<7;++q)if(w.parts[q])set_hidden(w.parts[q],!font);
  if(!font){hide_face_text(w);return;}
  int dtop,dh;digit_box(font,dtop,dh);
  const int radius=std::max(ui::px(4),bh/9),seam=std::max(1,bh/45);
  // The date: weekday over the day and month beside wide blocks, one line under blocks on a page or stacked.
  const std::string weekday=weekday_text(now),date=fill(fill(txt::date_day_month,"day",now.is_valid()?std::to_string(now.day_of_month):"--"),"month",month_short(now));
  int bx=0,by=0,group_w=(stacked?bw:2*bw+gb)+(aw?ui::px(6)+aw:0),group_h=stacked?2*bh+gb:bh;
  const int gap=ui::px(large?16:8);
  bool side=false,under=false;
  int bold_top,bold_h;digit_box(bold,bold_top,bold_h);
  const int col_w=std::max(text_width(weekday,bold),text_width(date,small)),col_h=bold_h+ui::px(large?9:5)+sh;
  if(!stacked && !w.full && group_w-reach_used+gap+col_w<=width && col_h<=height)side=true;
  else if((stacked||w.full) && group_h+gap+sh<=height && text_width(stacked?date:weekday+" "+date,small)<=width)under=true;
  if(side){
    const int spare=std::max(0,width+reach_used-(group_w+gap+col_w))/2;
    bx=std::min(spare,gap)-reach_used;by=(height-bh)/2;
    const int cx=bx+group_w+gap+std::min(spare,gap),cy=(height-col_h)/2;
    digit_label(w,15,bold,cx,cy,col_w+2,LV_TEXT_ALIGN_LEFT,weekday);
    digit_label(w,16,small,cx,cy+bold_h+ui::px(large?9:5),col_w+2,LV_TEXT_ALIGN_LEFT,date);
    set_hidden(w.parts[15],false);set_hidden(w.parts[16],false);
  }else{
    const int total=group_h+(under?gap+sh:0);
    bx=(width-group_w)/2;by=(height-total)/2;
    if(under){
      const std::string line=stacked?date:weekday+" "+date;
      digit_label(w,16,small,0,by+group_h+gap,width,LV_TEXT_ALIGN_CENTER,line);
      set_hidden(w.parts[16],false);
    }else if(w.parts[16])set_hidden(w.parts[16],true);
    if(w.parts[15])set_hidden(w.parts[15],true);
  }
  // Blocks 0 (hours) and 1 (minutes), their digits 2 and 3, the seams 4 and 5, AM/PM 6.
  for(int b=0;b<2;++b){
    const int x=stacked?bx:bx+b*(bw+gb),y=stacked?by+b*(bh+gb):by;
    part_rect(w,b,x,y,bw,bh,radius);
    digit_label(w,2+b,font,x,y+(bh-dh)/2,bw,LV_TEXT_ALIGN_CENTER,b?mm:hh);
    part_rect(w,4+b,x,y+bh/2-seam/2,bw,seam,0);
  }
  // AM/PM beside the minutes on the digits' baseline; beside the hours when the blocks are stacked.
  if(stacked)digit_label(w,6,small,bx+bw+ui::px(6),by+(bh-dh)/2+dh-sh,std::max(1,aw),LV_TEXT_ALIGN_LEFT,ampm);
  else digit_label(w,6,small,bx+2*bw+gb+ui::px(6),by+(bh-dh)/2+dh-sh,std::max(1,aw),LV_TEXT_ALIGN_LEFT,ampm);
  set_hidden(w.parts[6],ampm.empty());
  if(w.parts[17])set_hidden(w.parts[17],true);
}
// The colours of the two faces above, from the card's palette (called where the other cards get theirs).
inline void paint_face(Widgets &w,lv_color_t ink,lv_color_t muted,lv_color_t accent){
  const bool flip=w.extra_mode=="flip";
  const lv_color_t block=theme::color(theme::TRACK);
  const lv_color_t card=lv_obj_get_style_bg_opa(w.tile,LV_PART_MAIN)==LV_OPA_TRANSP?lv_color_hex(card_ground(w)):lv_obj_get_style_bg_color(w.tile,LV_PART_MAIN);
  for(unsigned i=0;i<w.parts.size();++i){
    auto *p=w.parts[i];if(!p)continue;
    if(lv_obj_check_type(p,&lv_label_class)){set_color(p,LV_STYLE_TEXT_COLOR,(flip?(i==6||i==16):(i==16||i==17))?muted:ink);continue;}
    if(flip){set_color(p,LV_STYLE_BG_COLOR,i==4||i==5?card:block);continue;}
    // The calm dial is the card turned round: a disc in the ink's colour, its strokes and hour hand in the card's
    // (dark on a light card, light on a dark one), so it stands out instead of fading into the card.
    if(lv_obj_check_type(p,&lv_line_class))set_color(p,LV_STYLE_LINE_COLOR,i==18?lv_color_hex(theme::foreground(theme::ha::ALARM)):i==13?accent:card);
    else set_color(p,LV_STYLE_BG_COLOR,i==19?ink:i==14?accent:muted);
  }
}
// ---- The bedside clock (firmware 0.8.0+) ----
// A clock over the whole page: the time as large as the page allows, and up to three round keys, each a tile of its
// own (runtime_model.h, Tile::parent). The keys stand in a row under the time; on a card too low for that, in a
// column beside it; on a card too narrow, under the hours stacked over the minutes. The room above the time, between
// the time and the keys and below the keys is the same, and the middle stops growing at 14 mm, so on a large glass
// the group stays together in the middle. The board's digits (FONT_BEDSIDE_SIZE) are the largest one of these fits
// in both orientations, so the same font serves the glass lying down and standing up.
// The keys a bedside clock's page has cards for: the cells its clock covers but its own (place_page).
static_assert(CELLS_MAX > BEDSIDE_KEYS, "a bedside clock's keys take the cards of the cells its page leaves free");
inline unsigned bedside_key_room(){return std::min<unsigned>(BEDSIDE_KEYS,std::min<unsigned>(widgets.size(),grid.slots())-1);}
struct BedsideLayout {
  enum Mode : uint8_t { ROW, COLUMN, STACK } mode = ROW;
  int digits_y = 0, digits_x = 0, digits_w = 0, digit_h = 0, line_gap = 0;  // content coordinates of the card
  int key = 0; unsigned keys = 0; bool names = false, fits = true; int name_h = 0, name_gap = 0;
  std::array<int, BEDSIDE_KEYS> key_x{}, key_y{};  // each key's top-left corner, content coordinates
  std::array<int, BEDSIDE_KEYS> name_x{}, name_y{}, name_w{};
};
// `pad`: the card's own padding, so the room above the time counts from the card's edge as it looks.
inline BedsideLayout bedside_layout(int w,int h,int pad,const std::vector<std::string> &names_in){
  BedsideLayout l;
  const lv_font_t *font=bedside_digits();
  const lv_font_t *small=small_font?small_font:font;
  int top;digit_box(font,top,l.digit_h);
  l.line_gap=l.digit_h/6;
  l.keys=std::min<unsigned>(names_in.size(),BEDSIDE_KEYS);
  // Names under the keys in the standard look; the compact look (a CYD) keeps the keys alone, its smallest letters
  // would be under the size the owner reads in the dark.
  l.names=l.keys && ui::large() && std::any_of(names_in.begin(),names_in.begin()+l.keys,[](const std::string &n){return !n.empty();});
  l.name_h=l.names?lv_font_get_line_height(small):0;l.name_gap=l.names?ui::px(8):0;
  int name_w=0;if(l.names)for(unsigned i=0;i<l.keys;++i)name_w=std::max(name_w,text_width(names_in[i],small));
  // A long name ends in dots rather than push the keys apart: a third of the card, about five letters and a half of
  // the name's size (the looks size FONT_BEDSIDE_SIZE with the same limit).
  name_w=std::min({name_w,w/3,(int)lv_font_get_line_height(small)*47/10});
  const int card_h=h+2*pad,least=std::max(ui::px(8),card_h*7/100),touch=ui::touch_min();
  const int time_w=text_width("00:00",font),pair_w=text_width("00",font);
  auto key_size=[&](int room){return std::max(touch,std::min<int>(ui::mm(12),room*28/100));};
  // What each arrangement needs; the first that fits is taken.
  int d=key_size(h);
  int kg=std::max({ui::px(16),d/2,l.names?name_w-d+ui::px(12):0});
  if(l.keys && (int)l.keys*d+((int)l.keys-1)*kg>w)d=std::max(touch,(w-((int)l.keys-1)*kg)/(int)l.keys);
  const int band=l.keys?d+l.name_gap+l.name_h:0;
  const bool row=time_w<=w && l.digit_h+band+(l.keys?3:2)*least<=card_h;
  const int vg=ui::px(12),col_d=std::max(touch,std::min(d,(h-2*vg)/3));
  const int col_w=col_d+(l.names?ui::px(12)+name_w:0);
  const bool column=!row && l.keys && time_w<=w-col_w-ui::px(28) && (int)l.keys*col_d+((int)l.keys-1)*vg<=h;
  const bool stack=!row && !column && pair_w<=w && 2*l.digit_h+l.line_gap+band+(l.keys?3:2)*least<=card_h;
  l.mode=row?BedsideLayout::ROW:column?BedsideLayout::COLUMN:stack?BedsideLayout::STACK:BedsideLayout::ROW;
  // The board's digits (bedside_digits, looks/shared/digits.yaml) are sized for one of the three to fit; the self test fails a
  // board where none does, instead of the time running into its keys.
  l.fits=row||column||stack;
  if(l.mode==BedsideLayout::COLUMN){
    l.key=col_d;
    const int area=w-col_w-ui::px(28);
    l.digits_x=0;l.digits_w=area;l.digits_y=(h-l.digit_h)/2;
    const int y0=(h-((int)l.keys*col_d+((int)l.keys-1)*vg))/2,x=w-col_w;
    for(unsigned i=0;i<l.keys;++i){
      l.key_x[i]=x;l.key_y[i]=y0+i*(col_d+vg);
      l.name_x[i]=x+col_d+ui::px(12);l.name_y[i]=l.key_y[i]+(col_d-l.name_h)/2;l.name_w[i]=std::max(1,w-l.name_x[i]);
    }
    return l;
  }
  l.key=d;
  const int tall=l.mode==BedsideLayout::STACK?2*l.digit_h+l.line_gap:l.digit_h;
  // Equal room above, between and below, measured from the card's edge; the middle stops at 14 mm.
  const int free=card_h-tall-band;
  const int mid=l.keys?std::min(free/3,ui::mm(14)):0,edge=(free-mid)/2;
  l.digits_x=0;l.digits_w=w;l.digits_y=edge-pad;
  const int keys_y=l.digits_y+tall+mid,x0=(w-((int)l.keys*d+((int)l.keys-1)*kg))/2;
  for(unsigned i=0;i<l.keys;++i){
    l.key_x[i]=x0+i*(d+kg);l.key_y[i]=keys_y;
    // A name may be wider than its key, never wider than the card: the outer ones stay inside it.
    const int nw=std::min(w,d+kg-ui::px(4));
    l.name_x[i]=std::clamp(l.key_x[i]+d/2-nw/2,0,w-nw);l.name_y[i]=keys_y+d+l.name_gap;l.name_w[i]=nw;
  }
  return l;
}
// The names of a bedside clock's keys, in their order (the tiles that name `index` as their clock).
inline std::vector<std::string> bedside_names(size_t index){
  std::vector<std::string> names;
  for(unsigned k=0;k<bedside_key_room();++k)for(size_t i=0;i<model.count;++i){
    const auto &t=model.tiles[i];
    // A key whose name is hidden (overlay "none", firmware 0.17.0+) keeps its place with an empty name.
    if(t.is_key() && (size_t)t.parent==index && t.key==k){names.push_back(!t.overlay?std::string():t.name.empty()?t.entity:t.name);break;}
  }
  return names;
}
// Parts: 0 the time (the hours when stacked), 1 the minutes when stacked, 2 AM/PM, 3-5 the keys' names.
inline void render_bedside(Widgets &w,const Tile &t,int width,int height){
  begin_extra(w,"bedside",width,height);
  auto now=now_time?now_time():esphome::ESPTime{};
  const int pad=lv_obj_get_style_space_top(w.tile,LV_PART_MAIN);
  const auto names=bedside_names(w.index);
  const auto l=bedside_layout(width,height,pad,names);
  const lv_font_t *font=bedside_digits(),*small=small_font?small_font:w.value_font;
  const std::string time=time_text(now),ampm=am_pm(now);
  const auto ink=theme::color(theme::BEDSIDE),muted=theme::color(theme::MUTED);
  if(l.mode==BedsideLayout::STACK){
    const size_t colon=time.find(':');
    digit_label(w,0,font,l.digits_x,l.digits_y,l.digits_w,LV_TEXT_ALIGN_CENTER,time.substr(0,colon));
    digit_label(w,1,font,l.digits_x,l.digits_y+l.digit_h+l.line_gap,l.digits_w,LV_TEXT_ALIGN_CENTER,colon==std::string::npos?"":time.substr(colon+1));
    set_hidden(w.parts[1],false);
  }else{
    digit_label(w,0,font,l.digits_x,l.digits_y,l.digits_w,LV_TEXT_ALIGN_CENTER,time);
    if(w.parts[1])set_hidden(w.parts[1],true);
  }
  set_color(w.parts[0],LV_STYLE_TEXT_COLOR,ink);if(w.parts[1])set_color(w.parts[1],LV_STYLE_TEXT_COLOR,ink);
  // AM or PM under the end of the time when the screen shows 12 hours (firmware 0.17.0+): beside it, "10:08" already
  // fills the width the digits were sized for and the letters ran off the glass (GitHub #93).
  if(!ampm.empty()){
    const int tw=text_width(l.mode==BedsideLayout::STACK?time.substr(time.find(':')+1):time,font);
    const int last=l.mode==BedsideLayout::STACK?l.digits_y+2*l.digit_h+l.line_gap:l.digits_y+l.digit_h;
    const int aw=text_width(ampm,small)+2,end=l.digits_x+(l.digits_w+tw)/2;
    auto *p=digit_label(w,2,small,end-aw,last+ui::px(10),aw,LV_TEXT_ALIGN_LEFT,ampm);
    set_color(p,LV_STYLE_TEXT_COLOR,muted);set_hidden(p,false);
  }else if(w.parts[2])set_hidden(w.parts[2],true);
  for(unsigned i=0;i<BEDSIDE_KEYS;++i){
    if(i<l.keys && l.names && !names[i].empty()){
      auto *p=part_label(w,3+i,small,l.name_x[i],l.name_y[i],l.name_w[i],l.mode==BedsideLayout::COLUMN?LV_TEXT_ALIGN_LEFT:LV_TEXT_ALIGN_CENTER,names[i]);
      lv_label_set_long_mode(p,LV_LABEL_LONG_DOT);set_color(p,LV_STYLE_TEXT_COLOR,muted);set_hidden(p,false);
    }else if(w.parts[3+i])set_hidden(w.parts[3+i],true);
  }
}
inline void render_clock(Widgets &w,const Tile &t,bool large,int width,int height) {
  if(t.display=="dial"||t.display=="flip"){
    // A part made on this render has no colour yet: the palette pass paints it (it runs after this, on a change).
    auto made=[&w]{return std::count_if(w.parts.begin(),w.parts.end(),[](lv_obj_t *p){return p!=nullptr;});};
    const auto before=w.extra_mode==(t.display=="dial"?"calm":"flip")?made():-1;
    if(t.display=="dial")render_calm_dial(w,t,large,width,height);else render_flip(w,t,large,width,height);
    if(made()!=before)w.cached_active=-1;
    return;
  }
  bool analog=t.display=="analog";
  begin_extra(w,analog?(w.wide?"analog":"calendar"):"digital",width,height);
  auto now=now_time?now_time():esphome::ESPTime{};
  const lv_font_t *big=clock_font?clock_font:watch_value_font?watch_value_font:w.value_font;
  // The card's own name font, not the name label's: a card that showed a centred name before (a tall on/off card)
  // left its label in that card's font, and a card reused for another page kept it (firmware 0.3.2).
  const lv_font_t *small=w.title_font;
  // The time beside a wide dial: on a card lower than the clock's own line (a fine grid, firmware 0.53.0+) the largest
  // step whose line fits.
  const lv_font_t *time_font=big;
  if(lv_font_get_line_height(big)>height)
    for(auto *f:{watch_value_font,watch_font,w.value_font})if(f && lv_font_get_line_height(f)<=height){time_font=f;break;}
  // The date line only appears when both lines fit the card height.
  bool with_date=lv_font_get_line_height(time_font)+2+lv_font_get_line_height(small)<=height;
  int text_h=lv_font_get_line_height(time_font)+(with_date?2+lv_font_get_line_height(small):0);
  if(!analog){
    // The largest time that fits, with the date under it when that fits too, centred on the digits themselves
    // (firmware 0.3.6+: a 61 px time in a 63 px card no longer hangs 8 px out of it).
    // A one-row card lends the time and date part of its padding, as it does a dial.
    const int reach=face_reach(w,t);
    const auto text=face_text(w,now,large,width,height+reach);
    if(!text.font){hide_face_text(w);return;}
    place_face_text(w,text,now,0,(height-text.height)/2,width,true);
    return;
  }
  // The dial keeps the same size with or without a card behind it.
  // A full-page card centres its dial; the digital time and date beside a wide dial stay off it.
  int dial=std::min(height,width);
  // A single card keeps the dial of the profile's card when it grows without the page bar (firmware 0.2.69+), so the
  // calendar block beside it keeps its room; the dial stays in the card's middle.
  if(!w.full && !w.wide)dial=std::min(dial,w.base_height-(tile_height(w)-height));
  // A single card whose width has no room for the date beside the dial centres the dial instead.
  bool date_fits=true;
  if(!w.full && w.wide){
    // Multi-row cards can be taller than they are wide. Keep the dial centred
    // when its usual time/date column has no room beside it.
    const int room=width-dial-ui::px(large?16:8);
    const int need=std::max(text_width(time_text(now),time_font),with_date?text_width(date_text(now),small):0);
    date_fits=room>=need;
  }
  if(!w.full && !w.wide){
    int room=width-dial-(ui::px(large?10:6)),need=0;lv_point_t sz;
    if(large){
      lv_text_get_size(&sz,weekday_text(now).c_str(),w.value_font,0,0,LV_COORD_MAX,LV_TEXT_FLAG_EXPAND);need=sz.x;
      std::string day_probe=now.is_valid()?std::to_string(now.day_of_month):"--";
      lv_point_t d,m;lv_text_get_size(&d,day_probe.c_str(),big,0,0,LV_COORD_MAX,LV_TEXT_FLAG_EXPAND);lv_text_get_size(&m,month_short(now).c_str(),small,0,0,LV_COORD_MAX,LV_TEXT_FLAG_EXPAND);
      need=std::max<int>(need,d.x+6+m.x);
    }else{
      const lv_font_t *font=watch_value_font?watch_value_font:w.value_font;
      std::string day_probe=now.is_valid()?std::to_string(now.day_of_month):"--";
      lv_text_get_size(&sz,fill(fill(txt::date_day_month,"day",day_probe),"month",month_short(now)).c_str(),font,0,0,LV_COORD_MAX,LV_TEXT_FLAG_EXPAND);need=sz.x;
    }
    date_fits=room>=need;
  }
  int cx=((w.full||!date_fits)?(width-dial)/2:0)+dial/2,cy=height/2,outer=dial/2-1,radius=dial/2-(ui::px(large?4:2));
  // Numerals replace the four cardinal strokes on a dial with room for them (firmware 0.35.0): the 12 and the 3 stand a
  // ring's radius apart either way, so a ring shorter than a numeral's box (a 4-inch with four rows) puts them on top
  // of each other, and the dial keeps its strokes instead.
  const int numeral_box=lv_font_get_line_height(w.value_font)+4,numeral_ring=outer-11;
  const bool numerals=large && numeral_ring>=numeral_box+ui::px(2);
  for(int i=0;i<12;++i){
    float a=i*3.14159265f/6;bool cardinal=i%3==0;
    // A part kept from a dial of the other size is the other kind (a numeral is a label, a stroke a line).
    // Its successor is made below without a colour; the palette pass paints it (cached_active, as the dial does).
    if(cardinal && w.parts[i] && lv_obj_check_type(w.parts[i],&lv_label_class)!=numerals){lv_obj_delete(w.parts[i]);w.parts[i]=nullptr;w.cached_active=-1;}
    if(cardinal && numerals){
      part_label(w,i,w.value_font,cx+std::lround(numeral_ring*sinf(a))-numeral_box/2,cy-std::lround(numeral_ring*cosf(a))-numeral_box/2,
                 numeral_box,LV_TEXT_ALIGN_CENTER,i==0?"12":std::to_string(i));
      continue;
    }
    int length=cardinal?(ui::px(large?9:5)):(ui::px(large?5:3));
    auto *p=w.points+4+2*i;
    p[0]={(lv_value_precise_t)(cx+outer*sinf(a)),(lv_value_precise_t)(cy-outer*cosf(a))};
    p[1]={(lv_value_precise_t)(cx+(outer-length)*sinf(a)),(lv_value_precise_t)(cy-(outer-length)*cosf(a))};
    part_line(w,i,p,2,cardinal?(ui::px(large?3:2)):(ui::px(large?2:1)));
  }
  float hour=((now.is_valid()?now.hour%12:0)+(now.is_valid()?now.minute:0)/60.0f)*3.14159265f/6, minute=(now.is_valid()?now.minute:0)*3.14159265f/30;
  w.points[0]={(lv_value_precise_t)cx,(lv_value_precise_t)cy};w.points[1]={(lv_value_precise_t)(cx+radius*0.52f*sinf(hour)),(lv_value_precise_t)(cy-radius*0.52f*cosf(hour))};
  w.points[2]={(lv_value_precise_t)cx,(lv_value_precise_t)cy};w.points[3]={(lv_value_precise_t)(cx+radius*0.82f*sinf(minute)),(lv_value_precise_t)(cy-radius*0.82f*cosf(minute))};
  part_line(w,12,w.points,2,ui::px(large?5:3));part_line(w,13,w.points+2,2,ui::px(large?3:2));
  int center=ui::px(large?8:4);part_dot(w,14,cx-center/2,cy-center/2,center);
  // A thin red second hand with a short tail, under the centre dot; tick() moves it every second.
  w.hand_cx=cx;w.hand_cy=cy;w.hand_r=radius;w.hand_width=ui::px(large?2:1);
  bool new_hand=!w.parts[18];
  second_hand(w,now);
  if(new_hand)lv_obj_move_to_index(w.parts[18],lv_obj_get_index(w.parts[14]));
  std::string day=now.is_valid()?std::to_string(now.day_of_month):"--";
  if(w.full){
    part_label(w,15,big,0,0,1,LV_TEXT_ALIGN_CENTER,"");
    part_label(w,16,small,0,0,1,LV_TEXT_ALIGN_CENTER,"");
    return;
  }
  // What does not fit is left out of the card: the date labels hide, nothing else moves.
  for(unsigned q=15;q<18;++q)if(w.parts[q])set_hidden(w.parts[q],!date_fits);
  if(!date_fits)return;
  if(w.wide){
    int x=dial+(ui::px(large?16:8)),y=std::max(0,(height-text_h)/2);
    part_label(w,15,time_font,x,y,width-x,LV_TEXT_ALIGN_CENTER,time_text(now));
    part_label(w,16,small,x,with_date?y+lv_font_get_line_height(time_font)+2:y,width-x,LV_TEXT_ALIGN_CENTER,with_date?date_text(now):"");
    return;
  }
  int x=dial+(ui::px(large?10:6)),room=std::max(1,width-x);
  if(!large){
    // Compact cards: "13 sep" in the large-value font beside the dial, in the language's order (screen.date.day_month).
    const lv_font_t *font=watch_value_font?watch_value_font:w.value_font;
    part_label(w,16,font,x,std::max(0,int(height-lv_font_get_line_height(font))/2),room,LV_TEXT_ALIGN_CENTER,
               fill(fill(txt::date_day_month,"day",day),"month",month_short(now)));
    return;
  }
  // Calendar block: weekday over a big day number with the short month beside it. It has to fit the card's
  // height: on a board with more rows than its size table was drawn for, the weekday and a big number are
  // together taller than the cell and the number was cut off at the bottom. The weekday goes first, then the
  // number takes the smaller font; the day and the month never go, they are what a calendar is for.
  const lv_font_t *day_font=big;
  int week_h=lv_font_get_line_height(w.value_font);
  bool with_weekday=week_h+lv_font_get_line_height(day_font)<=height;
  if(!with_weekday && lv_font_get_line_height(day_font)>height)day_font=w.value_font;
  if(!with_weekday)week_h=0;
  if(w.parts[15])set_hidden(w.parts[15],!with_weekday);
  int top=std::max(0,int(height-week_h-lv_font_get_line_height(day_font))/2);
  if(with_weekday)part_label(w,15,w.value_font,x,top,room,LV_TEXT_ALIGN_CENTER,weekday_text(now));
  std::string month=month_short(now);
  lv_point_t day_size,month_size;
  lv_text_get_size(&day_size,day.c_str(),day_font,0,0,LV_COORD_MAX,LV_TEXT_FLAG_EXPAND);
  lv_text_get_size(&month_size,month.c_str(),small,0,0,LV_COORD_MAX,LV_TEXT_FLAG_EXPAND);
  int gap=6,sx=x+std::max(0,int(room-(day_size.x+gap+month_size.x))/2),day_y=top+week_h;
  part_label(w,16,day_font,sx,day_y,std::min(room,(int)day_size.x+2),LV_TEXT_ALIGN_LEFT,day);
  // Both baselines line up: LVGL measures base_line from the bottom of the line box.
  int month_y=day_y+(day_font->line_height-day_font->base_line)-(small->line_height-small->base_line);
  part_label(w,17,small,sx+day_size.x+gap,std::max(0,month_y),std::max(1,int(x+room-(sx+day_size.x+gap))),LV_TEXT_ALIGN_LEFT,month);
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
