#pragma once
// The pager of every page that holds more than fits: the tile pages, the settings page, a light group, the media
// library and its speaker menu, a select's options and the weather card's days. One pager, the tile pages' own, so the
// one that is already learned is the one everywhere:
//
//  * each half of the bar is one key, a chevron in its outer corner with its ink on the tiles' margin (align);
//  * a press shows as a patch around what the key shows, a circle around a lone chevron and a pill around chevron and
//    word, never across the whole half, which runs under the dots (patch);
//  * a key that leads nowhere is dimmed and takes no touches (enable);
//  * the page dots stand between them, the page on screen in ink, and "3 / 12" past eight pages (dots).
//
// The tile pages' bar is declared in packages/core.yaml (page_prev, page_number, page_next) and dressed here; every
// other page builds the same three objects with make(), always where the tile pages have theirs: across the foot of
// the glass, at the band's height, the chevrons on the tiles' margin. A page's content ends above it.
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <string>
#include "lvgl.h"
#include "header_bar.h"
#include "overlay_card.h"
#include "theme.h"
#include "ui_scale.h"

namespace page_bar {

// The chevrons' font, and the words' past eight pages; set once by the core (packages/core.yaml).
inline const lv_font_t *icon_font = nullptr, *words_font = nullptr;
// The band under the tiles (PAGE_BAR_H) and the tiles' margin from the glass's side, from the tile area
// (runtime_tiles::grid_bind): every bar across the foot of the glass is this band, its chevrons on this margin.
inline int band = 0, margin = 0;
// The finger's guard every key of a bar asks first (screen_input::touch_guard: bounce, a swipe ending on the bar);
// `key` is 11 for back and 12 for forward, the tile pages' own.
inline bool (*allowed)(int key) = nullptr;

constexpr uint32_t PREV = 0xF0141, NEXT = 0xF0142;  // mdi:chevron-left, mdi:chevron-right
constexpr int MOST_DOTS = 8;

inline int height() { return band > 0 ? band : ui::px(ui::large() ? 60 : 36); }
inline int inset() { return margin > 0 ? margin : ui::px(ui::large() ? 16 : 10); }

// What a key shows: its chevron, the first label whose text is one. Not its first child: that is the patch behind it.
inline lv_obj_t *glyph(lv_obj_t *key) {
  for (uint32_t i = 0; key && i < lv_obj_get_child_count(key); ++i) {
    auto *child = lv_obj_get_child(key, i);
    if (!lv_obj_check_type(child, &lv_label_class)) continue;
    const std::string text(lv_label_get_text(child));
    size_t at = 0;
    const uint32_t cp = header_bar::next_codepoint(text, at);
    if (at == text.size() && (cp == PREV || cp == NEXT)) return child;
  }
  return nullptr;
}

// The inked box of what a label shows: for a lone icon the glyph's own box from the font, since the label's box
// carries the font's side bearings and line gap and a patch centred on it would sit off the chevron.
inline lv_area_t ink_area(lv_obj_t *o) {
  lv_area_t a;
  lv_obj_get_coords(o, &a);
  if (!lv_obj_check_type(o, &lv_label_class)) return a;
  const char *text = lv_label_get_text(o);
  if (!text || !*text) return a;
  const std::string shown(text);
  size_t i = 0;
  const uint32_t cp = header_bar::next_codepoint(shown, i);
  if (i != shown.size() || cp < 0xF0000) return a;  // words ("Back") keep their label box
  const lv_font_t *font = lv_obj_get_style_text_font(o, LV_PART_MAIN);
  lv_font_glyph_dsc_t g;
  if (!font || !lv_font_get_glyph_dsc(font, &g, cp, 0) || !g.box_w || !g.box_h) return a;
  const int32_t top = a.y1 + (font->line_height - font->base_line) - (int32_t) g.box_h - g.ofs_y, left = a.x1 + g.ofs_x;
  return lv_area_t{left, top, left + (int32_t) g.box_w - 1, top + (int32_t) g.box_h - 1};
}

// A key takes touches across its half of the bar; its press shows as a rounded patch around what it shows.
inline void patch_event(lv_event_t *e) {
  auto *key = static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  auto *patch = static_cast<lv_obj_t *>(lv_event_get_user_data(e));
  const auto code = lv_event_get_code(e);
  if (code == LV_EVENT_RELEASED || code == LV_EVENT_PRESS_LOST) { lv_obj_add_flag(patch, LV_OBJ_FLAG_HIDDEN); return; }
  if (code != LV_EVENT_PRESSED) return;
  // Around everything the key shows: the chevron, and "Back" beside it on a detail page.
  lv_area_t k, c{};
  bool any = false;
  lv_obj_get_coords(key, &k);
  for (uint32_t i = 0; i < lv_obj_get_child_count(key); ++i) {
    auto *child = lv_obj_get_child(key, i);
    if (child == patch || lv_obj_has_flag(child, LV_OBJ_FLAG_HIDDEN)) continue;
    const lv_area_t a = ink_area(child);
    if (!any) { c = a; any = true; }
    else { c.x1 = std::min(c.x1, a.x1); c.y1 = std::min(c.y1, a.y1); c.x2 = std::max(c.x2, a.x2); c.y2 = std::max(c.y2, a.y2); }
  }
  if (!any) return;
  // A circle around a lone chevron, a pill around chevron and word; never taller than the bar.
  const int pad = ui::px(ui::large() ? 14 : 10), bar = (int) lv_area_get_height(&k);
  const int iw = (int) lv_area_get_width(&c), ih = (int) lv_area_get_height(&c);
  const int h = std::min(bar - ui::px(4), std::max(iw, ih) + 2 * pad), w = std::max(h, iw + 2 * pad);
  const int cx = (int) (c.x1 + c.x2 + 1) / 2 - (int) k.x1, cy = (int) (c.y1 + c.y2 + 1) / 2 - (int) k.y1;
  lv_obj_set_size(patch, w, h);
  lv_obj_set_pos(patch, cx - w / 2, cy - h / 2);
  lv_obj_remove_flag(patch, LV_OBJ_FLAG_HIDDEN);
}
inline void patch(lv_obj_t *key) {
  if (!key) return;
  auto *patch = lv_obj_create(key);
  lv_obj_remove_style_all(patch);
  lv_obj_remove_flag(patch, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_remove_flag(patch, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_add_flag(patch, LV_OBJ_FLAG_IGNORE_LAYOUT);
  lv_obj_add_flag(patch, LV_OBJ_FLAG_HIDDEN);
  lv_obj_add_style(patch, theme::style(theme::Paint::page_pressed), 0);
  lv_obj_set_style_bg_opa(patch, LV_OPA_COVER, 0);
  lv_obj_set_style_radius(patch, LV_RADIUS_CIRCLE, 0);
  lv_obj_move_to_index(patch, 0);  // behind the chevron
  for (auto code : {LV_EVENT_PRESSED, LV_EVENT_RELEASED, LV_EVENT_PRESS_LOST}) lv_obj_add_event_cb(key, patch_event, code, patch);
}

// A key's chevron with its ink `inset` from the key's outer side (the tiles' margin on the tile pages), measured from
// the glyph itself so the font's side bearing does not push it inward.
inline void align(lv_obj_t *key, bool left, int inset) {
  auto *chevron = glyph(key);
  if (!chevron) return;
  const lv_font_t *font = lv_obj_get_style_text_font(chevron, LV_PART_MAIN);
  lv_font_glyph_dsc_t g;
  if (!font || !lv_font_get_glyph_dsc(font, &g, left ? PREV : NEXT, 0) || !g.box_w) return;
  lv_obj_set_x(chevron, left ? inset - g.ofs_x : -(inset - (int(g.adv_w) - g.ofs_x - int(g.box_w))));
}

// A key that leads nowhere: dimmed, and its touches go nowhere.
inline void enable(lv_obj_t *key, bool on) {
  if (!key) return;
  if (on) lv_obj_remove_state(key, LV_STATE_DISABLED); else lv_obj_add_state(key, LV_STATE_DISABLED);
  if (auto *chevron = glyph(key)) {
    const lv_opa_t opa = on ? LV_OPA_COVER : LV_OPA_30;
    if (lv_obj_get_style_text_opa(chevron, LV_PART_MAIN) != opa) lv_obj_set_style_text_opa(chevron, opa, 0);
  }
}

// The page dots, centred in `row`: the page on screen in ink and the others a quiet grey. The dots are made once and
// reused; `row` takes no touches. More pages than eight dots hold: "3 / 12" in their place.
inline void dots(lv_obj_t *row, int current, int total) {
  if (!row) return;
  const bool large = ui::large();
  const int dot = ui::px(large ? 8 : 6), gap = ui::px(large ? 10 : 7);
  total = std::max(total, 0);
  const bool words = total > MOST_DOTS;
  lv_obj_t *label = nullptr;
  int count = 0;
  for (int i = 0; i < (int) lv_obj_get_child_count(row); ++i) {
    auto *child = lv_obj_get_child(row, i);
    if (lv_obj_check_type(child, &lv_label_class)) label = child;
    else ++count;
  }
  const int wanted = words ? 0 : total;
  while (count < wanted) {
    auto *d = lv_obj_create(row);
    lv_obj_remove_style_all(d);
    lv_obj_remove_flag(d, static_cast<lv_obj_flag_t>(LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE));
    lv_obj_set_style_radius(d, LV_RADIUS_CIRCLE, 0);
    ++count;
  }
  if (words && !label && words_font) {
    label = lv_label_create(row);
    lv_obj_remove_flag(label, static_cast<lv_obj_flag_t>(LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE));
    lv_obj_set_style_text_font(label, words_font, 0);
  }
  if (label) {
    if (words) {
      char b[16];
      snprintf(b, sizeof(b), "%d / %d", current + 1, total);
      lv_label_set_text(label, b);
      lv_obj_set_style_text_color(label, theme::color(theme::MUTED), 0);
      lv_obj_align(label, LV_ALIGN_CENTER, 0, 0);
      lv_obj_remove_flag(label, LV_OBJ_FLAG_HIDDEN);
    } else {
      lv_obj_add_flag(label, LV_OBJ_FLAG_HIDDEN);
    }
  }
  const int width = wanted * dot + std::max(0, wanted - 1) * gap;
  int n = 0;
  for (int i = 0; i < (int) lv_obj_get_child_count(row); ++i) {
    auto *d = lv_obj_get_child(row, i);
    if (d == label) continue;
    const int at = n++;
    if (at >= wanted) { lv_obj_add_flag(d, LV_OBJ_FLAG_HIDDEN); continue; }
    lv_obj_remove_flag(d, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_size(d, dot, dot);
    lv_obj_align(d, LV_ALIGN_CENTER, at * (dot + gap) + dot / 2 - width / 2, 0);
    lv_obj_set_style_bg_color(d, theme::color(at == current ? theme::INK : theme::SUBTLE), 0);
    lv_obj_set_style_bg_opa(d, at == current ? LV_OPA_COVER : LV_OPA_40, 0);
  }
}

// ---- A bar of one's own, the tile pages' bar for another page ----
// `step` gets -1 or +1 when a key is tapped; a page turns its own way (a page of rows, of covers, of days) and draws.
using Step = void (*)(int step);
struct Bar { lv_obj_t *prev = nullptr, *dots = nullptr, *next = nullptr; };

inline void key_event(lv_event_t *e) {
  auto *key = static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  if (lv_obj_has_state(key, LV_STATE_DISABLED)) return;
  const int direction = (int) (intptr_t) lv_obj_get_user_data(key);
  if (allowed && !allowed(direction < 0 ? 11 : 12)) return;
  if (auto step = reinterpret_cast<Step>(lv_event_get_user_data(e))) step(direction);
}
// One half: the whole half takes touches. CLICKED, not SHORT_CLICKED: LVGL sends no short click after a press of
// 400 ms, so a firm or slow press did nothing (firmware 0.2.65+); the bar has no hold of its own.
inline lv_obj_t *half(lv_obj_t *parent, int x, int y, int w, int h, bool left, int inset, Step step) {
  auto *key = lv_obj_create(parent);
  lv_obj_remove_style_all(key);
  lv_obj_set_pos(key, x, y);
  lv_obj_set_size(key, w, h);
  lv_obj_remove_flag(key, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_add_flag(key, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_user_data(key, (void *) (intptr_t) (left ? -1 : 1));
  auto *chevron = lv_label_create(key);
  lv_obj_remove_flag(chevron, LV_OBJ_FLAG_CLICKABLE);
  if (icon_font) lv_obj_set_style_text_font(chevron, icon_font, 0);
  lv_obj_add_style(chevron, theme::style(theme::Paint::ink), 0);
  lv_label_set_text(chevron, left ? "\U000F0141" : "\U000F0142");
  lv_obj_align(chevron, left ? LV_ALIGN_LEFT_MID : LV_ALIGN_RIGHT_MID, 0, 0);
  patch(key);
  align(key, left, inset);
  overlay_card::touchable(key, h);  // a bar a card makes low still takes a finger
  lv_obj_add_event_cb(key, key_event, LV_EVENT_CLICKED, reinterpret_cast<void *>(step));
  return key;
}
// The bar in an area of `parent` (its coordinates), the chevrons' ink `inset` from the area's sides; only the bar across
// the foot of the glass below is made of it, so no page has a pager anywhere else.
inline Bar make_in(lv_obj_t *parent, int x, int y, int w, int h, Step step, int inset) {
  Bar bar;
  bar.prev = half(parent, x, y, w / 2, h, true, inset, step);
  bar.dots = lv_obj_create(parent);
  lv_obj_remove_style_all(bar.dots);
  lv_obj_remove_flag(bar.dots, static_cast<lv_obj_flag_t>(LV_OBJ_FLAG_SCROLLABLE | LV_OBJ_FLAG_CLICKABLE));
  lv_obj_set_pos(bar.dots, x, y);
  lv_obj_set_size(bar.dots, w, h);
  bar.next = half(parent, x + w - w / 2, y, w / 2, h, false, inset, step);
  return bar;
}
// The bar across the foot of the glass, as the tile pages have it, on any page's root: every page's pager. It stands on
// the glass, not in the card, so a card centred on the glass leaves it where it is (FLOATING, overlay_card::centre).
inline Bar make(lv_obj_t *parent, Step step) {
  const int h = height();
  Bar bar = make_in(parent, overlay_card::glass_left(parent), overlay_card::glass_top(parent) + overlay_card::screen_height() - h,
                 overlay_card::screen_width(), h, step, inset());
  for (auto *part : {bar.prev, bar.dots, bar.next}) lv_obj_add_flag(part, LV_OBJ_FLAG_FLOATING);
  return bar;
}
// Page `page` of `count`: the keys dimmed at the ends, the dots, and nothing at all for a single page.
inline void show(const Bar &bar, int page, int count) {
  const bool paged = count > 1;
  for (auto *part : {bar.prev, bar.dots, bar.next}) {
    if (!part) continue;
    if (paged) lv_obj_remove_flag(part, LV_OBJ_FLAG_HIDDEN); else lv_obj_add_flag(part, LV_OBJ_FLAG_HIDDEN);
  }
  if (!paged) return;
  enable(bar.prev, page > 0);
  enable(bar.next, page + 1 < count);
  dots(bar.dots, page, count);
}

}  // namespace page_bar
