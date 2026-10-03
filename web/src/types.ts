export type TileOptions = {
  display?: string;
  size?: string;
  controls?: string;
  inline?: string;
  guard?: string;
  tap?: string;
  icon?: string;
  background?: string;
  history_hours?: number;
  action?: { action: string; data?: Record<string, unknown> };
  [key: string]: unknown;
};
// What a favourite plays (app 0.4.42), as Home Assistant's library names it: its content id and type, the title and the
// picture the library gave, and the class of thing it is.
export type FavoritePlay = { id: string; type: string; title: string; thumb?: string; class?: string };
// A key as the page document keeps it: a tile without a place of its own.
export type ChildTile = {
  id: string;
  content: { kind: "entity"; entityId: string };
  appearance: { label: string; icon?: string; overlay?: string };
  interaction: { tap?: string; action?: TileOptions["action"]; guard?: string };
};
// A key of a bedside clock (app 0.4.12) is a tile like any other without a cell: it names the tile it stands under
// (`in`, that tile's entity) and its place there (`key`, from 0), and its slot is -1.
export type Tile = { id?: string; entity: string; name: string; slot: number; options?: TileOptions; in?: string; key?: number };
export type HeaderItem = { id?: string; type: string; entity?: string; content?: string; icon?: string; show?: string };
// `pages`: the most pages the screen takes, when the grid is the screen's (model/pages.ts pageLimit).
// What a screen says about the memory inside its chip (firmware 0.34.0+, components/smart_display/tile_memory.h), in
// bytes: the room it has for tiles and what the tiles on it take now, and what the tile catalogue's prices need from the
// board (whether it has PSRAM, the size of a tile and of its block of extras: model/memory.ts). `short`: a tile went
// without its extras for want of memory lately; `live`: said by the screen as it is now, rather than the last thing it
// said before it went offline.
export type ScreenMemory = { room: number; used: number; psram: boolean; tile: number; extra: number; page?: number; short?: boolean; live?: boolean };
// `barItems`: the items one page's top bar takes there (model/pages.ts barLimit).
export type PageGrid = Readonly<{ columns: number; rows: number; pages?: number; barItems?: number }>;
export type PageTarget = { kind: "page"; pageId: string } | { kind: "home" };
export type PageTile = {
  id: string;
  content: { kind: "entity"; entityId: string } | { kind: "builtin"; name: "clock" | "nightstand" | "settings" | "map" } | { kind: "navigation"; target: PageTarget };
  // A footprint is a rectangle. The renderer's capabilities decide which
  // rectangles it supports; the page's grid is never user-overridable.
  placement: { row: number; column: number; columns: number; rows: number };
  appearance: { label: string; presentation?: "single" | "wide" | "tall" | "square" | "full" | `${number}x${number}`; display?: string; icon?: string; background?: string; historyHours?: number; refresh?: number; subtitle?: string; fit?: string; overlay?: string;
    mapEntities?: string[]; mapFraming?: string; mapDistance?: string; mapFollow?: string; mapMarkers?: string; mapNames?: string;
    mapZones?: string; mapStreets?: string; mapLook?: string };
  interaction: { tap?: string; inline?: string; controls?: string; action?: TileOptions["action"]; guard?: string; play?: FavoritePlay; speaker?: string };
  children?: ChildTile[];
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
// The screensaver (app 0.4.48): a player, a camera optionally gated by movement, and the order the screen tries them in.
// `ready`: the screen's firmware takes one; `pictures`: its board draws pictures, else the clock alone; `standby`: it
// goes into standby at all.
export type SaverKind = "media" | "camera" | "clock";
// `weather` (app 0.4.52): the temperature under the clock, "auto" for Home Assistant's first weather entity, "" for none.
// `more` (app 0.4.54): the players the music step tries after `media`, in their order.
// `binary_sensor`: when selected, the camera shows while its movement sensor is on and for 60 seconds after it clears.
export type ScreensaverChoice = { show: boolean; media: string; camera: string; binary_sensor?: string; order: SaverKind[]; off: SaverKind[]; weather?: string; more?: string[] };
export type ScreensaverView = ScreensaverChoice & { ready: boolean; pictures: boolean; standby: boolean };
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
  width: number; height: number; dpi: number; look?: string; camera: boolean; dimmable: boolean; can_standby: boolean;
  // The chip its firmware is built for, as esptool names it ("ESP32-S3"): the browser flasher checks the board on the cable.
  chip?: string | null;
  // Whether it opens a Wi-Fi hotspot when its network is gone (app 0.4.32; 4 MB boards have no room for it).
  hotspot?: boolean;
  // The most tiles and pages a screen of it takes (firmware 0.34.0+, its board file).
  max_tiles?: number; max_pages?: number;
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
  // name: the editor's own name when one is set (app 0.4.2); ha_name: what Home Assistant calls the screen.
  id: string; name: string; ha_name?: string; online: boolean; area?: string; firmware?: string; board?: string;
  virtual?: boolean;
  layout: Layout; update?: UpdateInfo; settings?: SettingsView; delivery?: string; status?: string;
  screensaver?: ScreensaverView;
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
  // The memory this screen has for its tiles and what each costs, from its hello (firmware 0.34.0+, model/memory.ts).
  memory?: ScreenMemory | null;
  // The items one page's top bar takes: six, or more on a board with room for them (firmware 0.34.0+).
  bar_limit?: number;
  firmware_known?: string | null; tile_limit?: number; page_limit?: number; full_page?: boolean; page_tiles_repeat?: boolean; entity_tiles_repeat?: boolean; no_title?: boolean; climate_range?: boolean;
  // The language its firmware was built in (app 0.2.90); null for older firmware, which is English.
  language?: string | null;
  // What the screen looks like (app 0.2.94): the glass it draws on, the cells of one page, its density and its look,
  // from the screen itself (firmware 0.2.80) or from the board it was built for (core.shape_of); the editor draws it.
  shape?: { width: number; height: number; columns: number; rows: number; dpi?: number; look?: string; catalog?: BoardCatalog;
    fonts?: { watch_value?: number; sublabel_big?: number; sublabel?: number; icon_mini?: number; label?: number; headline?: number; icon_home?: number }; spacing?: { margin: number; gap: number; tile_pad: number } } | null;
  // Which way it was built to hang (app 0.2.107): a screen standing up has another canvas and another grid, and
  // while it is offline only the YAML of its own profile says so.
  orientation?: Orientation;
  // Whether its board draws pictures: camera tiles, an alert's snapshot, an album cover (app 0.2.94).
  pictures?: boolean;
};
export type ScreenShape = NonNullable<Screen["shape"]>;
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
// `boards`: the boards a firmware for some boards alone is for (app 0.3.21); empty or absent for the shared firmware.
export type ChangelogSection = { app: string; firmware: string; boards?: string[]; lines: string[] };
export type Entity = { id: string; name: string; area?: string; device?: string; icon?: string; state?: string; tile?: boolean; screen_name?: string };
export type IconInfo = { name: string; cp: string; label: string };
export type Inventory = {
  editor_features?: { tall_tiles?: boolean };
  csrf?: string;
  connected?: boolean;
  screens: Screen[];
  entities: Entity[];
  builtin?: Entity[];
  // Device trackers with a place, for a map card's "Also on the map" (app 0.4.35).
  trackers?: Entity[];
  // `seen`: Home Assistant found it on the network, waiting to be paired (app 0.4.32).
  pending?: { friendly: string; file: string; node?: string; installed?: boolean; downloaded?: boolean; api_key?: string; seen?: boolean }[];
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
  fields: { key: string; name: string; required?: boolean; description?: string; example?: unknown; selector?: Record<string, any>; options?: string[]; suggestions?: string[] }[];
};
