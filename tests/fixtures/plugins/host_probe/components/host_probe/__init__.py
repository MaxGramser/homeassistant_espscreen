"""Host probe: the ESPHome side (docs/PLUGINS.md). register_plugin() reads the id, version, tile memory and texts from
the manifest and translations/ beside this folder."""
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import smart_display
from esphome.const import CONF_ID
from esphome.coroutine import CoroPriority, coroutine_with_priority

DEPENDENCIES = ["smart_display"]

host_probe_ns = cg.esphome_ns.namespace("host_probe")
HostProbe = host_probe_ns.class_("HostProbe", cg.Component)

CONFIG_SCHEMA = cv.Schema({cv.GenerateID(): cv.declare_id(HostProbe)}).extend(cv.COMPONENT_SCHEMA)


# Made last, so its component is registered after the screen's on_boot automation: with the same setup priority (LATE,
# host_probe.h) ESPHome then sets up the screen's on_boot first, the order in which a plugin's moments could come before
# its setup(). Where a real plugin lands depends on the whole configuration (a job waiting for an id loses priority).
@coroutine_with_priority(CoroPriority.LATE)
async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await smart_display.register_plugin(var, __file__)
