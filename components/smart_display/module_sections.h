// Sections on a page (module sections, tier full; docs/PAGES.md "Sections", docs/MODULES.md): a block of cells with a
// title, an icon and a soft panel behind its tiles, and a short summary at the title's right end.
//
// What it knows: a page's blocks (page_protocol::Page::sections, read by page_receiver.cpp), the room a title takes
// (section_layout.h), the fonts and the grid's gap. What it does not know: which tiles are in a block (the add-on placed
// them in its cells), Home Assistant, the editor.
//
// The look (the study's C3 and its block model, 2026-11-15): the page's rows stay what they are, so no tile outside a
// section changes. The panel covers exactly the section's cells, the SECTION role, its corner the card's radius plus the
// padding. The title, its icon and the summary stand in the top of the panel; the room they take (the header: the
// title's top, its line and a gap) and the padding under the last row come out of the section's own tiles, shared
// evenly by its rows (section_layout::inside), and the cards at its sides keep the grid's gap as their margin. The
// title is the tile name's font and ink, its capitals as far from the panel's top as from its side; the icon (the small
// icon font) stands before it, centred on the capitals; the summary is the small grey font on the title's line, at the
// right. A section in contrast takes the page's opposite (SECTION_CONTRAST) and its words SECTION_CONTRAST_INK; its
// tiles keep their own cards, unless its tiles follow the contrast: then the whole section is a piece of the other look,
// its panel, its words and its cards (painted in the other look by render_slot, theme::Flip; what a card takes from the
// shared paints is set on it in the other look, follow()). The editor draws the same from boards.json's `section` metrics
// (tools/generate_board_shapes.py, web/src/model/sections.ts); tests/test_section_layout.cpp proves the arithmetic.
//
// The decorations of a page are made once, when the page is first placed (on the glass, or prepared off it), and kept:
// hidden while another page is on the glass and shown with their page, so a page switch stays a switch
// (docs/KEPT_PAGES.md). They are made again when the sections change; a new layout or grid lets them go (forget), a
// change of look repaints them (restyle).
// Included by runtime_tiles.h at the module site; ESPHome also puts every header of the component into main.cpp on its
// own: there the site is not defined and this file is empty.
#if defined(SD_MOD_SECTIONS) && defined(SMART_DISPLAY_MODULE_SITE) && !defined(SMART_DISPLAY_MODULE_SECTIONS)
#define SMART_DISPLAY_MODULE_SECTIONS
namespace sections {
using namespace runtime_tiles;

struct Drawn { lv_obj_t *panel = nullptr, *icon = nullptr, *title = nullptr, *summary = nullptr; bool contrast = false, follow = false; };
inline std::array<std::vector<Drawn>, page_protocol::MAX_PAGES> drawn{};
// What each page's decorations were made from (signature): a page placed before its sections arrived, or placed again
// after a layout changed them, makes them anew.
inline std::array<uint32_t, page_protocol::MAX_PAGES> made{};
inline int shown = -1;

inline const std::vector<section_layout::Section> &of(int page) {
  static const std::vector<section_layout::Section> none;
  return page >= 0 && size_t(page) < model.page_data.records.size() ? model.page_data.records[page].sections : none;
}
// The blocks, titles, icons and contrast of a page, folded into one number (FNV-1a); 0 never stands for any.
inline uint32_t signature(int page) {
  uint32_t h = 2166136261u;
  auto add = [&h](uint32_t v) { h = (h ^ v) * 16777619u; };
  for (const auto &s : of(page)) {
    add(s.column); add(s.row); add(s.columns); add(s.rows); add(s.icon); add(s.contrast); add(s.follow);
    for (unsigned char c : s.title) add(c);
    add(0xFF);
  }
  return h | 1;
}
// ---- The numbers: the grid's gap, a card's own padding and corner, and the title's font by its ink ----
inline int gap() { return tile_grid ? lv_obj_get_style_pad_row(tile_grid, LV_PART_MAIN) : ui::px(12); }
inline int tile_pad() {
  for (auto &w : widgets) if (w.tile) return lv_obj_get_style_pad_left(w.tile, LV_PART_MAIN);
  return ui::px(12);
}
inline int radius() {
  for (auto &w : widgets) if (w.tile) return lv_obj_get_style_radius(w.tile, LV_PART_MAIN);
  return ui::px(22);
}
inline int line_of(const lv_font_t *font) { return font ? lv_font_get_line_height(font) : ui::px(20); }
inline int ascent(const lv_font_t *font) { return font ? lv_font_get_line_height(font) - font->base_line : 0; }
// From the top of a font's line to the top of its capitals (the ink of an H), and the capitals' height.
inline int ink_top(const lv_font_t *font) {
  lv_font_glyph_dsc_t g;
  return font && lv_font_get_glyph_dsc(font, &g, 'H', 0) ? ascent(font) - (g.ofs_y + g.box_h) : 0;
}
inline int cap_height(const lv_font_t *font) {
  lv_font_glyph_dsc_t g;
  return font && lv_font_get_glyph_dsc(font, &g, 'H', 0) ? g.box_h : 0;
}
// From a block's side to its title: the panel's padding and a card's own, so the title stands over the cards' icons.
inline int inset() { return gap() + tile_pad(); }
// The top of the title's line from the panel's top: its capitals as far from the top as the inset.
inline int title_top() { return inset() - ink_top(label_font); }
// The room above the section's first row of tiles: the title's line and a gap under it.
inline int header() { return title_top() + line_of(label_font) + gap(); }

// ---- A card in its cell, with the room its section takes from it ----
// A margin, written only when it changes (a card of a kept page is placed again on every visit).
inline void margin(lv_obj_t *card, lv_style_prop_t prop, int32_t value) {
  if (lv_obj_get_style_prop(card, LV_PART_MAIN, prop).num == value) return;
  lv_style_value_t v;
  v.num = value;
  lv_obj_set_local_style_prop(card, prop, v, LV_PART_MAIN);
}
inline void place(lv_obj_t *card, int page, int32_t column, int32_t span_x, int32_t row, int32_t span_y) {
  set_cell(card, column, span_x, row, span_y);
  int32_t left = 0, right = 0, top = 0, bottom = 0;
  for (const auto &s : of(page)) {
    if (column < s.column || column + span_x > s.column + s.columns || row < s.row || row + span_y > s.row + s.rows) continue;
    const int g = gap();
    if (column == s.column) left = g;
    if (column + span_x == s.column + s.columns) right = g;
    const auto room = section_layout::inside(header(), g, s.rows, row - s.row, row + span_y - 1 - s.row);
    top = room.top;
    bottom = room.bottom;
    break;
  }
  margin(card, LV_STYLE_MARGIN_LEFT, left);
  margin(card, LV_STYLE_MARGIN_RIGHT, right);
  margin(card, LV_STYLE_MARGIN_TOP, top);
  margin(card, LV_STYLE_MARGIN_BOTTOM, bottom);
}

// ---- A card in a section whose tiles follow its contrast ----
// Whether the card in `slot` of the page being placed stands in such a section.
inline bool flips(const Widgets &w, size_t slot) {
  if (!w.tile || w.full || w.index >= model.count || slot >= grid.slots()) return false;
  const auto &t = model.tiles[w.index];
  const int32_t column = int32_t(slot % grid.columns), row = int32_t(slot / grid.columns), span_x = t.column_span(), span_y = t.row_span();
  for (const auto &s : of(applied_page))
    if (column >= s.column && column + span_x <= s.column + s.columns && row >= s.row && row + span_y <= s.row + s.rows) return s.follow;
  return false;
}
// What follow() set on a card, by card, so it goes again when the card is painted anew or shows another tile.
struct Override { lv_obj_t *obj; lv_style_prop_t prop; lv_style_selector_t part; };
inline std::vector<std::pair<lv_obj_t *, std::vector<Override>>> followed;
inline void collect(lv_obj_t *obj, std::vector<std::pair<Override, uint32_t>> &found) {
  static constexpr lv_style_prop_t PROPS[] = {LV_STYLE_BG_COLOR, LV_STYLE_BORDER_COLOR, LV_STYLE_TEXT_COLOR, LV_STYLE_LINE_COLOR, LV_STYLE_ARC_COLOR};
  static constexpr lv_part_t PARTS[] = {LV_PART_MAIN, LV_PART_INDICATOR, LV_PART_KNOB};
  for (auto part : PARTS)
    for (auto prop : PROPS) {
      lv_style_value_t mine;
      // What the code painted (in the other look already, under theme::Flip) is the card's own: left as it is.
      if (lv_obj_get_local_style_prop(obj, prop, &mine, part) == LV_STYLE_RES_FOUND) continue;
      if (prop == LV_STYLE_BG_COLOR && lv_obj_get_style_bg_opa(obj, part) == LV_OPA_TRANSP) continue;
      if (prop == LV_STYLE_BORDER_COLOR && lv_obj_get_style_border_width(obj, part) == 0) continue;
      const uint32_t now = theme::of(lv_obj_get_style_prop(obj, part, prop).color);
      const theme::Role role = theme::role_of(now);
      if (role == theme::ROLE_COUNT || theme::other(role) == now) continue;
      found.push_back({Override{obj, prop, part}, theme::other(role)});
    }
  for (uint32_t i = 0; i < lv_obj_get_child_count(obj); ++i) collect(lv_obj_get_child(obj, int32_t(i)), found);
}
inline bool following(lv_obj_t *card) {
  return std::any_of(followed.begin(), followed.end(), [card](const auto &entry) { return entry.first == card; });
}
// The card's colours that come from the shared paints, set on it in the other look (on), or given back (off).
inline void follow(lv_obj_t *card, bool on) {
  if (!card) return;
  auto it = std::find_if(followed.begin(), followed.end(), [card](const auto &entry) { return entry.first == card; });
  if (it != followed.end()) {
    for (const auto &o : it->second) if (lv_obj_is_valid(o.obj)) lv_obj_remove_local_style_prop(o.obj, o.prop, o.part);
    followed.erase(it);
  }
  if (!on) return;
  // Read every colour before any is set: a child's inherited text must not take its parent's new one for a paint.
  std::vector<std::pair<Override, uint32_t>> found;
  collect(card, found);
  std::vector<Override> set;
  set.reserve(found.size());
  for (const auto &[o, value] : found) {
    lv_style_value_t v;
    v.color = theme::rgb(value);
    lv_obj_set_local_style_prop(o.obj, o.prop, v, o.part);
    set.push_back(o);
  }
  followed.emplace_back(card, std::move(set));
}

// ---- The decorations ----
inline lv_obj_t *text(const std::string &value, const lv_font_t *font) {
  auto *l = lv_label_create(tile_grid);
  lv_label_set_text(l, value.c_str());
  lv_label_set_long_mode(l, LV_LABEL_LONG_MODE_DOTS);
  if (font) lv_obj_set_style_text_font(l, font, 0);
  lv_obj_remove_flag(l, LV_OBJ_FLAG_CLICKABLE);
  return l;
}
inline void utf8(uint32_t cp, char *out) {
  if (cp < 0x80) { out[0] = char(cp); out[1] = 0; }
  else if (cp < 0x800) { out[0] = char(0xC0 | cp >> 6); out[1] = char(0x80 | (cp & 0x3F)); out[2] = 0; }
  else if (cp < 0x10000) { out[0] = char(0xE0 | cp >> 12); out[1] = char(0x80 | (cp >> 6 & 0x3F)); out[2] = char(0x80 | (cp & 0x3F)); out[3] = 0; }
  else { out[0] = char(0xF0 | cp >> 18); out[1] = char(0x80 | (cp >> 12 & 0x3F)); out[2] = char(0x80 | (cp >> 6 & 0x3F)); out[3] = char(0x80 | (cp & 0x3F)); out[4] = 0; }
}
// The title's right end leaves room for the summary: its width, a gap, and the inset.
inline void fit_title(const section_layout::Section &s, Drawn &d) {
  int32_t right = inset();
  if (d.summary && !s.summary.empty() && small_font) {
    lv_point_t size;
    lv_text_get_size(&size, s.summary.c_str(), small_font, 0, 0, LV_COORD_MAX, LV_TEXT_FLAG_NONE);
    right += size.x + gap();
  }
  lv_obj_set_style_margin_right(d.title, right, 0);
}
inline void paint(Drawn &d) {
  // A section whose tiles follow its contrast is the other look whole: its own panel, ink and muted words there.
  theme::Flip other(d.follow);
  if (d.follow) {
    if (d.panel) lv_obj_set_style_bg_color(d.panel, theme::color(theme::SECTION), 0);
    for (lv_obj_t *obj : {d.icon, d.title}) if (obj) lv_obj_set_style_text_color(obj, theme::color(theme::INK), 0);
    if (d.summary) lv_obj_set_style_text_color(d.summary, theme::color(theme::MUTED), 0);
    return;
  }
  const theme::Role ink = d.contrast ? theme::SECTION_CONTRAST_INK : theme::INK;
  if (d.panel) lv_obj_set_style_bg_color(d.panel, theme::color(d.contrast ? theme::SECTION_CONTRAST : theme::SECTION), 0);
  if (d.icon) lv_obj_set_style_text_color(d.icon, theme::color(ink), 0);
  if (d.title) lv_obj_set_style_text_color(d.title, theme::color(ink), 0);
  if (d.summary) lv_obj_set_style_text_color(d.summary, theme::color(d.contrast ? theme::SECTION_CONTRAST_INK : theme::MUTED), 0);
}
inline void make(int page) {
  auto &list = drawn[page];
  const int32_t top = title_top(), corner = radius() + gap();
  for (const auto &s : of(page)) {
    Drawn d;
    d.contrast = s.contrast;
    d.follow = s.follow;
    // The panel behind the cards: exactly the section's cells.
    d.panel = lv_obj_create(tile_grid);
    lv_obj_remove_style_all(d.panel);
    lv_obj_remove_flag(d.panel, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_remove_flag(d.panel, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_bg_opa(d.panel, LV_OPA_COVER, 0);
    lv_obj_set_style_radius(d.panel, corner, 0);
    lv_obj_set_grid_cell(d.panel, LV_GRID_ALIGN_STRETCH, s.column, s.columns, LV_GRID_ALIGN_STRETCH, s.row, s.rows);
    lv_obj_move_to_index(d.panel, 0);
    // The icon's ink centred on the middle of the title's capitals, its ink's left edge on the inset.
    int32_t x = inset();
    lv_font_glyph_dsc_t g;
    if (s.icon && mini_icon_font && lv_font_get_glyph_dsc(mini_icon_font, &g, s.icon, 0)) {
      char glyph[5];
      utf8(s.icon, glyph);
      d.icon = text(glyph, mini_icon_font);
      lv_label_set_long_mode(d.icon, LV_LABEL_LONG_MODE_CLIP);
      const int cap_middle = top + ink_top(label_font) + cap_height(label_font) / 2;
      const int ink_middle = ascent(mini_icon_font) - (g.ofs_y + g.box_h) + g.box_h / 2;
      lv_obj_set_style_margin_left(d.icon, x - g.ofs_x, 0);
      lv_obj_set_style_margin_top(d.icon, cap_middle - ink_middle, 0);
      lv_obj_set_grid_cell(d.icon, LV_GRID_ALIGN_START, s.column, s.columns, LV_GRID_ALIGN_START, s.row, 1);
      x += g.box_w + ui::px(7);
    }
    d.title = text(s.title, label_font);
    lv_obj_set_style_margin_left(d.title, x, 0);
    lv_obj_set_style_margin_top(d.title, top, 0);
    lv_obj_set_grid_cell(d.title, LV_GRID_ALIGN_STRETCH, s.column, s.columns, LV_GRID_ALIGN_START, s.row, 1);
    // The summary on the title's line (its baseline on the title's), at the right end.
    if (small_font) {
      d.summary = text(s.summary, small_font);
      lv_label_set_long_mode(d.summary, LV_LABEL_LONG_MODE_CLIP);
      lv_obj_set_style_margin_right(d.summary, inset(), 0);
      lv_obj_set_style_margin_top(d.summary, top + ascent(label_font) - ascent(small_font), 0);
      lv_obj_set_grid_cell(d.summary, LV_GRID_ALIGN_END, s.column, s.columns, LV_GRID_ALIGN_START, s.row, 1);
    }
    fit_title(s, d);
    paint(d);
    list.push_back(d);
  }
  made[page] = signature(page);
  // The header's numbers, which the editor's boards.json `section` holds too (tools/generate_board_shapes.py).
  if (!list.empty()) ESP_LOGI("sections", "page %d: %u drawn, header %d, title top %d, ink top %d", page, (unsigned) list.size(),
                              (int) header(), (int) title_top(), ink_top(label_font));
}
inline void hide(int page, bool hidden) {
  if (page < 0 || size_t(page) >= drawn.size()) return;
  for (auto &d : drawn[page])
    for (lv_obj_t *obj : {d.panel, d.icon, d.title, d.summary})
      if (obj) { if (hidden) lv_obj_add_flag(obj, LV_OBJ_FLAG_HIDDEN); else lv_obj_remove_flag(obj, LV_OBJ_FLAG_HIDDEN); }
}
inline void drop(int page) {
  for (auto &d : drawn[page])
    for (lv_obj_t *obj : {d.panel, d.icon, d.title, d.summary}) if (obj && lv_obj_is_valid(obj)) lv_obj_delete(obj);
  drawn[page].clear();
  made[page] = 0;
}
// The page's decorations on the glass, every other page's off it. Called by place_page once its cards are placed.
inline void show(int page) {
  if (!tile_grid || page < 0 || size_t(page) >= drawn.size()) return;
  if (shown >= 0 && shown != page) hide(shown, true);
  if (made[page] != signature(page)) { drop(page); make(page); }
  else hide(page, false);
  shown = page;
}
inline void summaries(int page) {
  if (page < 0 || size_t(page) >= drawn.size() || made[page] != signature(page)) return;
  const auto &sections = of(page);
  for (size_t i = 0; i < drawn[page].size() && i < sections.size(); ++i) {
    auto &d = drawn[page][i];
    if (d.summary) lv_label_set_text(d.summary, sections[i].summary.c_str());
    if (d.title) fit_title(sections[i], d);
  }
}
inline void restyle() {
  for (auto &list : drawn) for (auto &d : list) paint(d);
}
// Another layout or another grid: every decoration goes, and is made again when its page is next placed.
inline void forget() {
  for (size_t page = 0; page < drawn.size(); ++page) drop(int(page));
  for (auto &[card, set] : followed)
    for (const auto &o : set) if (lv_obj_is_valid(o.obj)) lv_obj_remove_local_style_prop(o.obj, o.prop, o.part);
  followed.clear();
  shown = -1;
}
}  // namespace sections
#endif
