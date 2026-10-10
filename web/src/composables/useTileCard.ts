// A card on the mockup as its faces draw it (components/TileCard.vue and components/tile/): what the stores say of its
// tile (its name, what Home Assistant reports, its screen's grid, firmware and glass), the face the screen gives it
// (model/tile-face.ts) and the words it writes (model/tile-text.ts). One object per card, the same object for as long as
// the card stands, so a face reads only what it shows and is drawn again only when that changes. Its values are unwrapped
// on reading and handed over as they are (proxyRefs, not reactive): the tile a drag carries is the draft's own object.
import { computed, proxyRefs, reactive, watch } from "vue";
import { t } from "../i18n";
import { dimensions, displayName, isFull, isWide, keysOf, pageTarget, sizeOf } from "../model/layout";
import { clockSample } from "../model/clock";
import rules from "../model/page-rules.json";
import { energyPaints, tileActive, tilePalette } from "../model/tile-palette";
import { displayOf, tileFace } from "../model/tile-face";
import { bigKeyLine, bigValue, bodyText, favoriteLine, fillPercent, headLine, isGone, isOn, mediaSubtitle, pageLink, rangeChip, readingText,
  roundValue, runText, sameLive, sameWords, screenText, setpointText, stateText, subLine, type Live, type ScreenWords } from "../model/tile-text";
import { glyph, clockText } from "../model/topbar";
import { resolveControls } from "../model/catalogue";
import { cardContent, cardHeight, watchCard, watchPadding, wideChip, widestSetpoint } from "../model/ui-scale";
import { useCanvasStore } from "../stores/canvas";
import { useDocumentStore } from "../stores/document";
import { useEntitiesStore } from "../stores/entities";
import { useInspectorStore } from "../stores/inspector";
import { useInventoryStore } from "../stores/inventory";
import { usePluginsStore } from "../stores/plugins";
import { useRegionStore } from "../stores/region";
import { useScreenStore } from "../stores/screen";
import { useUiStore } from "../stores/ui";
import type { FavoritePlay, Tile } from "../types";

// `grid`: another screen's grid, for a card of that screen's home page on the overview (app 0.4.0); the editor's own
// screen otherwise. `round`: a key of a bedside clock (app 0.4.12), the same card in its round form. `keys`: a clock's
// keys where the card is drawn outside the editor's own layout (the overview).
export type TileCardProps = { tile: Tile; slot: number; placeholder?: boolean; preview?: boolean; grid?: { columns: number; rows: number; slots: number };
  round?: boolean; keys?: Tile[] };

// What a favourite plays, by its kind, where the tile has no icon of its own.
const FAVORITE_ICONS: Record<string, string> = { album: "F0025", playlist: "F0CB8", artist: "F0803", track: "F0387", podcast: "F0994", episode: "F0994", channel: "F0439" };

export function useTileCard(props: TileCardProps) {
  const ui = useUiStore(), region = useRegionStore(), entities = useEntitiesStore(), plugins = usePluginsStore(), scr = useScreenStore();
  const inv = useInventoryStore(), canvas = useCanvasStore(), doc = useDocumentStore(), insp = useInspectorStore();
  const { grid: editorGrid } = doc.editorLayout;

  const grid = computed(() => props.grid ?? editorGrid);
  // A card of another screen, on the overview: drawn only, never picked up, focused or opened.
  const foreign = computed(() => Boolean(props.grid));
  const domain = computed(() => props.tile.entity.split(".")[0]);
  const shape = computed(() => dimensions(sizeOf(props.tile), grid.value));
  const goesTo = computed(() => pageTarget(props.tile.entity));
  // How the screens write, in their language and number format (model/tile-text.ts).
  // Kept while they are the same, so a new inventory that changes none of them writes nothing again.
  const words = computed<ScreenWords>((before) => {
    const next = { locale: region.screenLanguage, marks: region.numberMarks, percentSpace: Boolean(inv.inventory.language?.percent_space) };
    return before && sameWords(before, next) ? before : next;
  });

  // ---- What Home Assistant reports, and the face the screen gives it ----
  // The same value for as long as Home Assistant reports the same: a new inventory hands over what it knew of an entity as
  // a new object, which would draw the card again for nothing.
  const current = computed<Live | null>((before) => {
    const next = domain.value === "screen" ? null : entities.liveOf(props.tile.entity);
    return before && next && sameLive(before, next) ? before : next;
  });
  // An automation set to run on a tap looks like a script's button (firmware 0.7.0+, Tile::runs): coloured while it runs.
  const runs = computed(() => domain.value === "automation" && props.tile.options?.tap === "run");
  const gone = computed(() => isGone(current.value));
  // A favourite (app 0.4.42) is named after what it plays until it has a name of its own.
  const display = computed(() => displayOf(props.tile.entity, props.tile.options));
  const favoritePlay = computed(() => display.value === "favorite" && domain.value === "media_player" ? (props.tile.options?.play as FavoritePlay | undefined) : undefined);
  // A plugin's tile (design): the editor cannot draw what the plugin draws on the glass, so it shows a placeholder with the
  // tile's icon, its name, one line of what it shows, and the plugin it comes from. With data, it looks like the glass:
  // the add-on fills in the manifest's preview, and the mockup counts down on the editor's clock as the screen does.
  const pluginTile = computed(() => plugins.pluginTileOf(props.tile.entity));
  const pluginRows = computed(() => (pluginTile.value && !props.placeholder ? plugins.previewFor(props.tile.entity, props.tile.options?.plugin, props.tile.options?.plugin_entity) : null));
  const pluginRow = computed(() => (pluginRows.value || []).find((row) => row.at === undefined || row.at + 30 >= ui.now / 1000) || null);
  // A Big number card as the glass lays it out in this card's room on this grid (ui-scale watchCard, app 0.4.74): the
  // icon and the name above the number in the largest face that fits, or in a low cell the name small in the corner and
  // the number under it. A card of another screen (the overview) keeps the old drawing.
  const unit = computed(() => current.value?.a?.unit_of_measurement as string | undefined);
  const value = computed(() => bigValue(domain.value, current.value, words.value));
  const watchFace = computed(() => {
    if (display.value !== "watch" || isFull(props.tile) || foreign.value || props.round || goesTo.value || props.slot < 0) return null;
    const s = doc.screenShape, g = grid.value, cell = props.slot % g.slots, pad = watchPadding(s, g.rows);
    const width = cardContent(s, g.columns, shape.value.columns, cell % g.columns);
    const height = cardHeight(s, g.rows, shape.value.rows, Math.floor(cell / g.columns), canvas.pageBarShown) - 2 * (pad + 1);
    return { pad, ...watchCard(s, width, height, value.value, unit.value && !gone.value ? unit.value : "", pad) };
  });
  // The screen draws a thermostat's range on its -/+ (firmware 0.19.0+); an older one gets such a thermostat without them.
  const rangeReady = computed(() => scr.currentScreen?.climate_range !== false);
  const face = computed(() => tileFace({
    entity: props.tile.entity, options: props.tile.options, shape: shape.value, full: isFull(props.tile), wide: isWide(props.tile),
    live: current.value, chosen: resolveControls(props.tile), rangeReady: rangeReady.value, bigKeys: scr.supports(0, 17, 0),
    favorite: Boolean(favoritePlay.value), plugin: Boolean(pluginTile.value), pluginRow: Boolean(pluginRow.value), watch: Boolean(watchFace.value),
  }));

  // ---- What it writes ----
  const name = computed(() => props.tile.name || favoritePlay.value?.title || (domain.value === "screen" && region.screenBuiltinName(props.tile.entity)) || entities.entityName(props.tile.entity));
  const note = computed(() => (face.value.display !== "standard" ? displayName(face.value.display) : ""));
  const status = computed(() => stateText(props.tile.entity, current.value, { runs: runs.value, note: note.value,
    controlled: Boolean(face.value.controls && face.value.controls !== "none") }, words.value));
  const line = computed(() => subLine(String(props.tile.options?.sub ?? "auto"), current.value, status.value, words.value));
  const fill = computed(() => fillPercent(domain.value, current.value));
  const lit = computed(() => isOn(domain.value, current.value, runs.value));
  // The value the body shows large; the same words are not repeated under the name (a second line of your own stays).
  const body = computed(() => {
    const f = face.value;
    return bodyText(domain.value, current.value, f.tall && !f.tallAction && !f.tallStack && !f.coverExtended, status.value, fill.value);
  });
  const chip = computed(() => rangeChip(domain.value, current.value, rangeReady.value, words.value));
  // What a thermostat measures, in its own unit: degrees, or a humidifier's humidity (tile_controls::reading_text).
  const measured = computed(() => current.value?.a?.[domain.value === "humidifier" ? "current_humidity" : "current_temperature"]);
  const texts = proxyRefs({
    name, note, status, line, value, unit,
    headLine: computed(() => headLine(body.value, line.value)),
    bigKeyLine: computed(() => bigKeyLine(domain.value, current.value, line.value, fill.value, words.value)),
    roundValue: computed(() => roundValue(domain.value, current.value, words.value)),
    setpoint: computed(() => setpointText(domain.value, current.value, chip.value, words.value)),
    reading: computed(() => (measured.value != null ? readingText(domain.value, measured.value, words.value) : "")),
    now: computed(() => (measured.value != null ? screenText(words.value, "screen.climate.now", { value: readingText(domain.value, measured.value, words.value) }) : "")),
    runText: computed(() => runText(domain.value, words.value)),
    pageLink: computed(() => pageLink(goesTo.value, words.value)),
    mediaSubtitle: computed(() => mediaSubtitle(current.value)),
    favoriteLine: computed(() => favoriteLine(favoritePlay.value?.class, props.tile.options?.speaker as string | undefined, words.value)),
    pluginValue: computed(() => {
      const row = pluginRow.value;
      if (!row) return "";
      if (row.at === undefined) return row.value || "";
      const left = row.at - ui.now / 1000;
      if (left < 60) return t("editor.plugin_tile.now");
      if (left >= 3600) return clockText(region.clock24, new Date(row.at * 1000));
      return t("editor.plugin_tile.minutes", { n: Math.floor(left / 60) });
    }),
  });

  // ---- How it looks ----
  // Its colour of the add-on's choices (none is a card without one).
  const background = computed(() => inv.inventory.backgrounds?.[props.tile.options?.background || ""]?.color);
  const palette = computed(() => tilePalette(props.tile.entity, current.value, runs.value));
  const on = computed(() => tileActive(props.tile.entity, current.value, runs.value));
  const icon = computed(() => entities.tileIconCp(props.tile));
  const controlGlyphs = computed(() => inv.inventory.icons?.controls || {});
  /** A control's glyph by its name, from the add-on's control glyphs. */
  const key = (glyphName: string) => (controlGlyphs.value[glyphName] ? glyph(controlGlyphs.value[glyphName]) : "");
  const glassScale = computed(() => Number(canvas.deviceStyle["--glass"]) || 1);
  // A wide card's chip as the glass works it out (ui-scale wideChip): its face and whether its icon fits.
  const wideFit = computed(() => chip.value && face.value.wide
    ? wideChip(doc.screenShape, doc.documentGrid?.columns ?? doc.screenShape.columns, widestSetpoint(current.value?.a || {})) : null);
  const sliderStyle = computed(() => ({ background: `linear-gradient(to right, ${palette.value.accent} ${fill.value}%, ${palette.value.track} ${fill.value}%)` }));
  const glassPx = (n: number) => `${(n * glassScale.value).toFixed(2)}px`;
  const watchStyle = computed(() => {
    const w = watchFace.value;
    if (!w) return null;
    const text = (box: { x: number; y: number; width: number; size: number; line: number }) =>
      ({ left: glassPx(box.x), top: glassPx(box.y), width: glassPx(box.width), fontSize: glassPx(box.size), lineHeight: glassPx(box.line) });
    const unitStyle = w.unit && { fontSize: glassPx(w.unit.size), lineHeight: glassPx(w.unit.line) };
    // Under a head the number stands at the left and its unit at the right edge, as wide as its own letters. Alone, the
    // two are one row in the middle of the card, their bottoms in line, so the browser's letters cannot push either out.
    return { pad: { paddingBlock: glassPx(w.pad) },
      circle: { left: glassPx(w.circle.x), top: glassPx(w.circle.y), width: glassPx(w.circle.size), height: glassPx(w.circle.size), fontSize: glassPx(w.circle.icon) },
      title: text(w.title), value: w.stacked ? text(w.value) : { fontSize: glassPx(w.value.size), lineHeight: glassPx(w.value.line) },
      row: { top: glassPx(w.value.y), height: glassPx(w.value.line), gap: glassPx(w.unitGap) },
      unit: unitStyle && (w.stacked ? { ...unitStyle, right: "0", top: glassPx(w.unit!.y) } : unitStyle) };
  });
  // The clock faces at the editor's one clock, as the screen draws them (model/clock.ts).
  const clock = computed(() => clockSample(ui.now, region.clock24, region.screenLanguage));

  // ---- Pictures: the add-on prepares them; source URLs and Home Assistant's credentials stay with it ----
  const loaded = reactive({ artwork: false, camera: false, favorite: false });
  const artwork = computed(() => scr.pictures && face.value.tall && face.value.display === "cover" && domain.value === "media_player" && current.value?.a?.artwork_mark
    ? `api/media-art?entity=${encodeURIComponent(props.tile.entity)}&v=${encodeURIComponent(String(current.value.a.artwork_mark))}` : "");
  // A live camera fills its card on every size (app 0.3.13; 1x2 and 2x2 since 0.3.8): the add-on's picture, cut the way
  // the tile asks, with the name at the bottom or nothing on it. Until the picture is here, the head as on the screen.
  const cameraPicture = computed(() => face.value.kind === "camera" ? `api/camera-preview?entity=${encodeURIComponent(props.tile.entity)}` : "");
  // A favourite (app 0.4.42): what it plays fills the card, dimmed as an album cover over a card is, with its name, its
  // line and a round play key; on a screen without pictures the ordinary tile with the icon of what it plays.
  const favoritePicture = computed(() => face.value.kind === "favorite" && scr.pictures && favoritePlay.value?.thumb
    ? `api/media/picture?entity=${encodeURIComponent(props.tile.entity)}&url=${encodeURIComponent(favoritePlay.value.thumb)}` : "");
  const favoriteIcon = computed(() => props.tile.options?.icon && props.tile.options.icon !== "auto" ? icon.value : FAVORITE_ICONS[favoritePlay.value?.class || ""] || "F024B");
  watch(artwork, () => { loaded.artwork = false; });
  watch(cameraPicture, () => { loaded.camera = false; });
  watch(favoritePicture, () => { loaded.favorite = false; });

  // ---- A bedside clock's keys (app 0.4.12): as many places as the add-on lets this clock hold (page-rules.json) ----
  const bedsideKeys = computed(() => props.keys ?? keysOf(doc.layout, props.tile));
  const keyPlaces = computed(() => Array.from({ length: (rules.keyHolders as Record<string, number>)[props.tile.entity] || 0 }, (_, place) =>
    ({ key: place, tile: bedsideKeys.value.find((tile) => tile.key === place) }))
    .filter((place) => place.tile || !props.preview));

  // ---- Where it stands in the editor ----
  const chosen = computed(() => doc.isSelected(props.tile) && insp.inspector?.kind === "tile");
  const live = computed(() => !props.placeholder && Boolean(doc.layout?.tiles.some((tile) => tile.id === props.tile.id)));

  return proxyRefs({
    tile: computed(() => props.tile), preview: computed(() => Boolean(props.preview)), placeholder: computed(() => Boolean(props.placeholder)),
    grid, foreign, domain, shape, goesTo, current, gone, face, texts, fill, lit, on, palette, background, icon, chip, wideFit, glassScale, sliderStyle,
    watchFace, watchStyle, clock, energy: energyPaints(), pluginTile, pluginRow, artwork, cameraPicture, favoritePicture, favoriteIcon, loaded,
    keyPlaces, chosen, live, features: computed(() => Number(current.value?.a?.supported_features || 0)),
    key,
  });
}
export type TileCardView = ReturnType<typeof useTileCard>;
