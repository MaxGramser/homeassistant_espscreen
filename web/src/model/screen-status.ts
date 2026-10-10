// A screen as the sidebar and the overview tell it: the firmware its features go by, whether an update waits, runs or
// failed, the light beside its icon and the one line under its name, and what an update brings. What the add-on is
// building for the screen and whether this page just asked for a build come in as Building, with the name of the
// screens' language and the time for what depends on them; the builds store gathers them (stores/builds.ts: buildOf,
// updating).
import { t } from "../i18n";
import { boardTitle } from "./boards";
import { versionAtLeast } from "./layout";
import type { Build, ChangelogSection, Screen } from "../types";

// The firmware version a screen's features go by, as the add-on works it out (firmware_known, app 0.2.78; null when it
// can't tell). A screen entry without the field goes by the firmware text, as before.
export const firmwareVersion = (screen: Screen | undefined) =>
  (screen && "firmware_known" in screen ? screen.firmware_known : screen?.firmware) || "";

// ---- Builds ----
// `build`: what the add-on says it builds for the screen now, whoever asked (inventory.builds: an update, a plugin build,
// an install from Firmware & USB). `asked`: the page just asked to build it, for the moment until the add-on names it.
export type Building = { build: Build | null; asked: boolean };
export const isBuilding = ({ build, asked }: Building) => build?.state === "running" || asked;
// What a running update is doing, by its phase.
export const phaseText = (phase: string | undefined) =>
  ["install", "verify", "settle"].includes(phase || "") ? t(`editor.update.phases.${phase}`) : t("editor.update.starting");
// What a running build is doing, in words: an update's phase, or what a plugin build or an install is.
export function buildText(screen: Screen, build: Build | null) {
  if (!build || build.by === "update") return phaseText(build?.phase ?? screen.update?.phase);
  return t(build.by === "plugins" ? "editor.build.plugins" : "editor.build.install");
}
// Progress of a running build, from an update's phase and the ESPHome stage of the build.
export function buildProgress(screen: Screen, building: Building): { percent: number; text: string } | null {
  if (!isBuilding(building)) return null;
  const { build } = building;
  const stage = build?.stage ?? undefined;
  const phase = build?.by === "update" || !build ? (build?.phase ?? screen.update?.phase) : "install";
  if (phase === "verify") return { percent: 78, text: phaseText("verify") };
  if (phase === "settle") return { percent: 92, text: phaseText("settle") };
  if (stage === "upload") return { percent: 66, text: t("editor.update.writing") };
  if (stage) return { percent: 40, text: t("editor.update.building") };
  return { percent: 12, text: buildText(screen, build) };
}

// ---- Updates ----
// A screen that doesn't run the chosen language yet needs its update as well.
export const needsUpdate = (screen: Screen) => Boolean(screen.update?.available || screen.update?.language);
/** The update a new language brings, with the language by its own name. */
export const newLanguageText = (language: string) => t("editor.update.new_language", { name: language });
// A screen that only needs the new language (app 0.2.90) says so instead of naming the version it already has.
export const languageOnly = (screen: Screen) => {
  const u = screen.update || {};
  return Boolean(u.language) && (!u.target || versionAtLeast(firmwareVersion(screen), u.target));
};

// ---- A screen's status, as the sidebar and the overview show it ----
// `language`: the screens' language by its own name; `now`: milliseconds, for a result that is a day old.
export type StatusFacts = Building & { language: string; now: number };
export type UpdateState = { kind: "running" | "queued" | "blocked" | "available" | "failed" | "done"; text: string };
export function updateState(screen: Screen, facts: StatusFacts): UpdateState | null {
  const u = screen.update || {};
  if (isBuilding(facts)) return { kind: "running", text: buildText(screen, facts.build) };
  if (facts.build?.state === "queued") return { kind: "queued", text: t("editor.sidebar.update.queued") };
  // A screen ESP Screens did not install has no YAML here to build from, so there is nothing to press: say why
  // instead of offering a button that cannot work (the nightly round already passes such a screen by).
  if (needsUpdate(screen) && screen.online && !u.profile)
    return { kind: "blocked", text: t("editor.sidebar.update.no_profile") };
  if (needsUpdate(screen) && screen.online)
    return { kind: "available", text: languageOnly(screen) ? newLanguageText(facts.language) : t("editor.sidebar.update.available", { version: u.target }) };
  if (u.result && facts.now / 1000 - u.result.time < 86400) return { kind: u.result.state === "failed" ? "failed" : "done", text: u.result.message };
  return null;
}
// The light beside the icon: green when all is well, amber when an update waits or runs, red when the screen is away.
export const screenLight = (screen: Screen, facts: StatusFacts) => {
  if (screen.virtual) return "ok";
  if (!screen.online) return "down";
  const kind = updateState(screen, facts)?.kind;
  return kind === "available" || kind === "blocked" || kind === "running" || kind === "queued" ? "update" : kind === "failed" ? "down" : "ok";
};
// One quiet line under the name, only when there is something to say; a healthy screen shows its name alone.
export const screenSubline = (screen: Screen, facts: StatusFacts): { kind: string; text: string } | null => {
  if (screen.virtual) return { kind: "ok", text: t("editor.preview.virtual") };
  if (!screen.online) return { kind: "down", text: t("editor.common.offline") };
  const u = updateState(screen, facts);
  // An update nothing here can build is still an update: the line names it, the details say why it waits.
  if (u?.kind === "blocked") return { kind: "update", text: t("editor.sidebar.update.available", { version: screen.update?.target }) };
  return u && u.kind !== "done" ? u : null;
};
// Whether a screen asks for a look (app 0.4.0): away, an update waiting, running or failed. Only such a screen opens its
// details in the sidebar by itself; a healthy one keeps them folded behind the chevron.
export const needsAttention = (screen: Screen, facts: StatusFacts) => screenLight(screen, facts) !== "ok";

// ---- What an update brings (app 0.2.73) ----
// The changelog comes with the full inventory only (app 0.2.78): the live payload goes out every few seconds.
// Each screen has its own target (app 0.3.21): a fix for one board is no update for another, and its notes are not
// what another board gets either. `target`: the add-on's target for every screen, where the screen names none.
export function whatsNew(screen: Screen, changelog: ChangelogSection[] | undefined, target?: string): string[] {
  const goal = screen.update?.target || target;
  if (!Array.isArray(changelog) || !goal) return [];
  const since = firmwareVersion(screen);
  const lines: string[] = [];
  for (const section of changelog) {
    if (versionAtLeast(section.firmware, goal) && section.firmware !== goal) continue;
    if (since && versionAtLeast(since, section.firmware)) continue;
    if (section.boards?.length && !section.boards.includes(screen.board || "")) continue;
    for (const line of section.lines) if (!lines.includes(line)) lines.push(line);
  }
  return lines;
}

// ---- A screen's row in the sidebar (app 0.4.32) ----
// The row says one thing at most, on its right: the update's button, its progress, or why it is quiet. `kind`: its
// update's state (updateState).
export type RowStatus = "virtual" | "down" | "running" | "update" | "failed" | "waiting" | "";
export function rowStatus(screen: Screen, kind: UpdateState["kind"] | undefined): RowStatus {
  if (screen.virtual) return "virtual";
  if (!screen.online) return "down";
  if (kind === "running" || kind === "queued") return "running";
  if (kind === "available" && screen.update?.profile) return "update";
  if (kind === "failed") return "failed";
  return kind === "blocked" || kind === "available" ? "waiting" : "";
}
/** Only a screen with something to explain opens its details by itself (app 0.4.32): an update that failed or waits for
 * a build, or one that has to be updated here rather than in ESPHome Device Builder while it waits (app 0.4.82). An
 * update ready to go has its button on the row; a screen that is away says so there. */
export const explainsItself = (screen: Screen, kind: UpdateState["kind"] | undefined) =>
  ["failed", "blocked"].includes(kind || "") || Boolean(screen.update_in_tessera && kind === "available");
// A board this app knows carries its catalog entry in its shape (boards.json, app 0.2.129), which also names it.
const knownBoard = (screen: Screen) => (screen.board && screen.shape?.catalog?.name ? screen.shape.catalog : null);
/** The icon of a screen's row: a phone for a screen standing up, a panel with tiles for a board this app knows, a
 * monitor for one it does not. */
export const screenIcon = (screen: Screen) => (screen.shape && screen.shape.height > screen.shape.width ? "F011C" : knownBoard(screen) ? "F0ECE" : "F0A07");
/** The board a screen is, by its name and the size of its glass; nothing for a board this app does not know. */
export const screenBoardName = (screen: Screen) => { const board = knownBoard(screen); return board ? boardTitle(board) : ""; };
/** What the update brings, in the sidebar: the new language first, when the version changes as well, then the
 * firmware's notes, each its first sentence and without what was tested (a column this narrow holds a few headlines,
 * not the release notes). */
export function updateNotes(screen: Screen, notes: readonly string[], languageText: string) {
  const headline = (line: string) => line.match(/^.*?[.!?](?=\s|$)/)?.[0] || line;
  return [...(screen.update?.language && !languageOnly(screen) ? [languageText] : []), ...notes.filter((line) => !/^(Tested|Getest)\b/i.test(line)).map(headline)];
}
/** A screen on its way in (app 0.4.73): Tessera adds one Home Assistant found by itself and says so while it does, and
 * that it is up to the person when Home Assistant asks something only they can answer. */
export type Pending = { installed?: boolean; downloaded?: boolean; file: string; seen?: boolean; pairing?: string | null };
export const pendingText = (p: Pending) => p.pairing === "failed" ? t("editor.sidebar.pending.failed")
  : p.seen ? t("editor.sidebar.pending.adding")
  : p.installed ? t("editor.sidebar.pending.installed")
  : p.downloaded ? t("editor.sidebar.pending.downloaded")
  : t("editor.sidebar.pending.not_flashed", { file: p.file });
