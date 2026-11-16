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
// What proves it: tests/test_page_pictures.cpp for the rules; on a board, Debug mode (or a build with
// -DSWIPE_PROFILE=1) compares the glass with the picture after every turn's redraw and says how many pixels differ
// (docs/KEPT_PAGES.md, "The proof on a board").
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
  bool compare = false;      // proving: the glass against the picture once that redraw is done
  // Made ahead: the buffer LVGL draws a page into off the glass (the screen as LVGL lays it out), held while pages
  // still lack a picture, and when the last one was made.
  uint8_t *scratch = nullptr;
  uint32_t ahead_at = 0;
  PagePicture *drawing_ahead = nullptr;  // the picture warm_page's pass is being drawn for
  void *held_memory = nullptr;  // a diagnostic's PSRAM (page_pictures_hold)
  lv_timer_t *hold_timer = nullptr;
  int taking = -1;           // the page a take is on its way for, for its log line
  uint32_t take_began = 0, take_bytes = 0, take_steps = 0, take_us = 0;
  const char *refused = nullptr;  // why the last put or take did not happen, said once
  // Giving memory up (page_pictures::Yield): the PSRAM refusals seen so far, when the free PSRAM was last read, and
  // when a picture last went, after which none takes memory for a while.
  // What the functions below work with, here and not on the loop task's stack: they run in its deepest chains (a page
  // turn inside a layout's apply, LVGL's refresh), where that stack has no kilobyte to spare. One task, so one of each.
  std::array<page_pictures::Card, CELLS_MAX> cards{};          // the cards on the glass (page_picture_turned)
  glass::Rect areas[glass::MAX_WAITING] = {};                  // what LVGL has waiting to draw
  glass::Rect spots[glass::MAX_ROOMS] = {};                    // where streams write the glass
  std::array<uint32_t, page_pictures::MAX_SIDE> skip{};        // the blocks a take leaves out this step
  page_pictures::Map compared;                                 // the map a compare goes by
  page_pictures::Yield yield;
  uint32_t looked_at = 0, yielded_at = 0;
};
inline PagePictures *page_pics = nullptr;
inline bool page_pictures_on = true;  // a diagnostic build's A/B (page_receiver.cpp, op "page_pictures")
// Pictures made ahead, off the glass: off until a board has shown what they need of the loop task's stack; switched on
// for a run by a Debug-mode message (page_receiver.cpp, "ahead"), off again at the next start.
inline bool page_pictures_ahead_on = false;
// A page rests this long before its picture is taken, and a take copies at most this much in one step of the main loop
// (docs/KEPT_PAGES.md has what a step costs).
constexpr uint32_t PICTURE_QUIET_MS = 1000, PICTURE_STEP_MS = 50;
// A block is taken once LVGL has not drawn it for this long: longer than a second, so what draws every second (a
// playing track's bar) is never taken, and short enough for a page someone looks at for a moment.
constexpr uint32_t PICTURE_STILL_MS = 1500;
constexpr size_t PICTURE_SLICE_BYTES = 400u << 10;

// Whether every put is proven afterwards (page_picture_compare): in a profiling build, and with Debug mode on, where
// the 50 ms it takes after a turn are what someone asked for.
inline bool page_pictures_proving() {
#ifdef SWIPE_PROFILE
  return true;
#else
  return settings_screen::debug_mode != 0;
#endif
}
inline void page_pictures_say(const char *why) {
  if (!page_pics || page_pics->refused == why) return;
  page_pics->refused = why;
  if (why) ESP_LOGI("page_pic", "none now: %s", why);
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
// The shelf as the layout and the memory have it now; false without room for any picture.
inline bool page_pictures_shelf() {
  const size_t capacity = page_pictures_capacity();
  if (!capacity || applied_page < 0) return false;
  if (!page_pics) {
    void *memory = kept_allocate(sizeof(PagePictures));
    if (!memory) return false;
    page_pics = new (memory) PagePictures();
  }
  auto &all = *page_pics;
  if (all.shelf.capacity != capacity) {
    for (size_t i = capacity; i < all.held.size(); ++i) page_picture_free(i);
    all.shelf.forget(capacity);
    all.shelf.capacity = capacity;
  }
  return true;
}
// The picture of entry `at`, its memory taken when it has none yet and `extra` more bytes would still be free beside
// it: the picture store's budget and a full camera's room must stay free after it (page_pictures::reserve); free sizes
// only, the PSRAM heap is never walked while the glass is lit. `fresh`: the entry holds nothing of its page yet.
inline PagePicture *page_picture_at(size_t at, bool fresh, size_t extra = 0) {
  auto &all = *page_pics;
  if (!all.held[at]) {
    // Not right after memory was short: what was refused has its turn first.
    const bool resting = all.yielded_at && esphome::millis() - all.yielded_at < page_pictures::YIELD_REST_MS;
    const size_t bytes = page_picture_bytes(), head = (sizeof(PagePicture) + 63) / 64 * 64;
    void *memory = !resting && page_pictures::affords(psram_free(), hw::caps().psram_bytes, bytes + head + extra, pictures.size())
                       ? heap_caps_aligned_alloc(64, head + bytes, MALLOC_CAP_SPIRAM) : nullptr;
    if (!memory) {
      all.shelf.entries[at] = page_pictures::Shelf::Entry{};
      if (!resting) page_pictures_say(page_pictures_log::NO_MEMORY);
      return nullptr;
    }
    all.held[at] = new (memory) PagePicture();
    all.held[at]->pixels = reinterpret_cast<uint16_t *>(static_cast<uint8_t *>(memory) + head);
    ESP_LOGI("page_pic", "memory for another page's picture (%u of %u, %u KB), PSRAM free %u B", (unsigned) at + 1,
             (unsigned) all.shelf.capacity, (unsigned) (bytes >> 10), (unsigned) psram_free());
  }
  if (fresh) { all.held[at]->map = page_pictures::Map{}; all.held[at]->left = false; all.held[at]->card_count = 0; all.held[at]->still = page_pictures::Stillness{}; }
  return page_picture_shaped(*all.held[at]) ? all.held[at] : nullptr;
}
// The picture of the page on the glass, made when it has none yet and the board has the room: the entry of the page
// farthest from it gives its picture up for it.
inline PagePicture *page_picture_for_glass() {
  if (!page_pictures_shelf()) return nullptr;
  bool fresh = false;
  const size_t at = page_pics->shelf.take(applied_page, static_cast<int>(page_count()), settings_screen::loop_pages != 0, fresh);
  return at == page_pictures::NONE ? nullptr : page_picture_at(at, fresh);
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
  glass::Rect *areas = page_pics->areas;
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
  auto &cards = page_pics->cards;
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
    all.compare = page_pictures_proving();
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
    glass::Rect *spots = all.spots;
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
  if (!glass::drawing()) { page_pictures_say(page_pictures_log::PAUSED); return false; }
  if (!page_picture_shaped(*picture) || !picture->map.true_blocks()) return false;  // another room, turn or panel
  if (!page_room_clear()) { page_pictures_say(drawn_over_by ? drawn_over_by : page_pictures_log::COVERED); return false; }
  // What the page lacks since it left: the cards whose tile changed, and everything when everything was asked for.
  if (!page_pictures::settle(picture->map, picture->cards.data(), picture->card_count, changes, all.shelf.entries[at].synced)) return false;
  const uint32_t began = esphome::micros();
  glass::hold();
  if (glass::streaming(nullptr, 0)) {  // a stream still writes the glass: its picture would land over the page's
    glass::release();
    page_pictures_say(page_pictures_log::STREAMING);
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
  ESP_LOGI("page_pic", "page %d: %u of %u blocks put in %.1f ms (%.1f waiting for the glass)", page + 1, map.true_blocks(),
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
  if (page_pics->scratch) { heap_caps_free(page_pics->scratch); page_pics->scratch = nullptr; }
}
// A diagnostic build's A/B on one firmware (page_receiver.cpp, op "page_pictures").
inline void page_pictures_switch(bool on) {
  page_pictures_on = on;
  page_pictures_forget();
}
// The proof of a put (page_pictures_proving): once LVGL has drawn the page, every block still true is compared with the
// glass. 0 pixels is what "LVGL draws the page underneath and changes no pixel" means.
inline void page_picture_compare(PagePicture &picture, int page) {
  // What LVGL has waiting to draw is about to be untrue, and is on the glass as it was: left out.
  page_pictures::Map &map = page_pics->compared;
  map = picture.map;
  glass::Rect *areas = page_pics->areas;
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
// ---- Diagnostics over the screen_message action, with Debug mode on (page_receiver.cpp; docs/KEPT_PAGES.md) ----
// What page pictures hold now, and the memory beside them, in one line: the heaps' own counters, read at once, so an A/B
// of the internal RAM needs no wait for a sensor.
inline void page_pictures_report() {
  unsigned kept = 0, truths = 0, of = 0;
  if (page_pics)
    for (size_t i = 0; i < page_pics->held.size(); ++i)
      if (page_pics->held[i] && page_pics->shelf.entries[i].page >= 0) {
        ++kept;
        truths += page_pics->held[i]->map.true_blocks();
        of += page_pics->held[i]->map.room_blocks();
      }
  ESP_LOGI("page_pic", "report: made ahead %s, the loop stack's low mark %u B", page_pictures_ahead_on ? "on" : "off",
           static_cast<unsigned>(uxTaskGetStackHighWaterMark(nullptr)));
  ESP_LOGI("page_pic", "report: %s, %u pictures kept of %u at most (%u KB each, %u of %u blocks true), internal RAM %u B free "
           "(lowest %u), PSRAM %u B free, %u PSRAM asks refused, a record is %u B",
           page_pictures_on ? "on" : "off", kept, (unsigned) page_pictures_capacity(), (unsigned) (page_picture_bytes() >> 10), truths, of,
           (unsigned) heap_caps_get_free_size(MALLOC_CAP_INTERNAL), (unsigned) heap_caps_get_minimum_free_size(MALLOC_CAP_INTERNAL),
           (unsigned) psram_free(), (unsigned) heap_watch::psram_refused(), (unsigned) sizeof(PagePicture));
}
// `mb` MB of PSRAM held for `seconds`, so what gives memory up first can be watched; more than there is asks and is
// refused, which is the other way a picture goes. 0 MB lets go at once.
inline void page_pictures_hold_end(lv_timer_t *) {
  if (!page_pics) return;
  if (page_pics->held_memory) kept_free(page_pics->held_memory);
  page_pics->held_memory = nullptr;
  if (page_pics->hold_timer) lv_timer_delete(page_pics->hold_timer);
  page_pics->hold_timer = nullptr;
  ESP_LOGI("page_pic", "hold: let go, PSRAM %u B free", (unsigned) psram_free());
}
inline void page_pictures_hold(unsigned mb, unsigned seconds) {
  if (!page_pics) { ESP_LOGI("page_pic", "hold: no page pictures yet"); return; }
  page_pictures_hold_end(nullptr);
  if (!mb) return;
  page_pics->held_memory = kept_allocate(static_cast<size_t>(mb) << 20);
  ESP_LOGI("page_pic", "hold: %u MB of PSRAM for %u s %s, PSRAM %u B free", mb, seconds, page_pics->held_memory ? "held" : "refused",
           (unsigned) psram_free());
  if (!page_pics->held_memory) return;
  page_pics->hold_timer = lv_timer_create(page_pictures_hold_end, std::min(seconds, 600u) * 1000u, nullptr);
}
// ---- Made ahead: a page that was never on the glass gets its picture off it ----
// As the kept pages have the cards of every page before anyone turns to it, a layout has the picture of every page:
// in idle moments LVGL draws a page that lacks one into a buffer instead of the panel (its snapshot, which a board
// with pictures has compiled in), and the page's room goes into the picture turned as the panel is. One page is one
// draw LVGL cannot be stopped in, about as long as a page turn's; so it starts only on a screen nobody uses, and a
// touch that comes meanwhile waits for it.
#if LV_USE_SNAPSHOT
constexpr uint32_t PICTURE_AHEAD_QUIET_MS = 3000, PICTURE_AHEAD_GAP_MS = 1000;
// Not in the first moments of a layout: its values, its covers and its first pictures are still arriving.
constexpr uint32_t PICTURE_AHEAD_START_MS = 15000;
inline void page_picture_scratch_free() {
  if (page_pics && page_pics->scratch) { heap_caps_free(page_pics->scratch); page_pics->scratch = nullptr; }
}
// LVGL draws the screen as it stands now into the scratch buffer; the room of it goes into `picture`, turned.
inline bool page_picture_drawn(PagePicture &picture, uint32_t &drew_us, uint32_t &turned_us) {
  auto *display = lv_display_get_default();
  const int sw = lv_display_get_horizontal_resolution(display), sh = lv_display_get_vertical_resolution(display);
  const auto p = glass::panel();
  const size_t bytes = static_cast<size_t>(sw) * sh * 2;
  // Each way this can fail says so, with its numbers: the buffer's memory, LVGL's own buffer record, LVGL's draw.
  if (!page_pics->scratch && page_pictures::affords_scratch(psram_free(), bytes))
    page_pics->scratch = static_cast<uint8_t *>(heap_caps_aligned_alloc(64, bytes, MALLOC_CAP_SPIRAM));
  if (!page_pics->scratch) {
    ESP_LOGI("page_pic", "off the glass: no memory for the buffer of %u B (%u B of PSRAM free, %u B must stay free beside it)",
             (unsigned) bytes, (unsigned) psram_free(), (unsigned) kept_pages::KEEP_RESERVE);
    return false;
  }
  lv_draw_buf_t buffer;
  const lv_result_t made = lv_draw_buf_init(&buffer, sw, sh, LV_COLOR_FORMAT_RGB565, sw * 2, page_pics->scratch, bytes);
  if (made != LV_RESULT_OK) {
    ESP_LOGI("page_pic", "off the glass: LVGL takes no buffer of %d x %d RGB565, stride %d, %u B (result %d)", sw, sh, sw * 2,
             (unsigned) bytes, (int) made);
    return false;
  }
  const uint32_t began = esphome::micros();
  lv_obj_update_layout(lv_screen_active());
  const lv_result_t drawn = lv_snapshot_take_to_draw_buf(lv_screen_active(), LV_COLOR_FORMAT_RGB565, &buffer);
  if (drawn != LV_RESULT_OK) {
    ESP_LOGI("page_pic", "off the glass: LVGL did not draw the screen (result %d): screen %d x %d, buffer %u x %u, stride %u, %u B",
             (int) drawn, sw, sh, (unsigned) buffer.header.w, (unsigned) buffer.header.h, (unsigned) buffer.header.stride,
             (unsigned) buffer.data_size);
    return false;
  }
  const uint32_t drew = esphome::micros();
  if (!page_pictures::turned(buffer.data, sw, sh, buffer.header.stride, picture.pixels, p.w, p.h, glass::turn(), picture.map.room, p.swapped)) {
    ESP_LOGI("page_pic", "off the glass: the screen LVGL drew (%d x %d) is not the panel (%d x %d) turned %d", sw, sh, p.w, p.h, glass::turn());
    return false;
  }
  drew_us = drew - began;
  turned_us = esphome::micros() - drew;
  return true;
}
// Whether anything on a card moves by itself: an animation runs on one of its objects (a spinner, a label that scrolls).
inline bool page_picture_moves(lv_obj_t *o, int depth = 0) {
  if (!o || lv_obj_has_flag(o, LV_OBJ_FLAG_HIDDEN)) return false;
  if (lv_anim_get(o, nullptr)) return true;
  if (depth >= 8) return true;  // deeper than a card goes: not known to stand still
  for (uint32_t i = 0; i < lv_obj_get_child_count(o); ++i)
    if (page_picture_moves(lv_obj_get_child(o, i), depth + 1)) return true;
  return false;
}
// The one rule for what of a page drawn off the glass is true: a card that will look on the glass exactly as it was
// drawn here. Not a plugin's tile (it draws by rules of its own), not a card that shows time (drawn a while before
// anyone turns to it: a playing track's bar, a clock, a timer), not a tile whose look depends on being seen (a camera,
// an image, a player, anything with a picture: Tile::seen_to_look_right; five camera tiles made ahead differed from
// the glass in 40 pixels on a Guition 10.1, 2026-11-16), and not a card on which anything moves by itself.
inline bool page_picture_ahead_true(const Widgets &w, const Tile &t) {
  return !w.plugin && !shows_time(t) && !t.seen_to_look_right() && !page_picture_moves(w.tile);
}
// warm_page has the page's cards on the glass's place and up to date, with LVGL's invalidation off: now it is drawn.
inline void page_picture_ahead_drawn(int page) {
  auto *picture = page_pics ? page_pics->drawing_ahead : nullptr;
  if (!picture) return;
  page_pics->drawing_ahead = nullptr;
  uint32_t drew = 0, turn = 0;
  picture->map.untrue_all();
  if (!page_picture_shaped(*picture) || !page_picture_drawn(*picture, drew, turn)) return;
  auto &map = picture->map;
  for (int row = 0; row < map.rows; ++row) map.took(row, map.in_room[row]);
  // What the glass may show otherwise is left to LVGL (page_picture_ahead_true): the rest of the page is true.
  picture->card_count = page_picture_cards(picture->cards);
  for (auto &w : widgets) {
    if (!w.tile || w.index >= model.count || lv_obj_has_flag(w.tile, LV_OBJ_FLAG_HIDDEN)) continue;
    if (page_picture_ahead_true(w, model.tiles[w.index])) continue;
    for (size_t i = 0; i < picture->card_count; ++i)
      if (picture->cards[i].tile == w.index) map.untrue(picture->cards[i].at);
  }
  picture->still = page_pictures::Stillness{};
  picture->left = true;
  const size_t at = page_pics->shelf.held(page);
  if (at != page_pictures::NONE) page_pics->shelf.entries[at].synced = changes.last;
  ESP_LOGI("page_pic", "page %d made ahead, off the glass: drawn in %.1f ms, turned in %.1f ms, %u of %u blocks true, %u pictures kept",
           page + 1, drew / 1000.0, turn / 1000.0, map.true_blocks(), map.room_blocks(), (unsigned) page_pics->shelf.pages());
}
// A step of making ahead: the nearest page that lacks a picture, when the screen is idle. True when it made one.
inline bool page_pictures_ahead(uint32_t now) {
  if (!page_pictures_shelf()) return false;
  auto &all = *page_pics;
  const int pages = static_cast<int>(page_count());
  const bool loop = settings_screen::loop_pages != 0;
  // A page lacks one when it has none, or one with nothing true (another look since); and only a kept page can be
  // drawn off the glass, as its cards are what is drawn.
  const int page = all.shelf.next_ahead(applied_page, pages, loop, [&](int candidate) {
    if (!shelf.keeps(candidate)) return false;
    auto *have = page_picture_of(candidate);
    if (!have || !have->left) return true;
    // Nothing true because everything was asked to be drawn since (another look): made again, once.
    const size_t entry = all.shelf.held(candidate);
    return !have->map.true_blocks() && entry != page_pictures::NONE && changes.all_after(all.shelf.entries[entry].synced);
  });
  if (page < 0) { page_picture_scratch_free(); return false; }
  if (!layout_landed_at || now - layout_landed_at < PICTURE_AHEAD_START_MS) return false;
  if (now - all.ahead_at < PICTURE_AHEAD_GAP_MS || !prepare_idle(now, PICTURE_AHEAD_QUIET_MS)) return false;
  if (glass::streaming(nullptr, 0) || !page_room_clear()) return false;
  all.ahead_at = now;
  bool fresh = false;
  const size_t at = all.shelf.take_for(page, applied_page, pages, loop, fresh);
  if (at == page_pictures::NONE) return false;
  // The scratch buffer comes on top of the picture's own memory, while the round lasts.
  auto *picture = page_picture_at(at, fresh, all.scratch ? 0 : page_picture_bytes());
  if (!picture) return false;
  all.drawing_ahead = picture;
  warm_drawn = page_picture_ahead_drawn;
  // The least the loop task's stack ever had free, before and after: LVGL draws a whole page from inside this timer,
  // and whether that goes deeper than a refresh does is read from these two numbers.
  const unsigned stack_before = static_cast<unsigned>(uxTaskGetStackHighWaterMark(nullptr));
  const uint32_t began = esphome::micros();
  warm_page(page);
  warm_drawn = nullptr;
  all.drawing_ahead = nullptr;
  ESP_LOGI("page_pic", "page %d made ahead: the loop stack's low mark %u B before, %u B after", page + 1, stack_before,
           static_cast<unsigned>(uxTaskGetStackHighWaterMark(nullptr)));
  // The whole of what the main loop was held for, on every board that does it: the governor hears a loop held up this
  // long the way it hears any other (ESPHome's own warning, pressure_lvgl.h).
  ESP_LOGI("page_pic", "page %d made ahead: %.1f ms of the loop", page + 1, (esphome::micros() - began) / 1000.0);
  return true;
}
// The proof that a page drawn off the glass is the page on the glass: the picture of the page on the glass is made the
// off-glass way and compared with the glass at once (page_receiver.cpp, with Debug mode on). It is true no more after:
// the next take makes it from the glass again.
inline void page_pictures_prove() {
  auto *picture = page_picture_for_glass();
  if (!picture) {
    ESP_LOGI("page_pic", "prove: no picture for the page on the glass: %u B of PSRAM free, a picture is %u B and %u B must stay "
             "free after it (the store holds %u B of its budget); %u kept of %u at most", (unsigned) psram_free(),
             (unsigned) page_picture_bytes(), (unsigned) page_pictures::reserve(hw::caps().psram_bytes, pictures.size()),
             (unsigned) pictures.size(), page_pictures_count(), (unsigned) page_pictures_capacity());
    return;
  }
  uint32_t drew = 0, turn = 0;
  picture->map.untrue_all();
  const unsigned stack_before = static_cast<unsigned>(uxTaskGetStackHighWaterMark(nullptr));
  if (!page_picture_drawn(*picture, drew, turn)) { ESP_LOGI("page_pic", "prove: LVGL could not draw into a buffer"); return; }
  ESP_LOGI("page_pic", "prove: the loop stack's low mark %u B before the draw, %u B after", stack_before,
           static_cast<unsigned>(uxTaskGetStackHighWaterMark(nullptr)));
  for (int row = 0; row < picture->map.rows; ++row) picture->map.took(row, picture->map.in_room[row]);
  ESP_LOGI("page_pic", "prove: page %d drawn off the glass in %.1f ms and turned in %.1f ms; against the glass:", applied_page + 1,
           drew / 1000.0, turn / 1000.0);
  page_picture_compare(*picture, applied_page);
  picture->map.untrue_all();
  picture->left = false;
  page_picture_scratch_free();
}
#else
inline bool page_pictures_ahead(uint32_t) { return false; }
inline void page_pictures_prove() {}
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
    if (refusals != all.yield.seen || look) {
      const size_t free = psram_free();
      const size_t held = all.shelf.pages() * page_picture_bytes();
      if (all.yield.due(refusals, heap_watch::psram_refused_bytes(), free, held)) {
        if (all.scratch) { heap_caps_free(all.scratch); all.scratch = nullptr; }  // the buffer pages are drawn into ahead, too
        const size_t gone = all.shelf.let_go(applied_page, static_cast<int>(page_count()), settings_screen::loop_pages != 0);
        if (gone != page_pictures::NONE) {
          page_picture_free(gone);
          all.turned = all.taking = -1;
          all.yielded_at = at ? at : 1;
          ESP_LOGI("page_pic", "memory is short (%u B of PSRAM free, %u asks refused): a page's picture goes, %u kept",
                   (unsigned) free, (unsigned) refusals, (unsigned) all.shelf.pages());
        }
      }
    }
  }
  if (applied_page < 0 || !room_label || !page_pictures_on) return;
  if (page_pics && page_pics->turned >= 0) return;  // LVGL still owes the turn's redraw
  if (!glass::drawing()) return;
  if (page_pics && page_pics->compare) {
    page_pics->compare = false;
    if (auto *picture = page_picture_of(applied_page)) page_picture_compare(*picture, applied_page);
    return;
  }
  // The cheap question first: a picture with nothing left to take, or only what does not stand still, costs a step
  // nothing.
  const uint32_t now = esphome::millis();
  if (auto *have = page_picture_of(applied_page); have && page_picture_shaped(*have)) {
    bool any = false;
    for (int row = 0; row < have->map.rows && !any; ++row)
      any = have->map.wanted(row, have->still.moving(row, now, PICTURE_STILL_MS)) != 0;
    if (!any) {
      // The glass's own page has its picture: the pages that lack one are made ahead, the nearest first.
      if (model.configured && model.ready() && !preparing.active && protocol_problem == ProtocolProblem::none && tiles_seen() &&
          pressure::level_of(pressure::BACKGROUND) == 0 && page_pictures_ahead_on)
        page_pictures_ahead(now);
      return;
    }
  }
  if (!model.configured || !model.ready() || preparing.active || protocol_problem != ProtocolProblem::none) return;
  if (!tiles_seen() || !prepare_idle(now, PICTURE_QUIET_MS)) return;
  if (!page_pictures::take_may(governor.step(), governor.cause() == pressure::SLOW_LOOP)) return;
  if (!page_room_clear()) { page_pictures_say(drawn_over_by ? drawn_over_by : page_pictures_log::COVERED); return; }
  auto *picture = page_picture_for_glass();
  if (!picture) return;
  auto &all = *page_pics;
  auto &map = picture->map;
  const uint32_t began = esphome::micros();
  glass::hold();
  // Where a stream writes the glass, the glass is not LVGL's: those blocks wait until the stream is gone. And what LVGL
  // has waiting to draw is about to change: those wait for it, so a card that never stands still never holds up the rest.
  auto &skip = all.skip;
  skip.fill(0);
  glass::Rect *areas = all.areas;
  const int waiting = glass::waiting(areas, glass::MAX_WAITING);
  for (int i = 0; i < waiting && i < glass::MAX_WAITING; ++i)
    map.blocks_of(panel_rect(areas[i]), [&](int row, uint32_t across) { skip[row] |= across; });
  glass::Rect *spots = all.spots;
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
    ESP_LOGI("page_pic", "page %d taken: %u KB in %u steps, %.1f ms of the loop over %u ms, %u of %u blocks true, %u pictures kept",
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
inline void page_pictures_report() {}
inline void page_pictures_hold(unsigned, unsigned) {}
inline void page_pictures_prove() {}
inline unsigned page_pictures_count() { return 0; }
#endif
}  // namespace runtime_tiles
#endif
