// New screen (app 0.4.32), what it works out from what it was told: the boards a search and a size leave, grouped into
// families, which way a board may hang and the grids it takes that way, a name another screen carries already, the ways
// to put the firmware on and what each says, and what is sent to make the screen's profile. Every board and everything
// said of one comes from the add-on (boards.json, model/boards.ts): nothing here names a board. Pure, with the words
// from the translations.
import { boardTitle } from "./boards";
import { matchesWords, queryWords } from "./search";
import { entitySlug } from "./slug";
import type { BoardChoice, BoardOrientation, Inventory, Orientation } from "../types";

export type BoardRow = BoardChoice & { key: string };
export type Grid = { columns: number; rows: number };

// ---- Which screen: the search, the sizes and the families of boards ----
export const SIZES = ["", "small", "medium", "large"] as const;
export type SizeFilter = (typeof SIZES)[number];
/** The size a board's glass is counted under: small below 4 inches, medium below 6, large from there. */
export const sizeOfInch = (inch: number): Exclude<SizeFilter, ""> => (inch < 4 ? "small" : inch < 6 ? "medium" : "large");
/** The boards a search and a size leave. Search reads what someone knows of their screen: the brand, the size ("4",
 * "4.3 inch", "4,3"), what is printed on it, its touch controller, the chip. */
export function boardsMatching(rows: readonly BoardRow[], query: string, size: SizeFilter) {
  const words = queryWords(query.replace(/[",]/g, ".")).map((word) => word.replace(/inch$/, ""));
  return rows.filter((board) => (!size || sizeOfInch(board.inch) === size) &&
    matchesWords(words, boardTitle(board), board.name, board.model, board.inch, board.touch, board.chip, board.key));
}
// Variants stay together only when brand, glass size, chip and resolution match. A board with a different chip or
// resolution gets its own card and specifications; display-controller variants and board revisions stay in Model.
const familyKey = (board: BoardChoice) => JSON.stringify([board.name, board.inch, board.chip || "", board.width, board.height]);
/** The boards grouped into families, in the order the first of each comes. */
export function boardFamilies(rows: readonly BoardRow[]) {
  const found = new Map<string, BoardRow[]>();
  for (const board of rows) found.set(familyKey(board), [...(found.get(familyKey(board)) || []), board]);
  return [...found.values()];
}
/** The models of the chosen board's family (one when it has no others). */
export const familyOf = (rows: readonly BoardRow[], board: BoardChoice | undefined) => (board ? rows.filter((row) => familyKey(row) === familyKey(board)) : []);
/** A family is as far along as its furthest model: stable if one is, else new, else experimental. */
export const familyStatus = (family: readonly BoardRow[]) =>
  family.some((b) => b.status === "stable") ? "stable" : family.some((b) => b.status === "new") ? "new" : "experimental";
/** A recommended board (boards.yaml `recommended`): stable, and the project's pick. */
const picked = (board: BoardChoice) => board.status === "stable" && !!board.recommended;
/** The families split in two (app 0.4.102): the recommended ones, which have a recommended model, first and apart, and
 * every other one (proven, new or experimental) under them, each in the order it comes. */
export function familyTiers(families: readonly BoardRow[][]) {
  return { recommended: families.filter((family) => family.some(picked)), more: families.filter((family) => !family.some(picked)) };
}
/** The model a click on a family's card picks: its recommended one, else its first stable one, else its first. */
export const familyLead = (family: readonly BoardRow[]) => family.find(picked) || family.find((b) => b.status === "stable") || family[0];

// ---- What it is called and how it hangs ----
/** Which way a board may hang, with the canvas and the cells of a page for each. Square glass hangs one way only, and
 * then there is nothing to ask; a board this add-on has not heard of asks nothing either. */
export function boardOrientations(board: BoardChoice | undefined): (BoardOrientation & { key: Orientation })[] {
  if (!board || board.square) return [];
  const sides = (["landscape", "portrait"] as Orientation[])
    .map((key) => ({ key, side: board.orientations[key] }))
    .filter((row) => row.side && row.side.columns > 0 && row.side.rows > 0);
  return sides.length === 2 ? sides.map((row) => ({ key: row.key, ...(row.side as BoardOrientation) })) : [];
}
/** The grids a board takes the way it hangs (app 0.4.85): from its least to its most, the board's own when it says none. */
export const gridRange = (side: BoardOrientation | undefined) =>
  ({ min: side?.min || [1, 1], max: side?.max || [side?.columns || 2, side?.rows || 3] }) as { min: [number, number]; max: [number, number] };
/** The grid a board starts with the way it hangs: the best that board has. */
export const bestGrid = (side: BoardOrientation | undefined): Grid => ({ columns: side?.columns || 2, rows: side?.rows || 3 });
/** Whether one axis of the grid may go a step up or down and stay within the range. */
export function canStep(grid: Grid, range: ReturnType<typeof gridRange>, axis: keyof Grid, by: number) {
  const index = axis === "columns" ? 0 : 1;
  return grid[axis] + by >= range.min[index] && grid[axis] + by <= range.max[index];
}
/** The drawing of a board on the list: lying down, with the cells of one page. */
export function boardArt(board: BoardChoice) {
  const side = board.orientations.landscape;
  return { width: side?.width || board.width, height: side?.height || board.height, columns: side?.columns || 2, rows: side?.rows || 3 };
}
// What the screens this app knows carry already (app 0.2.123): their ESPHome device names, and the starts Home Assistant
// gave their entity ids. The server refuses a clash, and saying it here means nothing is built first.
export type Taken = { nodes: string[]; prefixes: string[] };
/** Which name clashes: the name, whose start of entity ids another screen has (core.entity_slug), or the device name. */
export function nameClash(taken: Taken, friendly: string, node: string) {
  const prefix = entitySlug(friendly.trim());
  // " and \ end or break the C++ strings the name goes into, so the build would fail (#453): said before anything is built.
  return { name: !!prefix && taken.prefixes.includes(prefix), node: !!node && taken.nodes.includes(node.trim().toLowerCase()),
    quote: /["\\]/.test(friendly) };
}

// ---- How the firmware gets onto it ----
/** A USB port as a person knows it: "USB · Espressif USB JTAG serial debug unit". */
export function portLabel(port: string) {
  const id = port.replace(/^\/dev\/serial\/by-id\/usb-/, "").replace(/-if\d+(-port\d+)?$/, "").replace(/_/g, " ");
  return `USB · ${id === port ? port.replace(/^\/dev\//, "") : id}`;
}
export type InstallForm = { board: string; orientation: Orientation; grid: Grid; choices: Record<string, string>; friendly_name: string; name: string;
  wifi_ssid: string; wifi_password: string; target: string };
/** What makes the screen's profile (api/firmware/profiles): only a choice that differs from the board file's own, the grid
 * only when it is not the board's best, the Wi-Fi lines the add-on asks for. From this browser the add-on builds as for a
 * download. */
export function profileRequest(form: InstallForm, options: { choices: { key: string; options: string[] }[]; gridChosen: boolean; wifiMissing: readonly string[] | null; browser: boolean }) {
  const payload: Record<string, unknown> = { board: form.board, orientation: form.orientation, friendly_name: form.friendly_name, name: form.name,
    target: options.browser ? "download" : form.target };
  const picked = Object.fromEntries(options.choices.filter((choice) => form.choices[choice.key] !== choice.options[0]).map((choice) => [choice.key, form.choices[choice.key]]));
  if (Object.keys(picked).length) payload.choices = picked;
  if (options.gridChosen) payload.grid = { ...form.grid };
  if (options.wifiMissing) {
    if (options.wifiMissing.includes("wifi_ssid")) payload.wifi_ssid = form.wifi_ssid;
    if (options.wifiMissing.includes("wifi_password")) payload.wifi_password = form.wifi_password;
  }
  return payload;
}

// ---- After the firmware is on it: did the screen reach the Wi-Fi? (app 0.4.32) ----
// Home Assistant finds a screen on the network before anyone pairs it (the inventory's `seen`), so the page can say it
// arrived, or after three minutes without it, that the Wi-Fi is the likely cause and what fixes it. Tessera then adds it
// to Home Assistant itself (app 0.4.73): `failed` when Home Assistant asked something only the person can answer.
export const ARRIVE_MS = 3 * 60 * 1000;
export type Arrival = "ready" | "paired" | "seen" | "failed" | "missing" | "waiting";
/** Where the screen built from `file` stands, `waited` milliseconds after its firmware went on. `ready` (app 0.4.103) is
 * the end New screen waits for: in Home Assistant, online, and allowed to perform actions, so a tap on a tile does
 * something; `paired` is in Home Assistant but not there yet. A screen whose firmware someone puts on it themselves
 * (`patient`, a download) is never missing: nobody knows when they do. */
export function arrivalOf(inventory: Pick<Inventory, "screens" | "pending">, file: string, waited: number, patient = false): Arrival {
  const node = file.replace(/\.yaml$/, "");
  const screen = inventory.screens.find((one) => one.node === node);
  if (screen) return screen.online && !screen.actions_blocked ? "ready" : "paired";
  const found = inventory.pending?.find((entry) => entry.file === file && entry.seen);
  if (found) return found.pairing === "failed" ? "failed" : "seen";
  return !patient && waited > ARRIVE_MS ? "missing" : "waiting";
}

// ---- The steps, and the Plugins step (docs/PLUGINS.md, "Plugins a board starts with") ----
/** New screen asks one thing at a time (app 0.4.103): which screen, which version of it (only when it has more than one,
 * or a choice of its own), its name, which way it hangs (only glass that is not square), the plugins for its hardware
 * (only when one is suggested), the Wi-Fi (only when ESPHome has none yet), where its USB cable is, and then that way. */
export type InstallStage = "board" | "model" | "name" | "hang" | "plugins" | "wifi" | "cable" | "connect";
export function installStages(asks: { model: boolean; hang: boolean; plugins: boolean; wifi: boolean }): InstallStage[] {
  return ["board", ...(asks.model ? ["model" as const] : []), "name", ...(asks.hang ? ["hang" as const] : []),
    ...(asks.plugins ? ["plugins" as const] : []), ...(asks.wifi ? ["wifi" as const] : []), "cable", "connect"];
}
/** Where the screen's USB cable is: in the computer this page runs on, or in the machine Home Assistant runs on. */
export type Cable = "here" | "ha";
/** Where the cable most likely is to begin with: this computer when this browser can write a board itself (Chrome or
 * Edge, on a page served over https), else the Home Assistant machine. */
export const firstCable = (support: string): Cable => (support === "ok" ? "here" : "ha");

// USB devices on the Home Assistant machine that are certainly not a screen: the radios and meters a home plugs in there
// (Zigbee, Z-Wave and Thread sticks, a smart meter's cable). By the name the system gives them, so a screen is never
// among them; anything else may be the screen.
const NOT_A_SCREEN = /zigbee|z-?wave|zwave|conbee|raspbee|skyconnect|connect[_ -]?zbt|zbt-?1|sonoff[_ -]?(zigbee|dongle)|slzb|smlight|deconz|ezsp|thread|aeotec|zooz|nortek|husbzb|elelabs|tubeszb|rfxtrx|rfxcom|dsmr|p1[_ -]?(cable|meter)|enocean|velbus|insteon|zwa-?\d|uzb/i;
/** The ports on the Home Assistant machine split in two: what may be the screen, and what is certainly something else. */
export function screenPorts(ports: readonly string[]) {
  return { screens: ports.filter((port) => !NOT_A_SCREEN.test(port)), others: ports.filter((port) => NOT_A_SCREEN.test(port)) };
}
/** A port's name without its path, as a person reads it: "Espressif USB JTAG serial debug unit". */
export const portName = (port: string) => portLabel(port).replace(/^USB · /, "");

/** The rooms of the home as names for a new screen (app 0.4.103): Home Assistant's areas its entities stand in, the
 * most used first, without the ones another screen is called already. */
export function areaNames(entities: readonly { area?: string }[], taken: readonly string[], most = 6) {
  const count = new Map<string, number>();
  for (const entity of entities) if (entity.area) count.set(entity.area, (count.get(entity.area) || 0) + 1);
  const used = new Set(taken.map((name) => name.trim().toLowerCase()));
  return [...count.entries()].filter(([name]) => !used.has(name.toLowerCase())).sort((a, b) => b[1] - a[1]).slice(0, most).map(([name]) => name);
}
/** What the Plugins step sends with the profile: what stayed ticked is built in, what was unticked is kept as a no. */
export function pluginChoice(suggested: readonly { id: string }[], picks: Readonly<Record<string, boolean>>) {
  return { add: suggested.filter((plugin) => picks[plugin.id]).map((plugin) => plugin.id),
    declined: suggested.filter((plugin) => !picks[plugin.id]).map((plugin) => plugin.id) };
}
