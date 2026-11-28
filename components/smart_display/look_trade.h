#pragma once
// The style trade of a card's look (docs/THEME.md "A card's look"): on every object of a card, each shared style is
// traded for another in its own place in the object's list, keeping the selector it was added with. theme::restyle_card
// says which style becomes which (a paint's copy in the other look, or back); this file only trades.
//
// It is the one file of the component that reads LVGL's styles of an object (tests/test_card_look.py holds that).
//
// Why not LVGL's own lv_obj_replace_style(obj, old, new, selector). In LVGL 9.5.0 (src/core/lv_obj_style.c, the
// function from line 167) it writes the selector it is called with into every style it replaces:
// `obj->styles[i].selector = selector;`. A trade of one style for another wherever it stands has to call it with
// LV_PART_ANY | LV_STATE_ANY, and then every traded style ends up with that selector, which applies to no part and no
// state: the card falls back to LVGL's default theme (small corners, square circles with a border). Calling it once for
// each part and state an object may use would work, but it is many calls per object and still needs to know the
// selectors. So the trade reads the list itself. docs/open-issues/lvgl-replace-style-selector.md is the report LVGL
// could get.
//
// What it reads: lv_obj_t::styles and style_cnt (lv_obj_private.h), and each lv_obj_style_t's style, is_local and
// is_trans (lv_obj_style_private.h). It writes only `style`. A copy holds the same properties as its original, so LVGL's
// cache of which properties an object has (full_cache_refresh in lv_obj_style.c) stays true; lv_obj_refresh_style then
// redraws the object.
//
// When LVGL moves on, the check below stops the build. Check those fields, that a style's selector still sits beside it
// in lv_obj_style_t, and that the cache still records only which properties exist; then allow the version.
//
// The host build proves every trade (checked: traded, back and again against a note of every style and selector;
// tools/render/run.py fails on a "restyle check FAIL" line).
#if __has_include("esphome/core/defines.h")
#include "esphome/core/defines.h"
#endif
#ifdef SD_MOD_SECTIONS  // ESPHome puts every header into main.cpp: a board without sections reads none of this
#include "lvgl.h"
#include "lvgl_private.h"
#include <cstdint>
#include <vector>
#ifdef USE_HOST
#include "esphome/core/log.h"
#include "look_trade_log.h"
#endif

// LVGL 9.6 (ESPHome 2026.11) checked 2026-11-18: the same fields (lv_obj_style_t moved its selector after path_cb,
// still beside the style), the same presence-only cache (LV_OBJ_STYLE_CACHE, which ESPHome 2026.11 turns on), and
// lv_obj_refresh_style now also updates the object's cached blur status, which a trade of copies leaves as it was.
#if !(LVGL_VERSION_MAJOR == 9 && (LVGL_VERSION_MINOR == 5 || LVGL_VERSION_MINOR == 6))
#error "look_trade.h reads lv_obj_t::styles as LVGL 9.5 and 9.6 have them: check the fields named at its head before allowing this LVGL"
#endif

namespace look_trade {

// Every style on `obj` and its children that is not a local one or a transition becomes `want(style)`; `want` gives the
// style back to keep it. Each stays in its place with its selector.
template <class Want> inline void trade(lv_obj_t *obj, const Want &want) {
  if (!obj) return;
  bool changed = false;
  for (uint32_t i = 0; i < obj->style_cnt; ++i) {
    lv_obj_style_t &st = obj->styles[i];
    if (st.is_local || st.is_trans) continue;
    const lv_style_t *to = want(st.style);
    if (to && to != st.style) { st.style = to; changed = true; }
  }
  if (changed) lv_obj_refresh_style(obj, LV_PART_ANY, LV_STYLE_PROP_ANY);
  for (uint32_t i = 0; i < lv_obj_get_child_count(obj); ++i) trade(lv_obj_get_child(obj, int32_t(i)), want);
}

#ifdef USE_HOST
struct Note { lv_obj_t *obj; uint32_t index; const lv_style_t *style; lv_style_selector_t selector; };
inline void note(lv_obj_t *obj, std::vector<Note> &out) {
  for (uint32_t i = 0; i < obj->style_cnt; ++i) out.push_back({obj, i, obj->styles[i].style, obj->styles[i].selector});
  for (uint32_t i = 0; i < lv_obj_get_child_count(obj); ++i) note(lv_obj_get_child(obj, int32_t(i)), out);
}
inline uint32_t checks = 0, failures = 0;
// The trade to `other`, proven: every style of every object of the card is noted with its selector, the card traded to
// the look asked for, back and to it again, each step compared with the note. `in(style, other)` is the style a style
// is in a look. After a trade a style is that, at the same place with the same selector; after the trade back, exactly
// the note.
template <class In> inline void checked(lv_obj_t *card, bool other, const In &in) {
  std::vector<Note> before, after;
  note(card, before);
  const auto compare = [&](bool in_other, const char *step) {
    after.clear();
    note(card, after);
    bool same = after.size() == before.size();
    for (size_t i = 0; same && i < after.size(); ++i)
      same = after[i].obj == before[i].obj && after[i].index == before[i].index && after[i].selector == before[i].selector &&
             after[i].style == in(before[i].style, in_other);
    if (!same) {
      ++failures;
      ESP_LOGE("card_look", "restyle check FAIL: %s, card %p, %u styles noted, %u now", step, (void *) card,
               (unsigned) before.size(), (unsigned) after.size());
    }
  };
  const auto to = [&](bool look) { trade(card, [&](const lv_style_t *s) { return in(s, look); }); };
  to(other);
  compare(other, look_trade_log::TRADED);
  to(!other);
  compare(!other, look_trade_log::TRADED_BACK);
  to(other);
  compare(other, look_trade_log::TRADED_AGAIN);
  ++checks;
  ESP_LOGI("card_look", "restyle check: %u trades checked, %u failed", (unsigned) checks, (unsigned) failures);
}
#endif

}  // namespace look_trade
#endif  // SD_MOD_SECTIONS
