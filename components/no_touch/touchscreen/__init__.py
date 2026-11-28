"""The touchscreen platform `no_touch`: a touch panel that is not there (components/no_touch/__init__.py says why)."""
import esphome.codegen as cg
from esphome.components import touchscreen
import esphome.config_validation as cv
from esphome.const import CONF_ID

no_touch_ns = cg.esphome_ns.namespace("no_touch")
NoTouch = no_touch_ns.class_("NoTouch", touchscreen.Touchscreen)

CONFIG_SCHEMA = touchscreen.touchscreen_schema().extend({cv.GenerateID(): cv.declare_id(NoTouch)})


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await touchscreen.register_touchscreen(var, config)
