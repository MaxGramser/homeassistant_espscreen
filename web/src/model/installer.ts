// New screen (app 0.4.32), what it works out from what it was told: the boards a search and a size leave, grouped into
// families, which way a board may hang and the grids it takes that way, a name another screen carries already, the ways
// to put the firmware on and what each says, and what is sent to make the screen's profile. Every board and everything
// said of one comes from the add-on (boards.json, model/boards.ts): nothing here names a board. Pure, with the words
// from the translations.
import { t } from "../i18n";
import { boardDetail, boardTitle } from "./boards";
import { usbTarget } from "./firmware-job";
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
/** One model says what is printed on it; several say how many there are, and the next step asks which. */
export const familyLines = (family: readonly BoardRow[]) =>
  family.length > 1 ? [boardDetail(family[0])[1], t("editor.installer.models", family.length)] : boardDetail(family[0]);
/** How many families a size holds; every family for no size. */
export const sizeCount = (rows: readonly BoardRow[], size: SizeFilter) =>
  new Set(rows.filter((board) => !size || sizeOfInch(board.inch) === size).map(familyKey)).size;

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
  return { name: !!prefix && taken.prefixes.includes(prefix), node: !!node && taken.nodes.includes(node.trim().toLowerCase()) };
}

// ---- How the firmware gets onto it ----
/** A USB port as a person knows it: "USB · Espressif USB JTAG serial debug unit". */
export function portLabel(port: string) {
  const id = port.replace(/^\/dev\/serial\/by-id\/usb-/, "").replace(/-if\d+(-port\d+)?$/, "").replace(/_/g, " ");
  return `USB · ${id === port ? port.replace(/^\/dev\//, "") : id}`;
}
export type Way = { value: string; icon: "flash" | "monitor-dashboard" | "tray-arrow-down" | "clock-outline"; title: string; detail: string; live: boolean };
/** The ways in, as cards: USB on the Home Assistant machine first (each port found, or the one to plug into), then this
 * computer, a file, or nothing yet. */
export const installWays = (ports: readonly string[]): Way[] => [
  ...(ports.length ? ports : ["usb"]).map((port) => ({ value: port, icon: "flash" as const, title: t("editor.installer.ways.ha_title"),
    detail: port === "usb" ? t("editor.installer.ways.ha_waiting") : t("editor.installer.ways.ha_found", { port: portLabel(port).replace(/^USB · /, "") }), live: port !== "usb" })),
  { value: "browser", icon: "monitor-dashboard", title: t("editor.installer.ways.browser_title"), detail: t("editor.installer.ways.browser_detail"), live: false },
  { value: "download", icon: "tray-arrow-down", title: t("editor.installer.ways.download_title"), detail: t("editor.installer.ways.download_detail"), live: false },
  { value: "", icon: "clock-outline", title: t("editor.installer.ways.later_title"), detail: t("editor.installer.ways.later_detail"), live: false },
];
/** The way to install as the ports come and go: USB on the Home Assistant machine is listed first, also before a board is
 * plugged in, so nobody concludes it isn't possible; "usb" stands for that port until one shows up. Another way stays
 * once it was picked. */
export function wayTarget(target: string, picked: boolean, ports: readonly string[]) {
  if (!["download", "browser", ""].includes(target)) return usbTarget(target, ports);
  return picked ? target : usbTarget("usb", ports);
}
/** What the chosen way does, under the cards: `support` is whether this browser can write to a board itself. */
export function wayHint(target: string, support: string, ports: readonly string[]) {
  return t(target === "usb" ? "editor.installer.target.usb"
    : target === "download" ? "editor.installer.target.download"
    : target === "browser" ? support === "ok" ? "editor.webflash.hint" : `editor.webflash.unavailable.${support}`
    : !target ? "editor.installer.target.later"
    : ports.length > 1 ? "editor.installer.target.several" : "editor.installer.target.once");
}
/** The words on the last step's key. */
export const goLabel = (target: string) => t(target === "download" ? "editor.firmware.build_download" : target === "browser" ? "editor.webflash.go"
  : target ? "editor.installer.install" : "editor.installer.save_profile");

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
export type Arrival = "paired" | "seen" | "failed" | "missing" | "waiting";
/** Where the screen built from `file` stands, `waited` milliseconds after its firmware went on. */
export function arrivalOf(inventory: Pick<Inventory, "screens" | "pending">, file: string, waited: number): Arrival {
  const node = file.replace(/\.yaml$/, "");
  if (inventory.screens.some((screen) => screen.node === node)) return "paired";
  const found = inventory.pending?.find((entry) => entry.file === file && entry.seen);
  if (found) return found.pairing === "failed" ? "failed" : "seen";
  return waited > ARRIVE_MS ? "missing" : "waiting";
}
