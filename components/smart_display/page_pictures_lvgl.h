// Page pictures: a page's picture taken from the glass while it rests, and put back on it when the screen turns to it.
//
// The part of the tile renderer that does this with LVGL and the glass. It belongs to runtime_tiles.h's translation
// unit: it is included there in its place and uses what stands before it there (the pages, the cards, the change
// numbers, what lies over a page). ESPHome also includes every header of a component on its own (esphome.h): there this
// file is empty, which is what RUNTIME_TILES_PARTS is for.
// What it knows: the tile grid's room and the cards on it, the glass's lock, its copies and what LVGL is about to draw
// (glass::waiting: LVGL's own list is the glass's to read).
// What it knows nothing of: the rules (which blocks are true, which pages hold a picture, how many), which are plain
// C++ in page_pictures.h; the frame buffer's memory and its cache, which are the glass's (glass.h, taken and laid).
// What proves it: tests/test_page_pictures.cpp for the rules; on a board, a build with -DSWIPE_PROFILE=1 compares the
// glass with the picture after every turn's redraw and says how many pixels differ (docs/KEPT_PAGES.md).
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
#ifdef GLASS_STEADY
// ---- Page pictures (page_pictures.h, docs/KEPT_PAGES.md "Page pictures") ----
// One picture: its map and its pixels, laid out as the frame buffer is. All of it in PSRAM.
struct PagePicture {
  page_pictures::Map map;
  uint16_t *pixels = nullptr;
  // The page's cards as they lay when it left the glass, so its picture is put before a card is placed again: a layout
  // or a grid that would move one forgets the picture.
  std::array<page_pictures::Card, CELLS_MAX> cards{};
  size_t card_count = 0;
  page_pictures::Stillness still;  // when LVGL last drew each block while the page was on the glass
  bool left = false;  // it left the glass through a turn: `cards` and its entry's change number are of that moment
};
// Everything page pictures keep, in PSRAM too (made with the first picture): inside the chip stands one pointer.
struct PagePictures {
  page_pictures::Shelf shelf;
  std::array<PagePicture *, page_pictures::MAX_KEPT> held{};
  // The turn whose redraw LVGL still owes: the page a picture was put for, and the change number at the put.
  int turned = -1;
  uint32_t turned_at = 0;
  bool compare = false;      // a profiling build: the glass against the picture once that redraw is done
  int taking = -1;           // the page a take is on its way for, for its log line
  uint32_t take_began = 0, take_bytes = 0, take_steps = 0, take_us = 0;
  const char *refused = nullptr;  // why the last put or take did not happen, said once
  // Giving memory up (page_pictures::must_yield): the PSRAM refusals seen so far, when the free PSRAM was last read, and
  // when a picture last went, after which none takes memory for a while.
  uint32_t refusals_seen = 0, looked_at = 0, yielded_at = 0;
};
inline PagePictures *page_pics = nullptr;
inline bool page_pictures_on = true;  // a diagnostic build's A/B (page_receiver.cpp, op "page_pictures")
// A page rests this long before its picture is taken, and a take copies at most this much in one step of the main loop
// (docs/KEPT_PAGES.md has what a step costs).
constexpr uint32_t PICTURE_QUIET_MS = 1000, PICTURE_STEP_MS = 50;
// A block is taken once LVGL has not drawn it for this long: longer than a second, so what draws every second (a
// playing track's bar) is never taken, and short enough for a page someone looks at for a moment.
constexpr uint32_t PICTURE_STILL_MS = 1500;
constexpr size_t PICTURE_SLICE_BYTES = 400u << 10;

inline void page_pictures_say(const char *why) {
  if (!page_pics || page_pics->refused == why) return;
  page_pics->refused = why;
  if (why) ESP_LOGD("page_pic", "none now: %s", why);
}
inline glass::Rect panel_rect(const glass::Rect &on_screen) {
  const auto p = glass::panel();
  return glass::on_panel(on_screen, glass::turn(), p.w, p.h);
}
inline glass::Rect panel_rect(const lv_area_t &a) { return panel_rect(glass::Rect{a.x1, a.y1, a.x2 - a.x1 + 1, a.y2 - a.y1 + 1}); }
// The page's own room: the tile grid, as LVGL lays it out.
inline lv_area_t page_room() {
  lv_area_t a{0, 0, -1, -1};
  if (tile_grid) lv_obj_get_coords(tile_grid, &a);
  return a;
}
inline size_t page_picture_bytes() {
  const auto p = glass::panel();
  return static_cast<size_t>(p.w) * p.h * 2;
}
// How many pictures this board keeps for this layout: from its PSRAM, never from its name.
inline size_t page_pictures_capacity() {
  if (!page_pictures_on || !hw::caps().page_pictures || !tile_grid || !model.configured) return 0;
  return page_pictures::count(hw::caps().psram_bytes, page_picture_bytes(), page_count());
}
inline void page_picture_free(size_t at) {
  if (!page_pics || !page_pics->held[at]) return;
  kept_free(page_pics->held[at]);
  page_pics->held[at] = nullptr;
}
// The picture of `page`, when it has one.
inline PagePicture *page_picture_of(int page) {
  if (!page_pics) return nullptr;
  const size_t at = page_pics->shelf.held(page);
  return at == page_pictures::NONE ? nullptr : page_pics->held[at];
}
// The picture's map is of the panel, the turn and the room as they are now; else it is shaped anew, no block true.
inline bool page_picture_shaped(PagePicture &picture) {
  const auto p = glass::panel();
  const glass::Rect room = panel_rect(page_room());
  if (picture.map.fits(p.w, p.h, glass::turn(), room)) return true;
  return picture.map.shape(p.w, p.h, glass::turn(), room);
}
// The picture of the page on the glass, made when it has none yet and the board has the room: the entry of the page
// farthest from it gives its picture up for it.
inline PagePicture *page_picture_for_glass() {
  const size_t capacity = page_pictures_capacity();
  if (!capacity || applied_page < 0) return nullptr;
  if (!page_pics) {
    void *memory = kept_allocate(sizeof(PagePictures));
    if (!memory) return nullptr;
    page_pics = new (memory) PagePictures();
  }
  auto &all = *page_pics;
  if (all.shelf.capacity != capacity) {
    for (size_t i = capacity; i < all.held.size(); ++i) page_picture_free(i);
    all.shelf.forget(capacity);
    all.shelf.capacity = capacity;
  }
  bool fresh = false;
  const size_t at = all.shelf.take(applied_page, static_cast<int>(page_count()), settings_screen::loop_pages != 0, fresh);
  if (at == page_pictures::NONE) return nullptr;
  if (!all.held[at]) {
    // Not right after memory was short: what was refused has its turn first.
    if (all.yielded_at && esphome::millis() - all.yielded_at < page_pictures::YIELD_REST_MS) {
      all.shelf.entries[at] = page_pictures::Shelf::Entry{};
      return nullptr;
    }
    const size_t bytes = page_picture_bytes(), head = (sizeof(PagePicture) + 63) / 64 * 64;
    // The picture store's budget and a full camera's room must stay free after it (page_pictures::reserve); free sizes
    // only, the PSRAM heap is never walked while the glass is lit.
    void *memory = page_pictures::affords(psram_free(), hw::caps().psram_bytes, bytes + head)
                       ? heap_caps_aligned_alloc(64, head + bytes, MALLOC_CAP_SPIRAM) : nullptr;
    if (!memory) {
      all.shelf.entries[at] = page_pictures::Shelf::Entry{};
      page_pictures_say("no PSRAM to spare for another picture");
      return nullptr;
    }
    all.held[at] = new (memory) PagePicture();
    all.held[at]->pixels = reinterpret_cast<uint16_t *>(static_cast<uint8_t *>(memory) + head);
    ESP_LOGI("page_pic", "memory for another page's picture (%u of %u, %u KB), PSRAM free %u B", (unsigned) at + 1,
             (unsigned) capacity, (unsigned) (bytes >> 10), (unsigned) psram_free());
  }
  if (fresh) { all.held[at]->map = page_pictures::Map{}; all.held[at]->left = false; all.held[at]->card_count = 0; all.held[at]->still = page_pictures::Stillness{}; }
  return page_picture_shaped(*all.held[at]) ? all.held[at] : nullptr;
}
// The cards on the glass, each with the tile it shows and where it lies on the panel, with the gap around it: whatever
// a card draws around itself (a shadow, a ring) lies in the gap to the next card.
inline size_t page_picture_cards(std::array<page_pictures::Card, CELLS_MAX> &cards) {
  size_t n = 0;
  const int32_t gap = tile_grid ? std::max(lv_obj_get_style_pad_row(tile_grid, LV_PART_MAIN), lv_obj_get_style_pad_column(tile_grid, LV_PART_MAIN)) : 0;
  for (auto &w : widgets) {
    if (!w.tile || w.index >= model.count || lv_obj_has_flag(w.tile, LV_OBJ_FLAG_HIDDEN)) continue;
    lv_area_t a;
    lv_obj_get_coords(w.tile, &a);
    lv_area_increase(&a, gap, gap);
    cards[n++] = page_pictures::Card{static_cast<uint32_t>(w.index), panel_rect(a)};
  }
  return n;
}
// Nothing lies over the page's room: no open card, alert, screensaver, popup, loading screen or anything else LVGL
// would draw there, found as the live tiles find it (drawn_over), so a new overlay needs no line here.
inline bool page_room_clear() {
  if (!tile_grid || lv_obj_get_screen(tile_grid) != lv_screen_active()) return false;
  const lv_area_t a = page_room();
  return !drawn_over(tile_grid, a.x1, a.y1, a.x2 - a.x1 + 1, a.y2 - a.y1 + 1);
}
// What LVGL is about to draw (or has waiting to draw) makes the blocks under it untrue (`untrue`; not in the turn's own
// redraw), and is when those blocks last moved.
inline void page_picture_areas(PagePicture &picture, bool untrue = true) {
  glass::Rect areas[glass::MAX_WAITING];
  const int n = glass::waiting(areas, glass::MAX_WAITING);
  const uint32_t now = esphome::millis();
  for (int i = 0; i < n && i < glass::MAX_WAITING; ++i) {
    const glass::Rect area = panel_rect(areas[i]);
    if (untrue) picture.map.untrue(area);
    picture.still.drawn(picture.map, area, now);
  }
}
// The turn's own redraw: LVGL draws the page the picture was put for, pixel for pixel what the put blocks hold, so they
// stay true; but a card whose tile took a change number after the put is drawn with that change, and is not.
inline void page_picture_turned(PagePicture &picture) {
  std::array<page_pictures::Card, CELLS_MAX> cards;
  const size_t n = page_picture_cards(cards);
  page_pictures::settle(picture.map, cards.data(), n, changes, page_pics->turned_at);
}
// LVGL starts drawing (LV_EVENT_RENDER_START, its areas joined): the page on the glass loses the blocks it draws.
inline void page_pictures_drawing(lv_event_t *) {
  if (!page_pics) return;
  auto &all = *page_pics;
  auto *picture = page_picture_of(applied_page);
  if (all.turned >= 0 && all.turned == applied_page && picture) {
    page_picture_turned(*picture);
    page_picture_areas(*picture, false);
#ifdef SWIPE_PROFILE
    all.compare = true;
#endif
  } else if (picture) {
    page_picture_areas(*picture);
  }
  all.turned = -1;
}
// A page leaves the glass (show_page, before its cards go onto the shelf and after its live tiles were halted): what
// LVGL still has waiting to draw for it is not on its picture, a stream's last picture may still lie on the glass, and
// the number its cards are drawn up to stays with the picture, for what it lacks when it comes back.
inline void page_pictures_leave() {
  if (!page_pics) return;
  auto &all = *page_pics;
  const size_t at = all.shelf.held(applied_page);
  auto *picture = at == page_pictures::NONE ? nullptr : all.held[at];
  if (picture) {
    if (tile_grid) lv_obj_update_layout(tile_grid);
    if (all.turned == applied_page) page_picture_turned(*picture);  // turned away before LVGL drew it
    else page_picture_areas(*picture);
    glass::Rect spots[glass::MAX_ROOMS];
    const int streams = glass::streaming(spots, glass::MAX_ROOMS);
    for (int i = 0; i < streams && i < glass::MAX_ROOMS; ++i) picture->map.untrue(panel_rect(spots[i]));
    // A plugin's tile is never put: a plugin draws by rules of its own, with timers of its own.
    picture->card_count = page_picture_cards(picture->cards);
    for (auto &w : widgets)
      if (w.tile && w.plugin && w.index < model.count)
        for (size_t i = 0; i < picture->card_count; ++i)
          if (picture->cards[i].tile == w.index) picture->map.untrue(picture->cards[i].at);
    picture->left = true;
    all.shelf.entries[at].synced = glass_synced;
  }
  all.turned = -1;
  all.compare = false;
  all.taking = -1;
}
// The screen turns to `page` (show_page, before a card is exchanged or placed): its picture goes on the glass where it
// is still true. Everything else is left as it is, and LVGL draws the whole page next, as it always did.
inline bool page_pictures_put(int page) {
  if (!page_pics || !page_pictures_capacity()) return false;
  auto &all = *page_pics;
  const size_t at = all.shelf.held(page);
  auto *picture = at == page_pictures::NONE ? nullptr : all.held[at];
  if (!picture || !picture->map.shaped() || !picture->left) return false;
  if (!glass::drawing()) { page_pictures_say("LVGL is paused"); return false; }
  if (!page_picture_shaped(*picture) || !picture->map.true_blocks()) return false;  // another room, turn or panel
  if (!page_room_clear()) { page_pictures_say(drawn_over_by ? drawn_over_by : "something over the page"); return false; }
  // What the page lacks since it left: the cards whose tile changed, and everything when everything was asked for.
  if (!page_pictures::settle(picture->map, picture->cards.data(), picture->card_count, changes, all.shelf.entries[at].synced)) return false;
  const uint32_t began = esphome::micros();
  glass::hold();
  if (glass::streaming(nullptr, 0)) {  // a stream still writes the glass: its picture would land over the page's
    glass::release();
    page_pictures_say("a stream writes the glass");
    return false;
  }
  const uint32_t held = esphome::micros();
  const auto &map = picture->map;
  for (int row = 0; row < map.rows; ++row)
    page_pictures::runs(map, row, map.good[row], [&](const glass::Rect &r) { glass::laid(r, picture->pixels); });
  glass::shown(map.room.y, map.room.h);
  glass::release();
  all.turned = page;
  all.turned_at = changes.last;
  all.refused = nullptr;
  const uint32_t done = esphome::micros();
  swipe_profile::picture(map.true_blocks(), map.room_blocks());
  ESP_LOGD("page_pic", "page %d: %u of %u blocks put in %.1f ms (%.1f waiting for the glass)", page + 1, map.true_blocks(),
           map.room_blocks(), (done - held) / 1000.0, (held - began) / 1000.0);
  return true;
}
// A page changed off the glass by something that takes no change number (a section's summary): its picture is true no more.
inline void page_pictures_untrue(int page) {
  if (auto *picture = page_picture_of(page)) picture->map.untrue_all();
}
// Another layout or grid: no picture is of a page any more. The memory stays for the pages to come, but for what a
// layout with fewer pages has no use for.
inline void page_pictures_forget() {
  if (!page_pics) return;
  page_pics->shelf.forget();
  page_pics->turned = page_pics->taking = -1;
  page_pics->compare = false;
  for (size_t i = page_pictures_capacity(); i < page_pics->held.size(); ++i) page_picture_free(i);
}
// A diagnostic build's A/B on one firmware (page_receiver.cpp, op "page_pictures").
inline void page_pictures_switch(bool on) {
  page_pictures_on = on;
  page_pictures_forget();
}
#ifdef SWIPE_PROFILE
// The proof of a put, in a profiling build: once LVGL has drawn the page, every block still true is compared with the
// glass. 0 pixels is what "LVGL draws the page underneath and changes no pixel" means.
inline void page_picture_compare(PagePicture &picture, int page) {
  // What LVGL has waiting to draw is about to be untrue, and is on the glass as it was: left out.
  page_pictures::Map map = picture.map;
  glass::Rect areas[glass::MAX_WAITING];
  const int waiting = glass::waiting(areas, glass::MAX_WAITING);
  for (int i = 0; i < waiting && i < glass::MAX_WAITING; ++i) map.untrue(panel_rect(areas[i]));
  uint32_t differ = 0;
  glass::hold();
  for (int row = 0; row < map.rows; ++row)
    page_pictures::runs(map, row, map.good[row], [&](const glass::Rect &r) {
      const uint32_t n = glass::differs(r, picture.pixels);
      if (n) ESP_LOGW("page_pic", "page %d: %u px differ in panel %d,%d %dx%d", page + 1, (unsigned) n, r.x, r.y, r.w, r.h);
      differ += n;
    });
  glass::release();
  ESP_LOGI("page_pic", "page %d compared with the glass after LVGL drew it: %u px differ in %u true blocks", page + 1,
           (unsigned) differ, map.true_blocks());
}
#endif
// Every PICTURE_STEP_MS: a step of the take for the page on the glass, while it rests and nothing lies over it.
inline void page_pictures_step(lv_timer_t *) {
  // Memory is short: a page's picture is the first thing to go, the farthest from the glass first, one a step. A
  // refusal is known from the heap watch's count, which costs nothing to read; the free PSRAM is the heap's own
  // counter (no walk of the heap, docs/KEPT_PAGES.md), read once a second.
  if (page_pics) {
    auto &all = *page_pics;
    const uint32_t refusals = heap_watch::psram_refused(), at = esphome::millis();
    const bool look = at - all.looked_at >= 1000;
    if (look) all.looked_at = at;
    if (refusals != all.refusals_seen || look) {
      const size_t free = psram_free();
      if (page_pictures::must_yield(refusals, all.refusals_seen, free)) {
        const size_t gone = all.shelf.let_go(applied_page, static_cast<int>(page_count()), settings_screen::loop_pages != 0);
        if (gone != page_pictures::NONE) {
          page_picture_free(gone);
          all.turned = all.taking = -1;
          all.yielded_at = at ? at : 1;
          ESP_LOGI("page_pic", "memory is short (%u B of PSRAM free, %u asks refused): a page's picture goes, %u kept",
                   (unsigned) free, (unsigned) refusals, (unsigned) all.shelf.pages());
          if (all.shelf.pages()) return;  // the next one in the next step, should it still be short
        }
      }
      all.refusals_seen = refusals;
    }
  }
  if (applied_page < 0 || !room_label || !page_pictures_on) return;
  if (page_pics && page_pics->turned >= 0) return;  // LVGL still owes the turn's redraw
  if (!glass::drawing()) return;
#ifdef SWIPE_PROFILE
  if (page_pics && page_pics->compare) {
    page_pics->compare = false;
    if (auto *picture = page_picture_of(applied_page)) page_picture_compare(*picture, applied_page);
    return;
  }
#endif
  // The cheap question first: a picture with nothing left to take, or only what does not stand still, costs a step
  // nothing.
  const uint32_t now = esphome::millis();
  if (auto *have = page_picture_of(applied_page); have && page_picture_shaped(*have)) {
    bool any = false;
    for (int row = 0; row < have->map.rows && !any; ++row)
      any = have->map.wanted(row, have->still.moving(row, now, PICTURE_STILL_MS)) != 0;
    if (!any) return;
  }
  if (!model.configured || !model.ready() || preparing.active || protocol_problem != ProtocolProblem::none) return;
  if (!tiles_seen() || !prepare_idle(now, PICTURE_QUIET_MS) || pressure::level_of(pressure::BACKGROUND) != 0) return;
  if (!page_room_clear()) { page_pictures_say(drawn_over_by ? drawn_over_by : "something over the page"); return; }
  auto *picture = page_picture_for_glass();
  if (!picture) return;
  auto &all = *page_pics;
  auto &map = picture->map;
  const uint32_t began = esphome::micros();
  glass::hold();
  // Where a stream writes the glass, the glass is not LVGL's: those blocks wait until the stream is gone. And what LVGL
  // has waiting to draw is about to change: those wait for it, so a card that never stands still never holds up the rest.
  std::array<uint32_t, page_pictures::MAX_SIDE> skip{};
  glass::Rect areas[glass::MAX_WAITING];
  const int waiting = glass::waiting(areas, glass::MAX_WAITING);
  for (int i = 0; i < waiting && i < glass::MAX_WAITING; ++i)
    map.blocks_of(panel_rect(areas[i]), [&](int row, uint32_t across) { skip[row] |= across; });
  glass::Rect spots[glass::MAX_ROOMS];
  const int streams = glass::streaming(spots, glass::MAX_ROOMS);
  for (int i = 0; i < streams && i < glass::MAX_ROOMS; ++i)
    map.blocks_of(panel_rect(spots[i]), [&](int row, uint32_t across) { skip[row] |= across; });
  size_t bytes = 0;
  bool more = false;
  for (int row = 0; row < map.rows; ++row) {
    const uint32_t blocks = map.wanted(row, skip[row] | picture->still.moving(row, now, PICTURE_STILL_MS));
    if (!blocks) continue;
    const size_t of_row = page_pictures::bytes_of(map, row, blocks);
    if (bytes && bytes + of_row > PICTURE_SLICE_BYTES) { more = true; break; }
    page_pictures::runs(map, row, blocks, [&](const glass::Rect &r) { glass::taken(r, picture->pixels); });
    map.took(row, blocks);
    bytes += of_row;
  }
  glass::release();
  if (!bytes) return;
  if (all.taking != applied_page) { all.taking = applied_page; all.take_began = now; all.take_bytes = all.take_steps = all.take_us = 0; }
  all.take_bytes += bytes;
  all.take_us += esphome::micros() - began;
  ++all.take_steps;
  all.refused = nullptr;
  if (!more) {
    ESP_LOGD("page_pic", "page %d taken: %u KB in %u steps, %.1f ms of the loop over %u ms, %u of %u blocks true, %u pictures kept",
             applied_page + 1, (unsigned) (all.take_bytes >> 10), (unsigned) all.take_steps, all.take_us / 1000.0,
             (unsigned) (esphome::millis() - all.take_began), map.true_blocks(), map.room_blocks(), (unsigned) all.shelf.pages());
    all.taking = -1;
  }
}
// Once, when the first page is rendered: LVGL's drawing is watched from then on, and the take has its timer. Before any
// stream reserves a room, so this hook sees LVGL's areas before the glass's keep-out cuts the streams' out of them.
inline void page_pictures_start() {
  static bool started = false;
  if (started || !hw::caps().page_pictures) return;
  auto *display = lv_display_get_default();
  if (!display) return;
  started = true;
  lv_display_add_event_cb(display, page_pictures_drawing, LV_EVENT_RENDER_START, nullptr);
  lv_timer_create(page_pictures_step, PICTURE_STEP_MS, nullptr);
  ESP_LOGI("page_pic", "page pictures: %u KB a page, a share of %u KB of PSRAM", (unsigned) (page_picture_bytes() >> 10),
           (unsigned) (page_pictures::share(hw::caps().psram_bytes) >> 10));
}
inline unsigned page_pictures_count() { return page_pics ? static_cast<unsigned>(page_pics->shelf.pages()) : 0; }
#else
// A screen without a steady glass keeps no page pictures and turns its pages exactly as before.
inline void page_pictures_start() {}
inline void page_pictures_leave() {}
inline bool page_pictures_put(int) { return false; }
inline void page_pictures_untrue(int) {}
inline void page_pictures_forget() {}
inline void page_pictures_switch(bool) {}
inline unsigned page_pictures_count() { return 0; }
#endif
}  // namespace runtime_tiles
#endif
