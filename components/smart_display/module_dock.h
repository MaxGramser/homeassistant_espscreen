// The dock (module dock, tier full; docs/MODULES.md). Up from the bottom edge opens a drawer along
// the bottom of the glass with every page as a small picture and its name under it, two rows of them; a tap on one
// goes there, a tap above the drawer or a drag down closes it. A lite screen goes home on that swipe, as it always
// did, and compiles none of this.
//
// Each direction has one meaning: up and down open and close the drawer, sideways leafs through the pages when they
// do not all fit, one drawer's width at a time with a dot for each. The pictures are as large as the glass allows:
// all pages side by side where they fit at a readable size (a ten-inch glass holds eight), fewer and leafing on a
// small one. The drawer rides on the finger as an iOS sheet does, and only the drawer moves: no scale, no fade, and the
// dim behind it changes in one step once it stands open (dim), so the software renderer draws the drawer's own area
// for each frame of the way and not the whole glass.
//
// The pictures are drawn from the model, not from the cards: a kept page is drawn only while it is on the glass
// (docs/KEPT_PAGES.md), so a page's picture is its grid, each tile a rounded block in the colour its tile has now.
// Included by runtime_tiles.h where the touch code needs it. ESPHome also puts every header of the component into
// main.cpp on its own: there the site is not defined and this file is empty.
#if defined(SD_MOD_DOCK) && defined(SMART_DISPLAY_MODULE_SITE) && !defined(SMART_DISPLAY_MODULE_DOCK)
#define SMART_DISPLAY_MODULE_DOCK
namespace dock {
using namespace runtime_tiles;

inline lv_obj_t *root = nullptr;
// The drawer on its way out: it slides down, then goes. A new swipe up meanwhile deletes it at once.
inline lv_obj_t *leaving = nullptr;
inline lv_obj_t *drawer = nullptr, *strip = nullptr, *dots = nullptr;
inline int drawer_h = 0, views = 1, glass_w = 0, below = 0;

constexpr uint32_t RISE_MS = 260, LEAVE_MS = 200, BACK_MS = 200;
// After a finger let go of a drawer it carried up: the rest of the way, at most this long for the whole drawer.
constexpr uint32_t SETTLE_MS = 260;
constexpr lv_opa_t DIM = LV_OPA_50;

inline bool open() { return root != nullptr; }

// While the drawer moves only the drawer is drawn: the dim behind it is a full-glass layer, and a dim that changed on
// every frame had the software renderer draw the whole glass, every tile under it, for every frame of the way. So the
// glass dims in one step once the drawer stands open, and clears in one step before it moves again.
inline void dim(bool on) {
  if (!root) return;
  const lv_opa_t opa = on ? DIM : LV_OPA_TRANSP;
  if (lv_obj_get_style_bg_opa(root, LV_PART_MAIN) != opa) lv_obj_set_style_bg_opa(root, opa, 0);
}
inline void settled(lv_anim_t *) { dim(true); }
inline void set_rise(void *o, int32_t v) { lv_obj_set_style_translate_y(static_cast<lv_obj_t *>(o), v, 0); }
inline void animate(lv_obj_t *o, lv_anim_exec_xcb_t exec, int32_t from, int32_t to, uint32_t ms, uint32_t delay,
                    lv_anim_path_cb_t path, lv_anim_completed_cb_t done = nullptr) {
  lv_anim_t a;
  lv_anim_init(&a);
  lv_anim_set_var(&a, o);
  lv_anim_set_exec_cb(&a, exec);
  lv_anim_set_values(&a, from, to);
  lv_anim_set_duration(&a, ms);
  lv_anim_set_delay(&a, delay);
  lv_anim_set_path_cb(&a, path);
  if (done) lv_anim_set_completed_cb(&a, done);
  exec(o, from);
  lv_anim_start(&a);
}
// The drawer is off the glass: its Dock goes.
inline void gone(lv_anim_t *a) {
  auto *o = lv_obj_get_parent(static_cast<lv_obj_t *>(a->var));
  if (o == leaving) leaving = nullptr;
  lv_obj_delete_async(o);
}
inline void drop_leaving() {
  if (!leaving) return;
  lv_anim_delete(leaving, nullptr);
  if (auto *d = lv_obj_get_child(leaving, 0)) lv_anim_delete(d, nullptr);
  lv_obj_delete(leaving);
  leaving = nullptr;
}
// The finger that opened the Dock from the bottom edge carries the drawer for the rest of its touch: the drawer's top
// stays under it, as a phone's sheet does, instead of rising by itself once the swipe was recognised. Fed from the
// touchscreen's own reports (touch_input::edge_move), not from LVGL, which waits for the release after an edge swipe.
struct Lift {
  bool on = false;
  int start_y = 0, last_y = 0, speed = 0;  // speed in px a second, down positive
  uint32_t last_ms = 0;
};
inline Lift lift;
inline bool lifting() { return lift.on && drawer; }

// Down and off the glass from wherever the drawer is now (a drag may have taken it part of the way): the dim goes at
// once, then only the drawer moves.
inline void close() {
  lift.on = false;
  if (!root) return;
  drop_leaving();
  dim(false);
  leaving = root;
  root = nullptr;
  lv_obj_remove_flag(leaving, LV_OBJ_FLAG_CLICKABLE);
  if (drawer) {
    lv_anim_delete(drawer, nullptr);
    lv_obj_remove_flag(drawer, LV_OBJ_FLAG_CLICKABLE);
    animate(drawer, set_rise, lv_obj_get_style_translate_y(drawer, LV_PART_MAIN), drawer_h, LEAVE_MS, 0, lv_anim_path_ease_in, gone);
  } else {
    lv_obj_delete_async(leaving);
    leaving = nullptr;
  }
  drawer = strip = dots = nullptr;
}

// A finger that moves down over the drawer takes it along; let go past a quarter of its height, or with a flick, it
// closes, else it settles back. Sideways is the strip's, which LVGL scrolls; a drag never picks a page.
struct Drag {
  bool down = false, dragging = false, decided = false;
  int start_x = 0, start_y = 0, last_y = 0, offset = 0, speed = 0;
  uint32_t last_ms = 0;
};
inline Drag drag;
inline lv_point_t point() {
  lv_point_t p{0, 0};
  if (auto *indev = lv_indev_active()) lv_indev_get_point(indev, &p);
  return p;
}
inline void follow(int offset) {
  drag.offset = std::max(0, offset);
  // The dim stays as it is while the finger has the drawer: only the drawer is drawn again (dim).
  lv_obj_set_style_translate_y(drawer, drag.offset, 0);
}
inline void on_drag(lv_event_t *e) {
  if (!root || !drawer) return;
  const auto code = lv_event_get_code(e);
  const lv_point_t p = point();
  if (code == LV_EVENT_PRESSED) {
    drag = Drag{};
    drag.down = true;
    drag.start_x = p.x; drag.start_y = drag.last_y = p.y;
    drag.last_ms = lv_tick_get();
    return;
  }
  if (!drag.down) return;
  if (code == LV_EVENT_PRESSING) {
    const int dx = p.x - drag.start_x, dy = p.y - drag.start_y;
    if (!drag.decided && (std::abs(dx) > ui::mm(2) || std::abs(dy) > ui::mm(2))) {
      drag.decided = true;
      // Down, more than sideways, and the strip not already scrolling: the drawer's.
      auto *indev = lv_indev_active();
      drag.dragging = dy > 0 && dy > std::abs(dx) && !(indev && lv_indev_get_scroll_obj(indev));
      if (drag.dragging) {
        lv_anim_delete(drawer, nullptr);
        if (strip) lv_obj_remove_flag(strip, LV_OBJ_FLAG_SCROLLABLE);
      }
    }
    if (drag.dragging) {
      const uint32_t now = lv_tick_get();
      if (now != drag.last_ms) drag.speed = (p.y - drag.last_y) * 1000 / static_cast<int>(now - drag.last_ms);
      drag.last_y = p.y; drag.last_ms = now;
      follow(dy);
    }
    return;
  }
  if (code == LV_EVENT_RELEASED || code == LV_EVENT_PRESS_LOST) {
    drag.down = false;
    if (!drag.dragging) return;
    // Where the finger let go counts too: a panel read seldom may have reported only the start of the drag.
    if (p.y - drag.start_y > drag.offset) follow(p.y - drag.start_y);
    if (strip) lv_obj_add_flag(strip, LV_OBJ_FLAG_SCROLLABLE);
    // A flick is some 15 cm a second, whatever the glass.
    if (drag.offset > drawer_h / 4 || drag.speed > ui::mm(150)) {
      ESP_LOGI("touch", "dock: dragged away");
      close();
      return;
    }
    ESP_LOGI("touch", "dock: drag of %d px back (%d px/s)", drag.offset, drag.speed);
    animate(drawer, set_rise, drag.offset, 0, BACK_MS, 0, lv_anim_path_ease_out);
  }
}

// The drawer's top at the finger: as much of it shows as the finger has come up from where it touched. Past fully open
// it gives a third of the way, no further than the part below the glass reaches.
inline void lift_to(int y) {
  const int rest = drawer_h - (lift.start_y - y);
  const int rise = rest >= 0 ? std::min(rest, drawer_h) : -std::min(below, -rest / 3);
  lv_obj_set_style_translate_y(drawer, rise, 0);
}
inline void lift_move(int y) {
  if (!lifting()) return;
  const uint32_t now = lv_tick_get();
  // Two reports in the same millisecond say nothing about speed; half of the last keeps one quick report from
  // deciding alone.
  if (now != lift.last_ms) lift.speed = (lift.speed + (y - lift.last_y) * 1000 / static_cast<int>(now - lift.last_ms)) / 2;
  lift.last_y = y; lift.last_ms = now;
  lift_to(y);
}
// Let go: a flick up opens it, a flick down closes it, and otherwise more than a quarter in view opens it. The rest of
// the way takes as long as the part left, so a drawer let go nearly open does not crawl the last millimetres.
inline void lift_release() {
  if (!lifting()) { lift.on = false; return; }
  lift.on = false;
  const int rise = lv_obj_get_style_translate_y(drawer, LV_PART_MAIN), flick = ui::mm(50);
  if (lift.speed > flick || (lift.speed > -flick && rise > drawer_h * 3 / 4)) {
    ESP_LOGI("touch", "dock: let go at %d of %d px (%d px/s), closes", drawer_h - rise, drawer_h, lift.speed);
    close();
    return;
  }
  ESP_LOGI("touch", "dock: let go at %d of %d px (%d px/s), opens", drawer_h - rise, drawer_h, lift.speed);
  const uint32_t ms = std::max<uint32_t>(120, SETTLE_MS * static_cast<uint32_t>(std::abs(rise)) / std::max(1, drawer_h));
  animate(drawer, set_rise, rise, 0, ms, 0, lv_anim_path_ease_out, settled);
}

inline void pick(lv_event_t *e) {
  if (drag.dragging) return;
  const int page = static_cast<int>(reinterpret_cast<intptr_t>(lv_event_get_user_data(e)));
  ESP_LOGI("touch", "dock: page %d", page + 1);
  // The page goes on the glass above the drawer, and the drawer slides off it.
  go_to_page(page, false);
  close();
}
inline void backdrop(lv_event_t *e) {
  if (lv_event_get_target(e) == lv_event_get_current_target(e)) close();
}
// A dot per view, the one in view a short bar, centred under the pages (by hand: this LVGL has no flex layout).
inline void paint_dots(int view) {
  if (!dots) return;
  const int n = static_cast<int>(lv_obj_get_child_count(dots)), dot = ui::mm(1) + ui::mm(1) / 2, bar = ui::mm(4);
  int x = (glass_w - (n - 1) * (dot + dot) - bar) / 2;
  for (int i = 0; i < n; ++i) {
    auto *d = lv_obj_get_child(dots, i);
    const bool on = i == view;
    lv_obj_set_pos(d, x, 0);
    lv_obj_set_width(d, on ? bar : dot);
    lv_obj_set_style_bg_color(d, theme::color(on ? theme::INK : theme::TRACK), 0);
    x += (on ? bar : dot) + dot;
  }
}
inline void strip_scrolled(lv_event_t *e) {
  auto *s = static_cast<lv_obj_t *>(lv_event_get_target(e));
  const int w = lv_obj_get_width(s);
  if (w > 0) paint_dots((lv_obj_get_scroll_x(s) + w / 2) / w);
}

inline lv_obj_t *block(lv_obj_t *parent, int x, int y, int w, int h, int radius, uint32_t colour) {
  auto *o = lv_obj_create(parent);
  lv_obj_remove_style_all(o);
  lv_obj_remove_flag(o, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_pos(o, x, y);
  lv_obj_set_size(o, std::max(1, w), std::max(1, h));
  lv_obj_set_style_radius(o, radius, 0);
  lv_obj_set_style_bg_opa(o, LV_OPA_COVER, 0);
  lv_obj_set_style_bg_color(o, theme::rgb(colour), 0);
  return o;
}

// One page in small, quiet: the top bar as one thin stroke, then its tiles on the grid with room between them, a tile
// that is off a plain card as on the glass and one that is on a pale wash of its colour. `here` rings the page on the
// glass in the accent.
inline void picture(lv_obj_t *parent, int page, int w, int h, const std::array<Placement, TILES_MAX> &placement, bool here) {
  auto *glass = block(parent, 0, 0, w, h, std::max(3, w / 14), theme::hex(theme::PAGE));
  const int margin = std::max(3, w * 6 / 100), gap = std::max(2, w * 4 / 100), bar = std::max(4, h * 10 / 100);
  block(glass, margin, margin + bar / 3, w / 4, std::max(1, bar / 4), bar, theme::hex(theme::TRACK));
  const int top = margin + bar, cols = static_cast<int>(grid.columns), rows = static_cast<int>(grid.rows);
  const int cell_w = (w - 2 * margin - (cols - 1) * gap) / cols, cell_h = (h - top - margin - (rows - 1) * gap) / rows;
  const int radius = std::max(2, std::min(cell_w, cell_h) / 4);
  for (size_t i = 0; i < model.count && i < grid.max_tiles(); ++i) {
    if (placement[i].page != page) continue;
    const auto &t = model.tiles[i];
    const int col = placement[i].slot % cols, row = placement[i].slot / cols;
    const int cs = static_cast<int>(t.column_span()), rs = static_cast<int>(t.row_span());
    const uint32_t colour = t.active() ? theme::mix(tile_controls::accent(t), theme::hex(theme::CARD), 70) : theme::hex(theme::CARD);
    block(glass, margin + col * (cell_w + gap), top + row * (cell_h + gap), cs * cell_w + (cs - 1) * gap,
          rs * cell_h + (rs - 1) * gap, radius, colour);
  }
  // The ring lies over the picture as a layer of its own: a border on the picture itself would move its tiles in by
  // the border's width (LVGL places children inside it).
  if (here) {
    auto *ring = block(glass, 0, 0, w, h, std::max(3, w / 14), theme::hex(theme::ACCENT));
    lv_obj_add_flag(ring, LV_OBJ_FLAG_IGNORE_LAYOUT);
    lv_obj_set_style_bg_opa(ring, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(ring, std::max(2, ui::px(2)), 0);
    lv_obj_set_style_border_color(ring, theme::color(theme::ACCENT), 0);
  }
}

// A page with an icon of its own shows that instead of its picture: the icon in the middle of the same quiet card, the
// tile icon font where the card has room for it, the top bar's smaller one where it has not.
inline void icon_picture(lv_obj_t *parent, uint32_t icon, int w, int h, bool here) {
  auto *glass = block(parent, 0, 0, w, h, std::max(3, w / 14), theme::hex(theme::PAGE));
  const lv_font_t *font = tile_icon_font();
  if (!font || lv_font_get_line_height(font) > h * 7 / 10) font = mini_icon_font;
  auto *glyph = lv_label_create(glass);
  lv_label_set_text(glyph, tile_icon::utf8(icon).c_str());
  lv_obj_set_style_text_font(glyph, font, 0);
  lv_obj_set_style_text_color(glyph, theme::color(here ? theme::ACCENT : theme::SLATE), 0);
  lv_obj_center(glyph);
  if (here) {
    auto *ring = block(glass, 0, 0, w, h, std::max(3, w / 14), theme::hex(theme::ACCENT));
    lv_obj_add_flag(ring, LV_OBJ_FLAG_IGNORE_LAYOUT);
    lv_obj_set_style_bg_opa(ring, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(ring, std::max(2, ui::px(2)), 0);
    lv_obj_set_style_border_color(ring, theme::color(theme::ACCENT), 0);
  }
}

inline bool build(bool finger) {
  drop_leaving();
  root = lv_obj_create(lv_layer_top());
  lv_obj_remove_style_all(root);
  lv_obj_remove_flag(root, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_size(root, lv_pct(100), lv_pct(100));
  lv_obj_set_style_bg_color(root, theme::color(theme::SCRIM), 0);
  lv_obj_add_event_cb(root, backdrop, LV_EVENT_CLICKED, nullptr);

  const int glass = overlay_card::screen_width(), H = overlay_card::screen_height();
  // A small drawer, not a sheet: at most 12 cm wide, in the middle of the bottom edge. A 4-inch glass is narrower
  // than that, so there it spans the glass.
  const int W = std::min(glass, ui::mm(120));
  glass_w = W;
  // The pages it shows: every page of the swipe (a detail page, left out of it, is reached by its tile) that its
  // page settings leave in the Dock. An app from before the page settings sends no records: then every page.
  std::vector<int> shown;
  const auto &records = model.page_data.records;
  for (int i = 0; i < static_cast<int>(page_count()); ++i)
    if (static_cast<size_t>(i) >= records.size() || (!records[i].excluded && records[i].dock)) shown.push_back(i);
  const int pages = static_cast<int>(shown.size());
  ESP_LOGI("dock", "shows %d of %u pages", pages, page_count());
  // Every page left out: nothing to show, and the swipe goes home as it does on a lite screen.
  if (pages == 0) {
    lv_obj_delete(root);
    root = nullptr;
    return false;
  }
  const int pad = ui::mm(4), gap = ui::mm(3), inset = ui::mm(1) + ui::mm(1) / 2, line = lv_font_get_line_height(small_font);
  const int grab = ui::mm(6), dots_h = ui::mm(4), room_w = W - 2 * pad;
  // The columns of one drawer's width: every page in two rows when each picture keeps at least 13 mm (no more columns
  // than that), each picture at most 32 mm, and so many that the drawer stays within half the glass.
  auto item_w_of = [&](int cols) { return (room_w - (cols - 1) * gap) / cols; };
  // A picture has the glass's proportions, whatever the drawer's width.
  auto item_h_of = [&](int cols) { return inset + (item_w_of(cols) - 2 * inset) * H / glass + ui::mm(1) + line + inset; };
  // One row when every page fits in it, two otherwise; the dots when they do not all fit in two.
  auto rows_of = [&](int cols) { return pages > cols ? 2 : 1; };
  auto drawer_of = [&](int cols) {
    return grab + rows_of(cols) * item_h_of(cols) + (rows_of(cols) - 1) * gap + (pages > 2 * cols ? dots_h : 0) + pad;
  };
  const int most = std::max(1, (room_w + gap) / (ui::mm(13) + gap));
  // No picture wider than 32 mm, so a few pages stand side by side in one row instead of two rows of large ones.
  const int fewest = (room_w + gap + ui::mm(32) + gap - 1) / (ui::mm(32) + gap);
  int cols = std::min(std::max({1, (pages + 1) / 2, fewest}), most);
  while (cols < most && drawer_of(cols) > H / 2) ++cols;
  const int per_view = 2 * cols;
  views = (pages + per_view - 1) / per_view;
  const int item_w = item_w_of(cols), item_h = item_h_of(cols), pic_w = item_w - 2 * inset, pic_h = pic_w * H / glass;
  const int rows = rows_of(cols), band = rows * item_h + (rows - 1) * gap;
  drawer_h = drawer_of(cols);
  // The drawer reaches below the glass by its corner and the overshoot's way, so the bottom never shows a gap.
  below = std::max(ui::mm(5), drawer_h / 8);

  drawer = lv_obj_create(root);
  lv_obj_remove_style_all(drawer);
  lv_obj_remove_flag(drawer, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_pos(drawer, (glass - W) / 2, H - drawer_h);
  lv_obj_set_size(drawer, W, drawer_h + below);
  lv_obj_set_style_radius(drawer, ui::mm(6), 0);
  lv_obj_set_style_bg_opa(drawer, LV_OPA_COVER, 0);
  lv_obj_set_style_bg_color(drawer, theme::color(theme::RAISED), 0);
  for (auto code : {LV_EVENT_PRESSED, LV_EVENT_PRESSING, LV_EVENT_RELEASED, LV_EVENT_PRESS_LOST})
    lv_obj_add_event_cb(drawer, on_drag, code, nullptr);
  block(drawer, (W - ui::mm(10)) / 2, (grab - ui::mm(1)) / 2, ui::mm(10), ui::mm(1), LV_RADIUS_CIRCLE, theme::hex(theme::TRACK));

  strip = lv_obj_create(drawer);
  lv_obj_remove_style_all(strip);
  lv_obj_add_flag(strip, LV_OBJ_FLAG_EVENT_BUBBLE);
  lv_obj_set_pos(strip, 0, grab);
  lv_obj_set_size(strip, W, band);
  lv_obj_set_scroll_dir(strip, LV_DIR_HOR);
  lv_obj_set_scroll_snap_x(strip, LV_SCROLL_SNAP_START);
  lv_obj_add_flag(strip, LV_OBJ_FLAG_SCROLL_ONE);
  lv_obj_set_scrollbar_mode(strip, LV_SCROLLBAR_MODE_OFF);
  if (views <= 1) lv_obj_remove_flag(strip, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_add_event_cb(strip, strip_scrolled, LV_EVENT_SCROLL_END, nullptr);

  std::array<Placement, TILES_MAX> placement;
  place(model, placement);
  const int current = shown_page ? *shown_page : 0;
  // Where the page on the glass stands among them; a page the Dock leaves out opens it at the start.
  const int at = static_cast<int>(std::find(shown.begin(), shown.end(), current) - shown.begin()) % std::max(1, pages);
  // Each view is a drawer's width, so a sideways swipe stops at the next one; its pages fill it row by row.
  for (int v = 0; v < views; ++v) {
    auto *view = lv_obj_create(strip);
    lv_obj_remove_style_all(view);
    lv_obj_remove_flag(view, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_flag(view, LV_OBJ_FLAG_EVENT_BUBBLE);
    lv_obj_add_flag(view, LV_OBJ_FLAG_SNAPPABLE);
    lv_obj_set_pos(view, v * W, 0);
    lv_obj_set_size(view, W, band);
    for (int k = 0; k < per_view && v * per_view + k < pages; ++k) {
      const int page = shown[v * per_view + k], col = k % cols, row = k / cols;
      auto *item = lv_obj_create(view);
      lv_obj_remove_style_all(item);
      lv_obj_remove_flag(item, LV_OBJ_FLAG_SCROLLABLE);
      lv_obj_add_flag(item, LV_OBJ_FLAG_EVENT_BUBBLE);
      lv_obj_set_pos(item, pad + col * (item_w + gap), row * (item_h + gap));
      lv_obj_set_size(item, item_w, item_h);
      lv_obj_set_style_radius(item, ui::mm(3), 0);
      // Under a finger the page dims a little; the page on the glass has its ring and its name in the accent.
      lv_obj_set_style_opa(item, LV_OPA_60, LV_STATE_PRESSED);
      lv_obj_add_event_cb(item, pick, LV_EVENT_CLICKED, reinterpret_cast<void *>(static_cast<intptr_t>(page)));
      auto *pic = lv_obj_create(item);
      lv_obj_remove_style_all(pic);
      lv_obj_remove_flag(pic, LV_OBJ_FLAG_CLICKABLE);
      lv_obj_remove_flag(pic, LV_OBJ_FLAG_SCROLLABLE);
      lv_obj_set_pos(pic, inset, inset);
      lv_obj_set_size(pic, pic_w, pic_h);
      const uint32_t icon = static_cast<size_t>(page) < records.size() ? records[page].icon : 0;
      if (icon) icon_picture(pic, icon, pic_w, pic_h, page == current);
      else picture(pic, page, pic_w, pic_h, placement, page == current);
      auto *name = lv_label_create(item);
      lv_label_set_text(name, model.title_of(page).c_str());
      lv_label_set_long_mode(name, LV_LABEL_LONG_MODE_DOTS);
      // One line, its end dotted: LVGL dots a label only when its height is fixed.
      lv_obj_set_size(name, item_w - 2 * inset, line);
      lv_obj_set_style_text_align(name, LV_TEXT_ALIGN_CENTER, 0);
      lv_obj_set_style_text_font(name, small_font, 0);
      lv_obj_set_style_text_color(name, theme::color(page == current ? theme::ACCENT : theme::INK), 0);
      lv_obj_set_pos(name, inset, inset + pic_h + ui::mm(1));
    }
  }
  const int first_view = std::min(at / per_view, std::max(0, views - 1));
  if (views > 1) {
    dots = lv_obj_create(drawer);
    lv_obj_remove_style_all(dots);
    lv_obj_remove_flag(dots, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_flag(dots, LV_OBJ_FLAG_EVENT_BUBBLE);
    lv_obj_set_size(dots, W, dots_h);
    lv_obj_set_pos(dots, 0, grab + band + (dots_h - ui::mm(1) - ui::mm(1) / 2) / 2);
    for (int v = 0; v < views; ++v) {
      auto *d = block(dots, 0, 0, ui::mm(1) + ui::mm(1) / 2, ui::mm(1) + ui::mm(1) / 2, LV_RADIUS_CIRCLE, theme::hex(theme::TRACK));
      lv_obj_add_flag(d, LV_OBJ_FLAG_EVENT_BUBBLE);
    }
    paint_dots(first_view);
    lv_obj_scroll_to_x(strip, first_view * W, LV_ANIM_OFF);
  }

  // In: only the drawer moves, its pages in place, and the glass dims once it stands open (dim). Under a finger the
  // drawer is where the finger is; without one (a tap on the page dots, ui_dock) it rises from the bottom edge.
  if (finger) {
    lift_to(lift.last_y);
    return true;
  }
  animate(drawer, set_rise, drawer_h, 0, RISE_MS, 0, lv_anim_path_ease_out, settled);
  return true;
}

inline bool show(bool finger, int start_y, int y, uint32_t pressed_ms);
// The page dots in the middle of the tile pages' bar are a third key: a tap there opens the Dock. It lies over the
// inner ends of the two halves (the last child is hit first), so the chevrons keep the outer part of the bar and the
// middle is the Dock's, as wide as the dots' room (PAGE_NUMBER_W), whichever way the glass hangs.
inline void dots_open(lv_obj_t *number) {
  if (!number) return;
  lv_obj_add_flag(number, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_move_foreground(number);
  lv_obj_add_style(number, theme::style(theme::Paint::page_pressed), LV_STATE_PRESSED);
  lv_obj_set_style_bg_opa(number, LV_OPA_COVER, LV_STATE_PRESSED);
  lv_obj_set_style_radius(number, LV_RADIUS_CIRCLE, 0);
  lv_obj_add_event_cb(number, [](lv_event_t *) {
    if (!screen_input::touch_guard.accept_repeat(esphome::millis(), 13) || !navigation_ready()) return;
    ESP_LOGI("touch", "page dots: dock");
    show(false, 0, 0, 0);
  }, LV_EVENT_CLICKED, nullptr);
}

// Whether the Dock opened: with every page left out of it, the caller goes home instead. `finger` when a swipe up
// from the bottom edge opens it: the finger touched at `start_y` at `pressed_ms` and is at `y` now, and carries the
// drawer from there (lift_move, lift_release).
inline bool show(bool finger = false, int start_y = 0, int y = 0, uint32_t pressed_ms = 0) {
  static bool hooked = false;
  if (!hooked) {
    hooked = true;
    // Every card closing (go_home, the settings swipe, standby) takes the drawer with it, and while it is open the
    // screen counts as away, so "Back to page 1" closes it in time.
    screen_hooks::cards_closed().push_back(close);
    screen_hooks::away().push_back(open);
  }
  settings_screen::close();
  if (dismiss) dismiss();
  lift = Lift{};
  if (finger) {
    lift.on = true;
    lift.start_y = start_y;
    lift.last_y = y;
    lift.last_ms = lv_tick_get();
    // The way so far as the first speed: a quick swipe may be let go before the panel reports again.
    lift.speed = (y - start_y) * 1000 / std::max(1, static_cast<int>(lift.last_ms - pressed_ms));
  }
  if (build(finger)) return true;
  lift.on = false;
  return false;
}
}  // namespace dock
#endif
