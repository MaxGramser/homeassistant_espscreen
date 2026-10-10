"""Runtime tile configuration transported through the normal ESPHome API.

`smart_display: language: nl` (app 0.2.90) builds the screen's texts in that language: the `screen` section of
screen_manager/translations/nl.json, with English for any key it lacks, becomes one table in main.cpp
(screen_text_gen.py, screen_text.h). The shared core sets it from the LANGUAGE substitution, which ESP Screens writes
into a screen's YAML.
"""
import logging

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.core import CORE

from . import screen_text_gen

CODEOWNERS = []
AUTO_LOAD = ["json"]
_LOGGER = logging.getLogger(__name__)

CONF_LANGUAGE = "language"


def _language(value):
    value = cv.string_strict(value).strip()
    if not screen_text_gen.LANGUAGE_CODE.fullmatch(value):
        raise cv.Invalid("Expected a language code such as en, nl or pt-BR")
    return value


CONFIG_SCHEMA = cv.Schema({cv.Optional(CONF_LANGUAGE, default="en"): _language})


async def to_code(config):
    wanted = config[CONF_LANGUAGE]
    language, code = screen_text_gen.definitions(wanted)
    if language != wanted:
        # ESP Screens only writes languages it has; a hand-written one it lacks builds in the nearest it does have.
        _LOGGER.warning("No translation for %s yet; the screen's texts are in %s", wanted, language)
    cg.add_global(cg.RawStatement(code))
    # What the glass says about its network and an update (firmware 0.38.0), from ESPHome's own listeners: after every
    # Wi-Fi scan whether the network was there (wifi_status.h), and an update's progress from whichever OTA platform the
    # screen's own YAML has (ota_status.h). Each asks ESPHome for its slot here; a build without Wi-Fi or OTA (the host
    # renders) asks nothing.
    if "wifi" in CORE.config:
        from esphome.components import wifi

        wifi.request_wifi_scan_results_listener()
    if "ota" in CORE.config:
        from esphome.components import ota

        ota.request_ota_state_listeners()
    if _esp32_p4():
        await _p4(config)


# ---- The ESP32-P4 boards (docs/CAMERA.md, "Live on the P4 boards") ----
# Keyed on the chip, never on a board: a new P4 board has all of this without a line in its file, and the boards
# with less memory never do.
#
# Every P4 board reaches its Wi-Fi through an ESP32-C6 over SDIO (esp_hosted), where a packet's round trip takes long
# enough that ESP-IDF's default TCP receive window of four segments (5,760 bytes) held a download at about 0.7 MB/s.
# A window of 64 KB, as Espressif's own esp_hosted throughput settings have it, gave 2.6 MB/s on the reTerminal D1001
# (2026-10-10). The window applies to every connection, which is why it is the P4's alone: a CYD has 45 KB in one
# piece. A screen's own `sdkconfig_options` keep the last word.
P4_NETWORK = {
    "CONFIG_LWIP_TCP_WND_DEFAULT": 65534,
    "CONFIG_LWIP_TCP_RECVMBOX_SIZE": 64,
    "CONFIG_LWIP_TCPIP_RECVMBOX_SIZE": 64,
}


def _esp32_p4():
    if not CORE.is_esp32:
        return False
    from esphome.components.esp32 import get_esp32_variant
    from esphome.components.esp32.const import VARIANT_ESP32P4

    return get_esp32_variant() == VARIANT_ESP32P4


def p4_network_options(own):
    """The options a P4 gets, less those the screen's own sdkconfig_options set (tests/test_live_view.py)."""
    return {name: value for name, value in P4_NETWORK.items() if name not in own}


async def _p4(config):
    from esphome.components.esp32 import add_idf_sdkconfig_option

    own = ((CORE.config.get("esp32") or {}).get("framework") or {}).get("sdkconfig_options") or {}
    for name, value in p4_network_options(own).items():
        add_idf_sdkconfig_option(name, value)
    # The camera live, full screen (live_view.h): the decoded pictures go into the panel's frame buffer past LVGL. The
    # panel's handle is picked up as ESP-IDF makes it for ESPHome's display, whichever display platform that is.
    lvgl = CORE.config.get("lvgl")
    lvgl = lvgl[0] if isinstance(lvgl, list) else lvgl
    if not lvgl:
        return
    cg.add_define("USE_LIVE_VIEW")
    cg.add_build_flag("-Wl,--wrap=esp_lcd_new_panel_dpi")
    from esphome.const import CONF_ID

    component = await cg.get_variable(lvgl[CONF_ID])
    cg.add(cg.RawExpression(f"live_view::bind({component})"))


# ---- Plugins (docs/PLUGINS.md) ----
# The plugin API this core offers: plugin_api.h's PLUGIN_API_MAJOR/MINOR and the add-on's plugin_manifest.PLUGIN_API
# (a test keeps the three equal). A plugin builds on the same major from its own minor up.
PLUGIN_API = (0, 8)
PLUGIN_MANIFEST = "tessera-plugin.yaml"


def plugin_folder(component_file):
    """The plugin's own folder: the nearest folder above its component that holds tessera-plugin.yaml."""
    from pathlib import Path

    folder = Path(component_file).resolve().parent
    for _ in range(4):
        if (folder / PLUGIN_MANIFEST).is_file():
            return folder
        folder = folder.parent
    raise cv.Invalid(f"No {PLUGIN_MANIFEST} above {component_file}: a plugin's component lives in components/<name>/ "
                     "beside its manifest")


def plugin_texts(folder, language):
    """The plugin's texts for the screen (translations/<language>.json, part "screen"), English for what it lacks."""
    import json

    texts = {}
    for code in ("en", language.split("-")[0], language):
        path = folder / "translations" / f"{code}.json"
        if path.is_file():
            part = json.loads(path.read_text(encoding="utf-8")).get("screen") or {}
            texts.update({k: v for k, v in part.items() if isinstance(v, str)})
    return texts


def read_sound(path):
    """(rate, channels, samples) of a plugin's sound: a WAV file of 16-bit samples, mono or stereo, best at the screen's
    own speaker rate. Anything else is refused with the reason, when the configuration is read (plugin API 0.8)."""
    import wave

    try:
        with wave.open(str(path), "rb") as file:
            if file.getcomptype() != "NONE" or file.getsampwidth() != 2 or file.getnchannels() not in (1, 2):
                raise cv.Invalid(f"{path}: a plugin's sound is a WAV file of 16-bit samples, mono or stereo")
            return file.getframerate(), file.getnchannels(), file.readframes(file.getnframes())
    except (OSError, EOFError, wave.Error) as error:
        raise cv.Invalid(f"{path}: {error}") from error


def sound(owner, name, path):
    """A plugin's sound in flash, as a tessera::Sound for its component (plugin_sound.h): `owner` is the component's id,
    `name` names this sound among its own, `path` is the WAV file in the plugin's folder."""
    from esphome.core import ID, HexInt

    rate, channels, samples = read_sound(path)
    data = cg.progmem_array(ID(f"{owner}_{name}_sound", is_declaration=True, type=cg.uint8), [HexInt(b) for b in samples])
    return cg.StructInitializer(cg.global_ns.namespace("tessera").struct("Sound"), ("data", data),
                                ("length", len(samples)), ("rate", rate), ("channels", channels))


async def register_plugin(var, component_file):
    """What a plugin's component does in to_code after making its object: its id, version, tile memory and texts from its
    manifest and translations, and a check that it was written for this core's plugin API."""
    import yaml

    folder = plugin_folder(component_file)
    manifest = yaml.safe_load((folder / PLUGIN_MANIFEST).read_text(encoding="utf-8")) or {}
    wanted = str(manifest.get("api", ""))
    parts = wanted.split(".")
    ok = len(parts) == 2 and all(p.isdigit() for p in parts)
    major, minor = (int(parts[0]), int(parts[1])) if ok else (-1, -1)
    fits = ok and major == PLUGIN_API[0] and minor <= PLUGIN_API[1]
    if not fits:
        offered = f"{PLUGIN_API[0]}.{PLUGIN_API[1]}"
        raise cv.Invalid(f"Plugin {manifest.get('id')} wants plugin API {wanted or '?'}; this firmware offers {offered}. "
                         "Update the plugin, or the screen's firmware.")
    # The whole plugin API goes into this build only now that it has a plugin (plugin_host.cpp, USE_TESSERA_PLUGINS).
    cg.add_define("USE_TESSERA_PLUGINS")
    cg.add(var.set_identity(str(manifest["id"]), str(manifest["version"])))
    for tile in manifest.get("tiles") or []:
        memory = tile.get("memory")
        memory = memory.get("bytes") if isinstance(memory, dict) else memory
        cg.add(var.set_memory(str(tile["id"]), int(memory)))
    language = (CORE.config.get("smart_display") or {}).get(CONF_LANGUAGE, "en")
    for key, text in sorted(plugin_texts(folder, language).items()):
        cg.add(var.set_text(key, text))
