// A light's presets (module light_presets, docs/LIGHT_PRESETS.md): their round keys on a tile's panel, in the colour card
// and in the card of a light that only dims, and their taps. The module's header holds their rules and the key itself.
//
// Compiled on its own, as module_vacuum_tile.cpp is: on Xtensa the literal pool of one object file must stay within reach
// of all of its code, and main.cpp is at that edge.
#include "esphome/core/defines.h"
#ifdef SD_MOD_LIGHT_PRESETS
#include "esphome/core/log.h"
#include "runtime_tiles.h"

namespace runtime_tiles {

// The ring round the key of the preset the light shows, or, while a tapped preset is on its way (preset_pending), a
// spinner turning where its ring will be: the ring's size, width and ink, so the one becomes the other. The spinner is
// the key's sibling, kept in the key's user data: LVGL draws a child only inside its parent's box, which cut the arc to
// the key's square; the key's parent keeps the ring's room round it.
static void preset_spinner_drop(lv_obj_t *k) {
  if (!k) return;
  if (auto *spin = (lv_obj_t *) lv_obj_get_user_data(k)) lv_obj_delete(spin);
  lv_obj_set_user_data(k, nullptr);
}
static void preset_mark(lv_obj_t *k, bool lit, bool busy) {
  if (!k) return;
  auto *spin = (lv_obj_t *) lv_obj_get_user_data(k);
  if (!busy) preset_spinner_drop(k), spin = nullptr;
  const int width = std::max(2, ui::px(2)), size = lv_obj_get_style_width(k, LV_PART_MAIN);
  const int outer = size + 2 * (light_presets::ring_pad() + width);
  if (busy && !spin && (spin = spinner_create(lv_obj_get_parent(k), outer, width))) {
    lv_obj_set_style_arc_opa(spin, LV_OPA_TRANSP, LV_PART_MAIN);
    lv_obj_set_style_arc_color(spin, theme::color(theme::INK), LV_PART_INDICATOR);
    lv_obj_set_style_arc_opa(spin, light_presets::RING_OPA, LV_PART_INDICATOR);
    lv_obj_add_flag(spin, LV_OBJ_FLAG_IGNORE_LAYOUT);
    lv_obj_set_user_data(k, spin);
  }
  // Where the key stands now (the panel places its keys before it marks them).
  if (spin) lv_obj_set_pos(spin, lv_obj_get_style_x(k, LV_PART_MAIN) - (outer - size) / 2, lv_obj_get_style_y(k, LV_PART_MAIN) - (outer - size) / 2);
  // Without a spinner (a board that builds none) the ring shows at once, as before.
  light_presets::mark(k, busy ? !spin : lit);
}

// A tap on a preset's key: the light to that preset, as a wish, unless a preset is still on its way (its spinner turns).
// A preset is several wishes at once (its colour and brightness, an effect, the device's settings), and taps that fold
// field by field would leave the light with parts of two presets: the next one waits until Home Assistant has this one.
static void preset_tap(Tile &t, unsigned n) {
  if (preset_pending(t) >= 0) return;
  preset_wish(t, t.presets->items[n]);
}

// ---- A tile's panel ----
// A tap on a preset's key (user data: the slot times 8 plus the key): the light to that preset, as a wish.
static void preset_key_event(lv_event_t *e){
  const unsigned code=(uintptr_t)lv_event_get_user_data(e),slot=code/8,n=code%8;
  if(slot>=widgets.size()||n>=light_presets::MAX||widgets[slot].index>=model.count)return;
  auto &t=model.tiles[widgets[slot].index];
  if(!t.presets||n>=t.presets->count||!allowed_wish(esphome::millis(),(int)widgets[slot].index,"preset"))return;
  preset_tap(t,n);
}
// The panel's keys of the presets that fit (`r`), made again only when the presets, their number or their size change.
static void preset_keys(Widgets &w,const light_presets::Presets *ps,const light_presets::Row &r){
  const int shape=r.size*8+r.count;
  if(ps==w.dots_of&&shape==w.dots_size)return;
  for(auto *&d:w.dots)if(d){preset_spinner_drop(d);lv_obj_delete(d);d=nullptr;}
  w.dots_of=ps;w.dots_size=shape;
  if(!ps)return;
  for(int n=0;n<r.count;++n){
    w.dots[n]=light_presets::key(w.panel,ps->items[n],r.size,small_font?small_font:w.value_font,preset_key_event,
                                 (void*)(uintptr_t)((&w-widgets.data())*8+n),ps->label(ps->items[n]));
    light_presets::reach(w.dots[n],r.size,r.gap);
  }
}

// The panel's presets (layout_panel, its modes presets and brightness_presets): the keys that fit, the ring round the one
// the light shows, and the slider over them in the pair. Returns the panel's width; `panel_h` its height.
int preset_panel(Widgets &w, const Tile &t, const PanelMetrics &m, bool taller, int content_w, int content_h, int fill, int &panel_h) {
  const std::string mode = tile_controls::panel_kind(t);
  int panel_w = 0;
  // A light's presets (module light_presets): a row of round keys, at the right of a wide card as its slider stands, or
  // under the slider on a card with a second row; on a taller card or one cell they keep a hand's reach.
  const bool pair_light=mode=="brightness_presets";
  const int room=(w.full||taller||!w.wide)?std::min(content_w,ui::control_max_width()):fill;
  const int across=pair_light||taller||w.full||!w.wide?light_presets::tile_key():std::max(m.key_h,std::min(content_h,light_presets::tile_key()));
  const auto *ps=t.presets.get();
  const auto r=light_presets::row(room-2*light_presets::ring(),across,ps?ps->count:0,light_presets::tile_key(),light_presets::least(),light_presets::gap());
  preset_keys(w,ps,r);
  // The ring round a key stands inside the panel: the keys keep that much room round them.
  const int ring=r.count?light_presets::ring():0,row_w=r.length()+2*ring,slider_w=pair_light?m.pill_w:0;
  panel_w=std::max(row_w,slider_w);
  const int row_y=(pair_light?m.slider_h+(r.count?m.gap:0):0)+ring;
  panel_h=row_y+r.size+ring;
  const int lit=preset_lit(t),busy=preset_pending(t);
  for(int n=0;n<r.count;++n){
    lv_obj_set_pos(w.dots[n],(panel_w-row_w)/2+ring+n*(r.size+r.gap),row_y);
    preset_mark(w.dots[n],busy<0&&n==lit,n==busy);
  }
  if(pair_light&&w.control_slider){
    lv_obj_remove_flag(w.control_slider,LV_OBJ_FLAG_HIDDEN);lv_obj_set_pos(w.control_slider,(panel_w-slider_w)/2,0);
    // Keep the dragged value while the command is under way; HA's report takes over afterwards.
    travel_look(w.control_slider,t,false,true);if(!lv_obj_has_state(w.control_slider,LV_STATE_PRESSED) && !(t.pending && !t.confirmed))lv_slider_set_value(w.control_slider,slider_value(t),LV_ANIM_OFF);
    if(!r.count)panel_h=m.slider_h;
  }
  return panel_w;
}

// ---- The colour card's presets: the light's tile's, as a fourth row of the same shape under the three, or on glass wide
// for its height (three units to two, the rule every card splits by) as a column at their right, its keys one under the
// other ----
static void colour_preset_event(lv_event_t *e) {
  const unsigned n = (uintptr_t) lv_event_get_user_data(e);
  const int i = colour_index();
  if (i < 0 || light_controls::demo) return;
  auto &t = model.tiles[i];
  if (!t.presets || n >= t.presets->count || !allowed_wish(esphome::millis(), i, "preset")) return;
  preset_tap(t, n);
}
// The ring round the key of the preset the light shows, the spinner round one on its way.
void colour_presets_paint(const Tile &t) {
  const int lit = colour_presets ? preset_lit(t) : -1, busy = colour_presets ? preset_pending(t) : -1;
  for (unsigned n = 0; n < colour_dots.size(); ++n) preset_mark(colour_dots[n], busy < 0 && (int) n == lit, (int) n == busy);
}
// Whether the presets stand beside the rows, and the column's width.
int colour_column() { return light_presets::card_key() + 2 * light_controls::row_inset; }
bool colour_beside() {
  const int w = overlay_card::screen_width(), h = overlay_card::screen_height();
  return colour_presets && colour_presets->count && w * 2 >= h * 3 &&
         w >= ui::touch_min() * 5 + ui::px(ui::large() ? 18 : 10) * 2 + light_presets::card_key();
}
// The presets' card: under the rows at `y`, or beside them from `top` to `bottom`.
void colour_presets_draw(lv_obj_t *card, bool beside, int top, int bottom, int y) {
  colour_dots.fill(nullptr);
  if (!colour_presets || !colour_presets->count) return;
  const auto *ps = colour_presets.get();
  const lv_font_t *font = small_font;
  const int inset = light_controls::row_inset, gap = light_presets::gap(), size = light_presets::card_key();
  const int text_h = font ? (int) lv_font_get_line_height(font) : 0, under = ui::px(ui::large() ? 8 : 4);
  lv_obj_t *box;
  int x0, y0, along;
  bool column = beside;
  if (beside) {
    const int w = colour_column();
    box = light_controls::row_card(card, light_controls::row_x + light_controls::row_w + light_controls::row_gap, top, w, bottom - top);
    // Its name over the keys where it fits the column, else the keys alone.
    const char *name = screen_text::tr(screen_text::txt::light_presets);
    const bool named = font && text_width(name, font) <= w - 2 * ui::px(4);
    if (named) {
      auto *label = lv_label_create(box); lv_label_set_text(label, name);
      lv_obj_set_style_text_font(label, font, 0); lv_obj_set_style_text_color(label, theme::color(theme::INK), 0);
      lv_obj_set_width(label, w); lv_obj_set_style_text_align(label, LV_TEXT_ALIGN_CENTER, 0);
      lv_obj_set_pos(label, 0, light_controls::row_text_y);
    }
    const int head = named ? light_controls::row_text_y + text_h + under : inset;
    along = bottom - top - head - inset;
    const auto r = light_presets::row(along, w - 2 * ui::px(6), ps->count, size, light_presets::least(), gap);
    x0 = (w - r.size) / 2; y0 = head + (along - r.length()) / 2;
    for (int n = 0; n < r.count; ++n) {
      colour_dots[n] = light_presets::key(box, ps->items[n], r.size, font, colour_preset_event, (void *) (uintptr_t) n,
                                          ps->label(ps->items[n]));
      lv_obj_set_pos(colour_dots[n], x0, y0 + n * (r.size + r.gap));
      light_presets::reach(colour_dots[n], r.size, r.gap);
    }
  } else {
    // A row as the three are: its icon and name at the top, the keys where a track would be.
    box = light_controls::row_card(card, light_controls::row_x, y, light_controls::row_w, light_controls::row_h);
    int text_x = inset;
    if (mini_icon_font) {
      auto *icon = lv_label_create(box); lv_label_set_text(icon, "\U000F02D1");  // heart: Home Assistant's favourites
      lv_obj_set_style_text_font(icon, mini_icon_font, 0); lv_obj_set_style_text_color(icon, theme::color(theme::MUTED), 0);
      const int icon_h = lv_font_get_line_height(mini_icon_font);
      lv_obj_set_pos(icon, inset - ui::px(ui::large() ? 2 : 1), light_controls::row_text_y + (text_h - icon_h) / 2);
      text_x += icon_h + ui::px(ui::large() ? 6 : 4);
    }
    auto *label = lv_label_create(box); lv_label_set_text(label, screen_text::tr(screen_text::txt::light_presets));
    if (font) lv_obj_set_style_text_font(label, font, 0);
    lv_obj_set_style_text_color(label, theme::color(theme::INK), 0);
    lv_obj_set_pos(label, text_x, light_controls::row_text_y);
    const int head = light_controls::row_text_y + text_h + under;
    const int room = light_controls::row_h - head - ui::px(ui::large() ? 8 : 4);
    const auto r = light_presets::row(light_controls::row_w - 2 * inset, room, ps->count, size, light_presets::least(), gap);
    y0 = head + (room - r.size) / 2;
    for (int n = 0; n < r.count; ++n) {
      colour_dots[n] = light_presets::key(box, ps->items[n], r.size, font, colour_preset_event, (void *) (uintptr_t) n,
                                          ps->label(ps->items[n]));
      lv_obj_set_pos(colour_dots[n], inset + n * (r.size + r.gap), y0);
      light_presets::reach(colour_dots[n], r.size, r.gap);
    }
  }
  (void) column;
  // The ring round a key stands a little outside it.
  lv_obj_add_flag(box, LV_OBJ_FLAG_OVERFLOW_VISIBLE);
}

// ---- The card of a light that only dims ----
// A preset's key on the light's card: a tap is the preset as a wish; the ring is painted from the tile (card_bind).
static void detail_preset_event(lv_event_t *e){
  const unsigned n=(uintptr_t)lv_event_get_user_data(e);
  if(detail_index>=model.count)return;
  auto &t=model.tiles[detail_index];
  if(!t.presets||n>=t.presets->count||!allowed_wish(esphome::millis(),(int)detail_index,"preset"))return;
  preset_tap(t,n);
}
static void detail_preset_paint(lv_obj_t *key,const Tile &t,const CardPart &part){
  const int busy=t.presets?preset_pending(t):-1;
  preset_mark(key,busy<0&&t.presets&&preset_lit(t)==(int)part.arg,busy==(int)part.arg);
}
// Its presets in `x`, `y`, `width` x `height`: centred, or from the left edge where the card stands in two columns.
void light_card_presets(const Tile &t, int x, int y, int width, int height, bool left) {
  if (!t.presets) return;
  const light_card::Rect area{x, y, width, height};
{
  const auto r=light_presets::row(area.w,area.h,t.presets->count,light_presets::card_key(),light_presets::least(),light_presets::gap());
  // Under the value where it stands centred, from its left edge in two columns.
  const int x0=left?area.x:area.x+(area.w-r.length())/2;
  for(int n=0;n<r.count;++n){
    auto *key=light_presets::key(detail_root,t.presets->items[n],r.size,small_font,detail_preset_event,(void*)(uintptr_t)n,
                                 t.presets->label(t.presets->items[n]));
    lv_obj_set_pos(key,x0+n*(r.size+r.gap),area.y+(area.h-r.size)/2);
    light_presets::reach(key,r.size,r.gap);
    card_bind(key,t,detail_preset_paint,"",n);
  }
}
}

}  // namespace runtime_tiles
#endif
