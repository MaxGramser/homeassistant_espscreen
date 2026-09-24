// Generated from the firmware YAML by ESPHome. No host tile renderer.
#include "fonts.h"
static lv_style_t storage__lv_theme_style_obj_main_default; static lv_style_t *_lv_theme_style_obj_main_default = &storage__lv_theme_style_obj_main_default;
static lv_style_t storage__lv_theme_style_obj_main_pressed; static lv_style_t *_lv_theme_style_obj_main_pressed = &storage__lv_theme_style_obj_main_pressed;
static lv_style_t storage__lv_theme_style_arc_main_default; static lv_style_t *_lv_theme_style_arc_main_default = &storage__lv_theme_style_arc_main_default;
static lv_style_t storage__lv_theme_style_arc_knob_default; static lv_style_t *_lv_theme_style_arc_knob_default = &storage__lv_theme_style_arc_knob_default;
static lv_style_t storage__lv_theme_style_arc_knob_pressed; static lv_style_t *_lv_theme_style_arc_knob_pressed = &storage__lv_theme_style_arc_knob_pressed;
static lv_style_t storage__lv_theme_style_slider_main_default; static lv_style_t *_lv_theme_style_slider_main_default = &storage__lv_theme_style_slider_main_default;
static lv_style_t storage__lv_theme_style_slider_knob_default; static lv_style_t *_lv_theme_style_slider_knob_default = &storage__lv_theme_style_slider_knob_default;
static lv_style_t storage__lv_theme_style_slider_knob_pressed; static lv_style_t *_lv_theme_style_slider_knob_pressed = &storage__lv_theme_style_slider_knob_pressed;
static lv_style_t storage_style_page; static lv_style_t *style_page = &storage_style_page;
static lv_style_t storage_style_tile; static lv_style_t *style_tile = &storage_style_tile;
static lv_style_t storage_style_icon_circle; static lv_style_t *style_icon_circle = &storage_style_icon_circle;
static lv_style_t storage_style_room; static lv_style_t *style_room = &storage_style_room;
static lv_style_t storage_style_time; static lv_style_t *style_time = &storage_style_time;
static lv_style_t storage_style_title; static lv_style_t *style_title = &storage_style_title;
static lv_style_t storage_style_value; static lv_style_t *style_value = &storage_style_value;
static lv_style_t storage_style_value_big; static lv_style_t *style_value_big = &storage_style_value_big;
static lv_style_t storage_paint_page_soft; static lv_style_t *paint_page_soft = &storage_paint_page_soft;
static lv_style_t storage_paint_page_pressed; static lv_style_t *paint_page_pressed = &storage_paint_page_pressed;
static lv_style_t storage_paint_raised; static lv_style_t *paint_raised = &storage_paint_raised;
static lv_style_t storage_paint_key; static lv_style_t *paint_key = &storage_paint_key;
static lv_style_t storage_paint_ink; static lv_style_t *paint_ink = &storage_paint_ink;
static lv_style_t storage_paint_ink_soft; static lv_style_t *paint_ink_soft = &storage_paint_ink_soft;
static lv_style_t storage_paint_scrim; static lv_style_t *paint_scrim = &storage_paint_scrim;
static lv_style_t storage_paint_button_dark; static lv_style_t *paint_button_dark = &storage_paint_button_dark;
static lv_style_t storage_paint_button_dark_pressed; static lv_style_t *paint_button_dark_pressed = &storage_paint_button_dark_pressed;
static lv_obj_t *lbl_room;
static lv_obj_t *lbl_time;
static lv_obj_t *tile_scroll;
static lv_obj_t *page_prev;
static lv_obj_t *lv_label_t_id;
static lv_obj_t *page_number;
static lv_obj_t *page_next;
static lv_obj_t *lv_label_t_id_2;
static void setup_firmware_ui(lv_obj_t *root) {

  lv_style_init(_lv_theme_style_obj_main_default);

  lv_style_init(_lv_theme_style_obj_main_pressed);
  lv_style_set_bg_opa(_lv_theme_style_obj_main_pressed, static_cast<uint8_t>(114.75f));

  lv_style_init(_lv_theme_style_arc_main_default);

  lv_style_init(_lv_theme_style_arc_knob_default);

  lv_style_init(_lv_theme_style_arc_knob_pressed);
  lv_style_set_bg_opa(_lv_theme_style_arc_knob_pressed, static_cast<uint8_t>(165.75f));

  lv_style_init(_lv_theme_style_slider_main_default);

  lv_style_init(_lv_theme_style_slider_knob_default);

  lv_style_init(_lv_theme_style_slider_knob_pressed);
  lv_style_set_bg_opa(_lv_theme_style_slider_knob_pressed, static_cast<uint8_t>(165.75f));

  lv_style_init(style_page);
  lv_style_set_bg_opa(style_page, static_cast<uint8_t>(255.0f));
  lv_style_set_border_width(style_page, 0);
  lv_style_set_radius(style_page, 0);

  lv_style_init(style_tile);
  lv_style_set_bg_opa(style_tile, static_cast<uint8_t>(255.0f));
  lv_style_set_border_opa(style_tile, static_cast<uint8_t>(255.0f));
  lv_style_set_border_width(style_tile, 1);
  lv_style_set_pad_bottom(style_tile, 11);
  lv_style_set_pad_left(style_tile, 11);
  lv_style_set_pad_right(style_tile, 11);
  lv_style_set_pad_top(style_tile, 11);
  lv_style_set_radius(style_tile, 19);
  lv_style_set_shadow_opa(style_tile, static_cast<uint8_t>(102.0f));
  lv_style_set_shadow_width(style_tile, 0);

  lv_style_init(style_icon_circle);
  lv_style_set_bg_opa(style_icon_circle, static_cast<uint8_t>(255.0f));
  lv_style_set_border_width(style_icon_circle, 0);
  lv_style_set_radius(style_icon_circle, 999);

  lv_style_init(style_room);
  lv_style_set_text_font(style_room, headline);
  lv_style_set_text_opa(style_room, static_cast<uint8_t>(255.0f));

  lv_style_init(style_time);
  lv_style_set_text_font(style_time, time_label);
  lv_style_set_text_opa(style_time, static_cast<uint8_t>(255.0f));

  lv_style_init(style_title);
  lv_style_set_text_font(style_title, label);
  lv_style_set_text_opa(style_title, static_cast<uint8_t>(255.0f));

  lv_style_init(style_value);
  lv_style_set_text_font(style_value, sublabel);
  lv_style_set_text_opa(style_value, static_cast<uint8_t>(255.0f));

  lv_style_init(style_value_big);
  lv_style_set_text_font(style_value_big, sublabel_big);
  lv_style_set_text_opa(style_value_big, static_cast<uint8_t>(204.0f));

  lv_style_init(paint_page_soft);

  lv_style_init(paint_page_pressed);

  lv_style_init(paint_raised);

  lv_style_init(paint_key);

  lv_style_init(paint_ink);

  lv_style_init(paint_ink_soft);

  lv_style_init(paint_scrim);

  lv_style_init(paint_button_dark);

  lv_style_init(paint_button_dark_pressed);

lv_obj_add_style(root, style_page, (lv_state_t)(LV_PART_MAIN));
  lv_obj_set_style_pad_all(root, 0, LV_PART_MAIN);
  lv_obj_remove_flag(root, (lv_obj_flag_t)(LV_OBJ_FLAG_SCROLLABLE));
  lv_obj_set_scrollbar_mode(root, LV_SCROLLBAR_MODE_OFF);

   lbl_room = lv_label_create(root);
  lv_obj_add_style(lbl_room, style_room, (lv_state_t)(LV_PART_MAIN));
  lv_obj_set_style_x(lbl_room, 14, LV_PART_MAIN);
  lv_obj_set_style_y(lbl_room, 19, LV_PART_MAIN);
  lv_label_set_text(lbl_room, "");

   lbl_time = lv_label_create(root);
  lv_obj_add_style(lbl_time, style_time, (lv_state_t)(LV_PART_MAIN));
  lv_obj_set_style_align(lbl_time, LV_ALIGN_TOP_RIGHT, LV_PART_MAIN);
  lv_obj_set_style_x(lbl_time, -14, LV_PART_MAIN);
  lv_obj_set_style_y(lbl_time, 19, LV_PART_MAIN);
  lv_label_set_text(lbl_time, "");

   tile_scroll = lv_obj_create(root);
  lv_obj_add_style(tile_scroll, _lv_theme_style_obj_main_default, (lv_state_t)(LV_PART_MAIN));
  lv_obj_add_style(tile_scroll, _lv_theme_style_obj_main_pressed, (lv_state_t)(LV_STATE_PRESSED));
  lv_obj_set_layout(tile_scroll, LV_LAYOUT_GRID);
  lv_obj_set_style_pad_row(tile_scroll, 12, LV_STATE_DEFAULT);
  lv_obj_set_style_pad_column(tile_scroll, 12, LV_STATE_DEFAULT);
  static const lv_coord_t tile_scroll_row_dsc[] = {LV_GRID_FR(1), LV_GRID_TEMPLATE_LAST};
  lv_obj_set_style_grid_row_dsc_array(tile_scroll, tile_scroll_row_dsc, LV_STATE_DEFAULT);
  static const lv_coord_t tile_scroll_column_dsc[] = {LV_GRID_FR(1), LV_GRID_TEMPLATE_LAST};
  lv_obj_set_style_grid_column_dsc_array(tile_scroll, tile_scroll_column_dsc, LV_STATE_DEFAULT);
  lv_obj_set_style_bg_opa(tile_scroll, static_cast<uint8_t>(0.0f), LV_PART_MAIN);
  lv_obj_set_style_border_width(tile_scroll, 0, LV_PART_MAIN);
  lv_obj_set_style_height(tile_scroll, 1, LV_PART_MAIN);
  lv_obj_set_style_pad_bottom(tile_scroll, 0, LV_PART_MAIN);
  lv_obj_set_style_pad_left(tile_scroll, 16, LV_PART_MAIN);
  lv_obj_set_style_pad_right(tile_scroll, 16, LV_PART_MAIN);
  lv_obj_set_style_pad_top(tile_scroll, 0, LV_PART_MAIN);
  lv_obj_set_style_width(tile_scroll, 1, LV_PART_MAIN);
  lv_obj_set_style_x(tile_scroll, 0, LV_PART_MAIN);
  lv_obj_set_style_y(tile_scroll, 63, LV_PART_MAIN);
  lv_obj_set_style_bg_opa(tile_scroll, static_cast<uint8_t>(0.0f), LV_STATE_PRESSED);
  lv_obj_remove_flag(tile_scroll, (lv_obj_flag_t)(LV_OBJ_FLAG_SCROLLABLE));
  lv_obj_set_scrollbar_mode(tile_scroll, LV_SCROLLBAR_MODE_OFF);

   page_prev = lv_obj_create(root);
  lv_obj_add_style(page_prev, _lv_theme_style_obj_main_default, (lv_state_t)(LV_PART_MAIN));
  lv_obj_add_style(page_prev, _lv_theme_style_obj_main_pressed, (lv_state_t)(LV_STATE_PRESSED));
  lv_obj_set_style_align(page_prev, LV_ALIGN_BOTTOM_LEFT, LV_PART_MAIN);
  lv_obj_set_style_bg_opa(page_prev, static_cast<uint8_t>(0.0f), LV_PART_MAIN);
  lv_obj_set_style_border_width(page_prev, 0, LV_PART_MAIN);
  lv_obj_set_style_height(page_prev, 53, LV_PART_MAIN);
  lv_obj_set_style_pad_all(page_prev, 0, LV_PART_MAIN);
  lv_obj_set_style_radius(page_prev, 0, LV_PART_MAIN);
  lv_obj_set_style_width(page_prev, lv_pct(50), LV_PART_MAIN);
  lv_obj_set_style_x(page_prev, 0, LV_PART_MAIN);
  lv_obj_set_style_y(page_prev, 0, LV_PART_MAIN);
  lv_obj_add_style(page_prev, paint_page_pressed, (lv_state_t)(LV_STATE_PRESSED));
  lv_obj_set_style_bg_opa(page_prev, static_cast<uint8_t>(255.0f), LV_STATE_PRESSED);
  lv_obj_remove_flag(page_prev, (lv_obj_flag_t)(LV_OBJ_FLAG_SCROLLABLE));

   lv_label_t_id = lv_label_create(page_prev);
  lv_obj_add_style(lv_label_t_id, paint_ink, (lv_state_t)(LV_PART_MAIN));
  lv_obj_set_style_align(lv_label_t_id, LV_ALIGN_LEFT_MID, LV_PART_MAIN);
  lv_obj_set_style_text_font(lv_label_t_id, materialdesign_icons_mini, LV_PART_MAIN);
  lv_obj_set_style_x(lv_label_t_id, 21, LV_PART_MAIN);
  lv_obj_remove_flag(lv_label_t_id, (lv_obj_flag_t)(LV_OBJ_FLAG_CLICKABLE));
  lv_label_set_text(lv_label_t_id, "\363\260\205\201");

   page_number = lv_obj_create(root);
  lv_obj_add_style(page_number, _lv_theme_style_obj_main_default, (lv_state_t)(LV_PART_MAIN));
  lv_obj_add_style(page_number, _lv_theme_style_obj_main_pressed, (lv_state_t)(LV_STATE_PRESSED));
  lv_obj_set_style_align(page_number, LV_ALIGN_BOTTOM_MID, LV_PART_MAIN);
  lv_obj_set_style_bg_opa(page_number, static_cast<uint8_t>(0.0f), LV_PART_MAIN);
  lv_obj_set_style_border_width(page_number, 0, LV_PART_MAIN);
  lv_obj_set_style_height(page_number, 53, LV_PART_MAIN);
  lv_obj_set_style_pad_all(page_number, 0, LV_PART_MAIN);
  lv_obj_set_style_width(page_number, 140, LV_PART_MAIN);
  lv_obj_set_style_y(page_number, 0, LV_PART_MAIN);
  lv_obj_remove_flag(page_number, (lv_obj_flag_t)(LV_OBJ_FLAG_CLICKABLE|LV_OBJ_FLAG_SCROLLABLE));

   page_next = lv_obj_create(root);
  lv_obj_add_style(page_next, _lv_theme_style_obj_main_default, (lv_state_t)(LV_PART_MAIN));
  lv_obj_add_style(page_next, _lv_theme_style_obj_main_pressed, (lv_state_t)(LV_STATE_PRESSED));
  lv_obj_set_style_align(page_next, LV_ALIGN_BOTTOM_RIGHT, LV_PART_MAIN);
  lv_obj_set_style_bg_opa(page_next, static_cast<uint8_t>(0.0f), LV_PART_MAIN);
  lv_obj_set_style_border_width(page_next, 0, LV_PART_MAIN);
  lv_obj_set_style_height(page_next, 53, LV_PART_MAIN);
  lv_obj_set_style_pad_all(page_next, 0, LV_PART_MAIN);
  lv_obj_set_style_radius(page_next, 0, LV_PART_MAIN);
  lv_obj_set_style_width(page_next, lv_pct(50), LV_PART_MAIN);
  lv_obj_set_style_x(page_next, 0, LV_PART_MAIN);
  lv_obj_set_style_y(page_next, 0, LV_PART_MAIN);
  lv_obj_add_style(page_next, paint_page_pressed, (lv_state_t)(LV_STATE_PRESSED));
  lv_obj_set_style_bg_opa(page_next, static_cast<uint8_t>(255.0f), LV_STATE_PRESSED);
  lv_obj_remove_flag(page_next, (lv_obj_flag_t)(LV_OBJ_FLAG_SCROLLABLE));

   lv_label_t_id_2 = lv_label_create(page_next);
  lv_obj_add_style(lv_label_t_id_2, paint_ink, (lv_state_t)(LV_PART_MAIN));
  lv_obj_set_style_align(lv_label_t_id_2, LV_ALIGN_RIGHT_MID, LV_PART_MAIN);
  lv_obj_set_style_text_font(lv_label_t_id_2, materialdesign_icons_mini, LV_PART_MAIN);
  lv_obj_set_style_x(lv_label_t_id_2, -21, LV_PART_MAIN);
  lv_obj_remove_flag(lv_label_t_id_2, (lv_obj_flag_t)(LV_OBJ_FLAG_CLICKABLE));
  lv_label_set_text(lv_label_t_id_2, "\363\260\205\202");
}
static void setup_firmware_cell(size_t index) {
lv_obj_t *tile1;
lv_obj_t *tile1_icon_circle;
lv_obj_t *tile1_icon_lbl;
lv_obj_t *t1_title;
lv_obj_t *t1_value;
tile1 = lv_obj_create(tile_scroll);
  lv_obj_add_style(tile1, _lv_theme_style_obj_main_default, (lv_state_t)(LV_PART_MAIN));
  lv_obj_add_style(tile1, _lv_theme_style_obj_main_pressed, (lv_state_t)(LV_STATE_PRESSED));
  lv_obj_add_style(tile1, style_tile, (lv_state_t)(LV_PART_MAIN));
  lv_obj_set_style_height(tile1, 1, LV_PART_MAIN);
  lv_obj_set_style_width(tile1, 1, LV_PART_MAIN);
  lv_obj_set_style_grid_cell_row_pos(tile1, 0, LV_PART_MAIN);
  lv_obj_set_style_grid_cell_column_pos(tile1, 0, LV_PART_MAIN);
  lv_obj_set_style_grid_cell_x_align(tile1, LV_GRID_ALIGN_STRETCH, LV_PART_MAIN);
  lv_obj_set_style_grid_cell_y_align(tile1, LV_GRID_ALIGN_STRETCH, LV_PART_MAIN);
  lv_obj_remove_flag(tile1, (lv_obj_flag_t)(LV_OBJ_FLAG_SCROLLABLE));
  lv_obj_set_scrollbar_mode(tile1, LV_SCROLLBAR_MODE_OFF);

   tile1_icon_circle = lv_obj_create(tile1);
  lv_obj_add_style(tile1_icon_circle, _lv_theme_style_obj_main_default, (lv_state_t)(LV_PART_MAIN));
  lv_obj_add_style(tile1_icon_circle, _lv_theme_style_obj_main_pressed, (lv_state_t)(LV_STATE_PRESSED));
  lv_obj_add_style(tile1_icon_circle, style_icon_circle, (lv_state_t)(LV_PART_MAIN));
  lv_obj_set_style_height(tile1_icon_circle, 47, LV_PART_MAIN);
  lv_obj_set_style_width(tile1_icon_circle, 47, LV_PART_MAIN);
  lv_obj_remove_flag(tile1_icon_circle, (lv_obj_flag_t)(LV_OBJ_FLAG_CLICKABLE|LV_OBJ_FLAG_SCROLLABLE));
  lv_obj_set_scrollbar_mode(tile1_icon_circle, LV_SCROLLBAR_MODE_OFF);

   tile1_icon_lbl = lv_label_create(tile1_icon_circle);
  lv_obj_set_style_align(tile1_icon_lbl, LV_ALIGN_CENTER, LV_PART_MAIN);
  lv_obj_set_style_text_font(tile1_icon_lbl, materialdesign_icons, LV_PART_MAIN);
  lv_obj_remove_flag(tile1_icon_lbl, (lv_obj_flag_t)(LV_OBJ_FLAG_CLICKABLE));
  lv_label_set_text(tile1_icon_lbl, "\363\260\200\252");

   t1_title = lv_label_create(tile1);
  lv_obj_add_style(t1_title, style_title, (lv_state_t)(LV_PART_MAIN));
  lv_obj_remove_flag(t1_title, (lv_obj_flag_t)(LV_OBJ_FLAG_CLICKABLE));
  lv_label_set_text(t1_title, "Tile 1");

   t1_value = lv_label_create(tile1);
  lv_obj_add_style(t1_value, style_value, (lv_state_t)(LV_PART_MAIN));
  lv_obj_remove_flag(t1_value, (lv_obj_flag_t)(LV_OBJ_FLAG_CLICKABLE));
  lv_label_set_text(t1_value, "\342\200\224");


runtime_tiles::bind(index, tile1, t1_title, t1_value, tile1_icon_circle, tile1_icon_lbl);
}
static void bind_firmware_ui() {
theme::paints = []() {
            using theme::Paint;
            for (auto *style : {style_room, style_time, style_title, style_value_big, paint_ink}) theme::fill(style, Paint::ink);
            theme::fill(style_page, Paint::page);
            theme::fill(style_tile, Paint::card);
            theme::fill(style_icon_circle, Paint::accent_tint);
            theme::fill(style_value, Paint::muted);
            theme::fill(paint_page_soft, Paint::page_soft);
            theme::fill(paint_page_pressed, Paint::page_pressed);
            theme::fill(paint_raised, Paint::raised);
            theme::fill(paint_key, Paint::key);
            theme::fill(paint_ink_soft, Paint::ink_soft);
            theme::fill(paint_scrim, Paint::scrim);
            theme::fill(paint_button_dark, Paint::button_dark);
            theme::fill(paint_button_dark_pressed, Paint::button_dark_pressed);};
theme::paints();
runtime_tiles::watch_font = headline;
runtime_tiles::watch_value_font = watch_value;
runtime_tiles::watch_icon_font = watch_icon;
runtime_tiles::clock_font = clock_digits;
runtime_tiles::mini_icon_font = materialdesign_icons_mini;
runtime_tiles::big_icon_font = materialdesign_icons_big;
runtime_tiles::control_font = sublabel_big;
runtime_tiles::small_font = sublabel;
runtime_tiles::header_text_font = sublabel_big;
runtime_tiles::header_icon_font = materialdesign_icons_mini;
runtime_tiles::header_home_font = materialdesign_icons_home;
runtime_tiles::setpoint_font = setpoint_digits;
screen_input::touch_guard.configure(0, 20);
screen_input::edge_swipe.configure(28, 35);
screen_input::edge_snap_band = 59;
lv_obj_remove_flag(lv_screen_active(), LV_OBJ_FLAG_CLICKABLE);
lv_obj_remove_flag(tile_scroll, LV_OBJ_FLAG_CLICKABLE);
runtime_tiles::grid_bind(tile_scroll, 16, 53);
}
