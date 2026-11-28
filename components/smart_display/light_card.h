#pragma once
// The card a hold opens on a light without colour and on a fan (firmware 0.2.80): where its parts go. Pure
// arithmetic, free of LVGL and ESPHome, so tests/test_light_card.cpp checks every shape on a PC;
// runtime_tiles.h draws it.
//
// It used to be the one card still built in YAML: a full-screen overlay that sat in the LVGL tree whether it
// was open or not, with eight sizes of its own in every board file, its own scripts, and a slider whose
// rounding made LVGL draw it through a 61 KB buffer (0.2.93). This is that card the way the blind and the
// thermostat are: a white card with a standing slider, the value under it and what it is under that, made when
// it opens and cleaned away when it closes, with the power key in the top bar across from the back key -
// exactly where the thermostat has it.
//
// The value line is the state line: "64 %" or "Off" says what the row under the name would have said, so this
// card draws no second one. What must give, gives in this order: the caption under the value first (the name
// at the top already says which light it is), then the slider's own height. On wide and short glass the
// slider and its value stand beside each other instead of over each other, the way the blind's card splits
// (overlay_card::columns).
//
// A light Home Assistant lists as "onoff" and nothing else has no brightness to show, and its own dialog shows
// none either: that card has the light's icon on a round field where the slider would be, and the power key in
// the bar does the work. A slider there would fill to where the finger left it and fall back to empty as soon
// as the light answered without a brightness, and every drag would send one the light throws away.
#include <algorithm>

#include "ui_scale.h"

namespace light_card {

struct Rect {
  int x = 0, y = 0, w = 0, h = 0;
  int right() const { return x + w; }
  int bottom() const { return y + h; }
  int cx() const { return x + w / 2; }
  int cy() const { return y + h / 2; }
  bool empty() const { return w <= 0 || h <= 0; }
};

// What the board brings: its size class, the line heights of the fonts the card writes with, and its top bar.
struct Metrics {
  bool large = true;
  int value_h = 46;  // the percentage, in the big font
  int text_h = 22;   // the caption under it
  int icon_h = 42;   // the icon on the slider, and the one on the power key
  int touch = 48;    // ui::touch_min()
  int pad = 20;      // overlay_card::pad()
  int bar = 60;      // the top bar: the back key's size
  int bar_x = 16, bar_y = 16;

  int gap() const { return ui::px(large ? 12 : 6); }      // between the blocks
  int margin() const { return ui::px(large ? 18 : 6); }   // under the last block
  int edge() const { return ui::px(large ? 16 : 8); }     // inside the white card, around the slider
  // The slider: wide enough for a thumb to hold on a drag (the CYD drew 96 px, the Guition 144), and tall
  // enough that a percent is a pixel or two rather than a jump.
  int slider_w() const { return std::max(ui::touch_min(), ui::px(large ? 144 : 96)); }
  int slider_min_h() const { return std::max(2 * touch, ui::px(large ? 150 : 96)); }
  int min_card_h() const { return slider_min_h() + 2 * edge(); }
  // The round field a light that cannot be dimmed shows its icon on, the size the blind's card uses.
  int halo() const { return ui::px(large ? 120 : 72); }
  int top() const { return bar_y + bar + gap(); }         // the card starts under the top bar
};

struct Layout {
  int columns = 1;
  Rect power;     // in the top bar, across from the back key
  Rect card;      // the white card
  Rect slider;    // the standing slider inside it; empty on a light that cannot be dimmed
  Rect halo;      // the round field its icon sits on instead, then
  Rect icon;      // the entity's icon: near the slider's foot, or in the middle of the halo
  Rect value;     // the percentage or the state: under the card, or beside it in two columns
  Rect caption;   // what the slider is ("Brightness"); empty without a slider or without the room
  Rect presets;   // a light's presets (module light_presets): a row under it all, or under the value in two columns
};

// The height the card asks for in one column, which overlay_card::columns compares with the glass.
inline int stacked_height(const Metrics &m) {
  return m.top() + m.min_card_h() + m.value_h + m.text_h + m.margin();
}

// Where every part goes on glass of `width` x `height`, in `columns` columns (1 or 2). `dims` is false for a
// light Home Assistant lists as "onoff" only: the card then has no slider to draw and shows the light's icon
// on a round field instead, the way the blind's card does for a door that only opens and closes.
// `presets`: the height of a row of the light's presets (0: none), taken from the card's in one column.
inline Layout layout(const Metrics &m, int width, int height, int columns = 1, bool dims = true, int presets = 0) {
  Layout l;
  l.columns = columns >= 2 ? 2 : 1;
  const int inner = width - 2 * m.pad, top = m.top();
  int bottom = height - m.margin();
  if (presets > 0 && l.columns == 1) {
    l.presets = {m.pad, bottom - presets, inner, presets};
    bottom -= presets + m.gap();
  }
  l.power = {width - m.bar_x - m.bar, m.bar_y, m.bar, m.bar};

  if (l.columns == 2) {
    // Wide and short: the card keeps the whole height and the value stands beside it, big, with its caption
    // under it. The height the stack lacked is width the board has.
    const int text_w = std::max(ui::mm(24), m.slider_w() * 2);
    const int card_w = std::max(m.slider_w() + 2 * m.edge(), inner - text_w - ui::column_gap());
    l.card = {m.pad, top, card_w, std::max(ui::px(8), bottom - top)};
    const int block = m.value_h + m.text_h;
    const int below = presets > 0 ? m.gap() + presets : 0;
    l.value = {l.card.right() + ui::column_gap(), l.card.cy() - (block + below) / 2, inner - card_w - ui::column_gap(), m.value_h};
    l.caption = {l.value.x, l.value.bottom(), l.value.w, m.text_h};
    if (presets > 0) l.presets = {l.value.x, l.caption.bottom() + m.gap(), l.value.w, presets};
  } else {
    bool caption = true;
    auto room = [&]() { return bottom - top - m.value_h - (caption ? m.text_h : 0); };
    if (room() < m.min_card_h()) caption = false;
    l.card = {m.pad, top, inner, std::max(ui::px(8), room())};
    l.value = {l.card.x, l.card.bottom(), inner, m.value_h};
    if (caption) l.caption = {l.card.x, l.value.bottom(), inner, m.text_h};
  }

  if (dims) {
    const int slider_w = std::min(m.slider_w(), std::max(1, l.card.w - 2 * m.edge()));
    l.slider = {l.card.cx() - slider_w / 2, l.card.y + m.edge(), slider_w, std::max(1, l.card.h - 2 * m.edge())};
    // The icon sits on the foot of the slider, where the fill is and a finger is not.
    const int icon = std::min(m.icon_h, std::max(1, slider_w - ui::px(8)));
    l.icon = {l.slider.cx() - icon / 2, l.slider.bottom() - icon - m.edge(), icon, icon};
    if (l.icon.y < l.slider.y) l.icon = {};
  } else {
    // No slider: the icon on a round field in the middle of the card, as big as the card allows.
    const int halo = std::max(m.touch, std::min(std::min(l.card.w, l.card.h) - 2 * m.edge(), m.halo()));
    l.halo = {l.card.cx() - halo / 2, l.card.y + (l.card.h - halo) / 2, halo, halo};
    const int icon = std::min(m.icon_h, std::max(1, halo - ui::px(8)));
    l.icon = {l.halo.cx() - icon / 2, l.halo.y + (halo - icon) / 2, icon, icon};
    l.caption = {};   // "Brightness" would name a control this light does not have
  }
  return l;
}

}  // namespace light_card
