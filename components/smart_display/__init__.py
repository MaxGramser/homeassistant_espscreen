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
from esphome.components import microphone, speaker, switch
from esphome.components.esp32 import add_idf_component, require_certificate_bundle

from . import screen_text_gen

CODEOWNERS = []
def AUTO_LOAD(config):
    return ["json", "ring_buffer"] if "voice" in config else ["json"]


PanelVoice = cg.esphome_ns.namespace("smart_display").class_("PanelVoice", cg.Component)
VOICE_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(PanelVoice),
    cv.Required("url"): cv.All(cv.string_strict, cv.url),
    cv.Required("token"): cv.All(cv.string_strict, cv.Length(min=43, max=43)),
    cv.Required("microphone"): microphone.microphone_source_schema(min_bits_per_sample=16, max_bits_per_sample=16,
                                                                   min_channels=1, max_channels=1),
    cv.Required("speaker"): cv.use_id(speaker.Speaker),
    cv.Required("amplifier"): cv.use_id(switch.Switch),
}).extend(cv.COMPONENT_SCHEMA)
_LOGGER = logging.getLogger(__name__)

CONF_LANGUAGE = "language"


def _language(value):
    value = cv.string_strict(value).strip()
    if not screen_text_gen.LANGUAGE_CODE.fullmatch(value):
        raise cv.Invalid("Expected a language code such as en, nl or pt-BR")
    return value


def _audio_options(config):
    if config["audio_tests"] and not config["audio"]:
        raise cv.Invalid("audio_tests requires audio hardware")
    if "voice" in config:
        if not config["audio"] or config["audio_tests"]:
            raise cv.Invalid("voice requires audio hardware without diagnostic tests")
        if not config["voice"]["url"].startswith(("ws://", "wss://")):
            raise cv.Invalid("voice URL must use ws:// or wss://")
    return config


CONFIG_SCHEMA = cv.All(cv.Schema({
    cv.Optional(CONF_LANGUAGE, default="en"): _language,
    cv.Optional("audio", default=False): cv.boolean,
    cv.Optional("audio_tests", default=False): cv.boolean,
    cv.Optional("voice"): VOICE_SCHEMA,
}), _audio_options)

FINAL_VALIDATE_SCHEMA = cv.Schema({
    cv.Optional("voice"): cv.Schema({
        cv.Required("microphone"): microphone.final_validate_microphone_source_schema("panel_voice", sample_rate=16000),
    }, extra=cv.ALLOW_EXTRA),
}, extra=cv.ALLOW_EXTRA)


async def to_code(config):
    wanted = config[CONF_LANGUAGE]
    language, code = screen_text_gen.definitions(wanted, audio=config["audio"], audio_tests=config["audio_tests"], voice="voice" in config)
    if "voice" in config:
        voice = config["voice"]
        cg.add_define("USE_SCREEN_DEVICE_VOICE")
        add_idf_component(name="espressif/esp_websocket_client", ref="1.8.0")
        require_certificate_bundle()
        var = cg.new_Pvariable(voice["id"])
        await cg.register_component(var, voice)
        # Observe the standard wake detector's stream for a short local pre-roll.
        # PanelVoice owns the raw driver's start/stop only during a conversation.
        source = await microphone.microphone_source_to_code(voice["microphone"], passive=True)
        raw = await cg.get_variable(voice["microphone"]["microphone"])
        cg.add(var.set_microphone(source, raw))
        cg.add(var.set_speaker(await cg.get_variable(voice["speaker"])))
        cg.add(var.set_amplifier(await cg.get_variable(voice["amplifier"])))
        cg.add(var.set_url(voice["url"]))
        cg.add(var.set_token(voice["token"]))
    if config["audio"]:
        cg.add_define("USE_SCREEN_AUDIO")
    if config["audio_tests"]:
        cg.add_define("USE_SCREEN_AUDIO_TEST")
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
