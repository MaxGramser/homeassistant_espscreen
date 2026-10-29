/** The cards built into a screen, with no Home Assistant entity of their own (core.py BUILTIN, the page tiles aside). */
export type BuiltinName = "clock" | "nightstand" | "settings" | "map" | "energy" | "text";
export const BUILTIN_CARDS: string[] = ["screen.clock", "screen.nightstand", "screen.settings", "screen.map", "screen.energy", "screen.text"];
// A plugin tile's option as it is kept (plugin API 0.12): a text, number or toggle; a pick of a list found by searching,
// {value, label} with the words the person saw; or a list of texts or picks (the add-on's core.plugin_options).
// A light's preset as the tile keeps it: a brightness, a white shade in kelvin or a colour (hue, saturation), an effect
// (`fx`) and settings of its device (`rw`); or settings alone, a preset of the lamp itself (model/light-presets.ts).
export type LightPreset = { b?: number; k?: number; h?: number; s?: number; fx?: string; rw?: Record<string, string | number> };
export type PluginPick = { value: string; label: string };
export type PluginValue = string | number | boolean | PluginPick | (string | PluginPick)[];
export type TileOptions = {
  // A plugin tile's own options (design): what its manifest lets the inspector set.
  plugin?: Record<string, PluginValue>;
  // The entity a plugin tile belongs to, when its manifest names a domain (`entity`).
  plugin_entity?: string;
  display?: string;
  size?: string;
  controls?: string;
  inline?: string;
  guard?: string;
  // Where a cover's slats stand open: "100" (Home Assistant's rule, never stored) or "50".
  tilt_open?: string;
  // A light's presets (docs/LIGHT_PRESETS.md, light_presets.py): at most four, each a brightness with a white shade or a
  // colour, and whether each disc shows its brightness (stored only when it does).
  presets?: LightPreset[];
  preset_levels?: boolean;
  tap?: string;
  icon?: string;
  background?: string;
  history_hours?: number;
  action?: { action: string; data?: Record<string, unknown> };
  // The template tile's template (docs/TEXT_TILE.md, text_tile.py): Home Assistant renders it, the screen gets rows.
  template?: string;
  // A calendar card's choices (firmware 0.56.0, calendar_feed.validate): what it shows, the calendars beside the tile's
  // own, which events it lets through, how far it looks, when an event starts soon and where its full screen opens.
  style?: "events" | "busy_free" | "room";
  calendars?: string[];
  places?: string[];
  words?: string[];
  hide_words?: string[];
  all_day?: boolean;
  tentative?: boolean;
  private?: boolean;
  ahead?: number;
  soon?: number;
  start_view?: string;
  // ... and the week's first day, its hours, the month's week numbers, and where "Status and booking" books.
  week_start?: string;
  hours?: [number, number];
  week_numbers?: boolean;
  book_on?: string;
  book_place?: string;
  book_title?: string;
  // A sensor's meter (firmware 0.56.0, meter.validate): its look, its own range (both ends or none), how many colours,
  // their names (Home Assistant's) and the thresholds between them in the sensor's unit.
  meter?: "ring" | "tape" | "bar";
  min?: number;
  max?: number;
  segments?: number;
  colors?: string[];
  thresholds?: number[];
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
// `item`: a plugin's item (type "plugin"), plugin:<plugin>.<item> (docs/PLUGINS.md).
export type HeaderItem = { id?: string; type: string; entity?: string; content?: string; icon?: string; show?: string; item?: string };
// `pages`: the most pages the screen takes, when the grid is the screen's (model/pages.ts pageLimit).
// What a screen says about the memory inside its chip (firmware 0.34.0+, components/smart_display/tile_memory.h), in
// bytes: the room it has for tiles and what the tiles on it take now, and what the tile catalogue's prices need from the
// board (whether it has PSRAM, the size of a tile and of its block of extras: model/memory.ts). `short`: a tile went
// without its extras for want of memory lately; `live`: said by the screen as it is now, rather than the last thing it
// said before it went offline.
// `room` is null while the screen is still measuring it (firmware 0.51.0).
// `bar_cards`: the screen takes cards from its top bar (firmware 0.56.0), so its tiles of the top bar count too (model/memory.ts).
export type ScreenMemory = { room: number | null; used: number; psram: boolean; tile: number; extra: number; page?: number; short?: boolean; live?: boolean;
  bar_cards?: boolean };
// `barItems`: the items one page's top bar takes there (model/pages.ts barLimit). `plugins`: whether plugin tiles and
// items are taken there (the add-on serves plugins, the plugins store's pluginsEnabled); never stored with a document.
export type PageGrid = Readonly<{ columns: number; rows: number; pages?: number; barItems?: number; plugins?: boolean }>;
// The grids a screen takes one way its glass hangs, and the one it keeps for that way (firmware 0.53.0+, its hello).
export type GridWay = { columns: number; rows: number; min: [number, number]; max: [number, number] };
export type ScreenGrids = { upright: boolean; landscape: GridWay; portrait: GridWay };
export type PageTarget = { kind: "page"; pageId: string } | { kind: "home" };
export type PageTile = {
  id: string;
  content: { kind: "entity"; entityId: string } | { kind: "builtin"; name: BuiltinName } | { kind: "navigation"; target: PageTarget }
    // A plugin's tile type (design, docs: the plugins proposal): its options are the plugin's own, checked against its manifest.
    | { kind: "plugin"; plugin: string; tile: string; entityId?: string; options?: Record<string, PluginValue> };
  // A footprint is a rectangle. The renderer's capabilities decide which
  // rectangles it supports; the page's grid is never user-overridable.
  placement: { row: number; column: number; columns: number; rows: number };
  appearance: { label: string; presentation?: "single" | "wide" | "tall" | "square" | "full" | `${number}x${number}`; display?: string; icon?: string; background?: string; historyHours?: number; refresh?: number; subtitle?: string; fit?: string; overlay?: string;
    mapEntities?: string[]; mapFraming?: string; mapDistance?: string; mapFollow?: string; mapMarkers?: string; mapNames?: string;
    mapZones?: string; mapStreets?: string; mapLook?: string; energyFlow?: string;
    // The template tile's template (docs/TEXT_TILE.md): TileOptions' template.
    textTemplate?: string;
    // A calendar card's choices (firmware 0.56.0): TileOptions' style, calendars, places, words, hide_words, all_day,
    // tentative, private, ahead, soon and start_view.
    calendarStyle?: string; calendarEntities?: string[]; calendarPlaces?: string[]; calendarWords?: string[]; calendarHideWords?: string[];
    calendarAllDay?: boolean; calendarTentative?: boolean; calendarPrivate?: boolean; calendarAhead?: number; calendarSoon?: number; calendarStartView?: string;
    calendarWeekStart?: string; calendarHours?: [number, number]; calendarWeekNumbers?: boolean; calendarBookOn?: string; calendarBookPlace?: string; calendarBookTitle?: string;
    // A sensor's meter (firmware 0.56.0): TileOptions' meter, min, max, segments, colors and thresholds.
    meterStyle?: string; meterMin?: number; meterMax?: number; meterSegments?: number; meterColors?: string[]; meterThresholds?: number[] };
  interaction: { tap?: string; inline?: string; controls?: string; action?: TileOptions["action"]; guard?: string; play?: FavoritePlay; speaker?: string; shuffle?: string; repeat?: string; tilt_open?: string;
    presets?: LightPreset[]; preset_levels?: boolean };
  children?: ChildTile[];
};
export type Page = {
  id: string;
  // showInDock: whether the Dock of a larger board shows the page (docs/MODULES.md); left out, it does.
  navigation: { excludeFromPagination: boolean; showInDock?: boolean };
  topbar: {
    leading: { id: string; kind: "home" }[];
    title: { source: "screen" } | { source: "text"; text: string };
    trailing: (HeaderItem & { id: string })[];
  };
  tiles: PageTile[];
  // The page's own icon by name (a pickable MDI icon), which the Dock shows instead of its picture; left out, the picture.
  icon?: string;
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
// The screensaver (app 0.4.48): a player, a camera and the order the screen tries them in, the clock a step of its own.
// `ready`: the screen's firmware takes one; `pictures`: its board draws pictures, else the clock alone; `standby`: it
// goes into standby at all.
// `photos` (app 0.4.89): photos from a folder of Home Assistant's media, a step of its own after the music.
export type SaverKind = "media" | "photos" | "camera" | "clock";
// A plugin's screensaver (plugin API 0.14): a face of a step above, or a step of its own in the order, `plugin:<plugin>.<saver>`.
export type PluginSaverKey = `plugin:${string}.${string}`;
// A step in the order: one of the screen's own, or a plugin's (at most four of those).
export type SaverStep = SaverKind | PluginSaverKey;
// The photos step: the media source folder ('' for none yet), how many seconds a photo stands, in what order they come
// and how one fills the glass (`auto` fills it with a photo of about its shape and shows another whole).
export type SaverPhotos = { source: string; every: number; order: "shuffle" | "in_order"; fit: "auto" | "fill" | "whole"; motion?: "still" | "slow" };
// What a plugin's face or step keeps: its options as a plugin's tile keeps them, and the entity it belongs to.
export type SaverPluginSetting = { options: Record<string, PluginValue>; entity: string };
// `weather` (app 0.4.52): the temperature under the clock, "auto" for Home Assistant's first weather entity, "" for none.
// `more` (app 0.4.54): the players the music step tries after `media`, in their order.
// `face` and the rest (module clock_faces): the clock's face, Glass's numerals, the seconds hand and the face's look;
// `face` may also be a plugin's face of the clock, and `media_face`, `photos_face` a plugin's face of those steps ('' for
// the screen's own). `plugins`: the options and entity of each plugin face or step, by its key.
export type ScreensaverChoice = { show: boolean; media: string; camera: string; order: SaverStep[]; off: SaverStep[]; weather?: string; more?: string[]; items?: HeaderItem[];
  face?: "digital" | "glass" | "classic" | "bauhaus" | PluginSaverKey; numerals?: number; seconds?: boolean; look?: "dark" | "light" | "auto";
  photos?: SaverPhotos; media_face?: "" | PluginSaverKey; photos_face?: "" | PluginSaverKey; plugins?: Record<string, SaverPluginSetting> };
// `faces`: the screen's board has the clock's faces (docs/MODULES.md). `photos_step`: the screen's firmware takes the photos step.
export type ScreensaverView = ScreensaverChoice & { ready: boolean; pictures: boolean; standby: boolean; faces?: boolean; photos_step?: boolean };
export type SettingsView = { owner: string; keys: string[]; values: Record<string, any>; unavailable: string[]; rotations?: number[]; switches?: string[]; calibrate?: boolean };
// The two ways a screen can hang (app 0.2.107), chosen when it is built: lying down or standing up. A board's own
// numbers for each way come from boards.json, which the add-on serves with the firmware status.
export type Orientation = "landscape" | "portrait";
// `min` and `max`: the grids a screen of the board takes that way (firmware 0.53.0+, looks/shared/grid.yaml).
export type BoardOrientation = { width: number; height: number; columns: number; rows: number; rotation: number;
  min?: [number, number]; max?: [number, number] };
// What the add-on says of a board (boards.yaml and the board's own files, through boards.json, app 0.2.129): what it is
// called and printed on it, how far it has been tried, its glass, what it can do, and the choices made when a screen of
// it is built (the first value of each is the board file's own).
export type BoardCatalog = {
  order: number; name: string; model: string; status: "stable" | "new" | "experimental"; inch: number; touch: string;
  calibrate: boolean; choices: Record<string, string[]>;
  // Its extras under Screen settings (boards.yaml `settings`, docs/SETTINGS.md "A board's own settings").
  settings?: string[];
};
export type BoardChoice = BoardCatalog & {
  square: boolean; orientations: Partial<Record<Orientation, BoardOrientation>>;
  width: number; height: number; dpi: number; look?: string; camera: boolean; dimmable: boolean; can_standby: boolean;
  // Its fonts and its grid's sizes in glass pixels (boards.json, app 0.4.74), for a preview screen's mockup.
  fonts?: NonNullable<Screen["shape"]>["fonts"]; spacing?: NonNullable<Screen["shape"]>["spacing"];
  // The chip its firmware is built for, as esptool names it ("ESP32-S3"): the browser flasher checks the board on the cable.
  chip?: string | null;
  // Whether it opens a Wi-Fi hotspot when its network is gone (app 0.4.32; 4 MB boards have no room for it).
  hotspot?: boolean;
  // The most tiles and pages a screen of it takes (firmware 0.34.0+, its board file).
  max_tiles?: number; max_pages?: number;
};
// Does this screen work as you expect (app 0.3.10): what the add-on says about the board's shared answer. The key and
// the revision never reach the page; the add-on keeps them.
// The troubleshooting report of a screen ("My screen doesn't work right", components/ReportPanel.vue): what the add-on
// offers for a screen, the report as it is collected, and the answer of a send. Field names are the add-on's.
export type ReportDepth = "basic" | "full";
export type ReportBlocker = "no_profile" | "collecting";
export type ReportCrash = { at: string; reason: string; decoded: string[]; count: number };
export type ReportLast = { id: string; reference: string; sent_at: string; depth: ReportDepth };
export type ReportOffer = {
  ready: boolean; blockers: ReportBlocker[]; retention_days: number; last: ReportLast | null; crash: ReportCrash | null;
  email: string | null; privacy_url: string;
};
export type ReportState = "collecting" | "ready" | "failed" | "sent";
export type ReportStep = "identity" | "profile" | "screen_log" | "ha_log" | "addon_log" | "build_log" | "crash" | "zip";
export type ReportFile = { name: string; size: number; lines: number; kind: "md" | "json" | "yaml" | "log" | "txt" };
export type ReportWarning = "screen_offline" | "no_api_key" | "no_elf" | "ha_log_unavailable" | "addon_log_unavailable" | "no_crash_record";
export type ReportSummary = {
  board: string; board_name: string; chip: string; firmware: string | null; channel: string; esphome: string | null;
  addon: string; ha: string | null; plugins: { id: string; version: string }[]; crash: { reason: string; at: string } | null;
  online: boolean; built_on: "addon" | "build_server" | "unknown"; elf: boolean;
};
export type Report = {
  id: string; screen: string; depth: ReportDepth; state: ReportState; step: ReportStep | null; progress: number;
  files: ReportFile[]; summary: ReportSummary | null; warnings: ReportWarning[]; size: number;
  reference: string | null; sent_at: string | null; error: string | null;
};
export type ReportSendResult =
  | { state: "sent"; reference: string; expires_at: string }
  | { state: "retry" | "invalid" | "too_large" | "offline"; error: string };

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
// What this app shares about plugins (plugin_likes.py view): never the key.
export type PluginSharing = {
  consented: boolean; counting: boolean; counting_asked: boolean; asking: boolean; counted?: number | null; usable: boolean;
};
// The stars card above a screen (Plugins.ask_card): a plugin of the index it has run for a few days and not yet rated.
export type PluginAsk = {
  plugin: string; name: Record<string, string>; version?: string | null; days: number; maintainer: string; tessera: boolean;
  issues?: string | null; image?: string | null; board?: string | null; ask_counting: boolean; privacy: string;
};
export type Screen = {
  // name: the editor's own name when one is set (app 0.4.2); ha_name: what Home Assistant calls the screen.
  id: string; name: string; ha_name?: string; online: boolean; area?: string; firmware?: string; board?: string;
  virtual?: boolean;
  layout: Layout; update?: UpdateInfo; settings?: SettingsView; delivery?: string; status?: string;
  screensaver?: ScreensaverView;
  page_document?: PageDocument | PendingMigration | null;
  source_grid?: PageGrid | null;
  // The grids it takes (firmware 0.53.0+): the editor offers its columns and rows beside the mockup. None for a screen
  // whose grid is the one it was built with.
  grids?: ScreenGrids | null;
  // Which way it is to hang on glass that turns (app 0.4.85): what the editor chose, else the way it hangs; null on square glass.
  hang?: "landscape" | "portrait" | null;
  tile_sizes?: string[];
  page_capability?: "ready" | "update_screen" | "offline";
  // Home Assistant ignores its taps: it may not perform actions (app 0.4.63, the ESPHome integration's own repair issue).
  actions_blocked?: boolean;
  page_last_capability?: "ready" | "update_screen" | null;
  page_delivery?: string;
  page_saved_revision?: string | null;
  page_applied_revision?: string | null;
  // The layout is out and the screen holds it (app 0.2.108): the editor then shows no delivery line.
  in_sync?: boolean;
  feedback?: FeedbackView | null;
  // How a plugin it runs works for you (docs/PLUGINS.md, "Likes, ratings and counting"): the stars card, or none.
  plugin_ask?: PluginAsk | null;
  alert_action?: string; dismiss_action?: string;
  // What a doorbell's ring does here (app 0.4.91, docs/DOORBELL.md): its camera live, its alert with the picture, or the alert alone.
  doorbell?: "view" | "picture" | "plain";
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
  // A board with 4 MB of flash that still has ESPHome's partition table (app 0.4.82): its next update has to come from
  // Tessera, which moves the table; ESPHome Device Builder's firmware no longer fits its slot (core.update_in_tessera).
  update_in_tessera?: boolean;
  firmware_known?: string | null; tile_limit?: number; page_limit?: number; full_page?: boolean; page_tiles_repeat?: boolean; entity_tiles_repeat?: boolean; no_title?: boolean; climate_range?: boolean; vacuum_tile?: boolean;
  // The language its firmware was built in (app 0.2.90); null for older firmware, which is English.
  language?: string | null;
  // What the screen looks like (app 0.2.94): the glass it draws on, the cells of one page, its density and its look,
  // from the screen itself (firmware 0.2.80) or from the board it was built for (core.shape_of); the editor draws it.
  shape?: { width: number; height: number; columns: number; rows: number; dpi?: number; look?: string; catalog?: BoardCatalog;
    fonts?: { watch_value?: number; sublabel_big?: number; sublabel?: number; icon_mini?: number; label?: number; headline?: number; icon_home?: number;
      watch_icon?: number; setpoint?: number; icon?: number };
    // The grid in glass pixels (boards.json); its heights (gap_y, top, page_bar) and a card's circle from app 0.4.74, a
    // card's corner and its icon's face (fonts.icon) from app 0.4.90.
    spacing?: { margin: number; gap: number; tile_pad: number; gap_y?: number; top?: number; page_bar?: number; circle?: number; radius?: number } } | null;
  // Which way it was built to hang (app 0.2.107): a screen standing up has another canvas and another grid, and
  // while it is offline only the YAML of its own profile says so.
  orientation?: Orientation;
  // Whether its board draws pictures: camera tiles, an alert's snapshot, an album cover (app 0.2.94).
  pictures?: boolean;
  // Plugins (design): the size of its last firmware image and its update slot, from the add-on's last build of it.
  firmware_image?: { size: number; slot: number } | null;
  // Whether it has a battery the top bar can show (app 0.4.68, firmware 0.41.0): its hello said so, or its board has one.
  battery?: boolean;
  // Whether its board has the Dock (boards.json `modules`, docs/MODULES.md): a page then offers Show in Dock.
  dock?: boolean;
  // Whether its board draws the template tile (boards.json `modules` has text_card, docs/TEXT_TILE.md).
  text_tiles?: boolean;
  // Whether its board draws a light's presets (boards.json `modules` has light_presets, docs/LIGHT_PRESETS.md).
  light_presets?: boolean;
  /** Streams a camera live (a P4 whose hello says `live`, or such a board while it is offline): Live is a camera tile's
   * first and default pace there (app dev). */
  live_camera?: boolean;
  /** What its hardware can do, from its last hello (firmware hw.h, docs/PLATFORM_PLAN.md 3.3): null until it said so. */
  caps?: ScreenCaps | null;
};
// A screen's capability record (page_delivery.caps_of): `live_tiles`, the most live camera tiles it streams at once.
export type ScreenCaps = { live: boolean; speaker: boolean; microphone: boolean; echo_cancel: boolean; camera: boolean;
  live_tiles: number | null; psram_kb: number | null; internal_kb: number | null; text_tiles?: number | null; text_bytes?: number | null };
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
// `unavailable_since`: when an unavailable entity last changed in Home Assistant, in seconds; only on an unavailable one.
export type Entity = { id: string; name: string; area?: string; device?: string; icon?: string; state?: string; tile?: boolean; screen_name?: string; unavailable_since?: number };
export type IconInfo = { name: string; cp: string; label: string };
// What is being built for one screen right now, whoever asked (Manager.builds in the add-on): the firmware update, a
// plugin build, or New screen and Firmware & USB. The editor's one source for "something is building". Every build waits
// its turn in the add-on's one build line (docs/BUILDS.md): `place` is its turn while it waits (1 is next), `id` the
// build's own, which the line (LineBuild) names with its outcome once it ended. An update that a plugin build joined
// names the plugins it brings too.
export type Build = {
  id?: number; by: "update" | "plugins" | "install"; state: "queued" | "running"; place?: number; file?: string | null;
  stage?: string | null; phase?: string | null; plugins?: string[];
} & ServerSide;
// Where a build's compile runs (the add-on's build_server.py): `server` with the build server's name and its step
// (`remote`), or `here` after a fallback, with the reason (`fallback`, editor.build.server.fallback.<reason>).
export type ServerSide = { where?: "server" | "here" | null; server?: string | null; remote?: BuildServerStep | null; fallback?: string | null };
export type BuildServerStep = "bundle" | "send" | "queued" | "build" | "fetch";
export type Fingerprint = { emoji: string; name: string }[];
// The build server as the add-on keeps it (build_server.BuildServer.view): paired or not, on or off, there or not.
export type BuildServerView = {
  rev: number; available: boolean; enabled: boolean; esphome: string;
  own: { pin: string; emoji: Fingerprint };
  server: { host: string; port: number; name: string; esphome: string; state: "paired" | "pending"; since: number; emoji: Fingerprint } | null;
  connection: "off" | "connecting" | "online" | "offline" | "refused" | "mismatch"; error: string;
  queue: { idle: boolean; running: boolean; queue_depth: number } | null;
  building: { file: string; phase: BuildServerStep; started: number } | null;
  last: { file: string; where: "server" | "here"; server: string; seconds?: number; reason?: string; failed?: boolean; at: number } | null;
};
// What Look it up finds at an address: the server's name, its ESPHome, its fingerprint, and whether it wants the one-time
// key a headless server prints.
export type BuildServerPreview = { host: string; port: number; pin: string; name: string; esphome: string; needs_key: boolean; provisions: boolean; emoji: Fingerprint };
// One build of the add-on's build line (the live inventory's `line`, build_queue.BuildQueue.view): what runs, what waits
// in order and the last ones that ended, newest first. `check` is a YAML check. While it waits, `place` is its turn and
// `after` the profile that builds now; while it runs, ESPHome's `stage` and the build's `memory`; once it ended, why
// (`reason`) and the memory it had. Its log is asked by its id (stores/builds.ts loadBuildLog).
export type LineState = "queued" | "running" | "success" | "failed" | "skipped" | "interrupted";
export type LineBuild = {
  id: number; by: Build["by"] | "check"; file: string | null; screen?: string | null; action: string; target?: string;
  state: LineState; asked: number; started: number | null; finished: number | null; phase?: string | null; plugins?: string[];
  place?: number; after?: string | null; stage?: string | null; memory?: import("./model/install-progress").BuildMemory | null;
  reason?: string | null;
} & ServerSide;
export type VideoIntegration = {
  path: string; installed: boolean; current: boolean; version: string; loaded: string | null;
  screens: string[]; entries: number; restart?: boolean;
};

export type Inventory = {
  editor_features?: { tall_tiles?: boolean; plugins?: boolean };
  csrf?: string;
  connected?: boolean;
  screens: Screen[];
  entities: Entity[];
  builtin?: Entity[];
  // Device trackers with a place, for a map card's "Also on the map" (app 0.4.35).
  trackers?: Entity[];
  // `seen`: Home Assistant found it on the network, waiting to be paired (app 0.4.32). `pairing`: the app adds it itself
  // (app 0.4.73), `failed` when Home Assistant asked something only the person can answer.
  pending?: { friendly: string; file: string; node?: string; installed?: boolean; downloaded?: boolean; api_key?: string; seen?: boolean; pairing?: "adding" | "failed" | null }[];
  // `channel`: the branch the screens build from, when the app was added from this repository (docs/RELEASING.md).
  // `reinstallable`: on the dev channel, how many screens Reinstall all from dev builds again (Updater.reinstallable).
  updates?: { target: string; busy?: boolean | string | null; pending?: number; auto?: boolean; channel?: "main" | "dev" | null; reinstallable?: number };
  builds?: Record<string, Build>;
  // The add-on's build line (build_queue.py, docs/BUILDS.md): what runs, what waits and the last that ended (newest
  // first), from the same look at the line as `builds`, in every live answer.
  line?: LineBuild[];
  // The build server (build_server.py, docs/BUILDS.md "On a build server"), in every live answer.
  build_server?: BuildServerView;
  // What this app shares about plugins (plugin_likes.py): whether a like counts publicly, counting, the stars cards.
  plugin_sharing?: PluginSharing | null;
  // The live streams of every screen together and the most the app serves at once (live_stream.py, LiveFeed.usage).
  live_streams?: { used: number; most: number };
  // The CHANGELOG by release, newest first: only in the full inventory, not in the live payload (app 0.2.78).
  changelog?: ChangelogSection[];
  claude_skill?: { path: string; installed: boolean; current: boolean; restart?: boolean };
  // Video in Home Assistant (Settings, screen_video.py): the tessera_video integration in Home Assistant's folder, the
  // version Home Assistant runs (null until it restarted with it), and the screens with Screen camera's part Video.
  video?: VideoIntegration;
  icons?: {
    groups: { label: string; icons: IconInfo[] }[];
    builtin?: Record<string, string>; weather: Record<string, string>; sun: Record<string, string>; calendar?: Record<string, string>;
    defaults: Record<string, string>; fallback: string; controls?: Record<string, string>;
  };
  backgrounds?: Record<string, { label: string; color?: string }>;
  controls?: Record<string, { default: string; choices: { key: string; label: string }[] }>;
  header?: {
    max_items?: number; min_firmware?: string;
    builtin: { type: string; label: string }[];
    contents: { key: string; label: string }[];
    shows: { key: string; label: string }[];
    // The screen's own Wi-Fi item's choices and the firmware that draws the screen's own items (app 0.4.63).
    wifi_contents?: { key: string; label: string }[];
    wifi_shows?: { key: string; label: string }[];
    status_types?: string[]; status_min_firmware?: string;
    // The battery item's choices and the firmware that draws it (app 0.4.68); offered where Screen.battery is true.
    battery_contents?: { key: string; label: string }[];
    battery_shows?: { key: string; label: string }[];
    battery_min_firmware?: string;
    // A plugin's item: its icon and words, or its icon alone (plugin API 0.8).
    plugin_contents?: { key: string; label: string }[];
    suggestions?: Record<string, { item: HeaderItem; label: string; name?: string; area?: string; icon?: string }[]>;
  };
  alerts?: any;
  // The doorbell's event, its fields and what comes back (model/doorbell-yaml.ts DoorbellReference).
  doorbell?: any;
  // Missing from an add-on before 0.2.90: English everywhere, and no Language card.
  language?: Languages;
  [key: string]: unknown;
};
export type Capability = { toggle: boolean; inline: boolean; controls: string[]; displays: string[]; favorite?: string[] };
export type EntityAction = {
  action: string; name: string; description: string;
  fields: { key: string; name: string; required?: boolean; description?: string; example?: unknown; selector?: Record<string, any>; options?: string[]; suggestions?: string[] }[];
};
