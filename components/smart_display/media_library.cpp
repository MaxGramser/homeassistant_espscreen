// A media player's library and its speaker menu (firmware 0.24.0+): what media_library.h describes, drawn with LVGL.
//
// Compiled on its own, as page_receiver.cpp is: every header of this component lands in main.cpp, and on Xtensa the
// literal pool of one object file must stay within reach of all of its code (page_receiver.cpp says how that broke).
#include "esphome/core/log.h"
#include "runtime_tiles.h"

namespace media_library {
using runtime_tiles::Tile;
namespace rt = runtime_tiles;

// ---- state while open ----
static lv_obj_t *root = nullptr, *menu_root = nullptr;
static std::string entity;
static std::vector<std::pair<uint32_t, std::string>> trail;  // the folders opened, the top first: number and title
static Folder folder;
static unsigned page = 0;
static uint32_t asked_at = 0;
static uint8_t tries = 0;
static uint32_t starting = 0, starting_at = 0;  // the item just tapped, until the player plays (STARTING_MS at most)
static uint32_t marked = 0;                     // what plays now as far as this screen knows: the last item it started
static Grid grid;
// The covers of the page on the glass: one picture from the app, every cover its own part of it. It goes the one way
// every picture goes (picture_want, runtime_tiles::pictures_round): a page turned before its covers came breaks the
// download off, and a page that comes back has them from the store at once.
struct Art {
  std::string key, items, atlas;
  int x = 0, y = 0, scale = picture_store::SCALE_ONE;
  uint32_t ground = 0;
};
static Art art;
// What a finger uses, for describe(): the cells of the page, the pager's keys, the menu's rows.
static std::vector<lv_obj_t *> cell_objs, pager_objs, row_objs, join_objs, slider_objs, menu_pager_objs;
// Each cell's parts that say "this plays": its cover's frame (or its card) and its title.
struct Marked { lv_obj_t *frame = nullptr, *title = nullptr; size_t index = 0; };
static std::vector<Marked> marks;
static lv_obj_t *back_obj = nullptr, *speaker_obj = nullptr;
struct Cover { lv_obj_t *image = nullptr; int index = 0; Rect at; };
static std::vector<Cover> covers;
// The speaker menu.
static std::string menu_entity;
static std::string menu_drawn;   // the speakers and the one it plays on, as the menu shows them
static bool menu_due = false;    // they changed while a finger was on the glass
static uint32_t menu_then = 0;
static int menu_tile = -1;  // a favourite that starts on the speaker chosen
static unsigned menu_page = 0;

static const Tile *tile() {
  return effects_page::tile_of ? effects_page::tile_of(entity.empty() ? menu_entity : entity) : nullptr;
}
static const Tile *player(const std::string &id) { return effects_page::tile_of ? effects_page::tile_of(id) : nullptr; }
static uint32_t clock_ms() { return esphome::millis(); }
static const lv_font_t *name_font() { return effects_page::row_font ? effects_page::row_font : rt::detail_font; }
static const lv_font_t *cover_font() { return rt::small_font ? rt::small_font : name_font(); }
static const lv_font_t *icons() { return effects_page::icon_font ? effects_page::icon_font : rt::mini_icon_font; }

bool visible() { return root != nullptr; }
bool menu_visible() { return menu_root != nullptr; }

// The page's measures: the effects page's top bar and gaps, the glass as wide as it is (a page of covers is a picture,
// overlay_card::picture), a cover's title in the small font on two lines, and a folder's card at least a finger tall.
static Shape shape() {
  const auto m = effects_page::screen_metrics();
  Shape s;
  s.width = overlay_card::screen_width();
  s.height = overlay_card::screen_height();
  s.pad = m.pad;
  s.gap = m.gap;
  s.top = m.bar_y + m.bar + m.gap;
  s.line_h = lv_font_get_line_height(cover_font());
  s.pager_h = std::max(ui::touch_min(), m.bar * 3 / 4);
  s.card_h = std::max(ui::touch_min() * 3 / 2, m.row_h * 5 / 4);
  s.min_art = ui::mm(12);
  s.ring = ui::px(5);  // the ring's width and its gap to the cover (mark)
  return s;
}

// ---- the covers of a page ----
static void art_forget() {
  for (auto &c : covers) if (c.image) lv_image_set_src(c.image, nullptr);
  covers.clear();
  art = Art{};
}
// The picture onto every cover of the page, each its own frame of it.
static void art_show(lv_image_dsc_t *src) {
#if LV_USE_IMAGE
  if (!src || !src->data) return;
  for (auto &c : covers) {
    if (!c.image) continue;
    const int ax = c.at.x - art.x, ay = c.at.y - art.y;
    const int fx = picture_store::scaled(ax, art.scale), fy = picture_store::scaled(ay, art.scale);
    const int fw = std::max(1, picture_store::scaled(ax + c.at.w, art.scale) - fx), fh = std::max(1, picture_store::scaled(ay + c.at.h, art.scale) - fy);
    if (fx + fw > (int) src->header.w || fy + fh > (int) src->header.h) continue;
    lv_image_set_src(c.image, src);
    lv_image_set_offset_x(c.image, -fx);
    lv_image_set_offset_y(c.image, -fy);
    lv_obj_set_pos(c.image, (c.at.w - fw) / 2, (c.at.h - fh) / 2);
    lv_obj_set_size(c.image, fw, fh);
    lv_obj_remove_flag(c.image, LV_OBJ_FLAG_HIDDEN);
    // The placeholder goes under its picture: a picture over the cap comes smaller (picture_store) and would stand in
    // a rim of it.
    if (auto *frame = lv_obj_get_parent(c.image)) {
      lv_obj_set_style_bg_opa(frame, LV_OPA_TRANSP, 0);
      if (auto *icon = lv_obj_get_child(frame, 0)) if (icon != c.image) lv_obj_add_flag(icon, LV_OBJ_FLAG_HIDDEN);
    }
    lv_obj_invalidate(c.image);
  }
#else
  (void) src;
#endif
}
bool draws(const void *image) {
  if (!image) return false;
  for (auto &c : covers) if (c.image && rt::draws(c.image, static_cast<const lv_image_dsc_t *>(image))) return true;
  return false;
}
// What the page asks for: its pictured items by their numbers and the frames they fill, from the top left of the first.
static void art_want() {
  // Without a store (no PSRAM, or the host) the covers draw from the download itself, as a page's camera tiles do.
  if (covers.empty() || !rt::camera_supported()) return;
  art.x = art.y = INT32_MAX;
  int right = 0, bottom = 0;
  for (auto &c : covers) {
    art.x = std::min(art.x, c.at.x); art.y = std::min(art.y, c.at.y);
    right = std::max(right, c.at.right()); bottom = std::max(bottom, c.at.bottom());
  }
  art.scale = picture_store::fit_scale(right - art.x, bottom - art.y);
  art.ground = theme::hex(theme::PAGE);
  art.items.clear();
  art.atlas = "[";
  for (auto &c : covers) {
    if (!art.items.empty()) art.items += ',';
    art.items += std::to_string(folder.items[c.index].token);
    const int ax = c.at.x - art.x, ay = c.at.y - art.y;
    const int fx = picture_store::scaled(ax, art.scale), fy = picture_store::scaled(ay, art.scale);
    const int fw = std::max(1, picture_store::scaled(ax + c.at.w, art.scale) - fx), fh = std::max(1, picture_store::scaled(ay + c.at.h, art.scale) - fy);
    const int radius = std::min(std::min(fw, fh) / 2, picture_store::scaled(media_card::radius_for(c.at.w), art.scale));
    char frame[64];
    snprintf(frame, sizeof(frame), "%s[%d,%d,%d,%d,%d,0]", art.atlas.size() > 1 ? "," : "", fx, fy, fw, fh, radius);
    art.atlas += frame;
  }
  art.atlas += "]";
  char tail[16];
  snprintf(tail, sizeof(tail), "|%06X", (unsigned) art.ground);
  art.key = "lib|" + entity + "|" + std::to_string(folder.token) + "|" + art.items + "|" + art.atlas + tail;
  // What the store keeps of this page is on its covers at once; the rest comes with the next round (picture_want).
  if (auto *kept = rt::picture_of(art.key)) art_show(kept);
}
static void art_done(picture_loader::Outcome outcome) {
  if (!LIBRARY || !root || covers.empty()) return;
  if (!rt::shows(outcome)) { ESP_LOGI("library", "covers failed"); return; }
  art_show(rt::picture_of(art.key));
  ESP_LOGI("library", "covers shown");
}
bool picture_want(picture_loader::Want &w) {
  if (!LIBRARY || !root || covers.empty() || art.key.empty() || !rt::awake() || !rt::camera_supported()) return false;
  w.key = art.key;
  w.tag = "lib|" + entity;
  w.slot = picture_loader::Slot::FULL;
  w.rank = picture_loader::Rank::LIBRARY;
  const std::string who = entity, items = art.items, atlas = art.atlas;
  const uint32_t ground = art.ground;
  w.ask = [who, items, atlas, ground] { rt::library_art_request(who, items, atlas, ground); };
  w.done = art_done;
  return true;
}
void art_answer(const std::string &for_entity, const std::string &url) {
  if (!LIBRARY || !root || for_entity != entity) return;
  if (url.empty()) ESP_LOGI("library", "no covers for this page");
  rt::loader.answer("lib|" + entity, url, clock_ms());
}
void art_forget_download() {
  auto *download = rt::camera_full.source ? rt::camera_full.source() : nullptr;
  if (!download) return;
  for (auto &c : covers) if (c.image && rt::draws(c.image, download)) lv_image_set_src(c.image, nullptr);
}

// ---- drawing ----
static lv_obj_t *plain(lv_obj_t *parent, int x, int y, int w, int h) { return effects_page::plain(parent, x, y, w, h); }
static lv_obj_t *words(lv_obj_t *parent, const std::string &text, const lv_font_t *font, theme::Role role, lv_text_align_t align,
                       int x, int y, int w, int lines = 1) {
  auto *label = effects_page::text(parent, text, font, role, align);
  lv_obj_set_pos(label, x, y);
  lv_obj_set_width(label, std::max(1, w));
  lv_obj_set_height(label, lv_font_get_line_height(font) * lines);
  return label;
}
static lv_obj_t *glyph(lv_obj_t *parent, uint32_t codepoint, const char *fallback, const lv_font_t *font, uint32_t color) {
  auto *label = lv_label_create(parent);
  lv_obj_remove_flag(label, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_text_font(label, font, 0);
  lv_obj_set_style_text_color(label, theme::rgb(color), 0);
  std::string text = fallback;
  if (codepoint) { lv_font_glyph_dsc_t dsc; if (lv_font_get_glyph_dsc(font, &dsc, codepoint, 0)) text = tile_icon::utf8(codepoint); }
  lv_label_set_text(label, text.c_str());
  return label;
}
static uint32_t accent() { return theme::hex(theme::ACCENT); }
// A round key like effects_page::round_key, with a number for its handler.
static lv_obj_t *round_key(lv_obj_t *parent, int x, int y, int size, const char *mark, lv_event_cb_t handler, intptr_t user, bool enabled = true) {
  auto *key = plain(parent, x, y, size, size);
  lv_obj_set_style_bg_opa(key, LV_OPA_COVER, 0);
  lv_obj_set_style_bg_color(key, theme::color(theme::KEY), 0);
  lv_obj_set_style_bg_color(key, theme::color(theme::KEY_PRESSED), LV_STATE_PRESSED);
  lv_obj_set_style_radius(key, LV_RADIUS_CIRCLE, 0);
  auto *label = glyph(key, 0, mark, icons(), theme::hex(enabled ? theme::INK : theme::SUBTLE));
  lv_obj_center(label);
  if (enabled) {
    lv_obj_add_flag(key, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_add_event_cb(key, handler, LV_EVENT_SHORT_CLICKED, reinterpret_cast<void *>(user));
  }
  return key;
}
static bool steady() { return effects_page::steady(); }
static void draw();
static void remark();
static void load(uint32_t token, const std::string &title);

static void ask() {
  asked_at = clock_ms();
  rt::library_request(entity, folder.token, folder.next);
}
static void back_event(lv_event_t *) {
  if (!steady()) return;
  if (trail.size() > 1) {
    trail.pop_back();
    load(trail.back().first, trail.back().second);
    return;
  }
  close();
}
static void speaker_event(lv_event_t *) { if (steady()) speakers(entity); }
static void turn(int step) {
  const unsigned pages = page_count(folder.items.size(), grid.per_page);
  const int next = static_cast<int>(page) + step;
  if (next < 0 || next >= static_cast<int>(pages)) return;
  page = static_cast<unsigned>(next);
  draw();
}
static void pager_event(lv_event_t *e) { if (steady()) turn(static_cast<int>(reinterpret_cast<intptr_t>(lv_event_get_user_data(e)))); }
static void gesture_event(lv_event_t *) {
  const auto direction = lv_indev_get_gesture_dir(lv_indev_active());
  if (direction == LV_DIR_LEFT) turn(1);
  else if (direction == LV_DIR_RIGHT) turn(-1);
}
// What a tap on an item does: plays it on the speaker the player plays on, or asks for one first when it plays nowhere.
static void play(const Item &item) {
  const Tile *t = tile();
  const bool can_start = t && (!t->extra().media_source.empty() || (t->supported & tile_controls::feature::MEDIA_PLAY_MEDIA));
  if (!can_start && t && !t->extra().media_sources.empty()) { speakers(entity, item.token); return; }
  starting = item.token;
  starting_at = clock_ms();
  rt::play_request(entity, item.token, "");
  remark();
}
static void item_event(lv_event_t *e) {
  const auto code = lv_event_get_code(e);
  if ((code != LV_EVENT_SHORT_CLICKED && code != LV_EVENT_LONG_PRESSED) || !steady()) return;
  const size_t index = static_cast<size_t>(reinterpret_cast<intptr_t>(lv_event_get_user_data(e)));
  if (index >= folder.items.size()) return;
  const Item item = folder.items[index];
  switch (tap_of(item.flags, code == LV_EVENT_LONG_PRESSED)) {
    case Tap::open:
      trail.emplace_back(item.token, item.title);
      load(item.token, item.title);
      break;
    case Tap::play:
      play(item);
      break;
    case Tap::none:
      break;
  }
}
// A finger on a cell of covers presses its cover: the cell takes the tap, its cover shows it.
static void press_event(lv_event_t *e) {
  auto *holder = static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  auto *frame = holder ? lv_obj_get_child(holder, 0) : nullptr;
  if (!frame) return;
  if (lv_event_get_code(e) == LV_EVENT_PRESSED) lv_obj_add_state(frame, LV_STATE_PRESSED);
  else lv_obj_remove_state(frame, LV_STATE_PRESSED);
}
static bool playing_mark(const Item &item) {
  return item.token == starting || item.token == marked || (!marked && !starting && (item.flags & PLAYING));
}
// What plays now, marked: a ring of the accent round its cover (or its card) and its title in the accent.
static void mark(const Marked &m) {
  if (m.index >= folder.items.size()) return;
  const bool on = playing_mark(folder.items[m.index]);
  if (m.frame) {
    if (grid.covers) {
      lv_obj_set_style_outline_width(m.frame, on ? ui::px(3) : 0, 0);
      lv_obj_set_style_outline_pad(m.frame, ui::px(2), 0);
      lv_obj_set_style_outline_color(m.frame, theme::rgb(accent()), 0);
    } else {
      lv_obj_set_style_outline_width(m.frame, on ? ui::px(3) : 1, 0);
      lv_obj_set_style_outline_pad(m.frame, on ? ui::px(1) : -1, 0);
      lv_obj_set_style_outline_color(m.frame, on ? theme::rgb(accent()) : theme::color(theme::LINE), 0);
    }
  }
  if (m.title) lv_obj_set_style_text_color(m.title, theme::color(on ? theme::ACCENT : theme::INK), 0);
}
// The marks again, in place: a tap answers at once, and the covers stay where they are.
static void remark() { for (auto &m : marks) mark(m); }
static void cell(size_t index, const Rect &at, const Rect &cover_at) {
  const Item &item = folder.items[index];
  auto *holder = plain(root, at.x, at.y, at.w, at.h);
  // The ring round a cover lies outside it.
  lv_obj_add_flag(holder, LV_OBJ_FLAG_OVERFLOW_VISIBLE);
  cell_objs.push_back(holder);
  lv_obj_add_flag(holder, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_add_event_cb(holder, item_event, LV_EVENT_SHORT_CLICKED, reinterpret_cast<void *>(static_cast<intptr_t>(index)));
  lv_obj_add_event_cb(holder, item_event, LV_EVENT_LONG_PRESSED, reinterpret_cast<void *>(static_cast<intptr_t>(index)));
  if (grid.covers) {
    // The cover's place: its placeholder with the item's icon, the picture over it once the page's covers came.
    const Rect local{cover_at.x - at.x, cover_at.y - at.y, cover_at.w, cover_at.h};
    auto *frame = plain(holder, local.x, local.y, local.w, local.h);
    lv_obj_set_style_bg_opa(frame, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_color(frame, theme::rgb(theme::tint(theme::ha::LIGHT_BLUE, 51)), 0);
    lv_obj_set_style_radius(frame, media_card::radius_for(local.w), 0);
    // The big icon font carries only the tiles' own glyphs: an item's icon it lacks takes the small one.
    const std::string wanted = item.icon ? tile_icon::utf8(item.icon) : std::string("\U000F0387");
    const lv_font_t *big = rt::big_icon_font && local.w >= 2 * lv_font_get_line_height(rt::big_icon_font) && rt::font_has(rt::big_icon_font, wanted)
                               ? rt::big_icon_font : icons();
    auto *icon = glyph(frame, item.icon, "\U000F0387", big, theme::icon(theme::ha::LIGHT_BLUE));
    lv_obj_center(icon);
#if LV_USE_IMAGE
    if (item.flags & PICTURED) {
      Cover c;
      c.index = static_cast<int>(index);
      c.at = cover_at;
      c.image = lv_image_create(frame);
      lv_obj_remove_flag(c.image, LV_OBJ_FLAG_CLICKABLE);
      lv_image_set_inner_align(c.image, LV_IMAGE_ALIGN_TOP_LEFT);
      lv_obj_add_flag(c.image, LV_OBJ_FLAG_HIDDEN);
      covers.push_back(c);
    }
#endif
    lv_obj_add_flag(frame, LV_OBJ_FLAG_OVERFLOW_VISIBLE);
    lv_obj_set_style_transform_width(frame, -ui::px(3), LV_STATE_PRESSED);
    lv_obj_set_style_transform_height(frame, -ui::px(3), LV_STATE_PRESSED);
    lv_obj_add_event_cb(holder, press_event, LV_EVENT_PRESSED, nullptr);
    lv_obj_add_event_cb(holder, press_event, LV_EVENT_RELEASED, nullptr);
    lv_obj_add_event_cb(holder, press_event, LV_EVENT_PRESS_LOST, nullptr);
    auto *title = words(holder, item.title, cover_font(), theme::INK, LV_TEXT_ALIGN_CENTER, 0, local.bottom() + grid.ring + grid.gap / 2, at.w, 2);
    marks.push_back({frame, title, index});
    mark(marks.back());
    return;
  }
  // A card: a round badge with the item's icon at the left, the name beside it on two lines at most.
  lv_obj_set_style_bg_opa(holder, LV_OPA_COVER, 0);
  lv_obj_set_style_bg_color(holder, theme::color(theme::CARD), 0);
  lv_obj_set_style_bg_color(holder, theme::color(theme::CARD_PRESSED), LV_STATE_PRESSED);
  lv_obj_set_style_radius(holder, effects_page::screen_metrics().radius, 0);
  const int inset = effects_page::screen_metrics().inset, badge = std::min(at.h - 2 * ui::px(6), std::max(ui::px(24), at.h * 3 / 5));
  auto *circle = plain(holder, inset, (at.h - badge) / 2, badge, badge);
  lv_obj_set_style_bg_opa(circle, LV_OPA_COVER, 0);
  lv_obj_set_style_bg_color(circle, theme::rgb(theme::tint(theme::ha::LIGHT_BLUE, 51)), 0);
  lv_obj_set_style_radius(circle, LV_RADIUS_CIRCLE, 0);
  auto *icon = glyph(circle, item.icon, "\U000F024B", icons(), theme::icon(theme::ha::LIGHT_BLUE));
  lv_obj_center(icon);
  const lv_font_t *font = name_font();
  const int text_x = inset + badge + ui::px(ui::large() ? 12 : 8), text_w = at.w - text_x - inset;
  // Two lines for a name that needs them and has the room, one in the middle of the card for the rest.
  const int lines = rt::text_width(item.title, font) > text_w && at.h >= 2 * lv_font_get_line_height(font) + ui::px(8) ? 2 : 1;
  auto *name = words(holder, item.title, font, theme::INK, LV_TEXT_ALIGN_LEFT, text_x, 0, text_w, lines);
  lv_label_set_long_mode(name, LV_LABEL_LONG_DOT);
  lv_obj_set_y(name, (at.h - lv_font_get_line_height(font) * lines) / 2);
  marks.push_back({holder, name, index});
  mark(marks.back());
}
static void pager(unsigned pages) {
  const auto m = effects_page::screen_metrics();
  const Shape s = shape();
  const int key = s.pager_h, y = grid.pager_y;
  auto chevron = [&](int x, const char *mark, int step, bool enabled) { pager_objs.push_back(round_key(root, x, y, key, mark, pager_event, step, enabled)); };
  const int span = std::min(s.width - 2 * s.pad, ui::control_max_width()), left = (s.width - span) / 2;
  chevron(left, "\U000F0141", -1, page > 0);
  chevron(left + span - key, "\U000F0142", 1, page + 1 < pages);
  if (dots(pages)) {
    const int d = ui::px(ui::large() ? 8 : 6), gap = ui::px(ui::large() ? 10 : 7);
    const int row = static_cast<int>(pages) * d + (static_cast<int>(pages) - 1) * gap;
    for (unsigned i = 0; i < pages; ++i) {
      auto *dot = plain(root, (s.width - row) / 2 + static_cast<int>(i) * (d + gap), y + (key - d) / 2, d, d);
      lv_obj_set_style_bg_opa(dot, LV_OPA_COVER, 0);
      lv_obj_set_style_radius(dot, LV_RADIUS_CIRCLE, 0);
      lv_obj_set_style_bg_color(dot, theme::color(i == page ? theme::INK : theme::TRACK), 0);
    }
  } else {
    words(root, page_text(page, pages), name_font(), theme::MUTED, LV_TEXT_ALIGN_CENTER, left + key, y + (key - lv_font_get_line_height(name_font())) / 2, span - 2 * key);
  }
  (void) m;
}
static void draw() {
  if (!root) return;
  art_forget();
  lv_obj_clean(root);
  cell_objs.clear(); pager_objs.clear(); marks.clear();
  // The effects page's bar, across the whole glass: the page of covers is not capped to a hand's width.
  auto m = effects_page::screen_metrics();
  m.width = overlay_card::screen_width();
  const Shape s = shape();
  // The top bar: back (up a folder, or out), the folder's name, the speakers at the right.
  const Tile *t = tile();
  const std::string title = !folder.title.empty() ? folder.title : trail.empty() ? std::string() : trail.back().second;
  const bool with_speakers = t && !t->extra().media_sources.empty();
  back_obj = effects_page::top_bar(root, m, title.empty() ? std::string(screen_text::tr(screen_text::txt::media_library)) : title, back_event,
                                   with_speakers ? "\U000F04C3" : nullptr, speaker_event);
  speaker_obj = with_speakers ? lv_obj_get_child(root, 1) : nullptr;
  auto note = [&](uint16_t key) {
    words(root, screen_text::tr(key), name_font(), theme::MUTED, LV_TEXT_ALIGN_CENTER, s.pad, (s.top + s.height) / 2 - lv_font_get_line_height(name_font()), s.width - 2 * s.pad);
  };
  if (!folder.complete) { note(screen_text::txt::media_loading); return; }
  if (folder.failed) { note(screen_text::txt::media_library_failed); return; }
  if (folder.items.empty()) { note(screen_text::txt::media_library_empty); return; }
  grid = place(s, rt::camera_supported() && folder.pictured(), folder.items.size());
  const unsigned pages = page_count(folder.items.size(), grid.per_page);
  page = std::min(page, pages - 1);
  const size_t first = first_of(page, grid.per_page), end = end_of(page, grid.per_page, folder.items.size());
  for (size_t i = first; i < end; ++i) cell(i, grid.cell(static_cast<int>(i - first)), grid.cover(static_cast<int>(i - first)));
  if (grid.pager) pager(pages);
  if (grid.covers) art_want();
}
static void load(uint32_t token, const std::string &title) {
  folder = Folder{};
  folder.token = token;
  folder.title = title;
  page = 0;
  tries = 0;
  draw();
  ask();
}

// ---- the page ----
void open(const std::string &id) {
  if (!LIBRARY) return;
  const Tile *t = player(id);
  if (!t) return;
  close();
  entity = id;
  root = effects_page::page_root();
  // A page of covers is a picture: it takes the glass, not a hand's width (overlay_card::picture).
  lv_obj_set_style_pad_left(root, 0, 0);
  lv_obj_set_style_pad_right(root, 0, 0);
  lv_obj_set_style_bg_color(root, theme::color(theme::PAGE), 0);
  lv_obj_add_event_cb(root, gesture_event, LV_EVENT_GESTURE, nullptr);
  trail = {{0, std::string()}};
  marked = 0;
  ESP_LOGI("library", "Library of %s", id.c_str());
  load(0, std::string());
}
void close() {
  if (menu_root) { lv_obj_delete(menu_root); menu_root = nullptr; }
  row_objs.clear();
  menu_entity.clear();
  menu_then = 0;
  menu_tile = -1;
  if (!root) return;
  art_forget();
  lv_obj_delete(root);
  root = nullptr;
  cell_objs.clear(); pager_objs.clear(); marks.clear();
  back_obj = speaker_obj = nullptr;
  entity.clear();
  trail.clear();
  folder = Folder{};
  starting = 0;
  // The player's card under it shows what changed meanwhile.
  if (rt::detail_root && !lv_obj_has_flag(rt::detail_root, LV_OBJ_FLAG_HIDDEN) && rt::detail_index < rt::model.count) rt::refresh_detail(rt::detail_index);
}
void received(Answer &&answer) {
  if (!LIBRARY || !root || answer.entity != entity) return;
  if (!folder.take(std::move(answer))) return;
  tries = 0;
  if (!folder.complete) { ask(); return; }
  ESP_LOGI("library", "Folder %u: %u items", (unsigned) folder.token, (unsigned) folder.items.size());
  draw();
}

// ---- the speaker menu ----
// Two lists open here: the speakers (media_sources) and, from the input key, the inputs (media_inputs, firmware
// 0.26.0+). A player whose speakers carry flags (the app's speakers.py) gets a speaker menu that groups: a speaker in
// the group shows a filled tick and its own volume under its name, one that may join a round plus; a tap on the
// name of one outside the group picks it (or joins it), a tap on the name of one inside does nothing, so a finger
// that misses the volume never breaks the group.
static bool menu_inputs = false;
static std::vector<size_t> menu_starts;  // the first row of each page
static void draw_menu();
static const std::vector<std::string> *menu_list(const Tile *t) {
  if (!t) return nullptr;
  return menu_inputs ? &t->extra().media_inputs : &t->extra().media_sources;
}
static bool grouping(const Tile *t) { return t && !menu_inputs && !t->extra().speaker_flags.empty(); }
static uint8_t flags_of(const Tile *t, size_t index) {
  return grouping(t) && index < t->extra().speaker_flags.size() ? t->extra().speaker_flags[index] : 0;
}
static int volume_of(const Tile *t, size_t index) {
  return grouping(t) && index < t->extra().speaker_volumes.size() ? t->extra().speaker_volumes[index] : -1;
}
static bool with_volume(const Tile *t, size_t index) {
  const uint8_t f = flags_of(t, index);
  return (f & SPEAKER_ON) && (f & SPEAKER_GROUPS) && volume_of(t, index) >= 0;
}
// What the menu shows, to draw it again only when that changes.
static std::string menu_key(const Tile *t) {
  std::string key = menu_inputs ? "i" + t->extra().media_input : "s" + t->extra().media_source;
  const auto *list = menu_list(t);
  for (size_t i = 0; list && i < list->size(); ++i)
    key += "\n" + (*list)[i] + "," + std::to_string(flags_of(t, i)) + "," + std::to_string(volume_of(t, i));
  return key;
}
static void menu_close() {
  if (menu_root) { lv_obj_delete(menu_root); menu_root = nullptr; }
  row_objs.clear();
  join_objs.clear();
  slider_objs.clear();
  menu_pager_objs.clear();
  const bool was_card = !root;
  menu_entity.clear();
  menu_then = 0;
  menu_tile = -1;
  menu_inputs = false;
  if (was_card && rt::detail_root && !lv_obj_has_flag(rt::detail_root, LV_OBJ_FLAG_HIDDEN) && rt::detail_index < rt::model.count) rt::refresh_detail(rt::detail_index);
}
static void menu_scrim_event(lv_event_t *e) {
  if (lv_event_get_target(e) != lv_event_get_current_target(e) || !steady()) return;
  menu_close();
}
static void menu_pager_event(lv_event_t *e) {
  if (!steady()) return;
  menu_page = static_cast<unsigned>(std::max(0, static_cast<int>(menu_page) + static_cast<int>(reinterpret_cast<intptr_t>(lv_event_get_user_data(e)))));
  draw_menu();
}
// The flags of a speaker on every tile of the player, at once: Home Assistant's next state confirms them.
static void set_flags(const std::string &id, size_t index, uint8_t flags) {
  for (size_t i = 0; i < rt::model.count; ++i)
    if (rt::model.tiles[i].entity == id) if (auto *x = rt::model.tiles[i].extra_ptr()) if (index < x->speaker_flags.size()) x->speaker_flags[index] = flags;
}
static void choose(size_t index) {
  const Tile *t = player(menu_entity);
  const auto *list = menu_list(t);
  if (!t || !list || index >= list->size()) return;
  const std::string name = (*list)[index], id = menu_entity;
  if (menu_inputs) {
    // An input: Home Assistant's own action on the player, as its media dialog does.
    ESP_LOGI("library", "Input %s for %s", name.c_str(), id.c_str());
    if (name != t->extra().media_input) rt::action("media_player.select_source", id, "source", name);
    for (size_t i = 0; i < rt::model.count; ++i)
      if (rt::model.tiles[i].entity == id) if (auto *x = rt::model.tiles[i].extra_ptr()) x->media_input = name;
    menu_close();
    return;
  }
  const uint8_t flags = flags_of(t, index);
  const bool groups = grouping(t);
  if ((flags & SPEAKER_ON) && (flags & SPEAKER_GROUPS)) return;  // in the group: only its tick takes it out
  const uint32_t then = menu_then;
  const int favorite = menu_tile;
  // A speaker it plays on already is no change, unless it plays nowhere: then the choice wakes it.
  const bool change = groups ? !(flags & SPEAKER_ON) : (name != t->extra().media_source || t->state == "idle");
  ESP_LOGI("library", "Speaker %s for %s", name.c_str(), id.c_str());
  if (favorite >= 0) {
    if (static_cast<size_t>(favorite) < rt::TILES_MAX) rt::favorite_started_at[favorite] = std::max<uint32_t>(1, clock_ms());
    rt::library_event("esphome.screen_play", {{"entity", id}, {"tile", std::to_string(favorite)}, {"source", name}});
    rt::refresh_tile(static_cast<size_t>(favorite));
  } else if (then) {
    starting = then;
    starting_at = clock_ms();
    rt::play_request(id, then, name);
  } else if (change && groups) {
    rt::speaker_request(id, name, "pick");
  } else if (change) {
    rt::action("media_player.select_source", id, "source", name);
  }
  if (groups && (flags & SPEAKER_GROUPS) && !then && favorite < 0) {
    // Joined: the menu stays and shows it in the group at once.
    set_flags(id, index, flags | SPEAKER_ON);
    draw_menu();
    return;
  }
  // The pill says the new speaker at once; Home Assistant's next state confirms it.
  for (size_t i = 0; i < rt::model.count; ++i)
    if (rt::model.tiles[i].entity == id) if (auto *x = rt::model.tiles[i].extra_ptr()) x->media_source = name;
  menu_close();
  if (root) remark();
}
static void menu_row_event(lv_event_t *e) {
  if (!steady()) return;
  choose(static_cast<size_t>(reinterpret_cast<intptr_t>(lv_event_get_user_data(e))));
}
// The round key at the end of a speaker that groups: in the group it takes it out, outside it adds it.
static void menu_join_event(lv_event_t *e) {
  if (!steady()) return;
  const size_t index = static_cast<size_t>(reinterpret_cast<intptr_t>(lv_event_get_user_data(e)));
  const Tile *t = player(menu_entity);
  const auto *list = menu_list(t);
  if (!t || !list || index >= list->size()) return;
  const uint8_t flags = flags_of(t, index);
  const bool leave = flags & SPEAKER_ON;
  rt::speaker_request(menu_entity, (*list)[index], leave ? "leave" : "join");
  set_flags(menu_entity, index, leave ? flags & ~SPEAKER_ON : flags | SPEAKER_ON);
  draw_menu();
}
// A speaker's volume, sent when the finger lets go.
static void menu_volume_event(lv_event_t *e) {
  if (lv_event_get_code(e) != LV_EVENT_RELEASED || !steady()) return;
  auto *slider = static_cast<lv_obj_t *>(lv_event_get_target(e));
  const size_t index = static_cast<size_t>(reinterpret_cast<intptr_t>(lv_event_get_user_data(e)));
  const Tile *t = player(menu_entity);
  const auto *list = menu_list(t);
  if (!t || !list || index >= list->size()) return;
  const int value = lv_slider_get_value(slider);
  rt::speaker_request(menu_entity, (*list)[index], "volume", value);
  for (size_t i = 0; i < rt::model.count; ++i)
    if (rt::model.tiles[i].entity == menu_entity) if (auto *x = rt::model.tiles[i].extra_ptr())
      if (index < x->speaker_volumes.size()) x->speaker_volumes[index] = static_cast<int8_t>(value);
  menu_drawn = menu_key(t);
}
static lv_obj_t *volume_slider(lv_obj_t *parent, int x, int y, int w, int h, int value) {
  auto *s = lv_slider_create(parent);
  lv_obj_remove_style_all(s);
  lv_obj_remove_flag(s, LV_OBJ_FLAG_SCROLLABLE);
  const int track = std::max(4, ui::px(ui::large() ? 8 : 6)), knob = track + ui::px(ui::large() ? 14 : 10);
  lv_obj_set_pos(s, x, y + (h - track) / 2);
  lv_obj_set_size(s, w, track);
  lv_obj_set_ext_click_area(s, (h - track) / 2);
  lv_slider_set_range(s, 0, 100);
  lv_slider_set_value(s, value, LV_ANIM_OFF);
  for (auto part : {LV_PART_MAIN, LV_PART_INDICATOR}) {
    lv_obj_set_style_radius(s, LV_RADIUS_CIRCLE, part);
    lv_obj_set_style_bg_opa(s, LV_OPA_COVER, part);
  }
  lv_obj_set_style_bg_color(s, theme::color(theme::TRACK), LV_PART_MAIN);
  lv_obj_set_style_bg_color(s, theme::color(theme::ACCENT), LV_PART_INDICATOR);
  lv_obj_set_style_bg_opa(s, LV_OPA_COVER, LV_PART_KNOB);
  lv_obj_set_style_bg_color(s, theme::color(theme::SLIDER_KNOB), LV_PART_KNOB);
  lv_obj_set_style_radius(s, LV_RADIUS_CIRCLE, LV_PART_KNOB);
  lv_obj_set_style_pad_all(s, (knob - track) / 2, LV_PART_KNOB);
  return s;
}
static void draw_menu() {
  if (menu_root) { lv_obj_delete(menu_root); menu_root = nullptr; }
  row_objs.clear();
  join_objs.clear();
  slider_objs.clear();
  menu_pager_objs.clear();
  const Tile *t = player(menu_entity);
  const auto *list = menu_list(t);
  if (!t || !list || list->empty()) return;
  const auto &names = *list;
  menu_drawn = menu_key(t);
  menu_due = false;
  const auto m = effects_page::screen_metrics();
  const int width = overlay_card::screen_width(), height = overlay_card::screen_height();
  // A scrim over everything that closes the menu when tapped beside it.
  menu_root = plain(lv_screen_active(), 0, 0, width, height);
  lv_obj_add_flag(menu_root, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_bg_opa(menu_root, 120, 0);
  lv_obj_set_style_bg_color(menu_root, theme::color(theme::CAMERA_PAGE), 0);
  lv_obj_add_event_cb(menu_root, menu_scrim_event, LV_EVENT_SHORT_CLICKED, nullptr);
  lv_obj_move_foreground(menu_root);
  const int y = m.bar_y + m.bar + m.gap / 2, room = height - y - m.pad;
  // The volume line is three quarters of a finger; its slider reaches a finger's height with its click area, and a
  // tap beside it lands on a row that does nothing.
  const int row_h = std::max(ui::touch_min(), m.row_h), volume_h = ui::touch_min() * 3 / 4;
  const int panel_w = std::min(width - 2 * m.pad, ui::px(ui::large() ? 380 : 260));
  // Pages by height: a speaker in the group is a row taller for its volume. The pager takes a row of its own.
  std::vector<int> heights;
  for (size_t i = 0; i < names.size(); ++i) heights.push_back(row_h + (with_volume(t, i) ? volume_h : 0));
  menu_starts = page_starts(heights, room, row_h);
  const unsigned pages = static_cast<unsigned>(menu_starts.size());
  menu_page = std::min(menu_page, pages - 1);
  const size_t first = menu_starts[menu_page], last = menu_page + 1 < pages ? menu_starts[menu_page + 1] : names.size();
  int used = 0;
  for (size_t i = first; i < last; ++i) used += heights[i];
  const bool pager = pages > 1;
  auto *panel = plain(menu_root, (width - panel_w) / 2, y, panel_w, used + (pager ? row_h : 0));
  lv_obj_add_flag(panel, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_bg_opa(panel, LV_OPA_COVER, 0);
  lv_obj_set_style_bg_color(panel, theme::color(theme::RAISED), 0);
  lv_obj_set_style_radius(panel, m.radius, 0);
  lv_obj_set_style_clip_corner(panel, true, 0);
  // An outline, not a border: a border moves every row inside by its width.
  lv_obj_set_style_outline_width(panel, 1, 0);
  lv_obj_set_style_outline_color(panel, theme::color(theme::RAISED_LINE), 0);
  const lv_font_t *font = name_font();
  const int text_h = lv_font_get_line_height(font), icon_h = lv_font_get_line_height(icons());
  const std::string &current = menu_inputs ? t->extra().media_input : t->extra().media_source;
  const bool groups = grouping(t);
  const int key = std::min(row_h - ui::px(6), m.bar);
  int ry = 0;
  for (size_t index = first; index < last; ++index) {
    const uint8_t flags = flags_of(t, index);
    const bool on = groups ? (flags & SPEAKER_ON) : names[index] == current;
    const bool joins = groups && (flags & SPEAKER_GROUPS);
    auto *row = plain(panel, 0, ry, panel_w, heights[index]);
    lv_obj_add_flag(row, LV_OBJ_FLAG_CLICKABLE);
    // The speakers that play together share one pale ground; a chosen input or speaker has it too.
    if (on) {
      lv_obj_set_style_bg_opa(row, LV_OPA_COVER, 0);
      lv_obj_set_style_bg_color(row, theme::color(theme::ACCENT_TINT), 0);
    }
    if (!(on && joins)) {
      lv_obj_set_style_bg_opa(row, LV_OPA_COVER, LV_STATE_PRESSED);
      lv_obj_set_style_bg_color(row, theme::color(theme::CARD_PRESSED), LV_STATE_PRESSED);
    }
    lv_obj_add_event_cb(row, menu_row_event, LV_EVENT_SHORT_CLICKED, reinterpret_cast<void *>(static_cast<intptr_t>(index)));
    row_objs.push_back(row);
    auto *icon = glyph(row, 0, menu_inputs ? "\U000F0206" : "\U000F04C3", icons(), theme::hex(on ? theme::ACCENT : theme::MUTED));
    lv_obj_set_pos(icon, m.inset, (row_h - icon_h) / 2);
    const int x = m.inset + m.icon + ui::px(8), end = joins ? key + m.inset / 2 + ui::px(6) : m.inset + m.icon + ui::px(6);
    words(row, names[index], font, on ? theme::ACCENT : theme::INK, LV_TEXT_ALIGN_LEFT, x, (row_h - text_h) / 2, panel_w - x - end);
    if (joins) {
      auto *k = round_key(row, panel_w - m.inset / 2 - key, (row_h - key) / 2, key, on ? "\U000F012C" : "\U000F0415", menu_join_event, static_cast<intptr_t>(index));
      join_objs.push_back(k);
      if (on) {
        lv_obj_set_style_bg_color(k, theme::color(theme::ACCENT), 0);
        if (auto *mark = lv_obj_get_child(k, 0)) lv_obj_set_style_text_color(mark, theme::color(theme::ON_ACCENT), 0);
      }
    } else if (on) {
      auto *check = glyph(row, 0, "\U000F012C", icons(), accent());
      lv_obj_set_pos(check, panel_w - m.inset - m.icon, (row_h - icon_h) / 2);
    }
    if (with_volume(t, index)) {
      // Its own volume under its name, a finger tall, as the player's card has one for the whole player.
      auto *slider = volume_slider(row, x, row_h - ui::px(4), panel_w - x - end, volume_h, volume_of(t, index));
      lv_obj_add_event_cb(slider, menu_volume_event, LV_EVENT_RELEASED, reinterpret_cast<void *>(static_cast<intptr_t>(index)));
      slider_objs.push_back(slider);
    }
    ry += heights[index];
  }
  if (pager) {
    const int k = std::min(row_h - ui::px(8), m.bar);
    auto chevron = [&](int x, const char *mark, int step, bool enabled) { menu_pager_objs.push_back(round_key(panel, x, ry + (row_h - k) / 2, k, mark, menu_pager_event, step, enabled)); };
    chevron(m.inset, "\U000F0141", -1, menu_page > 0);
    chevron(panel_w - m.inset - k, "\U000F0142", 1, menu_page + 1 < pages);
    words(panel, page_text(menu_page, pages), font, theme::MUTED, LV_TEXT_ALIGN_CENTER, m.inset + k, ry + (row_h - text_h) / 2, panel_w - 2 * (m.inset + k));
  }
}
static void open_menu(const std::string &id, bool inputs, uint32_t then, int tile) {
  menu_entity = id;
  menu_inputs = inputs;
  menu_then = then;
  menu_tile = tile;
  menu_page = 0;
  const Tile *t = player(id);
  const auto *list = menu_list(t);
  if (!list || list->empty()) { menu_entity.clear(); menu_inputs = false; return; }
  // Open on the page with the speaker or input it plays on.
  const std::string &current = inputs ? t->extra().media_input : t->extra().media_source;
  draw_menu();
  for (size_t i = 0; i < list->size(); ++i) {
    if (!(grouping(t) ? (flags_of(t, i) & SPEAKER_ON) : (*list)[i] == current)) continue;
    for (unsigned p = 0; p < menu_starts.size(); ++p) if (menu_starts[p] <= i) menu_page = p;
    if (menu_page) draw_menu();
    break;
  }
}
void speakers(const std::string &id, uint32_t then, int tile) { open_menu(id, false, then, tile); }
void inputs(const std::string &id) { open_menu(id, true, 0, -1); }

// ---- what changes while open ----
static bool finger_down() {
  auto *input = lv_indev_get_next(nullptr);
  return input && lv_indev_get_state(input) == LV_INDEV_STATE_PRESSED;
}
void updated(const std::string &id) {
  // The menu changes only when the speakers do, and never under a finger: a row drawn anew loses the tap on it.
  if (menu_root && id == menu_entity) {
    const Tile *t = player(menu_entity);
    const std::string now = t ? menu_key(t) : std::string();
    if (now != menu_drawn) { if (finger_down()) menu_due = true; else draw_menu(); }
  }
  if (!root || id != entity) return;
  const Tile *t = tile();
  // A start that took: what was tapped is what plays now.
  if (starting && t && (t->state == "playing" || t->state == "paused") && t->supported & tile_controls::feature::MEDIA_PLAY_MEDIA) {
    marked = starting;
    starting = 0;
    remark();
  }
}
void restyle() {
  if (LIBRARY && root) {
    lv_obj_set_style_bg_color(root, theme::color(theme::PAGE), 0);
    draw();
  }
  if (menu_root) draw_menu();
}
void tick(uint32_t now) {
  if (!LIBRARY) {
    if (menu_root && menu_due && !finger_down()) draw_menu();
    return;
  }
  if (menu_root && menu_due && !finger_down()) draw_menu();
  if (root && !folder.complete && now - asked_at >= ASK_AGAIN_MS) {
    if (++tries >= ASK_TRIES) { folder.failed = folder.complete = true; draw(); }
    else ask();
  }
  if (root && starting && now - starting_at >= STARTING_MS) { starting = 0; remark(); }
}
std::string describe() {
  lv_obj_update_layout(lv_screen_active());
  auto centre = [](lv_obj_t *o) {
    if (!o) return std::string();
    lv_area_t a; lv_obj_get_coords(o, &a);
    return std::to_string((a.x1 + a.x2) / 2) + "," + std::to_string((a.y1 + a.y2) / 2);
  };
  auto list = [&](const std::vector<lv_obj_t *> &objects) { std::string out; for (auto *o : objects) out += centre(o) + ";"; return out; };
  int shown = 0;
  for (auto &c : covers) if (c.image && !lv_obj_has_flag(c.image, LV_OBJ_FLAG_HIDDEN)) ++shown;
  const unsigned pages = folder.complete ? page_count(folder.items.size(), grid.per_page) : 0;
  return "library=" + std::to_string(root != nullptr) + " menu=" + std::to_string(menu_root != nullptr) + " folder=" + std::to_string(folder.token) +
         " items=" + std::to_string(folder.items.size()) + " page=" + std::to_string(page) + "/" + std::to_string(pages) +
         " grid=" + std::to_string(grid.columns) + "x" + std::to_string(grid.rows) + " covers=" + std::to_string(covers.size()) +
         " shown=" + std::to_string(shown) + " marked=" + std::to_string(starting ? starting : marked) + " back=" + centre(back_obj) +
         " speaker=" + centre(speaker_obj) + " cells=" + list(cell_objs) + " pager=" + list(pager_objs) + " rows=" + list(row_objs) +
         " joins=" + list(join_objs) + " sliders=" + list(slider_objs) + " mpager=" + list(menu_pager_objs) + " inkey=" + centre(rt::media_input_key);
}
}  // namespace media_library
