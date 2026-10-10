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
