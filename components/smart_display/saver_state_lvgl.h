// The screensaver's state: whether it is wanted, lit or leaving, its words and its rows.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: what the screensaver draws (saver_lvgl.h).
// What proves it: tests/test_screen_saver.py, tests/test_saver_plugins.py.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// The screensaver (firmware 0.29.0+, app 0.4.48). When Auto standby dims the screen, a screen whose ESP Screen Manager
// chose a screensaver shows it over the dimmed tiles, at the standby level: the cover of what plays, a camera, or the
// clock. The app decides which (screen_manager/app/screen_saver.py) and says so in a small message whenever that
// changes; the screen keeps the last word and shows it the next time it goes into standby. A cover and a camera are the
// camera's full view without its keys, holding one picture of the whole glass the app made for it (darkened, the cover
// in its colour on long glass, picture_paint's fit `saver`) with a line or two of words over it (saver_view.h); the clock
// takes the bedside clock's digits. Nothing on it takes a tap: it lies on the top layer without one clickable object,
// so a finger falls through to dim_wake_overlay and only wakes the screen, the way it always did in standby (and
// wake_tap leaves the tile it lay over alone).
inline std::function<void()> saver_changed;  // the profile's apply_screen_settings, which ends in saver_sync
inline bool saver_lit = false;               // in standby with the backlight on (the standby or night level)
inline uint32_t saver_ticked = 0;
// A camera in standby loads at a live tile's default pace rather than the full view's four seconds: a screensaver can
// stand there all evening, and the Wi-Fi and Home Assistant need not fetch a picture every four seconds for it.
constexpr uint32_t SAVER_CAMERA_MS = 15000;

// The steps whose picture is the full view's (one picture of the whole glass the app made): a cover, a photo, a camera.
inline bool saver_picture_kind(const std::string &kind) { return kind == "media" || kind == "photos" || kind == "camera"; }
// A plugin draws this word (plugin API 0.14): a face of the step this screen has, or a plugin's step of its own. A face
// the screen lacks (the plugin left it) leaves the step's own face.
inline bool saver_plugin_draws(const SaverChoice &c) { return !c.plugin.empty() && plugin_host::saver_known(c.plugin); }
inline bool saver_wanted() {
  const auto &kind = saver_next.kind;
  if (kind == "plugin") return saver_plugin_draws(saver_next);
  return kind == "clock" || (saver_picture_kind(kind) && camera_supported() &&
                             (valid_entity(saver_next.entity) || saver_next.entity == SAVER_PHOTOS));
}
inline lv_obj_t *saver_text(lv_obj_t *parent, const lv_font_t *font, uint32_t color, const media_card::Rect &r, const std::string &text,
                            lv_text_align_t align = LV_TEXT_ALIGN_CENTER) {
  auto *label = lv_label_create(parent);
  lv_obj_remove_flag(label, LV_OBJ_FLAG_CLICKABLE);
  if (font) lv_obj_set_style_text_font(label, font, 0);
  lv_obj_set_style_text_color(label, theme::rgb(color), 0);
  lv_obj_set_style_text_align(label, align, 0);
  lv_label_set_long_mode(label, LV_LABEL_LONG_DOT);
  lv_obj_set_pos(label, r.x, r.y);
  // Its own room and no more (firmware 0.30.0+): what does not fit ends in dots instead of running over the next line.
  lv_obj_set_size(label, r.w, r.h);
  lv_label_set_text(label, text.c_str());
  return label;
}

// The clock's row of entities (firmware 0.50.0+): the top bar's items in the date's font, centred in `line` on its middle
// line, a middle dot between two, the first (the temperature) staying when the glass is too narrow for all. One soft
// ink on black, whatever an entity's colour: the screensaver gives as little light as it can.
inline void saver_row_draw(const std::vector<header_bar::Item> &row, const esphome::ESPTime &now, uint32_t ink,
                           const media_card::Rect &line, const lv_font_t *font) {
  lv_font_glyph_dsc_t zero;
  if (!lv_font_get_glyph_dsc(font, &zero, '0', 0) || !zero.box_h) return;
  const auto gaps = header_bar::gaps(zero.box_h);
  std::array<page_header::Piece, header_bar::MAX_ITEMS> pieces;
  std::array<int, header_bar::MAX_ITEMS> widths{};
  size_t count = 0;
  for (const auto &item : row) {
    if (count == pieces.size()) break;
    auto p = page_header::piece(item.icon, header_icon_font, page_header::item_text(item, now, now_epoch(), screen_settings::current.clock_24h != 0), font, gaps);
    if (p.width) { widths[count] = p.width; pieces[count++] = std::move(p); }
  }
  // A middle dot between two values, with a little more than half the bar's gap between two items on either side.
  const auto dot = page_header::piece(0, nullptr, "·", font, gaps);
  const int side = (gaps.item * 3 + 2) / 5;
  auto spaced = gaps;
  if (dot.text_w) spaced.item = 2 * side + dot.text_w;
  const auto placed = header_bar::centre(widths.data(), count, spaced, line.w);
  const int middle2 = 2 * line.y + line.h, baseline = page_header::digits_baseline(font, middle2);
  const int line_h = lv_font_get_line_height(font);
  for (size_t k = 0; k < placed.count; ++k) {
    const auto &p = pieces[k];
    int x = line.x + placed.x[k];
    if (k && dot.text_w) saver_text(saver_root, font, ink, {x - side - dot.text_w - dot.text_left, page_header::text_top(font, baseline), dot.text_left + dot.text_w + 2, line_h}, dot.text, LV_TEXT_ALIGN_LEFT);
    if (p.icon) {
      const auto glyph = tile_icon::utf8(p.icon);
      saver_text(saver_root, p.font, ink, {x - p.icon_left, page_header::icon_top(p.font, p.icon, middle2), p.icon_w + 2, (int) lv_font_get_line_height(p.font)}, glyph, LV_TEXT_ALIGN_LEFT);
      x += p.icon_w + (p.text_w ? gaps.icon : 0);
    }
    if (p.text_w) saver_text(saver_root, font, ink, {x - p.text_left, page_header::text_top(font, baseline), p.text_left + p.text_w + 2, line_h}, p.text, LV_TEXT_ALIGN_LEFT);
  }
}
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
