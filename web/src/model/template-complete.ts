// The template tile's editor (docs/TEXT_TILE.md, "Writing a template"): what to offer where the cursor stands. Pure: the
// text before the cursor in, a context out; TemplateEditor.vue turns a context into CodeMirror's completions with the
// entities, states and attributes Home Assistant has.
//
// Home Assistant is the reference for the functions and filters (its template docs and homeassistant/helpers/template):
// the ones a template tile needs most, with the arguments they take. The tile's own markup (headings, bullets, tables,
// **bold** and the tones) is offered outside the braces.

export type Context =
  /** An entity id as the first argument of states(), is_state(), state_attr() and their kind. */
  | { kind: "entity"; from: number; quote: string }
  /** An attribute of `entity`: state_attr('x', '…'), is_state_attr('x', '…'), states.d.o.attributes.… */
  | { kind: "attribute"; from: number; entity: string; quote: string }
  /** A state `entity` may have: is_state('x', '…'), or after == / != beside states('x'). */
  | { kind: "state"; from: number; entity: string; quote: string }
  /** A domain after `states.`; an entity of `domain` after `states.<domain>.`. */
  | { kind: "domain"; from: number }
  | { kind: "object"; from: number; domain: string }
  /** What a state object has: states.light.desk.… */
  | { kind: "member"; from: number; entity: string }
  /** A filter after |, a function or variable inside {{ }} or {% %}, a tag right after {%. */
  | { kind: "filter"; from: number }
  | { kind: "function"; from: number }
  | { kind: "tag"; from: number }
  /** Outside the braces at the start of a line: the tile's own markup. */
  | { kind: "markup"; from: number }
  | { kind: "none" };

export type Item = { label: string; apply: string; detail?: string; info?: string; boost?: number; kind: "function" | "filter" | "keyword" | "markup" | "variable" };

const ENTITY_FUNCTIONS = ["states", "is_state", "state_attr", "is_state_attr", "has_value", "state_translated", "expand", "area_name",
  "area_id", "device_id", "device_attr", "is_device_attr", "label_ids", "floor_name", "distance", "closest", "relative_time"];

/** Where the open {{ }} or {% %} began, or -1 when the cursor stands outside them. */
export function openBrace(before: string) {
  const open = Math.max(before.lastIndexOf("{{"), before.lastIndexOf("{%"));
  const close = Math.max(before.lastIndexOf("}}"), before.lastIndexOf("%}"));
  return open > close ? open : -1;
}

/** What the text before the cursor asks for. */
export function contextAt(before: string): Context {
  const at = openBrace(before);
  if (at < 0) {
    // Outside the braces: the markup, at the start of a line (after its spaces).
    const line = before.slice(before.lastIndexOf("\n") + 1);
    const m = /^\s*([#*\-|:]?[a-z]*)$/i.exec(line);
    return m ? { kind: "markup", from: before.length - m[1].length } : { kind: "none" };
  }
  const inside = before.slice(at);
  let m: RegExpExecArray | null;
  // A string being typed: which function's which argument.
  if ((m = /(\w+)\(\s*(['"])([\w.]*)$/.exec(inside)) && ENTITY_FUNCTIONS.includes(m[1]))
    return { kind: "entity", from: before.length - m[3].length, quote: m[2] };
  if ((m = /(state_attr|is_state_attr)\(\s*['"]([\w]+\.[\w]+)['"]\s*,\s*(['"])(\w*)$/.exec(inside)))
    return { kind: "attribute", from: before.length - m[4].length, entity: m[2], quote: m[3] };
  if ((m = /is_state\(\s*['"]([\w]+\.[\w]+)['"]\s*,\s*(['"])([^'"]*)$/.exec(inside)))
    return { kind: "state", from: before.length - m[3].length, entity: m[1], quote: m[2] };
  if ((m = /states\(\s*['"]([\w]+\.[\w]+)['"]\s*\)\s*(?:==|!=|in\s*\[?|not\s+in\s*\[?)\s*(['"])([^'"]*)$/.exec(inside)))
    return { kind: "state", from: before.length - m[3].length, entity: m[1], quote: m[2] };
  // The value of is_state_attr is the user's own.
  if (/is_state_attr\(\s*['"][\w.]+['"]\s*,\s*['"]\w+['"]\s*,\s*['"][^'"]*$/.test(inside)) return { kind: "none" };
  // states.<domain>.<object>.attributes.<name>
  if ((m = /states\.(\w+)\.(\w+)\.attributes\.(\w*)$/.exec(inside)))
    return { kind: "attribute", from: before.length - m[3].length, entity: `${m[1]}.${m[2]}`, quote: "" };
  if ((m = /states\.(\w+)\.(\w+)\.(\w*)$/.exec(inside)))
    return { kind: "member", from: before.length - m[3].length, entity: `${m[1]}.${m[2]}` };
  if ((m = /states\.(\w+)\.(\w*)$/.exec(inside))) return { kind: "object", from: before.length - m[2].length, domain: m[1] };
  if ((m = /states\.(\w*)$/.exec(inside))) return { kind: "domain", from: before.length - m[1].length };
  // Inside a string otherwise: nothing to offer.
  const quotes = (inside.match(/'/g) || []).length % 2 || (inside.match(/"/g) || []).length % 2;
  if (quotes) return { kind: "none" };
  if ((m = /\|\s*(\w*)$/.exec(inside))) return { kind: "filter", from: before.length - m[1].length };
  if ((m = /^\{%-?\s*(\w*)$/.exec(inside))) return { kind: "tag", from: before.length - m[1].length };
  if ((m = /(?:^|[^\w.])(\w*)$/.exec(inside.slice(2)))) return { kind: "function", from: before.length - m[1].length };
  return { kind: "none" };
}

// ---- What there is to offer, as Home Assistant's template docs name it.
// `apply` is a CodeMirror snippet: ${name} is a field the cursor stops at, Tab goes to the next, and ${} is where the
// cursor ends. `info` shows what it gives, beside the list.
export const FUNCTIONS: Item[] = [
  { label: "states", apply: "states('${entity_id}')", detail: "states(entity_id)", info: "{{ states('sensor.outside') }} → 12.4", kind: "function", boost: 9 },
  { label: "is_state", apply: "is_state('${entity_id}', '${state}')", detail: "is_state(entity_id, state)", info: "{% if is_state('lock.door', 'unlocked') %}", kind: "function", boost: 8 },
  { label: "state_attr", apply: "state_attr('${entity_id}', '${attribute}')", detail: "state_attr(entity_id, attribute)", info: "{{ state_attr('climate.living', 'current_temperature') }} → 21.4", kind: "function", boost: 8 },
  { label: "is_state_attr", apply: "is_state_attr('${entity_id}', '${attribute}', '${value}')", detail: "is_state_attr(entity_id, attribute, value)", kind: "function" },
  { label: "has_value", apply: "has_value('${entity_id}')", detail: "has_value(entity_id)", info: "false while unavailable or unknown", kind: "function" },
  { label: "state_translated", apply: "state_translated('${entity_id}')", detail: "state_translated(entity_id)", info: "{{ state_translated('lock.door') }} → Locked", kind: "function", boost: 4 },
  { label: "now", apply: "now()", detail: "now()", info: "{{ now().strftime('%H:%M') }} → 07:30", kind: "function", boost: 5 },
  { label: "today_at", apply: "today_at('${22:00}')", detail: "today_at(time)", kind: "function" },
  { label: "relative_time", apply: "relative_time(states.${sensor.x}.last_changed)", detail: "relative_time(datetime)", info: "→ 12 minutes", kind: "function" },
  { label: "time_since", apply: "time_since(${datetime})", detail: "time_since(datetime)", kind: "function" },
  { label: "time_until", apply: "time_until(${datetime})", detail: "time_until(datetime)", kind: "function" },
  { label: "as_timestamp", apply: "as_timestamp(${value})", detail: "as_timestamp(value)", kind: "function" },
  { label: "as_datetime", apply: "as_datetime(${value})", detail: "as_datetime(value)", kind: "function" },
  { label: "as_local", apply: "as_local(${datetime})", detail: "as_local(datetime)", kind: "function" },
  { label: "timedelta", apply: "timedelta(${hours=1})", detail: "timedelta(days, hours, minutes)", kind: "function" },
  { label: "area_name", apply: "area_name('${entity_id}')", detail: "area_name(entity_id)", kind: "function" },
  { label: "area_entities", apply: "area_entities('${area}')", detail: "area_entities(area)", kind: "function" },
  { label: "floor_name", apply: "floor_name('${entity_id}')", detail: "floor_name(entity_id)", kind: "function" },
  { label: "label_entities", apply: "label_entities('${label}')", detail: "label_entities(label)", kind: "function" },
  { label: "device_attr", apply: "device_attr('${entity_id}', '${attribute}')", detail: "device_attr(device_or_entity, attribute)", kind: "function" },
  { label: "expand", apply: "expand('${group}')", detail: "expand(group_or_entities)", kind: "function" },
  { label: "iif", apply: "iif(${condition}, '${yes}', '${no}')", detail: "iif(condition, if_true, if_false)", kind: "function" },
  { label: "min", apply: "min(${a}, ${b})", detail: "min(a, b)", kind: "function" },
  { label: "max", apply: "max(${a}, ${b})", detail: "max(a, b)", kind: "function" },
  { label: "distance", apply: "distance('${entity_id}')", detail: "distance(entity_id)", kind: "function" },
  { label: "states", apply: "states.", detail: "states.<domain>.<object_id>", kind: "variable" },
];
export const FILTERS: Item[] = [
  ["float(${0})", "float(default)", 9], ["int(${0})", "int(default)", 8], ["round(${1})", "round(digits)", 9], ["default('${}')", "default(value)", 6],
  ["timestamp_custom('${%H:%M}')", "timestamp_custom(format)", 5], ["as_timestamp", "as_timestamp", 4], ["as_datetime", "as_datetime", 3],
  ["as_local", "as_local", 3], ["relative_time", "relative_time", 4], ["title", "title", 5], ["upper", "upper", 3], ["lower", "lower", 3],
  ["replace('${old}', '${new}')", "replace(old, new)", 4], ["trim", "trim", 2], ["truncate(${30})", "truncate(length)", 2], ["join('${, }')", "join(separator)", 5],
  ["selectattr('${state}', 'eq', '${on}')", "selectattr(attribute, test, value)", 4], ["rejectattr('${state}', 'eq', '${on}')", "rejectattr(attribute, test, value)", 3],
  ["map(attribute='${name}')", "map(attribute=)", 4], ["list", "list", 4], ["count", "count", 4], ["length", "length", 3], ["sum", "sum", 3],
  ["average", "average", 3], ["median", "median", 2], ["first", "first", 2], ["last", "last", 2], ["sort", "sort", 2], ["unique", "unique", 2],
  ["abs", "abs", 2], ["is_defined", "is_defined", 2], ["regex_replace('${find}', '${replace}')", "regex_replace(find, replace)", 2],
  ["state_translated", "state_translated", 2], ["area_name", "area_name", 2], ["iif('${yes}', '${no}')", "iif(if_true, if_false)", 3],
].map(([apply, detail, boost]) => ({ label: String(apply).split("(")[0], apply: String(apply), detail: String(detail), boost: Number(boost), kind: "filter" as const }));
export const TAGS: Item[] = [
  { label: "if", apply: "if ${condition} %}\n${}\n{% endif %}", detail: "{% if … %} … {% endif %}", kind: "keyword", boost: 9 },
  { label: "elif", apply: "elif ${condition} %}", detail: "{% elif … %}", kind: "keyword" },
  { label: "else", apply: "else %}", detail: "{% else %}", kind: "keyword" },
  { label: "endif", apply: "endif %}", detail: "{% endif %}", kind: "keyword" },
  { label: "for", apply: "for ${item} in ${items} %}\n${}\n{% endfor %}", detail: "{% for … in … %} … {% endfor %}", kind: "keyword", boost: 7 },
  { label: "endfor", apply: "endfor %}", detail: "{% endfor %}", kind: "keyword" },
  { label: "set", apply: "set ${name} = ${value} %}", detail: "{% set name = … %}", kind: "keyword", boost: 6 },
];
/** A state object's own parts (states.light.desk.…), as Home Assistant's State has them. */
export const MEMBERS: Item[] = ["state", "name", "attributes", "last_changed", "last_updated", "entity_id", "domain", "object_id"]
  .map((label, i) => ({ label, apply: label, kind: "variable" as const, boost: 8 - i }));

/** A table to fill in: a head of two columns, its rule and a row, Tab from cell to cell. */
export const TABLE = "| ${name} | ${value} |\n|---|---|\n| ${} | ${} |";

/** The tile's own markup (text_tile.py): offered at the start of a line, outside the braces. `words` names them in the
 * editor's language. */
export function markup(words: Record<"heading" | "bullet" | "table" | "bold" | "good" | "alert" | "accent", string>): Item[] {
  return [
    { label: "#", apply: "# ${}", detail: words.heading, kind: "markup", boost: 5 },
    { label: "-", apply: "- ${}", detail: words.bullet, kind: "markup", boost: 5 },
    { label: "|", apply: TABLE, detail: words.table, kind: "markup", boost: 3 },
    { label: "**", apply: "**${}**", detail: words.bold, kind: "markup", boost: 2 },
    { label: ":good[", apply: ":good[${}]", detail: words.good, kind: "markup", boost: 2 },
    { label: ":alert[", apply: ":alert[${}]", detail: words.alert, kind: "markup", boost: 2 },
    { label: ":accent[", apply: ":accent[${}]", detail: words.accent, kind: "markup", boost: 1 },
  ];
}

/** The states a domain takes in Home Assistant, beside the one an entity has now and what its attributes list. */
export const DOMAIN_STATES: Record<string, string[]> = {
  light: ["on", "off"], switch: ["on", "off"], fan: ["on", "off"], input_boolean: ["on", "off"], binary_sensor: ["on", "off"],
  automation: ["on", "off"], script: ["on", "off"], remote: ["on", "off"], siren: ["on", "off"], humidifier: ["on", "off"],
  cover: ["open", "closed", "opening", "closing"], lock: ["locked", "unlocked", "locking", "unlocking", "jammed", "open"],
  media_player: ["playing", "paused", "idle", "on", "off", "standby", "buffering"], person: ["home", "not_home"],
  device_tracker: ["home", "not_home"], sun: ["above_horizon", "below_horizon"], timer: ["active", "paused", "idle"],
  vacuum: ["cleaning", "docked", "idle", "paused", "returning", "error"], climate: ["off", "heat", "cool", "heat_cool", "auto", "dry", "fan_only"],
  alarm_control_panel: ["disarmed", "armed_home", "armed_away", "armed_night", "armed_vacation", "pending", "arming", "triggered"],
  calendar: ["on", "off"], update: ["on", "off"], water_heater: ["off", "eco", "electric", "gas", "heat_pump", "performance"],
};
/** The states to offer for `entity`: the one it has now first, what its attributes list, then its domain's. */
export function statesOf(entity: string, now: string | undefined, listed: readonly string[] = []) {
  const domain = entity.split(".")[0];
  return [...new Set([...(now ? [now] : []), ...listed, ...(DOMAIN_STATES[domain] || []), "unavailable", "unknown"])];
}

/** The closing quote a string completion adds, unless the text after the cursor has it already. */
export function closer(quote: string, after: string) {
  return quote && !after.startsWith(quote) ? quote : "";
}

// ---- What the editor shows beside the code: the values a template reads, and what looks wrong.

/** A place in the template that reads an entity: `states('x')`, `state_attr('x', 'a')` or `is_state('x', 's')`, with where
 * the call ends (a value is shown there) and where the entity id stands. */
export type Ref = { kind: "state" | "attr" | "is"; entity: string; attribute?: string; value?: string; end: number; from: number; to: number };
export function refsOf(text: string): Ref[] {
  const out: Ref[] = [];
  const add = (re: RegExp, make: (m: RegExpExecArray) => Omit<Ref, "end" | "from" | "to">) => {
    for (const m of text.matchAll(re)) {
      if (openBrace(text.slice(0, m.index! + 1)) < 0) continue;
      const at = text.indexOf(m[2], m.index!);
      out.push({ ...make(m as RegExpExecArray), end: m.index! + m[0].length, from: at, to: at + m[2].length });
    }
  };
  add(/(?<![\w.])states\(\s*(['"])([a-z_]+\.[a-z0-9_]+)\1\s*\)/g, (m) => ({ kind: "state", entity: m[2] }));
  add(/state_attr\(\s*(['"])([a-z_]+\.[a-z0-9_]+)\1\s*,\s*(['"])(\w+)\3\s*\)/g, (m) => ({ kind: "attr", entity: m[2], attribute: m[4] }));
  add(/(?<![\w.])is_state\(\s*(['"])([a-z_]+\.[a-z0-9_]+)\1\s*,\s*(['"])([^'"]*)\3\s*\)/g, (m) => ({ kind: "is", entity: m[2], value: m[4] }));
  return out.sort((a, b) => a.end - b.end);
}

/** Every quoted entity id inside the braces, with where it stands: what the editor checks against Home Assistant's. */
export function quotedIds(text: string): { id: string; from: number; to: number }[] {
  const out: { id: string; from: number; to: number }[] = [];
  for (const m of text.matchAll(/(['"])([a-z_]+\.[a-z0-9_]+)\1/g)) {
    if (openBrace(text.slice(0, m.index! + 1)) < 0) continue;
    out.push({ id: m[2], from: m.index! + 1, to: m.index! + 1 + m[2].length });
  }
  return out;
}

function distance(a: string, b: string) {
  const row = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    let prev = row[0];
    row[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const keep = row[j];
      row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1));
      prev = keep;
    }
  }
  return row[b.length];
}
/** The entity `id` was most likely meant to be: of its own domain first, close enough to be a typing slip; else none. */
export function closest(id: string, ids: readonly string[]): string | null {
  const domain = id.split(".")[0];
  let best: string | null = null, score = Infinity;
  for (const other of ids) {
    const d = distance(id, other) + (other.split(".")[0] === domain ? 0 : 2);
    if (d < score) { score = d; best = other; }
  }
  return best && score <= Math.max(3, Math.floor(id.length / 3)) ? best : null;
}

/** The line Home Assistant's error names ("… line 3"), or null. */
export function errorLine(message: string | null | undefined): number | null {
  const m = /\bline (\d+)/i.exec(message || "");
  return m ? Number(m[1]) : null;
}

/** The number of a value as it is shown beside the code: a short text, its unit after it. */
export function shown(value: unknown, unit?: string) {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  const short = text.length > 28 ? `${text.slice(0, 27)}…` : text;
  return unit && short !== "unavailable" && short !== "unknown" ? `${short} ${unit}` : short;
}
