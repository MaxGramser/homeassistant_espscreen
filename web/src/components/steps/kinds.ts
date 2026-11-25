// The kinds of step a board can have (docs/BOARD_STEPS.md), each the component that does it: the editor's half of a
// row of KINDS in the add-on's board_steps.py. A step of a kind this editor does not know is not shown.
import type { Component } from "vue";
import type { IconName } from "../../model/ui-icons";
import ChipFirmware from "./ChipFirmware.vue";

export const KINDS: Record<string, Component> = { chip_firmware: ChipFirmware };
/** The picture a step's page starts with, by its id; a chip for one that names none. */
const ICONS: Record<string, IconName> = { buzzer: "bell-ring-outline" };
export const stepIcon = (id: string): IconName => ICONS[id] || "chip";
