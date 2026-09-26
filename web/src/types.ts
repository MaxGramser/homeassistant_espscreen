export type TileOptions = {
  display?: string;
  size?: string;
  controls?: string;
  inline?: string;
  tap?: string;
  icon?: string;
  background?: string;
  history_hours?: number;
  action?: { action: string; data?: Record<string, unknown> };
  [key: string]: unknown;
};
export type Tile = { id?: string; entity: string; name: string; slot: number; options?: TileOptions };
export type HeaderItem = { id?: string; type: string; entity?: string; content?: string; icon?: string; show?: string };
export type PageGrid = Readonly<{ columns: number; rows: number }>;
export type PageTarget = { kind: "page"; pageId: string } | { kind: "home" };
export type PageTile = {
  id: string;
  content: { kind: "entity"; entityId: string } | { kind: "builtin"; name: "clock" | "settings" } | { kind: "navigation"; target: PageTarget };
  // A footprint is a rectangle. The renderer's capabilities decide which
  // rectangles it supports; the page's grid is never user-overridable.
  placement: { row: number; column: number; columns: number; rows: number };
  appearance: { label: string; presentation?: "single" | "wide" | "tall" | "square" | "full"; display?: string; icon?: string; background?: string; historyHours?: number; refresh?: number; subtitle?: string; fit?: string; overlay?: string };
  interaction: { tap?: string; inline?: string; controls?: string; action?: TileOptions["action"] };
};
export type Page = {
  id: string;
  navigation: { excludeFromPagination: boolean };
  topbar: {
    leading: { id: string; kind: "home" }[];
    title: { source: "screen" } | { source: "text"; text: string };
    trailing: (HeaderItem & { id: string })[];
  };
  tiles: PageTile[];
};
export type PageLayout = { title: string; homePageId: string; pages: Page[] };
export type PageWorkspace = { revision: string; positions: Record<string, { x: number; y: number }> };
export type PageDocument = {
  format: "pages-v2"; sourceGrid: PageGrid; revision: string; layout: PageLayout;
  workspace?: PageWorkspace;
  migration?: { inactivePageTitles?: string[]; droppedTiles?: { entity: string; name: string; reason: string }[]; adjustedFields?: string[] };
};
export type PendingMigration = { format: "legacy-v1"; migrationError: string; migrationRevision: string };
export type Layout = {
  title: string;
  tiles: Tile[];
  pages?: number;
  // A title of its own per page (app 0.2.105); an empty entry, or none at all, means the screen's own title.
  page_titles?: string[];
  header?: { items: HeaderItem[] };
  settings?: Record<string, any>;
  [key: string]: unknown;
};
export type UpdateInfo = {
  available?: boolean; target?: string; state?: string; phase?: string; host?: string; profile?: string;
  result?: { state: string; message: string; time: number };
  // The screen still runs another language than the one chosen for the screens (app 0.2.90).
  language?: boolean;
};
// `rotations` (app 0.2.94): the angles this screen may be turned to, a half turn on any glass and the quarter turns on a square one.
// `switches` are keys this screen shows as a switch instead of a number (app 0.2.105): a backlight that is lit or
// dark has no percentage, so standby and night are on or off there.
// `calibrate` (app 0.2.117): this screen's panel is one you calibrate, so the panel offers Calibrate touch. The
// add-on reads it from the screen's own button in Home Assistant, the same one its settings page has a row for.
export type SettingsView = { owner: string; keys: string[]; values: Record<string, any>; unavailable: string[]; rotations?: number[]; switches?: string[]; calibrate?: boolean };
// The two ways a screen can hang (app 0.2.107), chosen when it is built: lying down or standing up. A board's own
// numbers for each way come from boards.json, which the add-on serves with the firmware status.
export type Orientation = "landscape" | "portrait";
export type BoardOrientation = { width: number; height: number; columns: number; rows: number; rotation: number };
// What the add-on says of a board (boards.yaml and the board's own files, through boards.json, app 0.2.129): what it is
// called and printed on it, how far it has been tried, its glass, what it can do, and the choices made when a screen of
// it is built (the first value of each is the board file's own).
export type BoardCatalog = {
  order: number; name: string; model: string; status: "stable" | "new" | "experimental"; inch: number; touch: string;
  calibrate: boolean; choices: Record<string, string[]>;
};
export type BoardChoice = BoardCatalog & {
  square: boolean; orientations: Partial<Record<Orientation, BoardOrientation>>;
  width: number; height: number; dpi: number; camera: boolean; dimmable: boolean; can_standby: boolean;
};
// Does this screen work as you expect (app 0.3.10): what the add-on says about the board's shared answer. The key and
// the revision never reach the page; the add-on keeps them.
export type FeedbackIssue = "display" | "touch" | "connection" | "installation" | "other";
export type FeedbackAnswer = { outcome: "working" | "not_working"; issues?: FeedbackIssue[] | null; comment?: string | null };
export type FeedbackView = {
  available: boolean; ask: boolean; answered: boolean;
  shared: FeedbackAnswer | null; pending: FeedbackAnswer | null;
  state: "idle" | "waiting" | "failed" | "deleting" | "delete_failed";
  problem: "conflict" | "rejected" | null; deleted: boolean; retry_at?: number | null;
  board: string; model?: string | null; privacy: string;
  versions: { firmware_version?: string | null; addon_version?: string | null };
};
export type Screen = {
  id: string; name: string; online: boolean; area?: string; firmware?: string; board?: string;
  layout: Layout; update?: UpdateInfo; settings?: SettingsView; delivery?: string; status?: string;
  page_document?: PageDocument | PendingMigration | null;
  source_grid?: PageGrid | null;
  tile_sizes?: string[];
  page_capability?: "ready" | "update_screen" | "offline";
  page_last_capability?: "ready" | "update_screen" | null;
  page_delivery?: string;
  page_saved_revision?: string | null;
  page_applied_revision?: string | null;
  // The layout is out and the screen holds it (app 0.2.108): the editor then shows no delivery line.
  in_sync?: boolean;
  feedback?: FeedbackView | null;
  alert_action?: string; dismiss_action?: string;
  // The screen's device name (its ESPHome name): what its actions are named after and what an alert's `screen` takes.
  node?: string;
  // The API key in the screen's own YAML (app 0.2.132), for pairing it again; null when the add-on has no profile for it.
  api_key?: string | null;
  // What the add-on reads from the firmware (app 0.2.78): its X.Y.Z (null when unknown), how many tiles it holds,
  // whether it draws full-page tiles, and whether it takes several tiles that go to the same page.
  firmware_known?: string | null; tile_limit?: number; full_page?: boolean; page_tiles_repeat?: boolean;
  // The language its firmware was built in (app 0.2.90); null for older firmware, which is English.
  language?: string | null;
  // What the screen looks like (app 0.2.94): the glass it draws on, the cells of one page, its density and its look,
  // from the screen itself (firmware 0.2.80) or from the board it was built for (core.shape_of); the editor draws it.
  shape?: { width: number; height: number; columns: number; rows: number; dpi?: number; look?: string; catalog?: BoardCatalog } | null;
  // Which way it was built to hang (app 0.2.107): a screen standing up has another canvas and another grid, and
  // while it is offline only the YAML of its own profile says so.
  orientation?: Orientation;
  // Whether its board draws pictures: camera tiles, an alert's snapshot, an album cover (app 0.2.94).
  pictures?: boolean;
};
// Language & region of the screens (app 0.2.90): the language setting ("auto" follows Home Assistant), the language that
// gives, Home Assistant's own, and every language there is, by its own name; the time and number format, each "auto"
// (as the language writes it) or a choice, and what that gives.
export type LanguageInfo = { code: string; name: string; english: string; checked: boolean };
export type Languages = {
  setting: string; effective: string; ha: string | null; languages: LanguageInfo[];
  clock?: "auto" | "24" | "12"; clock_effective?: "24" | "12";
  numbers?: "auto" | "point" | "comma" | "space"; numbers_effective?: "point" | "comma" | "space";
  /** From how many digits a whole number gets separators: 2 is 1234 but 12.345 (CLDR); a space before "%". */
  group_min?: number; percent_space?: boolean;
  /** What Automatic means now: the clock and numbers of Home Assistant's language (or the chosen one). */
  clock_auto?: "24" | "12"; numbers_auto?: "point" | "comma" | "space"; group_min_auto?: number;
};
export type ChangelogSection = { app: string; firmware: string; lines: string[] };
export type Entity = { id: string; name: string; area?: string; device?: string; icon?: string; state?: string; tile?: boolean; screen_name?: string };
export type IconInfo = { name: string; cp: string; label: string };
export type Inventory = {
  editor_features?: { tall_tiles?: boolean };
  csrf?: string;
  connected?: boolean;
  screens: Screen[];
  entities: Entity[];
  builtin?: Entity[];
  pending?: { friendly: string; file: string; installed?: boolean; downloaded?: boolean; api_key?: string }[];
  updates?: { target: string; busy?: boolean; pending?: number; auto?: boolean };
  // The CHANGELOG by release, newest first: only in the full inventory, not in the live payload (app 0.2.78).
  changelog?: ChangelogSection[];
  claude_skill?: { path: string; installed: boolean; current: boolean; restart?: boolean };
  icons?: {
    groups: { label: string; icons: IconInfo[] }[];
    builtin?: Record<string, string>; weather: Record<string, string>; sun: Record<string, string>;
    defaults: Record<string, string>; fallback: string; controls?: Record<string, string>;
  };
  backgrounds?: Record<string, { label: string; color?: string }>;
  controls?: Record<string, { default: string; choices: { key: string; label: string }[] }>;
  header?: {
    max_items?: number; min_firmware?: string;
    builtin: { type: string; label: string }[];
    contents: { key: string; label: string }[];
    shows: { key: string; label: string }[];
    suggestions?: Record<string, { item: HeaderItem; label: string; name?: string; area?: string; icon?: string }[]>;
  };
  alerts?: any;
  // Missing from an add-on before 0.2.90: English everywhere, and no Language card.
  language?: Languages;
  [key: string]: unknown;
};
export type Capability = { toggle: boolean; inline: boolean; controls: string[]; displays: string[] };
export type EntityAction = {
  action: string; name: string; description: string;
  fields: { key: string; name: string; required?: boolean; description?: string; example?: unknown; selector?: Record<string, any>; options?: string[] }[];
};
