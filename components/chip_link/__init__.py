"""A board's second chip on a serial line (docs/SECOND_CHIP.md): the line itself, and whether Tessera's firmware
answers on it. The SenseCAP Indicator's RP2040 is the first: its speaker platform (speaker.py) plays sound on the
buzzer that chip drives.

    chip_link:
      id: ts_chip
      tx_pin: GPIO19
      rx_pin: GPIO20

The line is the screen's own UART, taken straight from ESP-IDF with a buffer for what it sends: ESPHome's `uart:`
writes with none, and holds the screen's loop for as long as the bytes take.
"""
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.const import CONF_ID, CONF_PORT, CONF_RX_PIN, CONF_TX_PIN

CODEOWNERS = ["@MaxGramser"]
DEPENDENCIES = ["esp32"]

chip_link_ns = cg.esphome_ns.namespace("chip_link")
ChipLink = chip_link_ns.class_("ChipLink", cg.Component)

def _pin(value):
    """A pin of the chip by its number, `GPIO19` or 19. ESPHome's own pin check warns that an ESP32-S3's GPIO19 and
    GPIO20 are its USB pins, at every build; on the board this is for they are the line to the chip and nothing else."""
    if isinstance(value, str) and value.upper().startswith("GPIO"):
        value = value[4:]
    return cv.int_range(min=0, max=54)(value)


CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(ChipLink),
        cv.Required(CONF_TX_PIN): _pin,
        cv.Required(CONF_RX_PIN): _pin,
        # The UART of the chip: 0 is the log's on these boards.
        cv.Optional(CONF_PORT, default=1): cv.int_range(min=1, max=2),
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_line(config[CONF_PORT], config[CONF_TX_PIN], config[CONF_RX_PIN]))
