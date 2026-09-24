#pragma once

// Stable boundary between the shared LVGL renderer and its hardware host.
// Keep rendering and navigation outside this header; this is only the data and
// operations needed by a display/input adapter.
#define ESP_SCREEN_RENDERER_ABI 3

#ifdef __cplusplus
extern "C" {
#endif

// Browser adapter exports. These wrap the existing firmware renderer; the board
// target continues to use ESPHome's generated display/input setup.
int preview_init(int width, int height, int dpi, int columns, int rows);
const char *preview_receive(const char *protocol_json);
// Outgoing ESPHome requests and their normal action responses; neither renders UI.
const char *preview_next_action(void);
void preview_action_response(unsigned call_id, int success, const char *error);
void preview_time(unsigned milliseconds, unsigned unix_seconds, int offset_seconds);
void preview_touch(int x, int y, int pressed);
void preview_cancel(void);
void preview_render(void);
const unsigned *preview_frame(void);
int preview_page(void);
const char *preview_diagnostics(void);

#ifdef __cplusplus
}
#endif
