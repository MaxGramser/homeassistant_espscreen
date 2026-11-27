"""The paper glass as a display platform (paper_glass.h; docs/PAPER.md): the display LVGL draws on when the panel is
e-paper. It wraps a display of ESPHome's own `epaper_spi`, named by `panel`, turns what LVGL flushes into the panel's
inks and decides when the panel refreshes.

    display:
      - platform: epaper_spi
        id: paper_panel
        model: ...
        full_update_every: 255   # the driver's partial refresh on; the paper glass asks for the whole ones
        update_interval: never
      - platform: paper_glass
        id: my_display
        panel: paper_panel
        dimensions: {width: 800, height: 480}
        inks: 2

`inks` is how many greys the panel prints with, 2 or 4. `partial: false` is for a panel that has no partial refresh:
every print is then a whole one, after a longer quiet. The size is stated because ESPHome's LVGL asks for it before
any display exists; it is the panel's own.
"""
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import display
from esphome.const import CONF_DIMENSIONS, CONF_HEIGHT, CONF_ID, CONF_WIDTH

CODEOWNERS = []
# No DEPENDENCIES: `panel` names a display of the epaper_spi platform, which is what brings that driver in.

CONF_PANEL = "panel"
CONF_INKS = "inks"
CONF_PARTIAL = "partial"

paper_glass_ns = cg.esphome_ns.namespace("paper_glass")
PaperGlass = paper_glass_ns.class_("PaperGlass", cg.PollingComponent, display.Display)
EPaperBase = cg.esphome_ns.namespace("epaper_spi").class_("EPaperBase", cg.PollingComponent, display.Display)


def _describe(config):
    """What ESPHome's LVGL reads of a display before it exists: its size, that the panel turns itself (the driver
    does, the paper glass passes the turn on), and that nothing but LVGL draws on it."""
    size = config[CONF_DIMENSIONS]
    display.add_metadata(config[CONF_ID], size[CONF_WIDTH], size[CONF_HEIGHT], has_hardware_rotation=True,
                         byte_order=cv.UNDEFINED, has_writer=False, rotation=0, draw_rounding=0)
    return config


CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(PaperGlass),
            cv.Required(CONF_PANEL): cv.use_id(EPaperBase),
            cv.Required(CONF_DIMENSIONS): cv.Schema(
                {cv.Required(CONF_WIDTH): cv.positive_int, cv.Required(CONF_HEIGHT): cv.positive_int}
            ),
            cv.Optional(CONF_INKS, default=2): cv.one_of(2, 4, int=True),
            cv.Optional(CONF_PARTIAL, default=True): cv.boolean,
        }
    ).extend(cv.polling_component_schema("never")),
    _describe,
)


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_panel(await cg.get_variable(config[CONF_PANEL])))
    cg.add(var.set_inks(config[CONF_INKS]))
    cg.add(var.set_partial(config[CONF_PARTIAL]))
    # The firmware around it reads paper.h under this define (components/smart_display/hw.cpp and the binder).
    cg.add_define("USE_PAPER_GLASS")
