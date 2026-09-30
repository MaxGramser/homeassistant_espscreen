#pragma once
#include "header_bar.h"
#include "theme.h"
#include "tile_icon.h"
#include "esphome/core/time.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <string>

// The page header renderer owns one reusable set of LVGL widgets. It knows
// nothing about stored layouts, page order, HA transport or navigation history.
// Runtime selects the View and supplies a guarded action for the leading key.
namespace page_header {
enum class Leading { none, home, back };
struct Surface {
  lv_obj_t *title, *clock_anchor, *grid, *hold_area;
  const lv_font_t *text_font, *icon_font;
  // The home key's picture, the Tessera mark (an lv_image_dsc_t); without one the icon font's house stands there.
  const void *home_mark;
  const lv_font_t *back_font = nullptr;
};
struct View {
  const header_bar::Bar &bar;
  const std::string &title;
  esphome::ESPTime now;
  int64_t epoch;
  Leading leading;
  bool live, clock_24h;
};
class Renderer {
  void (*leading_action)() = nullptr;
  static void label(lv_obj_t *obj, const std::string &text) {
    if (text != lv_label_get_text(obj)) lv_label_set_text(obj, text.c_str());
  }
  static void set_font(lv_obj_t *obj, const lv_font_t *font) {
    if (lv_obj_get_style_text_font(obj, LV_PART_MAIN) != font) lv_obj_set_style_text_font(obj, font, 0);
  }
  static void set_line_width(lv_obj_t *obj, int width) {
    if (lv_obj_get_style_line_width(obj, LV_PART_MAIN) != width) lv_obj_set_style_line_width(obj, width, 0);
  }
  static std::string hhmm(const esphome::ESPTime &time) {
    char text[8]; snprintf(text, sizeof(text), "%02d:%02d", time.hour, time.minute); return text;
  }
  struct HeaderSlot { lv_obj_t *icon{}, *text{}; uint32_t icon_color = 0; bool own = false; };
  lv_obj_t *header_root = nullptr, *header_ring = nullptr;
  std::array<lv_obj_t *, 2> header_hands{};
  std::array<HeaderSlot, header_bar::MAX_ITEMS> header_slots{};
  lv_point_precise_t header_points[4]{};
  int header_dial_key = -1;
  // The home key at the far left of the top bar (firmware 0.2.100+): since firmware 0.10.0 the Tessera mark in its own
  // colours, the way the logo in a website's header or the start button of a desktop takes you home. It is as tall
  // as the house that stood there before (packages/core.yaml sizes it) and stands on the baseline of the page title.
  // It stands on every page and goes to the designated Home. With the bottom bar
  // hidden, a detail page replaces it with Back, independent of the Home setting.
  // `header_home_tap` is the area a finger gets, wider than the key; its action is supplied by the caller.
  // `header_home_icon` draws Back, and the house where a build has no mark.
  lv_obj_t *header_home_icon = nullptr, *header_home_mark = nullptr, *header_home_tap = nullptr;
  lv_obj_t *header_name_owner = nullptr;
  int header_name_left = 0;
  // mdi:home, in every board's icon font already (the tile icons): the key without a mark.
  static constexpr uint32_t HOME_GLYPH = 0xF02DC;
  void set_visible(lv_obj_t *obj, bool visible) {
    if (lv_obj_has_flag(obj, LV_OBJ_FLAG_HIDDEN) != visible) return;
    if (visible) lv_obj_remove_flag(obj, LV_OBJ_FLAG_HIDDEN); else lv_obj_add_flag(obj, LV_OBJ_FLAG_HIDDEN);
  }
  // Ink edges of a text from its label's left edge, and its advance (what LVGL sizes a label by).
  struct TextInk { int left = 0, right = 0, advance = 0; };
  TextInk text_ink(const lv_font_t *font, const std::string &text) {
    TextInk ink;
    bool first = true;
    size_t i = 0;
    for (uint32_t cp = header_bar::next_codepoint(text, i); cp; cp = header_bar::next_codepoint(text, i)) {
      lv_font_glyph_dsc_t g;
      if (!lv_font_get_glyph_dsc(font, &g, cp, 0)) continue;
      if (g.box_w > 0) {
        if (first) { ink.left = ink.advance + g.ofs_x; first = false; }
        ink.right = ink.advance + g.ofs_x + g.box_w;
      }
      ink.advance += g.adv_w;
    }
    return ink;
  }
  lv_obj_t *header_part(lv_obj_t *parent) {
    auto *part = lv_label_create(parent);
    lv_obj_remove_flag(part, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_flag(part, LV_OBJ_FLAG_HIDDEN);
    lv_obj_add_style(part, theme::style(theme::Paint::slate), 0);
    return part;
  }
  // `live`: Home Assistant's values may show; without its link or the manager's feed only clocks stay.
public:
  lv_obj_t *leading_target() const { return header_home_tap; }
  void restyle() { for (auto &slot : header_slots) { slot.own = true; slot.icon_color = UINT32_MAX; } }
  // Used only when a host renderer replaces its preview surface.
  void reset() {
    if (header_home_tap) lv_obj_delete(header_home_tap);
    if (header_root) lv_obj_delete(header_root);
    *this = Renderer{};
  }
  void draw(const Surface &surface, const View &view, void (*on_leading)()) {
    auto *room_label = surface.title, *time_label = surface.clock_anchor, *tile_grid = surface.grid;
    const auto *header_text_font = surface.text_font, *header_icon_font = surface.icon_font;
    const auto *home_mark = static_cast<const lv_image_dsc_t *>(surface.home_mark);
    const auto &header_name = view.title;
    const auto &bar = view.bar;
    const auto &now = view.now;
    const bool live = view.live;
    leading_action = on_leading;

    if (!room_label || !time_label || !header_text_font || !header_icon_font) return;
    set_visible(time_label, false);
    auto *page = lv_obj_get_parent(room_label);
    if (!header_root) {
      header_root = lv_obj_create(page);
      lv_obj_remove_style_all(header_root);
      lv_obj_remove_flag(header_root, LV_OBJ_FLAG_CLICKABLE);
      lv_obj_remove_flag(header_root, LV_OBJ_FLAG_SCROLLABLE);
      // The clock label's place in the drawing order: under the tiles, cards and overlays.
      lv_obj_move_to_index(header_root, lv_obj_get_index(time_label));
      for (auto &slot : header_slots) {
        slot.icon = header_part(header_root);
        slot.text = header_part(header_root);
        lv_obj_set_style_text_font(slot.icon, header_icon_font, 0);
        lv_obj_set_style_text_font(slot.text, header_text_font, 0);
      }
      header_home_icon = header_part(header_root);
#if LV_USE_IMAGE
      if (home_mark) {
        header_home_mark = lv_image_create(header_root);
        lv_image_set_src(header_home_mark, home_mark);
        lv_obj_remove_flag(header_home_mark, LV_OBJ_FLAG_CLICKABLE);
        lv_obj_add_flag(header_home_mark, LV_OBJ_FLAG_HIDDEN);
      }
#endif
      // The finger's area, over the glyph and bigger than it: an empty object that only takes taps. It sits on the
      // page itself, one place above the strip that opens the settings page on a long press, so a tap on the house
      // is the house's; the cards and the alert stay above it and keep every tap of their own.
      header_home_tap = lv_obj_create(page);
      lv_obj_remove_style_all(header_home_tap);
      lv_obj_remove_flag(header_home_tap, LV_OBJ_FLAG_SCROLLABLE);
      lv_obj_add_flag(header_home_tap, LV_OBJ_FLAG_CLICKABLE);
      lv_obj_add_flag(header_home_tap, LV_OBJ_FLAG_HIDDEN);
      lv_obj_move_to_index(header_home_tap, surface.hold_area && lv_obj_get_parent(surface.hold_area) == page
                                          ? lv_obj_get_index(surface.hold_area) + 1
                                          : lv_obj_get_index(header_root) + 1);
      lv_obj_add_event_cb(header_home_tap, [](lv_event_t *event) {
        auto *renderer = static_cast<Renderer *>(lv_event_get_user_data(event));
        if (renderer->leading_action) renderer->leading_action();
      }, LV_EVENT_CLICKED, this);
      header_ring = lv_obj_create(header_root);
      lv_obj_remove_style_all(header_ring);
      lv_obj_remove_flag(header_ring, LV_OBJ_FLAG_CLICKABLE);
      lv_obj_remove_flag(header_ring, LV_OBJ_FLAG_SCROLLABLE);
      lv_obj_set_style_radius(header_ring, LV_RADIUS_CIRCLE, 0);
      lv_obj_add_style(header_ring, theme::style(theme::Paint::slate), 0);
      lv_obj_set_style_border_opa(header_ring, LV_OPA_COVER, 0);
      lv_obj_add_flag(header_ring, LV_OBJ_FLAG_HIDDEN);
      for (auto *&hand : header_hands) {
        hand = lv_line_create(header_root);
        lv_obj_remove_flag(hand, LV_OBJ_FLAG_CLICKABLE);
        lv_obj_set_style_line_rounded(hand, true, 0);
        lv_obj_add_style(hand, theme::style(theme::Paint::slate), 0);
        lv_obj_add_flag(hand, LV_OBJ_FLAG_HIDDEN);
      }
      // A long name ends in dots instead of running under the items.
      lv_label_set_long_mode(room_label, LV_LABEL_LONG_DOT);
    }
    // Geometry from the profile's own widgets: the name's margin and baseline, the clock's right margin.
    const lv_font_t *name_font = lv_obj_get_style_text_font(room_label, LV_PART_MAIN);
    int page_w = lv_obj_get_width(page), left = lv_obj_get_x(room_label);
    // int32_t is long on the ESP32 toolchain: keep the arithmetic in int.
    int width = std::max(0, page_w + static_cast<int>(lv_obj_get_style_x(time_label, LV_PART_MAIN)) - left);
    // The name's margin from the side of the glass, as the profile placed it before the key moved it along.
    if (header_name_owner != room_label) { header_name_owner = room_label; header_name_left = left; }
    // The key's slot: the mark's picture, or the house of the icon font. Back takes the same slot, so the title and
    // the finger's area stay where they are when a detail page swaps the key for a chevron.
    int slot_w = 0, slot_h = 0;
    lv_font_glyph_dsc_t house, cap;
    if (header_home_mark) { slot_w = home_mark->header.w; slot_h = home_mark->header.h; }
    else if (lv_font_get_glyph_dsc(header_icon_font, &house, HOME_GLYPH, 0)) { slot_w = house.box_w; slot_h = house.box_h; }
    // The bar keeps one margin all round (firmware 0.14.0+): the top of the key's slot lies as far below the top of
    // the glass as the name lies from its side. Since firmware 0.15.0 the name's capitals are centred on the slot
    // (GitHub #90), so the name and the key share one middle line whatever the fonts, and the bar stays put when the
    // key is switched off.
    if (slot_h && lv_font_get_glyph_dsc(name_font, &cap, 'H', 0) && cap.box_h)
      lv_obj_set_y(room_label, header_name_left + (slot_h + cap.box_h) / 2 + cap.ofs_y - (name_font->line_height - name_font->base_line));
    int baseline = lv_obj_get_y(room_label) + (name_font->line_height - name_font->base_line);
    lv_obj_set_pos(header_root, 0, 0);
    lv_obj_set_size(header_root, page_w, baseline + name_font->line_height);
    lv_font_glyph_dsc_t zero, dial_glyph;
    if (!lv_font_get_glyph_dsc(header_text_font, &zero, '0', 0) || !zero.box_h) return;
    // Every part of the bar shares the key's middle line (firmware 0.15.0+): the name's capitals, the items' digits,
    // their icons and the dial. Twice the middle keeps the halves exact. Without a key, the digits' own middle on the
    // name's line.
    int middle2 = slot_h ? 2 * header_name_left + slot_h : 2 * (baseline - zero.ofs_y) - zero.box_h;
    // The items' words put their digits on that line; their baseline follows from the digits.
    const int item_baseline = (middle2 + zero.box_h) / 2 + zero.ofs_y;
    auto gaps = header_bar::gaps(zero.box_h);
    // The dial is as large as a round icon (clock-outline) of the icon font.
    int dial = lv_font_get_glyph_dsc(header_icon_font, &dial_glyph, 0xF0150, 0) && dial_glyph.box_h ? dial_glyph.box_h : zero.box_h * 3 / 2;

    struct Part { size_t item = 0; uint32_t icon = 0; int icon_left = 0, icon_w = 0, text_left = 0, text_w = 0, width = 0; bool dial = false; std::string text; };
    std::array<Part, header_bar::MAX_ITEMS> parts;
    std::array<int, header_bar::MAX_ITEMS> widths{};
    size_t count = 0;
    for (size_t i = 0; i < bar.count; ++i) {
      const auto &item = bar.items[i];
      using header_bar::Kind;
      if ((item.kind == Kind::text || item.kind == Kind::ago) && !live) continue;
      Part p;
      p.item = i;
      if (item.kind == Kind::analog) { p.dial = true; p.width = dial; }
      else {
        p.text = item.kind == Kind::clock ? (now.is_valid() ? screen_text::clock_text(hhmm(now), view.clock_24h) : std::string("--:--"))
               : item.kind == Kind::date ? (now.is_valid() ? header_bar::date_text(now.day_of_week, now.day_of_month, now.month) : std::string("—"))
               : item.kind == Kind::ago ? header_bar::ago_text(item.epoch, view.epoch) : item.text;
        lv_font_glyph_dsc_t g;
        if (item.icon && lv_font_get_glyph_dsc(header_icon_font, &g, item.icon, 0) && g.box_w) { p.icon = item.icon; p.icon_left = g.ofs_x; p.icon_w = g.box_w; }
        auto ink = text_ink(header_text_font, p.text);
        p.text_left = ink.left;
        p.text_w = std::max(0, ink.right - ink.left);
        p.width = p.icon_w + (p.icon && p.text_w ? gaps.icon : 0) + p.text_w;
      }
      if (!p.width) continue;
      widths[count] = p.width;
      parts[count++] = p;
    }
    // The home key at the left, before the name (firmware 0.2.100+). It stands where the name starts, the name moves
    // behind it, and the items on the right keep their space: only the name gives room.
    left = header_name_left;
    // The name may already stand behind the key from the last draw: the room is measured from the profile's own margin.
    width = std::max(0, page_w + static_cast<int>(lv_obj_get_style_x(time_label, LV_PART_MAIN)) - left);
    bool home_on = false, mark_on = false;
    const bool back = view.leading == Leading::back;
    const bool draw_mark = header_home_mark && !back;
    const uint32_t leading_glyph = back ? 0xF0141 : HOME_GLYPH;
    const lv_font_t *leading_font = back && surface.back_font ? surface.back_font : header_icon_font;
    lv_font_glyph_dsc_t leading{};
    if (view.leading != Leading::none && slot_w && slot_h &&
        (draw_mark || (lv_font_get_glyph_dsc(leading_font, &leading, leading_glyph, 0) && leading.box_w))) {
      // The key fills its slot from the bar's top margin down; the name's capitals are centred on it.
      const int ink_bottom = header_name_left + slot_h;
      if (draw_mark) {
        lv_obj_set_pos(header_home_mark, left, ink_bottom - slot_h);
        mark_on = true;
      } else {
        const int ink_top = ink_bottom - leading.box_h;
        // Its own font, or the bar's; without either LVGL draws the missing-glyph box.
        set_font(header_home_icon, leading_font);
        label(header_home_icon, tile_icon::utf8(leading_glyph));
        // Back replaces Home inside the same slot. Keep the title and touch
        // target fixed even though a chevron is naturally narrower than the mark.
        lv_obj_set_pos(header_home_icon, left + (slot_w - leading.box_w) / 2 - leading.ofs_x,
                       ink_top - ((leading_font->line_height - leading_font->base_line) - leading.box_h - leading.ofs_y));
      }
      // The finger gets the whole height of the bar and a little air either side of the key, so a tap near the
      // key is a tap on it; the key itself is only a couple of dozen pixels.
      const int pad = gaps.item / 2;
      // The band above the tiles, which the board states as the grid's own y; without it the name's line.
      const int band = tile_grid && lv_obj_get_y(tile_grid) > 0 ? lv_obj_get_y(tile_grid) : baseline + name_font->line_height;
      lv_obj_set_pos(header_home_tap, std::max(0, left - pad), 0);
      lv_obj_set_size(header_home_tap, slot_w + 2 * pad, band);
      // The same air on both sides of the key: the margin the board keeps from the edge of the glass stands between
      // the key and the name as well, measured ink to ink like every other gap in this bar.
      const int shift = slot_w + header_name_left;
      left += shift;
      width -= shift;
      home_on = true;
    }
    set_visible(header_home_icon, home_on && !mark_on);
    if (header_home_mark) set_visible(header_home_mark, mark_on);
    set_visible(header_home_tap, home_on);
    // The name's own left bearing, so the gap to the key is the gap the bar draws everywhere else.
    lv_obj_set_x(room_label, home_on ? left - text_ink(name_font, header_name.c_str()).left : left);
    lv_point_t name_size;
    lv_text_get_size(&name_size, header_name.c_str(), name_font, 0, 0, LV_COORD_MAX, LV_TEXT_FLAG_EXPAND);
    auto placement = header_bar::place(widths.data(), count, gaps, width, name_size.x);
    lv_obj_set_width(room_label, std::max(1, std::min<int>(name_size.x, placement.name_room)));
    lv_obj_set_height(room_label, lv_font_get_line_height(name_font));

    std::array<bool, header_bar::MAX_ITEMS> icon_on{}, text_on{};
    bool dial_on = false;
    for (size_t k = placement.first; k < count; ++k) {
      const auto &p = parts[k];
      auto &slot = header_slots[k];
      int x = left + placement.x[k];
      if (p.dial) {
        int top = (middle2 - dial) / 2, stroke = std::max(1, (dial + 5) / 10), hand = std::max(1, (dial * 75 + 500) / 1000);
        lv_obj_set_pos(header_ring, x, top);
        lv_obj_set_size(header_ring, dial, dial);
        if (lv_obj_get_style_border_width(header_ring, LV_PART_MAIN) != stroke) lv_obj_set_style_border_width(header_ring, stroke, 0);
        int minute = now.is_valid() ? now.hour * 60 + now.minute : 0;
        int key = ((minute * 1024 + x) * 1024 + top) * 64 + dial;
        if (key != header_dial_key) {
          header_dial_key = key;
          float centre = dial / 2.0f, hour_angle = (minute % 720) * 3.14159265f / 360, minute_angle = (minute % 60) * 3.14159265f / 30;
          header_points[0] = header_points[2] = {(lv_value_precise_t)centre, (lv_value_precise_t)centre};
          header_points[1] = {(lv_value_precise_t)(centre + 0.24f * dial * sinf(hour_angle)), (lv_value_precise_t)(centre - 0.24f * dial * cosf(hour_angle))};
          header_points[3] = {(lv_value_precise_t)(centre + 0.34f * dial * sinf(minute_angle)), (lv_value_precise_t)(centre - 0.34f * dial * cosf(minute_angle))};
          for (size_t h = 0; h < header_hands.size(); ++h) {
            lv_line_set_points(header_hands[h], header_points + 2 * h, 2);
            lv_obj_set_pos(header_hands[h], x, top);
            set_line_width(header_hands[h], hand);
          }
        }
        dial_on = true;
        continue;
      }
      if (p.icon) {
        lv_font_glyph_dsc_t g;
        lv_font_get_glyph_dsc(header_icon_font, &g, p.icon, 0);
        label(slot.icon, tile_icon::utf8(p.icon));
        // LVGL draws a glyph's ink from (line_height - base_line) - box_h - ofs_y below the label top.
        int ink_top = (middle2 - g.box_h) / 2;
        lv_obj_set_pos(slot.icon, x - g.ofs_x, ink_top - ((header_icon_font->line_height - header_icon_font->base_line) - g.box_h - g.ofs_y));
        const auto &item = bar.items[p.item];
        // The words, icons and dial of the top bar take the slate paint; an item's own colour sits on top of it.
        const uint32_t color = item.has_color ? theme::foreground(item.color) : 0;
        if (slot.own != item.has_color || slot.icon_color != color) {
          if (item.has_color) lv_obj_set_style_text_color(slot.icon, lv_color_hex(color), 0);
          else lv_obj_remove_local_style_prop(slot.icon, LV_STYLE_TEXT_COLOR, 0);
          slot.own = item.has_color;
          slot.icon_color = color;
        }
        icon_on[k] = true;
        x += p.icon_w + (p.text_w ? gaps.icon : 0);
      }
      if (p.text_w) {
        label(slot.text, p.text);
        lv_obj_set_pos(slot.text, x - p.text_left, item_baseline - (header_text_font->line_height - header_text_font->base_line));
        text_on[k] = true;
      }
    }
    for (size_t k = 0; k < header_slots.size(); ++k) { set_visible(header_slots[k].icon, icon_on[k]); set_visible(header_slots[k].text, text_on[k]); }
    set_visible(header_ring, dial_on);
    for (auto *hand : header_hands) set_visible(hand, dial_on);
  }
};
}  // namespace page_header
