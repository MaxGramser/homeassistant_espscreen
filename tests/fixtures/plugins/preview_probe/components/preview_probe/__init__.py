"""Preview probe: the ESPHome side (docs/PLUGINS.md). register_plugin() reads the id, version, tile memory and texts from
the manifest and translations/ beside this folder; web/wasm/build_plugin.py does the same for the editor's preview."""
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import smart_display
from esphome.const import CONF_ID

DEPENDENCIES = ["smart_display"]

preview_probe_ns = cg.esphome_ns.namespace("preview_probe")
PreviewProbe = preview_probe_ns.class_("PreviewProbe", cg.Component)

CONFIG_SCHEMA = cv.Schema({cv.GenerateID(): cv.declare_id(PreviewProbe)}).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await smart_display.register_plugin(var, __file__)
