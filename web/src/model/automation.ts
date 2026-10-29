// An automation the wizards of Events build (the doorbell's and the alerts'): what starts it (an entity the person picked),
// and one of our events as its action. One object: the YAML the page shows is that object written out, and "Add to Home
// Assistant" saves the same object (screen_manager/app/automations.py). Every one is called "Tessera: <name>", so Home
// Assistant's list shows which automations came from here. Pure.
import { yamlString } from "./alert-yaml";

export type Automation = { alias: string; description?: string; triggers: Record<string, unknown>[]; actions: Record<string, unknown>[] };
/** How an entity starts an automation: a doorbell Home Assistant knows as one (its trigger doorbell.rang), any other event
 * entity, something that turns on (a sensor, a switch: Reolink's Visitor), or a button. */
export type TriggerKind = "doorbell" | "event" | "on" | "press";
export const TITLE = "Tessera: ";
const DOMAINS: Record<string, TriggerKind> = { event: "event", binary_sensor: "on", switch: "on", input_boolean: "on", button: "press", input_button: "press" };

/** How `entity` starts an automation: `known` says so for some (a doorbell's event entity), else its domain does; null for
 * an entity that cannot start one. */
export function triggerKind(entity: string, known?: Record<string, TriggerKind>, domains: Record<string, TriggerKind> = DOMAINS): TriggerKind | null {
  return known?.[entity] ?? domains[entity.split(".", 1)[0]] ?? null;
}

/** The trigger of an automation from the entity that starts it. An event entity's or a button's state is the moment it
 * fired or was pressed: any new one counts, but not its coming back from unavailable. */
export function trigger(entity: string, kind: TriggerKind): Record<string, unknown> {
  if (kind === "doorbell") return { trigger: "doorbell.rang", target: { entity_id: entity } };
  if (kind === "on") return { trigger: "state", entity_id: entity, from: "off", to: "on" };
  return { trigger: "state", entity_id: entity, not_from: ["unavailable", "unknown"] };
}

/** "Tessera: <name>", whatever the name had in front. */
export const title = (name: string) => TITLE + name.replace(/^tessera:\s*/i, "").trim();

// ---- YAML, as Home Assistant's own editor writes it ----
// Words YAML would read as something else (a switch, nothing) are quoted, as is anything with a character of its own.
const AMBIGUOUS = /^(on|off|yes|no|true|false|null|~|y|n)$/i;
function scalar(value: unknown): string {
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  const text = String(value ?? "");
  return /^[A-Za-z0-9_][A-Za-z0-9_.-]*$/.test(text) && !AMBIGUOUS.test(text) && !/^\d/.test(text) ? text : yamlString(text);
}
const isScalar = (value: unknown) => value === null || typeof value !== "object";
function lines(value: Record<string, unknown>, indent: string): string[] {
  const out: string[] = [];
  for (const [key, item] of Object.entries(value)) {
    if (item === undefined || item === "") continue;
    if (Array.isArray(item)) {
      if (item.every(isScalar)) out.push(`${indent}${key}: [${item.map(scalar).join(", ")}]`);
      else {
        out.push(`${indent}${key}:`);
        for (const entry of item) {
          const [first, ...rest] = lines(entry as Record<string, unknown>, `${indent}    `);
          out.push(`${indent}  - ${first.trimStart()}`, ...rest);
        }
      }
    } else if (!isScalar(item)) {
      out.push(`${indent}${key}:`, ...lines(item as Record<string, unknown>, `${indent}  `));
    } else {
      out.push(`${indent}${key}: ${scalar(item)}`);
    }
  }
  return out;
}
/** The automation as YAML, for "Edit in YAML" of a new automation. */
export const automationYaml = (automation: Automation) => lines(automation as unknown as Record<string, unknown>, "").join("\n");
/** One of its actions as YAML, for "Edit in YAML" of an action in an automation of the person's own. */
export const actionYaml = (action: Record<string, unknown>) => lines(action, "").join("\n");
