"""Runtime tile configuration transported through the normal ESPHome API.

`smart_display: language: nl` (app 0.2.90) builds the screen's texts in that language: the `screen` section of
screen_manager/translations/nl.json, with English for any key it lacks, becomes one table in main.cpp
(screen_text_gen.py, screen_text.h). The shared core sets it from the LANGUAGE substitution, which ESP Screens writes
into a screen's YAML.
"""
import logging

import esphome.codegen as cg
import esphome.config_validation as cv

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


def _audio_options(config):
    if config["audio_tests"] and not config["audio"]:
        raise cv.Invalid("audio_tests requires audio hardware")
    return config


CONFIG_SCHEMA = cv.All(cv.Schema({
    cv.Optional(CONF_LANGUAGE, default="en"): _language,
    cv.Optional("audio", default=False): cv.boolean,
    cv.Optional("audio_tests", default=False): cv.boolean,
}), _audio_options)


async def to_code(config):
    wanted = config[CONF_LANGUAGE]
    language, code = screen_text_gen.definitions(wanted, audio=config["audio"], audio_tests=config["audio_tests"])
    if config["audio"]:
        cg.add_define("USE_SCREEN_AUDIO")
    if config["audio_tests"]:
        cg.add_define("USE_SCREEN_AUDIO_TEST")
    if language != wanted:
        # ESP Screens only writes languages it has; a hand-written one it lacks builds in the nearest it does have.
        _LOGGER.warning("No translation for %s yet; the screen's texts are in %s", wanted, language)
    cg.add_global(cg.RawStatement(code))
