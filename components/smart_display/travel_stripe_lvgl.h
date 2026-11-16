// A cover slider while its cover is on its way: the stripe that glides over it.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: the rules themselves, which are plain C++ without LVGL in cover_travel.h.
// What proves it: tests/test_cover_travel.cpp.
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// A cover slider while its cover is on its way (cover_travel.h). The fill stands faint at the target and the handle is
// gone, so nothing looks as if it waits for a finger, and a thin stripe glides over the slider from where Home Assistant
// last had the cover towards where it goes, about once a second: the cover moves, and which way, also where it cannot
// be seen. The slider still takes a finger: a press brings the handle back (the pressed state outranks the travel's)
// and the release sends the cover elsewhere. The slats' slider has no fill, so its handle goes faint instead.
// Only the sliders on the glass are redrawn, by one timer that lives while a stripe runs.
namespace travel_stripe {
struct Run { lv_obj_t *slider = nullptr; int from = 0, to = 0; };
inline std::array<Run, 8> runs{};
inline lv_timer_t *timer = nullptr;
constexpr uint32_t PERIOD = 1100, FRAME = 50;
inline Run *find(lv_obj_t *slider) {
  for (auto &r : runs) if (r.slider == slider) return &r;
  return nullptr;
}
inline void tick(lv_timer_t *) {
  bool any = false;
  for (auto &r : runs) if (r.slider) { lv_obj_invalidate(r.slider); any = true; }
  if (!any && timer) { lv_timer_delete(timer); timer = nullptr; }
}
// The slider's pixel along its axis for a raw value, in its own range (a reversed range runs the other way).
inline int at(lv_obj_t *slider, const lv_area_t &c, int raw) {
  const int lo = lv_slider_get_min_value(slider), hi = lv_slider_get_max_value(slider);
  const float share = hi == lo ? 0.0f : std::clamp((raw - lo) / float(hi - lo), 0.0f, 1.0f);
  const bool lying = lv_area_get_width(&c) >= lv_area_get_height(&c);
  return lying ? c.x1 + (int) std::lround(share * (lv_area_get_width(&c) - 1))
               : c.y2 - (int) std::lround(share * (lv_area_get_height(&c) - 1));
}
inline void draw(lv_event_t *e) {
  auto *slider = lv_event_get_target_obj(e);
  const Run *r = find(slider);
  if (!r || lv_obj_has_state(slider, LV_STATE_PRESSED)) return;
  lv_area_t c;
  lv_obj_get_coords(slider, &c);
  const bool lying = lv_area_get_width(&c) >= lv_area_get_height(&c);
  const int a = at(slider, c, r->from), b = at(slider, c, r->to), span = std::abs(b - a);
  const int across = lying ? lv_area_get_height(&c) : lv_area_get_width(&c);
  if (span < 2) return;
  // One thin stripe across the slider, as long as half its width, glides from where the cover was to where it goes,
  // slowing as it arrives, and fades in at the start and out at the end; it never reaches the slider's rounded ends.
  const int thick = std::max(3, across / 14), half = thick / 2;
  const int length = std::max(thick, across / 2);
  const float phase = (esphome::millis() % PERIOD) / float(PERIOD), eased = 1.0f - (1.0f - phase) * (1.0f - phase);
  const int lo_end = (lying ? c.x1 : c.y1) + across / 4, hi_end = (lying ? c.x2 : c.y2) - across / 4;
  const int at_ = std::clamp(a + (int) std::lround((b - a) * eased), lo_end, hi_end);
  const float fade = std::min({1.0f, phase / 0.2f, (1.0f - phase) / 0.25f});
  lv_draw_rect_dsc_t d;
  lv_draw_rect_dsc_init(&d);
  d.bg_color = lv_color_hex(cover_paint::ACCENT);
  d.bg_opa = (lv_opa_t) std::lround(LV_OPA_80 * fade);
  d.radius = LV_RADIUS_CIRCLE;
  const int middle = lying ? (c.y1 + c.y2) / 2 : (c.x1 + c.x2) / 2;
  lv_area_t stripe = lying ? lv_area_t{at_ - half, middle - length / 2, at_ - half + thick - 1, middle + length / 2}
                           : lv_area_t{middle - length / 2, at_ - half, middle + length / 2, at_ - half + thick - 1};
  lv_draw_rect(lv_event_get_layer(e), &d, &stripe);
}
inline void forget(lv_event_t *e) {
  if (Run *r = find(lv_event_get_target_obj(e))) *r = Run();
}
// The stripe of one slider: from and to in the slider's raw values, or none.
inline void set(lv_obj_t *slider, bool on, int from, int to) {
  Run *r = find(slider);
  if (!on) { if (r) { *r = Run(); lv_obj_invalidate(slider); } return; }
  if (!r) {
    r = find(nullptr);
    if (!r) return;
    // Once per slider, however often a cover on it travels.
    lv_obj_remove_event_cb(slider, draw);
    lv_obj_remove_event_cb(slider, forget);
    lv_obj_add_event_cb(slider, draw, LV_EVENT_DRAW_MAIN_END, nullptr);
    lv_obj_add_event_cb(slider, forget, LV_EVENT_DELETE, nullptr);
  }
  r->slider = slider;
  r->from = from;
  r->to = to;
  if (!timer) timer = lv_timer_create(tick, FRAME, nullptr);
}
}  // namespace travel_stripe
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
