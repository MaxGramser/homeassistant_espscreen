// The tile's widgets: the guarded style setters, a tile's sizes, its press feedback, how a card and its extra layer are made.
//
// The part of the tile renderer that draws this with LVGL. It belongs to runtime_tiles.h's translation unit: it is
// included there in its place and uses what stands before it there (the model, the widgets, the cards' shared
// helpers). ESPHome also includes every header of a component on its own (esphome.h): there this file is empty,
// which is what RUNTIME_TILES_PARTS is for.
// What it knows nothing of: what a card of any one entity type shows (render_slot and the cards).
// What proves it: tests/test_editor_parity.py (the sizes), tests/test_card_look.py (the draw callbacks).
#ifdef RUNTIME_TILES_PARTS
namespace runtime_tiles {
// and each real set refreshes the style and invalidates the object (about 0.3 ms on the Guition).
inline void set_color(lv_obj_t *obj, lv_style_prop_t prop, lv_color_t color, lv_style_selector_t selector) {
#if defined(USE_HOST) && defined(SD_MOD_SECTIONS)
  // A card in the other look is painted only inside its scope (CardScope, docs/THEME.md "A card's look"): the host
  // build names a path that paints it in the screen's look, and the render fails on it (tools/render/run.py).
  static unsigned outside = 0;
  if (theme::dark == theme::screen_dark && theme::other_look(obj) && outside++ < 8)
    ESP_LOGE("card_look", "paint outside its card's look FAIL: object %p, style property %d", (void *) obj, (int) prop);
#endif
  lv_style_value_t current;
  if (lv_obj_get_local_style_prop(obj, prop, &current, selector) == LV_STYLE_RES_FOUND && lv_color_eq(current.color, color)) return;
  lv_style_value_t value{}; value.color = color;
  lv_obj_set_local_style_prop(obj, prop, value, selector);
}
inline void set_number(lv_obj_t *obj, lv_style_prop_t prop, int32_t number, lv_style_selector_t selector) {
  lv_style_value_t current;
  if (lv_obj_get_local_style_prop(obj, prop, &current, selector) == LV_STYLE_RES_FOUND && current.num == number) return;
  lv_style_value_t value{}; value.num = number;
  lv_obj_set_local_style_prop(obj, prop, value, selector);
}
// Card sliders follow Home Assistant's control slider (a 42 px track there): corners of 12 and
// 8 px on track and fill, a white handle 4 px wide and half the height, an eighth of the height in
// from the end of the fill, and a fill that never gets shorter than a third of the height. LVGL
// centres the knob on the end of the fill, so the knob is narrowed and moved back; the range starts
// below zero, so at 0 the fill is still that short stub holding the handle. Values below zero never
// leave the slider (see slider_event). Small strips keep round ends: the corners would not show.
inline int slider_handle_width(int height) { return height > 20 ? 4 : 2; }
inline int slider_stub(int height) { return std::max(height / 3, 2 * std::max(1, height / 8) + slider_handle_width(height)); }
inline void slider_handle(lv_obj_t *slider, int width, int height) {
  int handle = slider_handle_width(height), inset = std::max(1, height / 8) + handle / 2, half = height >> 1;
  // Track and fill share one radius: a fill rounded less than its track makes LVGL draw the fill into
  // a buffer of its own size on every redraw (15 KB on a CYD card), which the CYD's heap can't spare.
  int corner = height > 20 ? height * 12 / 42 : LV_RADIUS_CIRCLE;
  set_number(slider, LV_STYLE_RADIUS, corner, LV_PART_MAIN);
  set_number(slider, LV_STYLE_RADIUS, corner, LV_PART_INDICATOR);
  set_number(slider, LV_STYLE_PAD_LEFT, inset + handle / 2 - half, LV_PART_KNOB);
  set_number(slider, LV_STYLE_PAD_RIGHT, handle / 2 - inset - (height - half), LV_PART_KNOB);
  set_number(slider, LV_STYLE_PAD_TOP, -(height / 4), LV_PART_KNOB);
  set_number(slider, LV_STYLE_PAD_BOTTOM, -(height / 4), LV_PART_KNOB);
  int stub = slider_stub(height), below = width > stub ? 1000 * stub / (width - stub) : 0;
  if (lv_slider_get_min_value(slider) != -below || lv_slider_get_max_value(slider) != 1000) lv_slider_set_range(slider, -below, 1000);
}
// A player's keys and volume on a taller card grow with it, up to half again the look's finger key, so a player that
// takes a large card's height reads and plays from across the room (the same key on a 4-inch cell and a 10-inch column).
inline int media_tall_key(int base,int height){return std::clamp(height/6,base,base*3/2);}
// The same handle on a standing slider (a player's volume at the right of its card): the fill rises from the bottom,
// the white bar lies across it an eighth of the slider's width under the end of the fill.
inline void slider_handle_standing(lv_obj_t *slider, int width, int height) {
  int handle = slider_handle_width(width), inset = std::max(1, width / 8) + handle / 2, half = width >> 1;
  int corner = width > 20 ? width * 12 / 42 : LV_RADIUS_CIRCLE;
  set_number(slider, LV_STYLE_RADIUS, corner, LV_PART_MAIN);
  set_number(slider, LV_STYLE_RADIUS, corner, LV_PART_INDICATOR);
  set_number(slider, LV_STYLE_PAD_TOP, handle / 2 - inset - half, LV_PART_KNOB);
  set_number(slider, LV_STYLE_PAD_BOTTOM, inset + handle / 2 - (width - half), LV_PART_KNOB);
  set_number(slider, LV_STYLE_PAD_LEFT, -(width / 4), LV_PART_KNOB);
  set_number(slider, LV_STYLE_PAD_RIGHT, -(width / 4), LV_PART_KNOB);
  int stub = slider_stub(width), below = height > stub ? 1000 * stub / (height - stub) : 0;
  if (lv_slider_get_min_value(slider) != -below || lv_slider_get_max_value(slider) != 1000) lv_slider_set_range(slider, -below, 1000);
}
// An off light or fan shows only the grey track, as in Home Assistant: no fill, no handle.
inline void slider_bar(lv_obj_t *slider, bool shown) {
  set_number(slider, LV_STYLE_BG_OPA, shown ? LV_OPA_COVER : LV_OPA_TRANSP, LV_PART_INDICATOR);
  set_number(slider, LV_STYLE_BG_OPA, shown ? LV_OPA_COVER : LV_OPA_TRANSP, LV_PART_KNOB);
}
inline bool slider_bar_shown(const Tile &t, bool on) { auto d = t.domain(); return on || (d != "light" && d != "fan"); }
inline void set_hidden(lv_obj_t *obj, bool hidden) {
  if (lv_obj_has_flag(obj, LV_OBJ_FLAG_HIDDEN) == hidden) return;  // only a change touches the object
  if (hidden) lv_obj_add_flag(obj, LV_OBJ_FLAG_HIDDEN); else lv_obj_remove_flag(obj, LV_OBJ_FLAG_HIDDEN);
}
// A card's size as its styles request it. LVGL's own getters only follow after a layout pass, and
// that pass walks every object on the screen, so the cards are laid out without asking for one.
// The card's size as the grid laid it out (place_page updates the layout before a card is drawn).
inline int tile_width(const Widgets &w) { return lv_obj_get_width(w.tile); }
inline int tile_height(const Widgets &w) { return lv_obj_get_height(w.tile); }
inline int content_width(const Widgets &w) {
  return tile_width(w) - lv_obj_get_style_space_left(w.tile, LV_PART_MAIN) - lv_obj_get_style_space_right(w.tile, LV_PART_MAIN);
}
// The name of a plain card. The compact look draws it in small letters for a cell of two columns (a CYD lying down);
// a card whose name has more room than that (one column standing up, a double-width card, a 4-inch glass) gets the
// L step of the text set a little larger (WIDE_NAME_FONT in looks/compact.yaml; a bold 14 of its own before firmware
// 0.17.0), so the words are not small in a wide empty card (GitHub #50). The standard look keeps one size. The room is the name's own, after a panel or a graph took
// theirs.
inline const lv_font_t *wide_name_font = nullptr;
inline int wide_name_room() { return ui::mm(30); }
inline const lv_font_t *name_font(const Widgets &w, int room) {
  return !ui::large() && wide_name_font && room >= wide_name_room() ? wide_name_font : w.title_font;
}
inline int content_height(const Widgets &w) {
  return tile_height(w) - lv_obj_get_style_space_top(w.tile, LV_PART_MAIN) - lv_obj_get_style_space_bottom(w.tile, LV_PART_MAIN);
}
// The room a control that fills it takes on a wide card of one row: every cell after the first. The first cell holds
// the icon, the name and the state, as a card of one cell does, and the control fills the cells beside it as if they
// were one card, less a card's padding and border; its edges then stand where the cards in the rows above and below
// have theirs. On a card of two cells that is the second cell; on a card of three, the second and the third (GitHub
// #250: before, one cell at the right end of every wide card, a short slider on a card of three). The look's own
// numbers (panel_metrics) are what one cell of a Guition and a CYD measures, give or take two pixels; a board whose
// grid divides its glass differently (three columns on a 4.3 inch) gets its own cells instead of that number.
inline int rest_content_width(const Widgets &w) {
  const int edges = tile_width(w) - content_width(w);
  if (tile_grid && grid.wide_span() > 1) {
    const int gap = lv_obj_get_style_pad_column(tile_grid, LV_PART_MAIN);
    const int cell = (lv_obj_get_content_width(tile_grid) - (int) (grid.columns - 1) * gap) / (int) grid.columns;
    const int rest = tile_width(w) - cell - gap - edges;
    if (rest > 0) return rest;
  }
  return std::max(1, w.base_width > edges ? w.base_width - edges : content_width(w) / 2);
}
// The head of a card: the icon circle at the left, the name and the state as two lines beside it. One rule for
// every card that draws it (a single or double-width card, the top of a full-page card), whatever grid the board
// has: the row is centred on the room it got, never on a place typed per board, so two rows or three on the same
// glass both stand in the middle. The circle keeps the board's icon size (TILE_ICON_SIZE) while it leaves `edge`
// to the tile's border, standing a little into the padding for that (three rows on 800x480: a 69 px circle in
// 65 px of content); a cell shorter than that shrinks it. The two lines keep the look's own spacing (the
// Guition's 6 px between the name and the state) instead of packing when the rows are short.
struct HeadRow { int circle=0, circle_y=0, text_x=0, title_y=0, value_y=0; };
inline int head_gap(bool large) { return ui::px(large ? 6 : 1); }
inline int head_text_x(int circle, bool large) { return circle + ui::px(large ? 10 : 12); }
// `value_h` is 0 for a card with no second line (firmware 0.2.90+): the name is then the whole head and stands in
// the middle of the room on its own, instead of sitting high with an empty line under it. One rule, so it holds on
// every board and on every cell a grid gives a card.
inline HeadRow head_row(const Widgets &w, bool large, int circle, int room, int title_h, int value_h) {
  HeadRow h;
  const int pad = lv_obj_get_style_space_top(w.tile, LV_PART_MAIN) + lv_obj_get_style_space_bottom(w.tile, LV_PART_MAIN);
  h.circle = std::max(1, std::min(circle, room + pad - 2 * ui::px(large ? 6 : 3)));
  h.circle_y = (room - h.circle) / 2;
  h.title_y = std::max(0, (room - (title_h + (value_h ? head_gap(large) + value_h : 0))) / 2);
  h.value_y = h.title_y + title_h + head_gap(large);
  h.text_x = head_text_x(h.circle, large);
  return h;
}
// A card's strip is thin (8 px on a CYD card), so the whole card belongs to it: a finger that lands above the strip
// still drags it. A press that never moves taps or holds the card instead (slider_event), so nothing is lost.
inline int slider_zone(const Widgets &w, int strip) {
  return std::max(8, (int) lv_obj_get_style_space_top(w.tile, LV_PART_MAIN) + content_height(w) - strip);
}
// A card under a finger (firmware 0.2.95+). The press darkens the card the moment the finger lands (theme::pressed on
// the PRESSED state, in place of the theme's 45 % veil); letting go fades the card back over PRESS_FADE_MS. The fade is
// LVGL's own style transition on the card's background: no object, no layer, one small animation that redraws the
// card alone. LVGL takes the transition of the most specific state that matches the new one, so the PRESSED state
// carries one of 0 ms and the press stays instant; the fade lives on one shared style every card gets in bind().
constexpr uint32_t PRESS_FADE_MS = 200;
struct PressStyles { lv_style_t fade; lv_style_transition_dsc_t release, at_once; };
inline PressStyles &press_styles() {
  static PressStyles s;
  static bool ready = false;
  if (!ready) {
    static const lv_style_prop_t props[] = {LV_STYLE_BG_COLOR, LV_STYLE_BG_OPA, LV_STYLE_PROP_INV};
    lv_style_transition_dsc_init(&s.release, props, lv_anim_path_ease_out, PRESS_FADE_MS, 0, nullptr);
    lv_style_transition_dsc_init(&s.at_once, props, lv_anim_path_linear, 0, 0, nullptr);
    lv_style_init(&s.fade);
    lv_style_set_transition(&s.fade, &s.release);
    ready = true;
  }
  return s;
}
inline void press_feedback(lv_obj_t *tile) {
  auto &s = press_styles();
  lv_obj_add_style(tile, &s.fade, 0);
  lv_obj_set_style_transition(tile, &s.at_once, LV_STATE_PRESSED);
  lv_obj_set_style_bg_opa(tile, LV_OPA_COVER, LV_STATE_PRESSED);
}
// The card's own colour. A new colour ends a fade that may still run from the card this slot showed before (a page
// switch within PRESS_FADE_MS), so the new card never wears the old one's shade: adding a style again is LVGL's way
// to end the transitions of an object.
inline void press_ground(lv_obj_t *tile, lv_color_t colour) {
  lv_style_value_t was;
  if (lv_obj_get_local_style_prop(tile, LV_STYLE_BG_COLOR, &was, 0) == LV_STYLE_RES_FOUND && !lv_color_eq(was.color, colour))
    lv_obj_add_style(tile, &press_styles().fade, 0);
  set_color(tile, LV_STYLE_BG_COLOR, colour);
}
// The circle of a thermostat card with controls switches it on and off (firmware 0.3.3), as the icon of a Home
// Assistant tile does: off is no mode on the card's mode bar. Turning on restores the mode Home Assistant remembers,
// as the card's power key does. render_slot makes the circle clickable for such a card only.
inline void climate_circle_event(lv_event_t *e){
  const unsigned slot=(uintptr_t)lv_event_get_user_data(e);
  if(slot>=widgets.size())return;
  auto &w=widgets[slot];
  if(!enabled||!fresh()||w.index>=model.count)return;
  auto &t=model.tiles[w.index];const uint32_t now=esphome::millis();
  if(!tile_controls::thermostat(t)||!t.available()||t.waiting(now))return;
  if(!allowed(now,2000+slot,"power "+std::to_string(slot)))return;
  climate_power(t);
  refresh_tile(w.index, redraw_log::TileWhy::finger);
}
// The ring of a favourite that plays (ring_favorite marks the card with LV_OBJ_FLAG_USER_1): the accent along the
// card's own edge and corners, over everything the card holds, inside the card's box. Nothing of the card moves.
inline void ring_draw(lv_event_t *e){
  auto *tile=static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  if(!lv_obj_has_flag(tile,LV_OBJ_FLAG_USER_1))return;
  CardScope look(tile);  // LVGL draws it later, outside render_slot: in the card's look
  lv_draw_rect_dsc_t ring;lv_draw_rect_dsc_init(&ring);
  ring.bg_opa=LV_OPA_TRANSP;ring.border_width=ui::px(3);ring.border_opa=LV_OPA_COVER;
  ring.border_color=theme::color(theme::ACCENT);ring.radius=lv_obj_get_style_radius(tile,LV_PART_MAIN);
  lv_area_t box;lv_obj_get_coords(tile,&box);
  lv_draw_rect(lv_event_get_layer(e),&ring,&box);
}
// A card into its set at `index`. Its callbacks name the index and `widgets[index]`: they only fire while the card is on
// the glass, and then that is where it is (the set exchange in keep_page never moves a card to another index).
// `like`: a card of the board's own set whose measurements this one takes over (make_card), instead of laying the grid
// out to measure it; that pass walks every card on the screen, kept ones too, and made a new set cost up to a second.
inline void bind_card(Widgets &into, size_t index, lv_obj_t *tile, lv_obj_t *title, lv_obj_t *value, lv_obj_t *circle, lv_obj_t *icon,
                      const Widgets *like = nullptr) {
  // A card is measured in the cell it will live in (firmware 0.2.92+). Everything below reads the size the card
  // has here, so it is put in the first cell of the grid first: one cell is exactly what a plain single card
  // gets, whatever the board and whichever way its glass hangs. place_page moves it to its real cell later.
  if (!like) {
    if (tile_grid) {
      lv_obj_set_grid_cell(tile, LV_GRID_ALIGN_STRETCH, 0, 1, LV_GRID_ALIGN_STRETCH, 0, 1);
      lv_obj_update_layout(tile_grid);
    }
    lv_obj_update_layout(tile);
  }
  const int width = like ? like->base_width : lv_obj_get_width(tile), height = like ? like->base_height : lv_obj_get_height(tile);
  // Compact cards need room for two text lines and a separate dimmer track.
  if(height<=80){lv_obj_set_style_pad_top(tile,4,0);lv_obj_set_style_pad_bottom(tile,4,0);}
  lv_obj_set_style_border_width(tile,1,0);
  press_feedback(tile);
  if (!like) lv_obj_update_layout(tile);
  into = {tile, title, value, circle, icon, index};
  lv_obj_add_event_cb(circle,climate_circle_event,LV_EVENT_SHORT_CLICKED,(void*)(uintptr_t)index);
  lv_obj_set_style_opa(circle,LV_OPA_60,LV_STATE_PRESSED);
  auto &w=into; w.value_font=lv_obj_get_style_text_font(value,LV_PART_MAIN);
  w.base_width=width;w.base_height=height;w.base_circle=like ? like->base_circle : lv_obj_get_width(circle);
  w.title_font=lv_obj_get_style_text_font(title,LV_PART_MAIN);
  w.icon_font=lv_obj_get_style_text_font(icon,LV_PART_MAIN);
  w.unit=lv_label_create(tile);lv_obj_set_style_text_font(w.unit,w.value_font,0);lv_obj_remove_flag(w.unit,LV_OBJ_FLAG_CLICKABLE);lv_obj_add_flag(w.unit,LV_OBJ_FLAG_HIDDEN);
  lv_label_set_long_mode(w.unit,LV_LABEL_LONG_DOT);
  // Fixed one-line boxes prevent wrapped names from overlapping the state on both boards.
  lv_obj_set_height(title,lv_font_get_line_height(lv_obj_get_style_text_font(title,LV_PART_MAIN)));
  lv_obj_set_height(value,lv_font_get_line_height(w.value_font));
  lv_label_set_long_mode(title,LV_LABEL_LONG_DOT);lv_label_set_long_mode(value,LV_LABEL_LONG_DOT);
  w.progress=lv_obj_create(tile);lv_obj_remove_style_all(w.progress);lv_obj_set_size(w.progress,0,3);lv_obj_align(w.progress,LV_ALIGN_BOTTOM_LEFT,0,0);lv_obj_add_flag(w.progress,LV_OBJ_FLAG_HIDDEN);
  w.slider=lv_slider_create(tile);lv_obj_set_size(w.slider,width-24,ui::px(ui::large()?28:10));lv_obj_align(w.slider,LV_ALIGN_BOTTOM_MID,0,0);lv_slider_set_range(w.slider,0,1000);
  // A short white bar inside the fill as handle, like the control sliders (invisible before 0.2.20).
  int strip=ui::px(ui::large()?28:10);
  lv_obj_add_style(w.slider,theme::style(theme::Paint::knob),LV_PART_KNOB);lv_obj_set_style_bg_opa(w.slider,LV_OPA_COVER,LV_PART_KNOB);
  slider_handle(w.slider,width-24,strip);
  lv_obj_set_style_border_width(w.slider,0,LV_PART_KNOB);lv_obj_set_style_shadow_width(w.slider,0,LV_PART_KNOB);
  // Track and fill follow the card's palette (render_slot), which is drawn before the slider shows.
  lv_obj_set_style_radius(w.slider,2,LV_PART_KNOB);
  lv_obj_add_flag(w.slider,LV_OBJ_FLAG_HIDDEN);
  lv_obj_remove_flag(w.slider,LV_OBJ_FLAG_GESTURE_BUBBLE);
  lv_obj_add_event_cb(w.slider,slider_event,LV_EVENT_ALL,(void*)(uintptr_t)index);
  lv_obj_add_event_cb(tile, event, LV_EVENT_SHORT_CLICKED, &widgets[index]);
  lv_obj_add_event_cb(tile, event, LV_EVENT_LONG_PRESSED, &widgets[index]);
  lv_obj_add_event_cb(tile, ring_draw, LV_EVENT_DRAW_POST, nullptr);
}
// A card: the four styles of packages/core.yaml (card_look), a circle of the board's icon size with its icon, and the
// name and the state. Hidden until a page shows it. Without `like` it is measured in the grid's first cell (bind_card),
// and only hidden after that, as LVGL's grid gives a hidden card no size.
inline void build_card(Widgets &into, size_t index, int circle_size, const lv_font_t *icon_font, const Widgets *like) {
  auto *tile = lv_obj_create(tile_grid);
  if (like) lv_obj_add_flag(tile, LV_OBJ_FLAG_HIDDEN);  // out of the grid's layout from the start
  lv_obj_add_style(tile, card_look.tile, 0);
  lv_obj_set_size(tile, 1, 1);
  auto *circle = lv_obj_create(tile);
  lv_obj_add_style(circle, card_look.circle, 0);
  lv_obj_set_size(circle, circle_size, circle_size);
  auto *icon = lv_label_create(circle);
  lv_obj_set_style_text_font(icon, icon_font, 0);
  lv_obj_align(icon, LV_ALIGN_CENTER, 0, 0);
  auto *title = lv_label_create(tile);
  lv_obj_add_style(title, card_look.title, 0);
  auto *value = lv_label_create(tile);
  lv_obj_add_style(value, card_look.value, 0);
  for (auto *o : {tile, circle}) { lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE); lv_obj_set_scrollbar_mode(o, LV_SCROLLBAR_MODE_OFF); }
  for (auto *o : {circle, icon, title, value}) lv_obj_remove_flag(o, LV_OBJ_FLAG_CLICKABLE);
  bind_card(into, index, tile, title, value, circle, icon, like);
  if (!like) lv_obj_add_flag(tile, LV_OBJ_FLAG_HIDDEN);
}
// A card like the first of the board's set, whose measurements it takes over: the cards of a kept page.
inline void make_card(Widgets &into, size_t index, const Widgets &like) {
  build_card(into, index, like.base_circle, like.icon_font, &like);
}
// The board's own cards, one per cell of the grid the screen runs on, made at boot (packages/core.yaml) from the board's
// icon size and the icon font. They used to be widgets in YAML, a file of them per number of cells (packages/cells/,
// before firmware 0.53.0), which tied a screen to the grid it was built with.
inline int cell_circle = 0;
inline void make_cells(const lv_font_t *icon_font, int circle_size) {
  cell_icon_font = icon_font;
  cell_circle = circle_size;
  for (size_t i = 0; i < grid.slots(); ++i) {
    if (i == 0) build_card(widgets[0], 0, circle_size, icon_font, nullptr);
    else make_card(widgets[i], i, widgets[0]);
  }
}
inline void label(lv_obj_t *obj, const std::string &text) {
  if (text != lv_label_get_text(obj)) lv_label_set_text(obj, text.c_str());
}
// The name in the top bar. Its own copy is the truth about what it says: the dots LVGL writes into the label are
// not a change of name, so they neither set the text again nor pass for the name when the bar measures it.
inline void name_label(lv_obj_t *obj, const std::string &text) {
  if (!obj || (header_named && header_name == text)) return;
  header_named = true;
  header_name = text;
  lv_label_set_text(obj, text.c_str());
}
// lv_obj_set_style_* always invalidates the object; these only do so on a real change,
// which keeps a one-second clock tick or a busy spinner from redrawing whole cards.
inline void set_font(lv_obj_t *obj, const lv_font_t *value) { if (lv_obj_get_style_text_font(obj, LV_PART_MAIN) != value) lv_obj_set_style_text_font(obj, value, 0); }
inline void set_text_align(lv_obj_t *obj, lv_text_align_t value) { if (lv_obj_get_style_text_align(obj, LV_PART_MAIN) != value) lv_obj_set_style_text_align(obj, value, 0); }
inline void pad_vertical(lv_obj_t *obj, int value) {
  if (lv_obj_get_style_pad_top(obj, LV_PART_MAIN) != value) lv_obj_set_style_pad_top(obj, value, 0);
  if (lv_obj_get_style_pad_bottom(obj, LV_PART_MAIN) != value) lv_obj_set_style_pad_bottom(obj, value, 0);
}
inline void set_line_width(lv_obj_t *obj, int value) { if (lv_obj_get_style_line_width(obj, LV_PART_MAIN) != value) lv_obj_set_style_line_width(obj, value, 0); }
// Custom cards draw into a transparent `extra` container; parts are rebuilt only
// when a slot changes mode, so paging keeps RAM use flat on the CYD.
// A slot whose next card draws no custom part only hides them: paging back to the clock or
// graph in that slot reuses its objects instead of creating them again (tens of ms per card).
inline void hide_extra(Widgets &w) {
  if(!w.extra)return;
  if(!lv_obj_has_flag(w.extra,LV_OBJ_FLAG_HIDDEN))lv_obj_add_flag(w.extra,LV_OBJ_FLAG_HIDDEN);
  w.fill_points=nullptr;w.fill_count=0;
  // A plugin's tile goes as soon as its card shows something else (plugin_api.h), not when the slot next draws a custom
  // card: its object first, then its parts, as end_extra does. Its layer holds nothing of Tessera's worth keeping. A
  // kept card set off the glass keeps its plugin tiles: keep_page hides a kept card's tile, never its extra layer.
  if(w.plugin){plugin_host::release(w);lv_obj_clean(w.extra);w.extra_mode.clear();free_points(w.points);}
}
inline void end_extra(Widgets &w) {
  if(!w.extra)return;
  hide_extra(w);
  if(!w.extra_mode.empty()){
    if(captured_slider&&std::find(w.parts.begin(),w.parts.end(),captured_slider)!=w.parts.end()){captured_slider=nullptr;slider_changed=false;}
    if(w.energy)energy_view::release(w);
    if(w.calendar)calendar_view::release(w);
    if(w.meter)meter_view::release(w);
#ifdef SD_MOD_TEXT_CARD
    if(w.text)text_card_view::release(w);
#endif
#ifdef SD_MOD_TODO
    if(w.todo)todo_view::release(w);
#endif
#ifdef SD_MOD_VACUUM_CARD
    if(w.vacuum_face)vacuum_face::release(w);
#endif
    if(w.plugin)plugin_host::release(w);
    lv_obj_clean(w.extra);w.parts.fill(nullptr);w.extra_mode.clear();free_points(w.points);}
}
// Two triangles per segment between the polyline and its baseline. No canvas
// buffer is needed, so the CYD can afford it as well.
// The Widgets whose extra layer this is, wherever keep_page moved it: the slots and the kept sets.
inline Widgets *extra_owner(lv_obj_t *extra) {
  for (auto &w : widgets) if (w.extra == extra) return &w;
  for (auto *set : kept_sets) if (set) for (auto &w : *set) if (w.extra == extra) return &w;
  return nullptr;
}
inline void extra_draw(lv_event_t *e) {
  // The pointer given at creation names the slot the layer was made in; after keep_page swapped Widgets it may be
  // another card's, so the layer's own card is looked up when they differ.
  auto *given=static_cast<Widgets *>(lv_event_get_user_data(e));
  auto *extra=static_cast<lv_obj_t *>(lv_event_get_current_target(e));
  auto *owner=given && given->extra==extra?given:extra_owner(extra);
  if(!owner)return;
  auto &w=*owner;
  if(!w.fill_points || w.fill_count<2 || !w.fill_opa)return;
  auto *layer=lv_event_get_layer(e);lv_area_t area;lv_obj_get_coords(w.extra,&area);
  lv_draw_triangle_dsc_t dsc;lv_draw_triangle_dsc_init(&dsc);dsc.color=w.fill_color;dsc.opa=w.fill_opa;
  const lv_value_precise_t ox=area.x1+w.fill_x, oy=area.y1+w.fill_y, base=oy+w.fill_base;
  for(unsigned i=0;i+1<w.fill_count;++i){
    const auto &a=w.fill_points[i],&b=w.fill_points[i+1];
    dsc.p[0]={ox+a.x,oy+a.y};dsc.p[1]={ox+b.x,oy+b.y};dsc.p[2]={ox+b.x,base};lv_draw_triangle(layer,&dsc);
    dsc.p[1]=dsc.p[2];dsc.p[2]={ox+a.x,base};lv_draw_triangle(layer,&dsc);
  }
}
inline void begin_extra(Widgets &w,const char *mode,int width,int height) {
  if(!w.extra){
    w.extra=lv_obj_create(w.tile);lv_obj_remove_style_all(w.extra);lv_obj_remove_flag(w.extra,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(w.extra,LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_add_event_cb(w.extra,extra_draw,LV_EVENT_DRAW_MAIN,&w);
    // LVGL draws the children of an object whose overflow is visible only as far as its own extra draw size: a clock
    // face asks for the card's padding, so its dial and a date's descenders show up to the card's edge.
    // It reads the object itself and its card, never a Widgets pointer: kept pages swap whole Widgets between a slot
    // and a kept set (keep_page), so a pointer given here would name another card, or a fresh one without parts, and
    // LVGL asks for this size in any layout pass, also of a hidden kept page (firmware 0.3.6 crash-looped on it).
    lv_obj_add_event_cb(w.extra,[](lv_event_t *e){
      auto *extra=static_cast<lv_obj_t *>(lv_event_get_current_target(e));
      auto *tile=extra?lv_obj_get_parent(extra):nullptr;
      if(tile && lv_obj_has_flag(extra,LV_OBJ_FLAG_OVERFLOW_VISIBLE))
        lv_event_set_ext_draw_size(e,std::max({lv_obj_get_style_space_left(tile,LV_PART_MAIN),lv_obj_get_style_space_top(tile,LV_PART_MAIN),
                                               lv_obj_get_style_space_right(tile,LV_PART_MAIN),lv_obj_get_style_space_bottom(tile,LV_PART_MAIN)}));
    },LV_EVENT_REFR_EXT_DRAW_SIZE,nullptr);
  }
  if(w.extra_mode!=mode || w.extra_full!=w.full){end_extra(w);w.extra_mode=mode;w.extra_full=w.full;w.points=(w.extra_mode=="tall"||w.extra_mode=="cover_tilt")?nullptr:new_points();w.paint_again();}
  w.fill_points=nullptr;w.fill_count=0;
  // Parts that were hidden kept the colours of the card they last showed.
  if(lv_obj_has_flag(w.extra,LV_OBJ_FLAG_HIDDEN)){w.paint_again();lv_obj_remove_flag(w.extra,LV_OBJ_FLAG_HIDDEN);}
  lv_obj_set_pos(w.extra,0,0);lv_obj_set_size(w.extra,width,height);
  // A clock face may use the card's padding (firmware 0.3.6+): a dial or flip blocks reach nearer the card's edge
  // on a one-row card, and a big font's letters below the line (a date's y and p) are not cut off.
  const bool face=w.extra_mode=="calm"||w.extra_mode=="flip"||w.extra_mode=="digital"||w.extra_mode=="bedside";
  if(face!=lv_obj_has_flag(w.extra,LV_OBJ_FLAG_OVERFLOW_VISIBLE)){
    if(face)lv_obj_add_flag(w.extra,LV_OBJ_FLAG_OVERFLOW_VISIBLE);else lv_obj_remove_flag(w.extra,LV_OBJ_FLAG_OVERFLOW_VISIBLE);
  }
  // The padding can change with the card (a short cell keeps less of it), so the draw size is asked for every time.
  lv_obj_refresh_ext_draw_size(w.extra);
}
// How far a clock face may reach past the content area into the card's padding: up to a small margin from the edge.
inline int face_reach(const Widgets &w,const Tile &t){
  if(w.full || t.row_span()>1)return 0;
  // The smallest side: a short cell keeps less padding above and below than beside (and a dial reaches up and down).
  const int pad=std::min({lv_obj_get_style_space_left(w.tile,LV_PART_MAIN),lv_obj_get_style_space_top(w.tile,LV_PART_MAIN),
                          lv_obj_get_style_space_bottom(w.tile,LV_PART_MAIN)});
  return std::max(0,pad-ui::px(6));
}
// Catmull-Rom curve through the samples: the trend reads smoothly without extra data.
inline unsigned smooth(const lv_point_precise_t *in,unsigned n,lv_point_precise_t *out,unsigned capacity,int width,int height) {
  if(n<2 || capacity<2){for(unsigned i=0;i<n && i<capacity;++i)out[i]=in[i];return n<capacity?n:capacity;}
  const unsigned steps=4;unsigned count=0;
  for(unsigned i=0;i+1<n;++i){
    const auto &p0=in[i?i-1:0],&p1=in[i],&p2=in[i+1],&p3=in[i+2<n?i+2:n-1];
    for(unsigned s=0;s<steps && count<capacity-1;++s){
      float t=float(s)/steps,t2=t*t,t3=t2*t;
      float x=0.5f*(2*p1.x+(-p0.x+p2.x)*t+(2*p0.x-5*p1.x+4*p2.x-p3.x)*t2+(-p0.x+3*p1.x-3*p2.x+p3.x)*t3);
      float y=0.5f*(2*p1.y+(-p0.y+p2.y)*t+(2*p0.y-5*p1.y+4*p2.y-p3.y)*t2+(-p0.y+3*p1.y-3*p2.y+p3.y)*t3);
      out[count++]={(lv_value_precise_t)std::clamp(x,0.0f,float(width-1)),(lv_value_precise_t)std::clamp(y,0.0f,float(height-1))};
    }
  }
  out[count++]=in[n-1];return count;
}
inline lv_obj_t *part_label(Widgets &w,unsigned i,const lv_font_t *font,int x,int y,int width,lv_text_align_t align,const std::string &text) {
  auto *&p=w.parts[i];
  if(!p){p=lv_label_create(w.extra);lv_label_set_long_mode(p,LV_LABEL_LONG_CLIP);lv_obj_remove_flag(p,LV_OBJ_FLAG_CLICKABLE);}
  set_font(p,font);set_text_align(p,align);
  lv_obj_set_pos(p,x,y);lv_obj_set_size(p,std::max(1,width),lv_font_get_line_height(font));label(p,text);return p;
}
inline lv_obj_t *part_dot(Widgets &w,unsigned i,int x,int y,int size) {
  auto *&p=w.parts[i];
  if(!p){p=lv_obj_create(w.extra);lv_obj_remove_style_all(p);lv_obj_set_style_bg_opa(p,LV_OPA_COVER,0);lv_obj_set_style_radius(p,LV_RADIUS_CIRCLE,0);lv_obj_remove_flag(p,LV_OBJ_FLAG_CLICKABLE);lv_obj_remove_flag(p,LV_OBJ_FLAG_SCROLLABLE);}
  lv_obj_set_pos(p,x,y);lv_obj_set_size(p,size,size);return p;
}
// Points are relative to (x,y): the line object then covers only its own rectangle.
inline lv_obj_t *part_line(Widgets &w,unsigned i,lv_point_precise_t *points,unsigned count,int width,int x=0,int y=0) {
  auto *&p=w.parts[i];
  if(!p){p=lv_line_create(w.extra);lv_obj_remove_flag(p,LV_OBJ_FLAG_CLICKABLE);lv_obj_set_style_line_rounded(p,true,0);}
  set_line_width(p,width);lv_line_set_points(p,points,count);lv_obj_set_pos(p,x,y);return p;
}
// The big digits of the clock card: "07:12" on 24 hours, "7:12" on 12 (the clock font has no letters for AM and PM).
}  // namespace runtime_tiles
#endif  // RUNTIME_TILES_PARTS
