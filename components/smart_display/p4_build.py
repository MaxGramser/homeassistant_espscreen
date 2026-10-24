"""The ESP32-P4's build: the facts that pick a screen's picture engine and glass, and the network of its Wi-Fi
co-processor (docs/PICTURE_ARCHITECTURE.md, section 3.9; docs/CAMERA.md, "Live on the P4 boards").

Keyed on the chip, never on a board: a new P4 board has all of this without a line in its file, and the boards with
less memory never do. Free of ESPHome, so tests/test_live_view.py checks it; __init__.py applies it to the build.
"""

# Every P4 board reaches its Wi-Fi through an ESP32-C6 over SDIO (esp_hosted), where a packet's round trip takes long
# enough that ESP-IDF's default TCP receive window of four segments (5,760 bytes) held a download at about 0.7 MB/s.
# A window of 64 KB, as Espressif's own esp_hosted throughput settings have it, gave 2.6 MB/s on the reTerminal D1001
# (2026-10-10). The window applies to every connection, which is why it is the P4's alone: a CYD has 45 KB in one
# piece. A screen's own `sdkconfig_options` keep the last word.
#
# The send buffer likewise: ESP-IDF's 5,760 bytes let one connection carry about 1.5 Mbit/s over the C6, and Screen
# camera's video (one TCP connection a viewer, docs/CAMERA.md "The screen's own camera as video in Home Assistant") held
# its sound up behind the picture for seconds. And all of it in PSRAM first (ESPHome's `wifi: use_psram` sets the same
# option): what a connection holds unsent or unread lived in internal RAM, which a P4 runs short of. With live camera
# tiles on the glass and the video playing, the reTerminal D1001 went from 160 KB to 13 KB free in two seconds and the
# C6's driver aborted the chip (2026-10-21). A P4's panel is MIPI-DSI with PSRAM to spare, so the reason the ESP32-S3's
# RGB panels keep these buffers inside (packages/hardware/esp32s3-rgb.yaml) does not hold here.
#
# That covers what lwIP allocates itself, not what it receives: esp_hosted hands each packet from the C6 to lwIP without
# a copy (esp_netif_receive with a free callback), so a received packet stays in the driver's own buffer, internal RAM
# that DMA can reach, until the reader of its connection has taken it, and with a window of 64 KB a live stream whose
# reader is busy laying out a picture holds up to that much of it. Two live tiles took the reTerminal D1001 from about
# 250 KB to 60 KB free and left the driver's next buffer of 1,536 bytes without room, 32 times in an hour (heap_watch,
# 2026-10-24), the lost packets the C6's RPC answers die in. LWIP_L2_TO_L3_COPY copies each packet into a buffer of
# lwIP's own, in PSRAM by the option above, and gives the driver's back at once: one copy of 1.5 KB a packet.
P4_NETWORK = {
    "CONFIG_LWIP_TCP_WND_DEFAULT": 65534,
    "CONFIG_LWIP_TCP_SND_BUF_DEFAULT": 65534,
    "CONFIG_LWIP_TCP_RECVMBOX_SIZE": 64,
    "CONFIG_LWIP_TCPIP_RECVMBOX_SIZE": 64,
    "CONFIG_SPIRAM_TRY_ALLOCATE_WIFI_LWIP": True,
    "CONFIG_LWIP_L2_TO_L3_COPY": True,
}


def network_options(own):
    """The options a P4 gets, less those the screen's own sdkconfig_options set."""
    return {name: value for name, value in P4_NETWORK.items() if name not in own}


# The picture engine (picture_engine.h) and the glass (glass.h) a screen is built with. Two engines exist: the P4's,
# whose hardware decodes JPEG and whose PPA scales and turns a picture straight into the panel's frame buffer past LVGL
# (picture_engine_p4.cpp, glass_dsi.cpp), and the software one, the BMP rows of picture_fetch with LVGL drawing every
# still (the inline stubs of both headers). The P4's is chosen by the chip and LVGL; whether the panel gives a frame
# buffer a task may write is a fact the glass finds at run time (glass::direct), so a P4 whose display ESP-IDF did not
# make as MIPI-DSI simply shows stills. A chip with another decoder or 2D engine is a row here, with its own files
# beside the P4's; nothing in picture_fetch, live_view, live_spots or runtime_tiles changes for it.
ENGINES = {
    # The define the P4 engine, the glass and the streams build under (live_view.h, glass.h, picture_engine.h).
    "p4": {"define": "USE_LIVE_VIEW",
           # The linker wraps the engine and the glass need: the panel picked up as ESP-IDF makes it and every PPA
           # client's bursts (glass_dsi.cpp), and the guard of every turned copy (ppa_guard.cpp).
           "wraps": ("esp_lcd_new_panel_dpi", "ppa_register_client", "ppa_do_scale_rotate_mirror")},
    "software": {"define": None, "wraps": ()},
}


def picture_engine(variant, has_lvgl):
    """The engine a build gets: 'p4' for an ESP32-P4 with LVGL (`variant` as ESPHome names it, lowercase), else
    'software'."""
    return "p4" if variant == "esp32p4" and has_lvgl else "software"
