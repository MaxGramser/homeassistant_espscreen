// A cover group's page (module cover_groups, tier full; docs/MODULES.md): a card per cover on the page a light group's
// lamps have (group_page.h), reached from a key on the group's cover card where the lamps key stands. A lite screen
// compiles none of it, says no group_covers in its hello, and ESP Screens sends it no covers.
// Included by group_page.h inside its namespace, at the place its cards need; elsewhere this file is empty.
#if defined(SD_MOD_COVER_GROUPS) && defined(SMART_DISPLAY_COVER_GROUPS_SITE) && !defined(SMART_DISPLAY_MODULE_COVER_GROUPS)
#define SMART_DISPLAY_MODULE_COVER_GROUPS

// A cover of the group as a tile of its own, so it is read by the rules every cover tile is (tile_controls::cover_card,
// cover_keys, cover_tilt_keys, status_text).
inline Tile blind_tile(const Blind &b) {
  Tile t;
  t.entity = b.entity; t.name = b.name; t.state = b.unavailable ? "unavailable" : b.state; t.device_class = b.device_class;
  t.supported = b.supported; t.position = b.position;
  if (std::isfinite(b.tilt)) t.edit_extra().tilt = b.tilt;
  return t;
}
// What the cover's card offers: a position bar, its keys instead where it has none, its slats behind the ellipsis key.
inline bool blind_bar(const Blind &b) { return !b.unavailable && tile_controls::cover_card(blind_tile(b)).position; }
inline bool blind_panel(const Blind &b) {
  if (b.unavailable) return false;
  const auto c = tile_controls::cover_card(blind_tile(b));
  return c.tilt || c.tilt_keys;
}

// ---- a cover group's cards (firmware 0.57.0) ----
// A cover's change: its position or its tilt as a wish (shown at once on its card, MEMBER_POSITION / MEMBER_TILT), its
// open, stop and close as the action alone, as Home Assistant's cover keys are (no value the screen could know).
inline void cover_want(optimistic::Field field, const std::string &cover, int value) {
  const bool tilt = field == optimistic::Field::MEMBER_TILT;
  want(field, cover, std::to_string(value), tilt ? "cover.set_cover_tilt_position" : "cover.set_cover_position",
       tilt ? "tilt_position" : "position", std::to_string(value));
}
inline void cover_key(const std::string &cover, int command) {
  const Blind *b = blind_of(cover);
  if (!b || b->unavailable) return;
  const auto call = tile_controls::key_action(blind_tile(*b), command);
  if (!call.service.empty()) emit(call.service.c_str(), cover, call.key.c_str(), call.value);
}
// The cover's card as it is now: its icon open or closed, its bar where no finger holds it, its keys where it has them.
inline void paint_blind(Card &c, const Blind &b, bool fresh_card) {
  const auto t = blind_tile(b);
  const bool shut = b.state == "closed" || (std::isfinite(b.position) && b.position <= 0.5f);
  if (c.icon) {
    lv_label_set_text(c.icon, shut ? "\U000F1A2C" : tile_controls::glyph::SLATS);
    lv_obj_set_style_text_color(c.icon, shut || b.unavailable ? theme::color(theme::MUTED) : lv_color_hex(cover_paint::ACCENT), 0);
  }
  if (c.slider && (fresh_card || (!c.dirty && !lv_obj_has_state(c.slider, LV_STATE_PRESSED)))) {
    // A closed cover shows its track alone, as a lamp that is off, until a finger moves it.
    const int open = (int) std::lround(std::isfinite(b.position) ? b.position : 0);
    lv_obj_set_style_bg_opa(c.slider, open > 0 ? LV_OPA_COVER : LV_OPA_TRANSP, LV_PART_INDICATOR);
    lv_obj_set_style_bg_opa(c.slider, open > 0 ? LV_OPA_COVER : LV_OPA_TRANSP, LV_PART_KNOB);
    lv_slider_set_value(c.slider, std::max(1, open), LV_ANIM_OFF);
  }
  std::array<tile_controls::Key, 3> keys;
  const unsigned count = tile_controls::cover_keys(t, keys);
  for (unsigned n = 0; n < c.keys.size(); ++n) {
    if (!c.keys[n]) continue;
    const bool off = n >= count || keys[n].disabled;
    if (off) lv_obj_add_state(c.keys[n], LV_STATE_DISABLED); else lv_obj_remove_state(c.keys[n], LV_STATE_DISABLED);
    lv_obj_set_style_opa(c.keys[n], off ? LV_OPA_40 : LV_OPA_COVER, 0);
  }
  lv_obj_set_style_opa(c.box, b.unavailable ? LV_OPA_50 : LV_OPA_COVER, 0);
}
// A tap on a cover's card opens or closes it, as Home Assistant's toggle does: a cover on its way or open closes.
inline void blind_card_event(lv_event_t *e) {
  const int i = card_index(e);
  if (!effects_page::steady() || i < 0 || i >= static_cast<int>(cards.size())) return;
  const Blind *b = blind_of(cards[i].entity);
  if (!b || b->unavailable) return;
  const bool shut = b->state == "closed" || b->state == "closing";
  cover_key(b->entity, shut ? tile_controls::COVER_OPEN : tile_controls::COVER_CLOSE);
}
inline void blind_slider_event(lv_event_t *e) {
  const int i = card_index(e);
  if (i < 0 || i >= static_cast<int>(cards.size())) return;
  auto &c = cards[i];
  const auto code = lv_event_get_code(e);
  if (code == LV_EVENT_VALUE_CHANGED) {
    c.dirty = true;
    lv_obj_set_style_bg_opa(c.slider, LV_OPA_COVER, LV_PART_INDICATOR);
    lv_obj_set_style_bg_opa(c.slider, LV_OPA_COVER, LV_PART_KNOB);
  }
  if (code == LV_EVENT_PRESS_LOST) c.dirty = false;
  if (code == LV_EVENT_RELEASED && c.dirty) {
    c.dirty = false;
    cover_want(optimistic::Field::MEMBER_POSITION, c.entity, std::clamp((int) lv_slider_get_value(c.slider), 0, 100));
  }
}
// A key of a cover's card: user data card * 4 + key.
inline void blind_key_event(lv_event_t *e) {
  const int tag = card_index(e), i = tag / 4, n = tag % 4;
  if (!effects_page::steady() || i < 0 || i >= static_cast<int>(cards.size())) return;
  const Blind *b = blind_of(cards[i].entity);
  if (!b) return;
  std::array<tile_controls::Key, 3> keys;
  if (n < (int) tile_controls::cover_keys(blind_tile(*b), keys) && !keys[n].disabled) cover_key(b->entity, keys[n].command);
}
// The panel of a blind with slats: its tilt as a lying slider with the slats at their angle, or its tilt keys.
inline void blind_tilt_event(lv_event_t *e) {
  if (panel_card < 0 || panel_card >= static_cast<int>(cards.size()) || panel_sliders.empty()) return;
  auto &p = panel_sliders[0];
  const auto code = lv_event_get_code(e);
  if (code == LV_EVENT_VALUE_CHANGED) {
    p.dirty = true;
    if (p.value) lv_label_set_text(p.value, screen_text::percent(std::clamp((int) lv_slider_get_value(p.slider) / 10, 0, 100)).c_str());
  }
  if (code == LV_EVENT_PRESS_LOST) p.dirty = false;
  if (code == LV_EVENT_RELEASED && p.dirty) {
    p.dirty = false;
    cover_want(optimistic::Field::MEMBER_TILT, cards[panel_card].entity, std::clamp((int) std::lround(lv_slider_get_value(p.slider) / 10.0f), 0, 100));
  }
}
inline void blind_tilt_key_event(lv_event_t *e) {
  if (panel_card < 0 || panel_card >= static_cast<int>(cards.size())) return;
  const int n = card_index(e);
  const Blind *b = blind_of(cards[panel_card].entity);
  if (!b) return;
  std::array<tile_controls::Key, 3> keys;
  if (n < (int) tile_controls::cover_tilt_keys(blind_tile(*b), keys) && !keys[n].disabled) cover_key(b->entity, keys[n].command);
}
inline void open_cover_panel(int index) {
  const Blind *b = blind_of(cards[index].entity);
  if (!b || !blind_panel(*b)) return;
  panel_card = index;
  const bool large = ui::large();
  const auto t = blind_tile(*b);
  const auto card = tile_controls::cover_card(t);
  const lv_font_t *font = effects_page::row_font;
  const int pad = ui::px(large ? 8 : 4), inset = ui::px(large ? 14 : 7), text_y = ui::px(large ? 10 : 4);
  const int text_h = lv_font_get_line_height(font), foot = ui::px(large ? 12 : 6);
  const int track_h = std::max(ui::touch_min() * 85 / 100, ui::px(large ? 40 : 24));
  const auto em = effects_page::screen_metrics();
  const int w = std::min(em.width - 2 * em.pad, ui::px(large ? 320 : 220));
  const int h = 2 * pad + text_y + text_h + ui::px(large ? 10 : 5) + track_h + foot;
  make_panel(index, w, h);
  int tx = inset;
  if (effects_page::icon_font) {
    auto *ic = effects_page::text(panel, tile_controls::glyph::SLATS, effects_page::icon_font, theme::MUTED);
    lv_obj_set_width(ic, LV_SIZE_CONTENT);
    const int ih = lv_font_get_line_height(effects_page::icon_font);
    lv_obj_set_pos(ic, inset - ui::px(large ? 2 : 1), pad + text_y + (text_h - ih) / 2);
    tx += ih + ui::px(large ? 6 : 4);
  }
  const int value_w = ui::px(large ? 80 : 50);
  PanelSlider p;
  p.value = effects_page::text(panel, card.tilt && std::isfinite(b->tilt) ? screen_text::percent((int) std::lround(b->tilt)) : "", font, theme::MUTED, LV_TEXT_ALIGN_RIGHT);
  lv_obj_set_width(p.value, value_w);
  lv_obj_set_pos(p.value, w - inset - value_w, pad + text_y);
  auto *label = effects_page::text(panel, screen_text::tr(screen_text::txt::cover_tilt), font, theme::INK);
  lv_obj_set_width(label, w - inset - value_w - ui::px(4) - tx);
  lv_obj_set_pos(label, tx, pad + text_y);
  const int y = h - pad - foot - track_h;
  if (card.tilt) {
    p.slider = cover_paint::tilt_bar(panel, inset, y, w - 2 * inset, track_h, b->tilt);
    lv_obj_set_ext_click_area(p.slider, ui::px(large ? 12 : 8));
    lv_obj_add_event_cb(p.slider, blind_tilt_event, LV_EVENT_ALL, nullptr);
  } else {
    std::array<tile_controls::Key, 3> keys;
    const unsigned count = tile_controls::cover_tilt_keys(t, keys);
    const int gap = ui::px(large ? 8 : 4), key_w = (w - 2 * inset - (int) (count - 1) * gap) / (int) std::max(1u, count);
    for (unsigned n = 0; n < count; ++n) {
      auto *k = effects_page::round_key(panel, inset + n * (key_w + gap), y, track_h, keys[n].icon, blind_tilt_key_event);
      lv_obj_set_width(k, key_w);
      lv_obj_set_style_radius(k, track_h / 2, 0);
      lv_obj_add_event_cb(k, blind_tilt_key_event, LV_EVENT_SHORT_CLICKED, reinterpret_cast<void *>(static_cast<intptr_t>(n)));
      if (lv_obj_t *g = lv_obj_get_child(k, 0)) lv_obj_center(g);
      if (keys[n].disabled) lv_obj_set_style_opa(k, LV_OPA_40, 0);
    }
  }
  panel_sliders.push_back(p);
  ESP_LOGI("group", "Panel of %s: %s", b->entity.c_str(), card.tilt ? "tilt slider" : "tilt keys");
}
// One cover's card, as a lamp's: its icon and name on the first line, under them its position bar shaped as the lamp's
// brightness slider in the cover's purple; open, stop and close at the right where it has no position; the ellipsis key
// of a blind with slats.
inline void blind_card(lv_obj_t *parent, int x, int y, int w, int h, const Blind &b, int index) {
  const bool large = ui::large();
  const auto user = reinterpret_cast<void *>(static_cast<intptr_t>(index));
  Card c; c.entity = b.entity; c.cover = true;
  c.box = effects_page::card(parent, x, y, w, h, ui::px(large ? 18 : 10));
  lv_obj_add_flag(c.box, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_set_style_bg_color(c.box, theme::color(theme::CARD_PRESSED), LV_STATE_PRESSED);
  lv_obj_add_event_cb(c.box, blind_card_event, LV_EVENT_SHORT_CLICKED, user);
  const lv_font_t *font = effects_page::row_font;
  const int inset = ui::px(large ? 16 : 8), text_y = ui::px(large ? 11 : 4), text_h = lv_font_get_line_height(font);
  const int key = std::min(ui::touch_min(), h - 2 * ui::px(large ? 8 : 4));
  int right = w;
  if (blind_panel(b)) {
    c.key = effects_page::round_key(c.box, w - inset - key, (h - key) / 2 - 1, key, "\U000F01D8", [](lv_event_t *) {});
    lv_obj_add_event_cb(c.key, key_event, LV_EVENT_SHORT_CLICKED, user);
    right = w - key - ui::px(large ? 10 : 5);
  }
  const bool bar = blind_bar(b);
  std::array<tile_controls::Key, 3> keys;
  const unsigned count = !bar && !b.unavailable ? tile_controls::cover_keys(blind_tile(b), keys) : 0;
  const int line_y = bar ? text_y : (h - text_h) / 2 - 1;
  int text_x = inset, name_right = right - inset;
  if (effects_page::icon_font) {
    c.icon = effects_page::text(c.box, "", effects_page::icon_font, theme::MUTED);
    lv_obj_set_width(c.icon, LV_SIZE_CONTENT);
    const int icon_h = lv_font_get_line_height(effects_page::icon_font);
    lv_obj_set_pos(c.icon, inset - ui::px(large ? 2 : 1), line_y + (text_h - icon_h) / 2);
    text_x += icon_h + ui::px(large ? 6 : 4);
  }
  if (count) {
    const int gap = ui::px(large ? 6 : 4);
    for (unsigned n = 0; n < count; ++n) {
      auto *k = effects_page::round_key(c.box, right - inset - (int) (count - n) * key - (int) (count - 1 - n) * gap, (h - key) / 2 - 1, key,
                                        keys[n].icon, [](lv_event_t *) {});
      lv_obj_add_event_cb(k, blind_key_event, LV_EVENT_SHORT_CLICKED, reinterpret_cast<void *>(static_cast<intptr_t>(index * 4 + (int) n)));
      c.keys[n] = k;
    }
    name_right -= (int) count * key + (int) (count - 1) * gap + ui::px(large ? 10 : 5);
  }
  auto *name = effects_page::text(c.box, b.name.empty() ? b.entity : b.name, font, theme::INK);
  lv_obj_set_width(name, std::max(ui::px(20), name_right - text_x));
  lv_obj_set_pos(name, text_x, line_y);
  if (bar) {
    const int track_h = ui::px(large ? 28 : 14), foot = ui::px(large ? 12 : 5);
    c.slider = brightness_slider(c.box, inset, h - foot - track_h - 2, right - 2 * inset, track_h);
    // The lamp's slider in the cover's colours, its fill the share the cover is open (Home Assistant's cover-position).
    lv_obj_set_style_bg_color(c.slider, lv_color_hex(cover_paint::track()), LV_PART_MAIN);
    lv_obj_set_style_bg_color(c.slider, lv_color_hex(cover_paint::ACCENT), LV_PART_INDICATOR);
    lv_obj_set_style_bg_opa(c.slider, LV_OPA_COVER, LV_PART_INDICATOR);
    lv_obj_set_style_bg_opa(c.slider, LV_OPA_COVER, LV_PART_KNOB);
    lv_obj_add_event_cb(c.slider, blind_slider_event, LV_EVENT_ALL, user);
  }
  cards.push_back(std::move(c));
  paint_blind(cards.back(), b, true);
}

// A state of the cover group while its page is open (group_page::updated): the cards follow Home Assistant, a card
// whose shape changed draws the page again unless a finger is on it.
inline void draw();
inline void close();
inline void cover_updated(const Tile &t) {
  const auto &blinds = t.extra().blinds;
  if (blinds.empty()) { close(); return; }
  const Layout l = layout(static_cast<int>(blinds.size()), room());
  const int first = std::min(page, l.pages - 1) * l.per_page;
  bool same = static_cast<int>(cards.size()) == std::min(l.per_page, static_cast<int>(blinds.size()) - first);
  for (size_t i = 0; same && i < cards.size(); ++i) {
    const Blind &b = blinds[first + i];
    std::array<tile_controls::Key, 3> keys;
    const unsigned count = !blind_bar(b) && !b.unavailable ? tile_controls::cover_keys(blind_tile(b), keys) : 0;
    same = b.entity == cards[i].entity && blind_panel(b) == (cards[i].key != nullptr) && blind_bar(b) == (cards[i].slider != nullptr) &&
           (count > 0) == (cards[i].keys[0] != nullptr);
  }
  if (!same) { if (!lv_indev_get_active_obj()) draw(); return; }
  for (size_t i = 0; i < cards.size(); ++i) paint_blind(cards[i], blinds[first + i], false);
  if (panel_card >= 0 && panel_card < static_cast<int>(cards.size()) && !panel_sliders.empty()) {
    auto &p = panel_sliders[0];
    const Blind &b = blinds[first + panel_card];
    if (p.slider && !p.dirty && !lv_obj_has_state(p.slider, LV_STATE_PRESSED) && std::isfinite(b.tilt)) {
      lv_slider_set_value(p.slider, (int) std::lround(b.tilt * 10), LV_ANIM_OFF);
      if (p.value) lv_label_set_text(p.value, screen_text::percent((int) std::lround(b.tilt)).c_str());
    }
  }
}

#endif
