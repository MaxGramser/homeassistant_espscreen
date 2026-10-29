"""Runtime tile configuration transported through the normal ESPHome API.

`smart_display: language: nl` (app 0.2.90) builds the screen's texts in that language: the `screen` section of
screen_manager/translations/nl.json, with English for any key it lacks, becomes one table in main.cpp
(screen_text_gen.py, screen_text.h). The shared core sets it from the LANGUAGE substitution, which ESP Screens writes
into a screen's YAML.
"""
import logging

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import socket
from esphome.core import CORE

from . import engine_build, hw_build, modules, p4_build, screen_text_gen

CODEOWNERS = []
AUTO_LOAD = ["json"]
_LOGGER = logging.getLogger(__name__)

CONF_LANGUAGE = "language"


def _language(value):
    value = cv.string_strict(value).strip()
    if not screen_text_gen.LANGUAGE_CODE.fullmatch(value):
        raise cv.Invalid("Expected a language code such as en, nl or pt-BR")
    return value


CONF_FLASH_MB = "flash_mb"
CONF_CAMERA_ORIENTATION = "camera_orientation"


def _camera_orientation(value):
    """How the board mounts its camera's sensor against the glass (CAMERA_ORIENTATION): as the glass, or upside down."""
    value = cv.int_(value)
    if value not in (0, 180):
        raise cv.Invalid(f"CAMERA_ORIENTATION {value}: only 0 and 180 are supported; a sensor turned a quarter against "
                         f"the glass is not (camera_turn.h)")
    return value


CONFIG_SCHEMA = cv.Schema({
    cv.Optional(CONF_LANGUAGE, default="en"): _language,
    # The flash a host build stands in for (tools/render/host.py), which has no esp32 block to read it from.
    cv.Optional(CONF_FLASH_MB): cv.positive_int,
    cv.Optional(CONF_CAMERA_ORIENTATION, default=0): _camera_orientation,
})


# The connections a screen that streams holds open at once beside the ones ESPHome's own components count: a live
# stream for each of live_view::MAX_STREAMS (live_view.h: four tiles, the full view, a plugin's places) and a download in
# each of picture_fetch's three slots (full, thumb, live). ESPHome sums every component's count into
# CONFIG_LWIP_MAX_SOCKETS and allocates a socket only once it opens, so a count that covers them costs a few bytes each.
# Without it a D1001 had 12: four live tiles and the video's three viewers took them, and a fifth tile's still found no
# connection.
P4_STREAM_SOCKETS = 7
PICTURE_SOCKETS = 3


def _engine_of(full_config):
    """This build's row of engine_build.ENGINES: from the chip, and LVGL and PSRAM in the whole configuration."""
    if not CORE.is_esp32:
        return engine_build.ENGINES["software"]
    from esphome.components.esp32 import get_esp32_variant

    return engine_build.ENGINES[
        engine_build.picture_engine(str(get_esp32_variant()).lower(), bool(full_config.get("lvgl")),
                                    "psram" in full_config)
    ]


def _sockets(config):
    import esphome.final_validate as fv

    if "USE_LIVE_VIEW" in _engine_of(fv.full_config.get())["defines"]:
        socket.consume_sockets(P4_STREAM_SOCKETS + PICTURE_SOCKETS, "smart_display")(config)
    return config


FINAL_VALIDATE_SCHEMA = _sockets


# The linker wraps every ESP32 build gets, beside the picture engine's (engine_build.ENGINES): what an abort said, kept
# across the reset (abort_record.h, which defines them).
DIAGNOSTIC_WRAPS = ("panic_abort",)


async def to_code(config):
    wanted = config[CONF_LANGUAGE]
    cg.add_define("SCREEN_CAMERA_ORIENTATION", config[CONF_CAMERA_ORIENTATION])
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
    # The governor's signs from the log (runtime_tiles.h pressure_log, docs/PLATFORM_PLAN.md 4.10): a slot of its own
    # among the logger's listeners, which ESPHome sizes from these requests (a listener added without one is dropped,
    # as the first build of the governor on a reTerminal D1001 showed, 2026-10-28). No fallback: an ESPHome without it
    # stops the build here, and pressure_listen's static_assert stops one that dropped the slot.
    if "logger" in CORE.config:
        from esphome.components import logger

        logger.request_log_listener()
    if CORE.is_esp32:
        for wrap in DIAGNOSTIC_WRAPS:
            cg.add_build_flag(f"-Wl,--wrap={wrap}")
    if _esp32_p4():
        _p4(config)
    if CORE.is_esp32:
        await _engine(config)
    # The capability record's build half (hw.h, docs/PLATFORM_PLAN.md 3.3): what the configuration contains, a speaker, a
    # microphone, an echo canceller, a camera of the board's own, as defines; the boot adds what only it knows.
    for define in hw_build.defines(CORE.config):
        cg.add_define(define)
    _tier(config)


# ---- The tier and its modules (modules.py, docs/MODULES.md) ----
# From the flash ESPHome builds for, so a new board takes its tier without a line in its file. A module's define is
# all that lets its code into the build: a lite screen compiles none of it.
def _flash_mb(config):
    if CONF_FLASH_MB in config:
        return config[CONF_FLASH_MB]
    if not CORE.is_esp32:
        return None
    from esphome.components.esp32 import KEY_ESP32, KEY_FLASH_SIZE

    return int(str(CORE.data[KEY_ESP32][KEY_FLASH_SIZE]).removesuffix("MB"))


def _tier(config):
    tier = modules.tier_for_flash(_flash_mb(config))
    cg.add_define(f"SD_TIER_{tier.upper()}")
    for name in modules.modules_for(tier):
        cg.add_define(modules.MODULES[name]["define"])
    _LOGGER.info("Tier %s: %s", tier, ", ".join(modules.modules_for(tier)) or "no modules")


# ---- The ESP32-P4 boards' network (docs/CAMERA.md, "Live on the P4 boards") ----
# Keyed on the chip, never on a board: a new P4 board has all of this without a line in its file, and the boards with
# less memory never do. The facts themselves are p4_build.py's, free of ESPHome, so tests/test_live_view.py checks them.
def _esp32_p4():
    if not CORE.is_esp32:
        return False
    from esphome.components.esp32 import get_esp32_variant
    from esphome.components.esp32.const import VARIANT_ESP32P4

    return get_esp32_variant() == VARIANT_ESP32P4


def p4_network_options(own):
    """The options a P4 gets, less those the screen's own sdkconfig_options set (p4_build.network_options)."""
    return p4_build.network_options(own)


def _p4(config):
    from esphome.components.esp32 import add_idf_sdkconfig_option

    own = ((CORE.config.get("esp32") or {}).get("framework") or {}).get("sdkconfig_options") or {}
    for name, value in p4_network_options(own).items():
        add_idf_sdkconfig_option(name, value)


# ---- The picture engine, the glass and the live streams (engine_build.py; docs/PICTURE_ARCHITECTURE.md, 3.9) ----
# On a P4 with LVGL the hardware JPEG decoder and the PPA write the decoded pictures into the panel's frame buffer past
# LVGL (picture_engine_p4.cpp, glass_dsi.cpp, live_view.cpp); the panel's handle is picked up as ESP-IDF makes it for
# ESPHome's display, whichever display platform that is. On an S3 with LVGL and PSRAM Espressif's software decoder
# turns a JPEG still into the pixels LVGL draws (picture_engine_s3.cpp), and a live tile's picture into the RGB panel's
# frame buffer past LVGL (glass_rgb.cpp, live_view.cpp). Every other build has the headers' inline stubs, nothing added.
async def _engine(config):
    from esphome.components.esp32 import add_idf_component

    lvgl = CORE.config.get("lvgl")
    lvgl = lvgl[0] if isinstance(lvgl, list) else lvgl
    engine = _engine_of(CORE.config)
    for define in engine["defines"]:
        cg.add_define(define)
    # The linker wraps the engine and the glass need: the panel as ESP-IDF makes it and every PPA client's bursts (so
    # the panel's own DMA keeps up: glass.h, "The panel's share of the memory bus"), and the guard that copies a turned
    # block the 2D-DMA would never finish in pieces (ppa_guard.h).
    for wrap in engine["wraps"]:
        cg.add_build_flag(f"-Wl,--wrap={wrap}")
    for name, ref in engine["components"]:
        add_idf_component(name=name, ref=ref)
    if any(define.startswith("GLASS_") for define in engine["defines"]):
        from esphome.const import CONF_ID

        component = await cg.get_variable(lvgl[CONF_ID])
        cg.add(cg.RawExpression(f"glass::bind({component})"))


# ---- Plugins (docs/PLUGINS.md) ----
# The plugin API this core offers: plugin_api.h's PLUGIN_API_MAJOR/MINOR and the add-on's plugin_manifest.PLUGIN_API
# (a test keeps the three equal). A plugin builds on the same major from its own minor up, unless a minor between its
# own and this one changed the meaning of a name while the major is 0 (PLUGIN_API_BREAKS, the same as plugin_manifest.py's).
PLUGIN_API = (0, 24)
PLUGIN_API_BREAKS = {0: (4,)}
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
    broke = [b for b in PLUGIN_API_BREAKS.get(major, ()) if minor < b <= PLUGIN_API[1]] if fits else []
    offered = f"{PLUGIN_API[0]}.{PLUGIN_API[1]}"
    if broke:
        raise cv.Invalid(f"Plugin {manifest.get('id')} was written for plugin API {wanted}; plugin API {major}.{broke[-1]} "
                         f"changed a name it may use, and this firmware offers {offered}. Update the plugin.")
    if not fits:
        raise cv.Invalid(f"Plugin {manifest.get('id')} wants plugin API {wanted or '?'}; this firmware offers {offered}. "
                         "Update the plugin, or the screen's firmware.")
    # The whole plugin API goes into this build only now that it has a plugin (plugin_host.cpp, USE_TESSERA_PLUGINS).
    cg.add_define("USE_TESSERA_PLUGINS")
    cg.add(var.set_identity(str(manifest["id"]), str(manifest["version"])))
    # A plugin that brings the screen's own camera (the feature `camera`, ts_camera): the core watches it by itself and
    # shows its dot while Home Assistant uses it (plugin API 0.17, docs/PICTURES.md "Capture"), whatever the plugin does.
    if "camera" in (manifest.get("provides") or []):
        from esphome.core import ID
        camera = await cg.get_variable(ID("ts_camera"))
        cg.add(cg.RawStatement(f"plugin_host::watch_camera({camera});"))
    for tile in manifest.get("tiles") or []:
        memory = tile.get("memory")
        if not isinstance(memory, int) or isinstance(memory, bool) or not 64 <= memory <= 16384:
            raise cv.Invalid(f"Plugin {manifest.get('id')}: tile {tile.get('id')} names its memory in bytes, 64 to 16384 "
                             "(tessera-plugin.yaml, tiles[].memory)")
        cg.add(var.set_memory(str(tile["id"]), memory))
    # A screensaver that moves itself (plugin API 0.14, `moves: true`): the host leaves it where it draws.
    for saver in manifest.get("savers") or []:
        if saver.get("moves") is True:
            cg.add(var.set_moves(str(saver["id"])))
        # Parts that take taps only on a saver whose manifest says so (`taps: true`), as the editor tells the person.
        if saver.get("taps") is True:
            cg.add(var.set_taps(str(saver["id"])))
        # The step's own picture under the saver (`backdrop: true`): the screen shows it, the saver draws over it.
        if saver.get("backdrop") is True:
            cg.add(var.set_backdrop(str(saver["id"])))
    language = (CORE.config.get("smart_display") or {}).get(CONF_LANGUAGE, "en")
    for key, text in sorted(plugin_texts(folder, language).items()):
        cg.add(var.set_text(key, text))
