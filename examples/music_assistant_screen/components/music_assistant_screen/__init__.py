import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import smart_display, number, switch
from esphome.const import CONF_ID
DEPENDENCIES = ["smart_display"]
ns=cg.esphome_ns.namespace("music_assistant_screen")
MusicAssistantScreen=ns.class_("MusicAssistantScreen",cg.Component)
CONFIG_SCHEMA=cv.Schema({
    cv.GenerateID():cv.declare_id(MusicAssistantScreen),
    cv.Required("player"):cv.All(cv.string_strict, cv.Length(min=1)),
    cv.Required("library_entry"):cv.All(cv.string_strict, cv.Length(min=1)),
    cv.Required("favorite_button"):cv.All(cv.string_strict, cv.Length(min=1)),
    cv.Required("enabled"):cv.use_id(switch.Switch),
    cv.Required("volume"):cv.use_id(number.Number),
    cv.Required("artwork_timeout"):cv.use_id(number.Number),
}).extend(cv.COMPONENT_SCHEMA)
async def to_code(config):
    if getattr(smart_display, "MEDIA_SCREEN_API", 0) != 1:
        raise cv.Invalid("Music Assistant Screen requires the private Tessera media-screen extension; stock Tessera cannot build this plugin yet.")
    var=cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var,config)
    await smart_display.register_plugin(var,__file__)
    cg.add(var.set_player(config["player"]))
    cg.add(var.set_library_entry(config["library_entry"]))
    cg.add(var.set_favorite_button(config["favorite_button"]))
    for key in ("enabled","volume","artwork_timeout"):
        value=await cg.get_variable(config[key])
        cg.add(getattr(var,"set_"+key)(value))
