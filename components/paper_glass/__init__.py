"""The paper glass: a panel of e-paper as the display LVGL draws on (display.py is the platform, paper_glass.h the
component). The plain files beside them hold its rules and are tested on a PC: paper_ink.h (a pixel to an ink),
paper_print.h (when the panel refreshes) and paper.h (what the firmware around it calls). docs/PAPER.md has the story.

As a key of its own it is a paper glass without a panel, for a program that has no e-paper under it and still wants
the firmware to be on paper: the host render (tools/render/host.py), where an SDL display stands for the glass.

    paper_glass:
      inks: 2

That brings paper.h into the build and says the inks at the start, so the theme, the still glass and the standby do
what they do on a paper screen. The display itself (PaperGlass) is not built then: it needs ESPHome's e-paper driver.
"""
import esphome.codegen as cg
import esphome.config_validation as cv

CODEOWNERS = []

CONF_INKS = "inks"

CONFIG_SCHEMA = cv.Schema({cv.Optional(CONF_INKS, default=2): cv.one_of(2, 4, int=True)})


async def to_code(config):
    cg.add_global(cg.RawStatement('#include "esphome/components/paper_glass/paper.h"'))
    cg.add(cg.RawExpression(f"paper::inks() = {config[CONF_INKS]}"))
