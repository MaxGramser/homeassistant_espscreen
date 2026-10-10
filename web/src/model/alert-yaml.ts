// Alerts (docs/ALERTS.md): the YAML the cheatsheet hands out to copy into an automation, built from what the add-on says
// of an alert's fields (inventory.alerts, the add-on's alert_reference): one screen's action, the event for every screen
// and for one of them, the event with a second button, and waiting for the answer. The examples are the doorbell, its
// words in the editor's language; the YAML itself stays as code. Pure, with the words from the translations.
import { andList, t } from "../i18n";

export type AlertField = { name: string; type: string; example: unknown; label?: string; help?: string };
/** What the add-on says of alerts: their fields, the bytes a field holds per look and the boards that have it, the
 * events, a picture's field, a second button's fields, a screen's field. Any of it may be missing from an older add-on. */
export type AlertReference = {
  fields?: AlertField[]; limits?: Record<string, Record<string, number>>; limit_boards?: Record<string, string[]>;
  event?: string; broadcast?: { show?: string; dismiss?: string }; camera?: { name: string; example: string };
  choice?: { fields?: AlertField[]; action2?: { name: string; example: string } }; screen?: { example?: string };
};
export type AlertScreen = { node?: string; name: string; pictures?: boolean };

const SHOW = "esp_screens_show_alert";
const ACTION = "esphome.<device_name>_show_alert";
/** A text as a YAML string in double quotes. */
export const yamlString = (text: unknown) => `"${String(text).replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
/** A field's example as YAML writes it: a plain word bare, other text quoted, a switch true or false, a number as it is. */
export const fieldValue = (field: AlertField) => field.type === "string"
  ? (/^[a-z][a-z0-9-]*$/.test(String(field.example)) ? String(field.example) : yamlString(field.example))
  : field.example === true ? "true" : field.example === false ? "false" : String(field.example);
/** A name as YAML writes it: a plain one bare, any other quoted. */
export const yamlName = (text: string) => (/^[a-z][a-z0-9_-]*$/.test(text) ? text : yamlString(text));
/** What goes after `screen:` for a screen (app 0.2.133): the device name it reports, which its actions are named after;
 * one that has not said it yet goes by the name Home Assistant shows, which the app matches as well. */
export const screenValue = (screen: AlertScreen) => screen.node || screen.name;
const fieldLines = (reference: AlertReference | undefined) => (reference?.fields || []).map((field) => `  ${field.name}: ${fieldValue(field)}`);
// A field's own example, else the doorbell's English one.
const example = (reference: AlertReference | undefined, name: string, fallback: string) =>
  yamlString(reference?.fields?.find((field) => field.name === name)?.example || fallback);
const showEvent = (reference: AlertReference | undefined) => reference?.broadcast?.show || SHOW;

/** The bytes a field holds on each look, with the boards that have it ("CYD 48 · Guition and Waveshare 64 bytes"): the
 * add-on names the boards from its catalog, so a new board shows up here without a word of this page changing. */
export function limitText(reference: AlertReference | undefined, field: string) {
  const limits = reference?.limits || {}, boards = reference?.limit_boards || {};
  const parts = Object.entries(limits).filter(([look, values]) => values[field] && boards[look]?.length)
    .map(([look, values]) => `${andList(boards[look])} ${values[field]}`);
  return parts.length ? t("editor.alerts.fields.bytes", { limits: parts.join(" · ") }) : "";
}
/** One screen's own action with every field. */
export const actionYaml = (reference: AlertReference | undefined, action: string) =>
  `action: ${action || ACTION}\ndata:\n${fieldLines(reference).join("\n")}`;
/** The action, then waiting for the person's answer (the event's `ok`) and acting on it. */
export const waitYaml = (reference: AlertReference | undefined, action: string) => [
  `# ${t("editor.alerts.wait_yaml.comment")}`,
  `actions:`,
  `  - action: ${action || ACTION}`,
  `    data:`,
  `      title: ${example(reference, "title", "Someone is at the door")}`,
  `      subtitle: ${example(reference, "subtitle", "Door 3, back")}`,
  `      icon: doorbell`,
  `      color: orange`,
  `      button_text: ${example(reference, "button_text", "Coming")}`,
  `      timeout: 0`,
  `      flash: true`,
  `  - wait_for_trigger:`,
  `      - trigger: event`,
  `        event_type: ${reference?.event || "esphome.screen_alert"}`,
  `        event_data:`,
  `          action: ok`,
  `    timeout: "00:05:00"`,
  `  - if:`,
  `      - condition: template`,
  `        value_template: "{{ wait.trigger is not none }}"`,
  `    then:`,
  `      - action: notify.notify`,
  `        data:`,
  `          message: ${yamlString(t("editor.alerts.wait_yaml.message"))}`,
].join("\n");
/** One event for every screen (app 0.2.45): what "Edit in YAML" of the Event action takes. */
export function allScreensYaml(reference: AlertReference | undefined) {
  const lines = fieldLines(reference);
  const camera = reference?.camera;
  if (camera) lines.push(`  # ${camera.name}: ${camera.example}   # a Guition shows its picture on the card`);
  return `event: ${showEvent(reference)}\nevent_data:\n${lines.join("\n")}`;
}
/** The same event for one screen (app 0.2.133), with the picture only where the board draws one: a CYD gets the same
 * alert without it. */
export function oneScreenYaml(reference: AlertReference | undefined, screen: AlertScreen | undefined) {
  const lines = [`  screen: ${screen ? yamlName(screenValue(screen)) : reference?.screen?.example || "kitchen-screen"}`, ...fieldLines(reference)];
  if (reference?.camera && (!screen || screen.pictures)) lines.push(`  ${reference.camera.name}: ${reference.camera.example}`);
  return `event: ${showEvent(reference)}\nevent_data:\n${lines.join("\n")}`;
}
/** Two buttons (firmware 0.3.3+): the event with a second button, its colours and its action, as an automation writes it. */
export function choiceYaml(reference: AlertReference | undefined) {
  const choice = reference?.choice;
  const lines = [`  title: ${example(reference, "title", "Someone is at the door")}`, `  icon: doorbell`,
    `  button_text: ${example(reference, "button_text", "Coming")}`, `  button_color: green`];
  const text = choice?.fields?.find((field) => field.name === "button2_text")?.example || "Not now";
  lines.push(`  button2_text: ${yamlString(text)}`, `  button2_color: red`, `  action: script.open_gate`,
    `  ${choice?.action2?.name || "button2_action"}: ${choice?.action2?.example || "script.snooze_reminder"}`);
  return `event: ${showEvent(reference)}\nevent_data:\n${lines.join("\n")}`;
}
