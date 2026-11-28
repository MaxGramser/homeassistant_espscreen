#pragma once
// Paints a calendar_card::Scene into an LVGL layer: the calendar card's one object per card (calendar_view.cpp) and the
// host design study (tools/render/calendar_card.py) share it, so what the study shows is what the glass shows.
#include "calendar_card.h"
#include "theme.h"
#include "draw_text.h"

#include <algorithm>
#include <array>

namespace calendar_paint {
namespace cc = calendar_card;

// A plan's paint as this look draws it: the theme's roles, and a calendar's own colour from the card's data.
inline uint32_t colour(cc::Paint p, const std::vector<uint32_t> &colors) {
  // The room's state (calendar_card FREE_COLOUR, BUSY_COLOUR): Home Assistant's green and red, painted as a calendar's.
  const uint32_t key = p.cal == cc::FREE_COLOUR ? theme::ha::GREEN : p.cal == cc::BUSY_COLOUR ? theme::ha::RED
                       : p.cal < colors.size() ? colors[p.cal] : theme::ha::BLUE;
  // Every role as a part of the theme: the head's circle is a disc that says a state (an event running or none),
  // now is a mark, and a calendar's own colour is the theme's calendar parts.
  switch (p.role) {
    case cc::INK: return theme::hex(theme::INK);
    case cc::MUTED: return theme::hex(theme::MUTED);
    case cc::SUBTLE: return theme::hex(theme::SUBTLE);
    case cc::TRACK: return theme::hex(theme::TRACK);
    case cc::GRID: return theme::hex(theme::GRID);
    case cc::SOFT: return theme::hex(theme::PAGE_SOFT);
    case cc::CARD: return theme::hex(theme::CARD);
    case cc::KEY: return theme::hex(theme::KEY);
    case cc::NOW: return theme::mark(theme::ha::RED);
    case cc::ON_NOW: return theme::hex(theme::ON_ACCENT);
    case cc::RAISED: return theme::hex(theme::RAISED);
    case cc::RAISED_LINE: return theme::hex(theme::RAISED_LINE);
    case cc::SCRIM: return theme::scrim();
    case cc::ACCENT: return theme::hex(theme::ACCENT);
    case cc::ACCENT_TINT: return theme::hex(theme::ACCENT_TINT);
    case cc::ON_TINT: return theme::state_disc(theme::ha::AMBER, true, true, 40).ground;
    case cc::ON_ICON: return theme::state_disc(theme::ha::AMBER, true, true, 40).ink;
    case cc::OFF_TINT: return theme::state_disc(theme::STATE_OFF, true, false, 40).ground;
    case cc::OFF_ICON: return theme::state_disc(theme::STATE_OFF, true, false, 40).ink;
    case cc::CAL_KEY: return theme::calendar_key(key);
    case cc::CAL_BLOCK: return theme::calendar_block(key);
    case cc::CAL_INK: return theme::calendar_ink(key);
    case cc::CAL_TRACK: return theme::calendar_track(key);
    case cc::CAL_KEY_PAST: return theme::calendar_key_past(key);
    case cc::CAL_BLOCK_PAST: return theme::calendar_block_past(key);
    case cc::CAL_INK_PAST: return theme::calendar_ink_past(key);
    default: return theme::hex(theme::INK);
  }
}
using Faces = std::array<const lv_font_t *, cc::FACES>;
inline bool meets(const lv_area_t &clip, int x1, int y1, int x2, int y2) {
  return x1 <= clip.x2 && x2 >= clip.x1 && y1 <= clip.y2 && y2 >= clip.y1;
}
// Paints `sc` with its origin at (ox, oy); only what meets the layer's clip area is handed to LVGL, so a scroll redraws
// the strip that comes into view, not the day.
inline void paint(lv_layer_t *layer, const cc::Scene &sc, int ox, int oy, const Faces &faces, const std::vector<uint32_t> &colors) {
  const lv_area_t clip = layer->_clip_area;
  for (auto &b : sc.boxes) {
    const int x1 = ox + b.x, y1 = oy + b.y, x2 = x1 + b.w - 1, y2 = y1 + b.h - 1;
    if (!meets(clip, x1, y1, x2, y2)) continue;
    lv_draw_rect_dsc_t d;
    lv_draw_rect_dsc_init(&d);
    d.bg_color = lv_color_hex(colour(b.paint, colors));
    // A ground that lets what is under it through, at the strength the glass shows that (theme::solid), and a line in
    // a colour of its own (theme::line).
    d.bg_opa = theme::solid(b.opa);
    d.radius = b.radius;
    if (b.border) { d.border_width = b.border; d.border_color = lv_color_hex(theme::line(colour(b.line, colors))); d.border_opa = LV_OPA_COVER; }
    // A ground whose colour is the card's own needs a line to be a shape, where the glass gives it none
    // (theme::shape_rim): an event's block, a track, a key, the head's circle while nothing runs, a colour its giver
    // made the card's, and the accent's pale share, which marks what is chosen (a row of the view choice, the
    // keyboard's shift).
    if (const int rim = theme::shape_rim(); rim && !b.border && b.radius > 0 && d.bg_opa) {
      const auto role = b.paint.role;
      const bool own_blank = (role == cc::CAL_KEY || role == cc::CAL_KEY_PAST) && colour(b.paint, colors) == theme::hex(theme::CARD);
      if (own_blank || role == cc::ACCENT_TINT || role == cc::CAL_BLOCK || role == cc::CAL_BLOCK_PAST || role == cc::OFF_TINT || role == cc::TRACK || role == cc::KEY) {
        d.border_width = rim;
        d.border_color = lv_color_hex(theme::hex(theme::INK));
        d.border_opa = LV_OPA_COVER;
      }
    }
    lv_area_t a{x1, y1, x2, y2};
    if (b.cw > 0) {
      // Cut to its strip: the shape keeps its corners, only the part inside the strip is drawn.
      const lv_area_t keep = layer->_clip_area;
      const lv_area_t both{std::max<int32_t>(keep.x1, ox + b.cx), std::max<int32_t>(keep.y1, oy + b.cy),
                           std::min<int32_t>(keep.x2, ox + b.cx + b.cw - 1), std::min<int32_t>(keep.y2, oy + b.cy + b.ch - 1)};
      if (both.x1 > both.x2 || both.y1 > both.y2) continue;
      layer->_clip_area = both;
      lv_draw_rect(layer, &d, &a);
      layer->_clip_area = keep;
      continue;
    }
    lv_draw_rect(layer, &d, &a);
  }
  for (auto &t : sc.texts) {
    const lv_font_t *f = faces[t.face];
    if (!f || t.s.empty()) continue;
    const int h = lv_font_get_line_height(f), x1 = ox + t.x, y1 = oy + t.y;
    if (!meets(clip, x1, y1, x1 + t.w - 1, y1 + h - 1)) continue;
    lv_draw_label_dsc_t d;
    lv_draw_label_dsc_init(&d);
    d.font = f;
    d.color = lv_color_hex(colour(t.paint, colors));
    d.text = t.s.c_str();
    d.align = t.align == cc::CENTRE ? LV_TEXT_ALIGN_CENTER : t.align == cc::RIGHT ? LV_TEXT_ALIGN_RIGHT : LV_TEXT_ALIGN_LEFT;
    // The plan already fitted the line to its box; a glyph's overhang may not wrap a left-aligned line onto a second.
    if (t.align == cc::LEFT) d.flag = LV_TEXT_FLAG_EXPAND;
    lv_area_t a{x1, y1, x1 + t.w - 1, y1 + h - 1};
    draw_text::label(layer, d, a);
  }
}
// The hit under a point in the scene's coordinates (the last one drawn wins: sheets lie over the page).
inline const cc::Hit *hit(const cc::Scene &sc, int x, int y) {
  for (auto it = sc.hits.rbegin(); it != sc.hits.rend(); ++it)
    if (x >= it->x && x < it->x + it->w && y >= it->y && y < it->y + it->h) return &*it;
  return nullptr;
}
}  // namespace calendar_paint
