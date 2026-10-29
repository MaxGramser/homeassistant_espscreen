"""The picture engine, the glass and the live streams a build gets (docs/PICTURE_ARCHITECTURE.md, section 3.9; docs/
PLATFORM_PLAN.md 3.2): keyed on the chip and on what the build has (LVGL, PSRAM), never on a board, so a new board has
them without a line in its file. Free of ESPHome, so tests/test_live_view.py checks it; __init__.py applies it.

Three things, each a define the C++ builds under, and one may come without the others:

- The engine (picture_engine.h): what turns a picture's bytes into pixels. PICTURE_ENGINE_P4 is the ESP32-P4's hardware
  JPEG decoder and its PPA, which also scales, turns and copies pixels (picture_engine_p4.cpp, with ppa_guard.cpp
  between). PICTURE_ENGINE_S3 is Espressif's software JPEG decoder, esp_new_jpeg, with the ESP32-S3's SIMD, for a board
  with PSRAM to decode into (picture_engine_s3.cpp); it has no 2D engine. Without either, the BMP rows of picture_fetch.
- The glass (glass.h): a frame buffer a task may write past LVGL. GLASS_DSI is a P4's MIPI-DSI panel as ESP-IDF makes it
  (glass_dsi.cpp), GLASS_RGB an S3's RGB panel (glass_rgb.cpp); whether a board's display is one is found at run time
  (glass::direct), and an S3 with another panel shows stills.
- The live streams (live_view.h): USE_LIVE_VIEW, a camera's pictures written onto the glass as they come. They need an
  engine that copies pixels and a glass to copy them onto: a P4's PPA, or an S3's CPU for a live tile's picture as the
  app sends it.

A chip with another decoder or panel kind is a row here, with its own files beside these; nothing in picture_fetch,
live_view, live_spots or runtime_tiles changes for it.
"""

ENGINES = {
    "p4": {
        "defines": ("PICTURE_ENGINE_P4", "GLASS_DSI", "USE_LIVE_VIEW"),
        # The linker wraps the engine and the glass need: the panel picked up as ESP-IDF makes it, the panel watch's
        # frame callback beside the display's and every PPA client's bursts (glass_dsi.cpp), and the guard of every
        # turned copy (ppa_guard.cpp).
        "wraps": ("esp_lcd_new_panel_dpi", "esp_lcd_dpi_panel_register_event_callbacks", "ppa_register_client",
                  "ppa_do_scale_rotate_mirror"),
        "components": (),
    },
    "s3": {
        "defines": ("PICTURE_ENGINE_S3", "GLASS_RGB", "USE_LIVE_VIEW"),
        # The RGB panel picked up as ESP-IDF makes it (glass_rgb.cpp), and the decoder's memory from PSRAM first
        # (picture_engine_s3.cpp).
        "wraps": ("esp_lcd_new_rgb_panel", "jpeg_calloc", "jpeg_calloc_inner", "jpeg_calloc_align", "jpeg_calloc_align_inner"),
        # Espressif's registry component, MIT licence; its README has the S3's figures (docs/research/s3-jpeg-2026-10-28.md).
        "components": (("espressif/esp_new_jpeg", "1.0.2"),),
    },
    "software": {"defines": (), "wraps": (), "components": ()},
}


def picture_engine(variant, has_lvgl, has_psram=False):
    """The engine a build gets: 'p4' for an ESP32-P4 with LVGL, 's3' for an ESP32-S3 with LVGL and PSRAM, else
    'software'. `variant` as ESPHome names it, lowercase."""
    if not has_lvgl:
        return "software"
    if variant == "esp32p4":
        return "p4"
    if variant == "esp32s3" and has_psram:
        return "s3"
    return "software"
