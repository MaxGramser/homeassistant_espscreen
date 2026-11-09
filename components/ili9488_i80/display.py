"""Native ESP-IDF i80 transport; pins belong to the board, not the driver."""
from esphome import pins
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import display
from esphome.components.esp32 import VARIANT_ESP32S3, only_on_variant
from esphome.const import CONF_ID, CONF_DATA_PINS, CONF_DC_PIN, CONF_INVERT_COLORS

DEPENDENCIES = ["esp32"]
ns = cg.esphome_ns.namespace("ili9488_i80")
ILI9488I80 = ns.class_("ILI9488I80", display.Display)

CONFIG_SCHEMA = cv.All(
    display.FULL_DISPLAY_SCHEMA.extend({
        cv.GenerateID(): cv.declare_id(ILI9488I80),
        cv.Required(CONF_DATA_PINS): cv.All(
            [pins.internal_gpio_output_pin_schema], cv.Length(min=16, max=16)),
        cv.Required(CONF_DC_PIN): pins.internal_gpio_output_pin_schema,
        cv.Required("wr_pin"): pins.internal_gpio_output_pin_schema,
        cv.Required("rd_pin"): pins.internal_gpio_output_pin_schema,
        cv.Optional("data_rate", default="10MHz"): cv.All(cv.frequency, cv.Range(min=1000000, max=20000000)),
        cv.Optional("madctl", default=0x08): cv.hex_uint8_t,
        cv.Optional(CONF_INVERT_COLORS, default=False): cv.boolean,
        # LVGL owns rotation. A second rotation here would also break touch coordinates.
        cv.Optional("rotation", default=0): cv.one_of(0, int=True),
    }),
    only_on_variant(supported=[VARIANT_ESP32S3]),
)

async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await display.register_display(var, config)
    for i, pin in enumerate(config[CONF_DATA_PINS]):
        cg.add(var.set_data_pin(i, await cg.gpio_pin_expression(pin)))
    for key in (CONF_DC_PIN, "wr_pin", "rd_pin"):
        cg.add(getattr(var, f"set_{key}")(await cg.gpio_pin_expression(config[key])))
    cg.add(var.set_data_rate(config["data_rate"]))
    cg.add(var.set_madctl(config["madctl"]))
    cg.add(var.set_invert_colors(config[CONF_INVERT_COLORS]))
