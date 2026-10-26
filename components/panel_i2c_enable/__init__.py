"""A panel that is switched on by an I2C register rather than a GPIO, before the display sets up.

Some panels have no enable or reset pin wired to the chip: the line that powers them lives in a register of a small
I2C controller on the board. ESPHome's display platforms take an `enable_pin`/`reset_pin`, which cannot express that,
and the shared `on_boot` in packages/core.yaml runs at priority -100, long after every component has set up. So the
sequence lives in a component of its own, which runs at `setup_priority::IO` -- after the I2C bus (`BUS`) and before
any display.

The Waveshare 10.1-DSI-TOUCH-A panel on an ESP32-P4-NANO carrier is the case this was written for
(packages/boards/wavesharep4nano.yaml). Waveshare's own driver does the same writes inside
`esp_lcd_new_panel_jd9365()`, before any DSI traffic; without them the panel never drives its side of the link, the
DSI command FIFO fills after about 19 commands and never drains, and the task watchdog aborts the boot
(esphome/esphome#21451).

    panel_i2c_enable:
      - i2c_id: touch_bus
        address: 0x45
        sequence: [[0x95, 0x11], [0x95, 0x17], [0x96, 0x00], 100ms, [0x96, 0xFF], 1000ms]
"""
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import i2c
from esphome.const import CONF_ADDRESS, CONF_ID

CODEOWNERS = []
DEPENDENCIES = ["i2c"]
MULTI_CONF = True

CONF_SEQUENCE = "sequence"

panel_i2c_enable_ns = cg.esphome_ns.namespace("panel_i2c_enable")
PanelI2CEnable = panel_i2c_enable_ns.class_("PanelI2CEnable", cg.Component, i2c.I2CDevice)


def _write_pair(value):
    """A [register, value] pair, both one byte."""
    pair = cv.All(
        cv.ensure_list(cv.hex_uint8_t), cv.Length(min=2, max=2)
    )(value)
    return ("write", pair[0], pair[1])


def _step(value):
    """One step: a [register, value] pair to write, or a wait before the next one."""
    if isinstance(value, list):
        return _write_pair(value)
    return ("delay", cv.positive_time_period_milliseconds(value).total_milliseconds, 0)


CONFIG_SCHEMA = (
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(PanelI2CEnable),
            cv.Required(CONF_SEQUENCE): cv.All(cv.ensure_list(_step), cv.Length(min=1)),
        }
    )
    .extend(cv.COMPONENT_SCHEMA)
    .extend(i2c.i2c_device_schema(None))
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await i2c.register_i2c_device(var, config)
    for kind, a, b in config[CONF_SEQUENCE]:
        if kind == "write":
            cg.add(var.add_write(a, b))
        else:
            cg.add(var.add_delay(a))
