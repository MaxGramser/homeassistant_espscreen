// The doorbell (docs/DOORBELL.md): the automation Events, Doorbell builds from what the person picked in its wizard (the
// entity that rings, the camera, the screens) and what the add-on says of the event (inventory.doorbell, the add-on's
// doorbell.reference), plus the YAML of what comes after a ring. Pure, with the words from the translations.
import { t } from "../i18n";
import { yamlString } from "./alert-yaml";
import { automationYaml as written, title, trigger, triggerKind as kindOf, type Automation, type TriggerKind } from "./automation";

export type { TriggerKind } from "./automation";
export type DoorbellField = { name: string; type: string; label?: string; help?: string; example: unknown };
/** A doorbell this Home Assistant has (doorbell.suggestions): the entity that rings, how, and the camera on its device. */
export type DoorbellSuggestion = { trigger: string; kind: TriggerKind; camera: string | null; name: string };
/** What the add-on says of the doorbell's event; any of it may be missing from an older add-on. */
export type DoorbellReference = {
  show?: string; dismiss?: string; event?: string; feature?: string; answered?: string; missed?: string;
  timeout?: { default: number; min: number; max: number };
  /** How long a missed ring stays in the top bars, in minutes (0: until someone opens it): the wizard's choices and what a
   * new automation gets. */
  keep?: { choices: number[]; new: number; max: number };
  fields?: DoorbellField[]; endings?: { action: string; label: string }[];
  trigger_domains?: Record<string, TriggerKind>; suggestions?: DoorbellSuggestion[];
};
/** What a ring does on a screen (server.doorbell_kind): the camera live, its alert with its picture, or the alert alone. */
export type DoorbellKind = "view" | "picture" | "plain";
/** The ring's door key (docs/DOORBELL.md, "Open the door"): a lock, or another action of an entity's own (a script, a
 * gate's button) that the app performs on the second tap. */
export type DoorChoice = { kind: "none" | "lock" | "action"; lock?: string; entity?: string; action?: string };
/** `sound`: whether the view opens with its sound on (the default) or quiet, for a screen somewhere quiet; `chime`: whether
 * the screen chimes when it rings (the default) or rings without; `keep`: the minutes a missed ring stays in the top bars,
 * 0 until someone opens it. */
export type DoorbellChoice = { trigger?: string; camera?: string; title?: string; screens?: string[]; timeout?: number; name?: string; door?: DoorChoice; sound?: boolean; chime?: boolean; keep?: number };

/** The event's fields of a door: `lock`, or `door_action` with the entity in `door_data`; none without one. */
export function doorFields(door: DoorChoice | undefined): Record<string, unknown> {
  if (door?.kind === "lock" && door.lock) return { lock: door.lock };
  if (door?.kind === "action" && door.entity && door.action) return { door_action: door.action, door_data: { entity_id: door.entity } };
  return {};
}

const SHOW = "esp_screens_doorbell", DISMISS = "esp_screens_dismiss_doorbell", MISSED = "esp_screens_doorbell_missed";

/** How `entity` starts the automation: a suggestion says so (a doorbell's event entity), else its domain. */
export const triggerKind = (reference: DoorbellReference | undefined, entity: string) =>
  kindOf(entity, Object.fromEntries((reference?.suggestions || []).map((s) => [s.trigger, s.kind])), reference?.trigger_domains);

/** The automation: the trigger, then the doorbell's event with its camera, title, screens and timeout, called
 * "Tessera: Doorbell <name>". */
export function doorbellAutomation(reference: DoorbellReference | undefined, choice: DoorbellChoice): Automation {
  const fallback = reference?.timeout?.default ?? 60;
  const entity = choice.trigger || "event.front_door_doorbell";
  const screens = choice.screens || [];
  return {
    alias: title(`${t("editor.events.doorbell")} ${choice.title || choice.name || ""}`.trim()),
    description: t("editor.doorbell.yaml.description"),
    triggers: [trigger(entity, triggerKind(reference, entity) || "event")],
    actions: [{ event: reference?.show || SHOW, event_data: {
      camera: choice.camera || "camera.front_door",
      ...(choice.title ? { title: choice.title } : {}),
      ...(screens.length ? { screen: screens.length === 1 ? screens[0] : screens } : {}),
      ...(choice.timeout && choice.timeout !== fallback ? { timeout: choice.timeout } : {}),
      ...(choice.sound === false ? { sound: false } : {}),
      ...(choice.chime === false ? { chime: false } : {}),
      ...(choice.keep ? { keep_minutes: choice.keep } : {}),
      ...doorFields(choice.door),
    } }],
  };
}
export const automationYaml = (reference: DoorbellReference | undefined, choice: DoorbellChoice) => written(doorbellAutomation(reference, choice));

/** A ring nobody answered, to a phone: the app fires esp_screens_doorbell_missed once per ring. */
export const missedYaml = (reference: DoorbellReference | undefined) => [
  `alias: ${yamlString(t("editor.doorbell.yaml.missed_alias"))}`,
  "triggers:",
  "  - trigger: event",
  `    event_type: ${reference?.missed || MISSED}`,
  "actions:",
  "  - action: notify.notify",
  "    data:",
  `      message: ${yamlString(t("editor.doorbell.yaml.missed_message"))}`,
].join("\n");

/** Close a ring on every screen, such as when the door opened. */
export const dismissYaml = (reference: DoorbellReference | undefined) => `event: ${reference?.dismiss || DISMISS}`;
