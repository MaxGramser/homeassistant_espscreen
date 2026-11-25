"""The sound output of a board's second chip as ESPHome's speaker (docs/SECOND_CHIP.md):

    speaker:
      - platform: chip_link
        id: ts_speaker
        chip_link_id: ts_chip
"""
import esphome.codegen as cg
from esphome.components import speaker
import esphome.config_validation as cv
from esphome.const import CONF_ID

from . import ChipLink, chip_link_ns

AUTO_LOAD = ["audio"]
DEPENDENCIES = ["chip_link"]

CONF_CHIP_LINK_ID = "chip_link_id"
ChipSpeaker = chip_link_ns.class_("ChipSpeaker", cg.Component, speaker.Speaker)

CONFIG_SCHEMA = speaker.SPEAKER_SCHEMA.extend(
    {
        cv.GenerateID(): cv.declare_id(ChipSpeaker),
        cv.GenerateID(CONF_CHIP_LINK_ID): cv.use_id(ChipLink),
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await speaker.register_speaker(var, config)
    cg.add(var.set_link(await cg.get_variable(config[CONF_CHIP_LINK_ID])))
