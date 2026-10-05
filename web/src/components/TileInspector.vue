<script setup lang="ts">
import { editorLayout } from "../store";
const { grid, pageCount, pageOf } = editorLayout;

// One tile's settings. Every change applies live, so the card on the mockup shows the result while you pick.
import { computed, ref, watch } from "vue";
import { t } from "../i18n";
import { beginFieldEdit, endFieldEdit } from '../store';
import { ACTS_ON_TAP, domainInfo, entriesOf, holdHintKey, inlineControlKind, pageTarget, SLIDER_DOMAINS, SWITCHES_ON_TAP, TOGGLE_BEFORE } from "../model/layout";
import { glyph } from "../model/topbar";
import { controlOption, drawable, fits, ofType } from "../model/catalogue";
import { currentScreen, automaticIcon, entityName, liveOf, moveTileToPage, openPage, openTile, phone, screenBuiltinName, fullPage, loadSubtitleValues, setTileName, pictures, removeTile, retargetPageTile, setTileOption, state, supports, tileIconCp } from "../store";
import { titleOf } from "../model/pages";
import type { Tile } from "../types";
import ActionPicker from "./ActionPicker.vue";
import IconPicker from "./IconPicker.vue";
import { coverPrimary, hasCoverTilt, withCoverTilt } from "../model/tall-controls";
import ChoiceField from "./ChoiceField.vue";
import FavoritePicker from "./FavoritePicker.vue";
import type { FavoritePlay } from "../types";
import PropRow from "./ui/PropRow.vue";
import Icon from "./ui/Icon.vue";
import InspectorHead from "./ui/InspectorHead.vue";
import Section from "./ui/Section.vue";
import SwitchRow from "./ui/SwitchRow.vue";
import UiSelect from "./ui/UiSelect.vue";
import UiMenu from "./ui/UiMenu.vue";
import UiMenuItem from "./ui/UiMenuItem.vue";
import UiMenuSeparator from "./ui/UiMenuSeparator.vue";
import { textDraft } from '../model/text-draft';
import rules from "../model/page-rules.json";
import { choiceOffered, offeredChoices } from "../model/tile-options";
import { isTallSize } from "../model/sizes";

const props = defineProps<{ tile: Tile }>();
// On a phone (app 0.4.40) the sheet starts with what a tile is changed for most: its name, icon and colour, then a way
// to move it or take it off. Everything else stands behind More settings, the same rows as on a wider page.
const more = ref(false);
watch(() => props.tile.id, () => { more.value = false; });
// The tile goes to the first free cell of another page, and the sheet follows it there.
function moveTile(page: number) {
  const id = state.document?.pages[page]?.id;
  if (moveTileToPage(props.tile, page) && id) state.selectedPageId = id;
}
const otherPages = computed(() => (state.document?.pages || []).map((page, index) => ({ index, name: titleOf(state.document!, page) || t("editor.page.label", { page: index + 1 }) }))
  .filter((page) => page.index !== pageOf(props.tile.slot)));
const nameDraft = textDraft(() => props.tile.name, value => setTileName(props.tile, value));
const domain = computed(() => props.tile.entity.split(".")[0]);
const name = computed(() => entityName(props.tile.entity));
// A navigation tile (screen.page_<n>): the page it opens, its size, icon and colour; nothing else applies.
const goesTo = computed(() => pageTarget(props.tile.entity));
// Pages counted from 1. "Goes to page" offers the pages the screen has and the empty one after them, where a sub-page
// starts (app 0.2.78), and keeps a target beyond those so the choice stays visible.
const pageTotal = computed(() => (state.layout ? pageCount(entriesOf(state.layout), state.layout.pages) : 1));
// A key stands on its clock's page (it has no cell of its own); the clock is on a screen once.
const holder = computed(() => props.tile.in !== undefined ? state.layout?.tiles.find((item) => item.entity === props.tile.in && item.in === undefined) : undefined);
const pageHere = computed(() => pageOf((holder.value || props.tile).slot) + 1);
const emptyPage = (n: number) => !state.layout?.tiles.some((t) => pageOf(t.slot) === n - 1);
const pages = computed(() => {
  const list = Array.from({ length: Math.min(grid.pages, pageTotal.value + 1) }, (_, i) => i + 1);
  if (goesTo.value > list.length) list.push(goesTo.value);
  return list.map((n) => [n, emptyPage(n) ? t("editor.tile.goes_to.empty", { page: n }) : String(n)] as [number, string]);
});
const goesToHint = computed(() => !fullPage.value
  ? { text: t("editor.tile.goes_to.needs_firmware"), warn: false }
  : goesTo.value > pageTotal.value
    ? { text: t("editor.tile.goes_to.no_page", { page: goesTo.value }), warn: true }
    : { text: t("editor.tile.goes_to.hint"), warn: false });
const caps = computed(() => state.capabilities[props.tile.entity]);
const current = (key: string, fallback: unknown) => props.tile.options?.[key] ?? fallback;
const clock = computed(() => props.tile.entity === "screen.clock");
// The bedside clock (app 0.4.12): always the whole page, with no face to pick. Its keys are tiles of their own, set here
// like any tile but for what their clock decides for them: their size, their page and their card's colour.
const bedside = computed(() => props.tile.entity === "screen.nightstand");
const key = computed(() => props.tile.in !== undefined);
// The settings card has no face to pick: the screen draws it as a plain card whatever it carries (GitHub #47).
const display = computed(() => props.tile.entity === "screen.settings" ? "standard" : current("display", clock.value ? "digital" : "standard") as string);
// The add-on's own table of displays per domain (page-rules.json), so the editor never offers one it refuses to save:
// a camera has no large value (app 0.3.8). What Home Assistant says an entity can do narrows it further.
const displays = computed(() => {
  const c = caps.value;
  const keys = ((rules.displays as Record<string, string[]>)[domain.value] || ["standard", "watch"]).filter((key) => {
    if (key === "forecast") return !c || c.displays.includes("forecast") || display.value === "forecast";
    if (key === "graph") return !c || c.displays.includes("graph") || display.value === "graph";
    // The album cover on a media tile (app 0.2.92), on a board that draws pictures; the tile over the whole page has the card's big cover.
    if (key === "cover") return (pictures.value || display.value === "cover") && size.value !== "full";
    // A map (app 0.4.33) is a picture the add-on draws: only on a board that draws pictures.
    if (key === "map") return pictures.value || display.value === "map";
    // A favourite (app 0.4.42): a player whose library Home Assistant browses; never the whole page, where the card is the player.
    if (key === "favorite") return ((!c || c.displays.includes("favorite")) && size.value !== "full") || display.value === "favorite";
    return true;
  });
  return offer("display", keys.map((key) => [key, t(`editor.tile.display.${key}`)] as [string, string]), display.value);
});
// A live camera fills its card on every size (app 0.3.13, firmware 0.3.7; 1x2 and 2x2 since app 0.3.8, firmware 0.3.3):
// whole or cut to fill it, its name on it or nothing.
const pictureCard = computed(() => display.value === "live");
const cardFilled = computed(() => supports(0, 3, 7) || (taller.value && supports(0, 3, 3)));
// A hint is a warning unless the screen's firmware already does what it describes.
const clockFace = computed(() => clock.value && ["dial", "flip"].includes(display.value));
const displayWarns = computed(() => !(display.value === "live" && cardFilled.value) && !(display.value === "cover" && supports(0, 2, 78)) &&
  !(display.value === "favorite" && supports(0, 24, 0)) &&
  !(display.value === "map" && supports(0, 20, 0)) && !(clockFace.value && supports(0, 3, 6)));
// A map card (app 0.4.33, docs/MAP.md): who rides along beside the tile's own person, how it frames them and how far a
// fixed view reaches. The choices are the catalogue's (catalogue/person.yaml), the first of each the default.
const MAP = ofType("person")?.map;
const mapCard = computed(() => display.value === "map");
const mapWith = computed(() => (props.tile.options?.map as string[] | undefined) ?? []);
// The map tile of the screen's own cards (app 0.4.36): no person of its own, following everyone or whom it lists.
const mapTile = computed(() => props.tile.entity === "screen.map");
// The energy card (app 0.4.77) is its diagram: no face and no second line to choose, its sensors are Home Assistant's.
const energyTile = computed(() => props.tile.entity === "screen.energy");
const mapFollow = computed(() => current("follow", MAP?.follow[0]) as string);
const mapListed = computed(() => !mapTile.value || mapFollow.value === "chosen");
const mapFull = computed(() => mapWith.value.length >= (MAP?.max ?? 8) - (mapTile.value ? 0 : 1));
const mapOffered = computed(() => [...(state.inventory.entities || []), ...(state.inventory.trackers || [])]
  .filter((item) => (MAP?.with ?? []).includes(item.id.split(".")[0]) && item.id !== props.tile.entity && !mapWith.value.includes(item.id))
  .map((item) => [item.id, item.name || item.id] as [string, string]));
const mapFraming = computed(() => current("framing", MAP?.framing[0]) as string);
type MapChoice = "framing" | "distance" | "follow" | "markers" | "names" | "zones" | "streets" | "look";
const mapChoices = (key: MapChoice) => offer(key, (MAP?.[key] ?? [])
  // Around this person is a person's map: the map tile has no person of its own.
  .filter((value) => !(key === "framing" && value === "person" && mapTile.value))
  .map((value) => [value, t(`editor.tile.map.${key}.${value}`)] as [string, string]), current(key, MAP?.[key][0]));
// A favourite (app 0.4.42): what it plays, chosen in the player's library, and on which speaker (or where it plays).
const favoriteCard = computed(() => display.value === "favorite" && domain.value === "media_player");
const favoritePlay = computed(() => props.tile.options?.play as FavoritePlay | undefined);
const choosing = ref(false);
watch(() => props.tile.id, () => { choosing.value = false; });
const speakers = computed(() => {
  // The rows of the player's speaker menu (app speakers.py), or its sources from an app before them.
  const live = liveOf(props.tile.entity)?.a;
  const listed = ((live?.speakers ?? live?.source_list) as string[] | undefined) ?? [];
  const chosen = props.tile.options?.speaker as string | undefined;
  const names = chosen && !listed.includes(chosen) ? [...listed, chosen] : listed;
  return [["", t("editor.tile.favorite.speaker_now")] as [string, string], ...names.map((name) => [name, name] as [string, string])];
});
function pickFavorite(play: FavoritePlay) { setTileOption(props.tile, "play", play); choosing.value = false; }
function pickSpeaker(name: string) { setTileOption(props.tile, "speaker", name || undefined); }
function addMapEntity(id: string) { if (id) setTileOption(props.tile, "map", [...mapWith.value, id]); }
function removeMapEntity(id: string) { setTileOption(props.tile, "map", mapWith.value.filter((item) => item !== id)); }
const pictureChoices = (key: "fit" | "overlay") => offer(key, rules.picture[key].map((value) => [value, t(`editor.tile.picture.${key}.${value}`)] as [string, string]), current(key, rules.picture[key][0]));
const refreshChoices = computed(() => offer("refresh", rules.refresh.map((seconds) => [seconds, t("editor.tile.refresh.seconds", { n: seconds })] as [number, string]), refresh.value));
const historyChoices = computed(() => offer("history_hours", [1, 6, 24].map((hours) => [hours, t("editor.tile.history.hours", hours)] as [number, string]), history.value));
const displayHint = computed(() => {
  const c = caps.value;
  if (c && display.value === "graph" && !c.displays.includes("graph")) return t("editor.tile.display.no_graph");
  if (c && display.value === "forecast" && !c.displays.includes("forecast")) return t("editor.tile.display.no_forecast");
  if (display.value === "live") return t(cardFilled.value ? "editor.tile.display.live_card_hint" : supports(0, 2, 77) ? "editor.tile.display.live_card_needs_firmware" : "editor.tile.display.live_needs_firmware");
  if (display.value === "map") return t(supports(0, 20, 0) ? "editor.tile.display.map_hint" : "editor.tile.display.map_needs_firmware");
  if (display.value === "favorite") return t(supports(0, 24, 0) ? "editor.tile.display.favorite_hint" : "editor.tile.display.favorite_needs_firmware");
  if (display.value === "cover" && taller.value) return t("editor.tile.display.tall_cover_hint");
  if (display.value === "cover") return t(supports(0, 2, 78) ? "editor.tile.display.cover_hint" : "editor.tile.display.cover_needs_firmware");
  // The calm dial and the flip clock (firmware 0.3.6): an older screen shows the digital clock until it is updated.
  if (clockFace.value && !supports(0, 3, 6)) return t("editor.tile.display.face_needs_firmware");
  return "";
});
const refresh = computed(() => current("refresh", 15) as number);
const size = computed(() => current("size", "single") as string);
const taller = computed(() => isTallSize(size.value));
const catalogue = computed(() => state.inventory.controls?.[domain.value]);
// Every choice the panel shows is one the add-on saves (app 0.4.0, GitHub #47): tried the way the panel applies it,
// against the same card check the save runs (model/tile-options.ts). The tile's own choice always stays in sight.
const controlled = computed(() => Boolean(catalogue.value));
function offer<T extends string | number>(key: string, choices: [T, string][], now: unknown, sample?: (value: T) => unknown) {
  return offeredChoices(props.tile, key, choices, now, controlled.value, sample);
}
const controls = computed(() => taller.value && current("inline", "none") === "slider" ? inlineControlKind(domain.value) : current("controls", ["tall", "full"].includes(size.value) ? "none" : catalogue.value?.default) as string);
const primaryControl = computed(() => domain.value === 'cover' ? coverPrimary(controls.value) : controls.value);
const tiltSelected = computed(() => domain.value === 'cover' && hasCoverTilt(controls.value));
const offerTilt = computed(() => domain.value === 'cover' && (isTallSize(size.value) || size.value === 'full')
  && (tiltSelected.value || (caps.value?.controls.includes('tilt') && choiceOffered(props.tile, 'controls', withCoverTilt(primaryControl.value, true), controlled.value))));
function pickControl(value: string) {
  setTileOption(props.tile, 'controls', domain.value === 'cover' ? withCoverTilt(value, tiltSelected.value) : value);
}
const controlChoices = computed(() => {
  const c = caps.value;
  // Temperature and mode need a second row: offered on 1 x 2, 2 x 2 and full-page cards only.
  const choices = (catalogue.value?.choices || []).filter(ch => domain.value !== "cover" || !hasCoverTilt(ch.key))
    // The tile catalogue decides the rest (model/catalogue.ts): room for it on a card of this size (the mode keys and
    // the slats ask a second row), and a screen that draws it for this entity (a range: firmware 0.19.0+).
    .filter(ch => ch.key === "none" || fits(controlOption(domain.value, ch.key), size.value, grid.columns))
    .filter(ch => ch.key === "none" || drawable(domain.value, ch.key, liveOf(props.tile.entity)?.a || {},
      currentScreen.value?.climate_range === false ? new Set<string>() : null) === ch.key)
    .filter((ch) => !c || ch.key === "none" || ch.key === primaryControl.value || c.controls.includes(ch.key)).map((ch) => [ch.key, ch.label] as [string, string]);
  return offer("controls", choices, primaryControl.value, (key) => domain.value === "cover" ? withCoverTilt(key, tiltSelected.value) : key);
});
const controlHint = computed(() => {
  const c = caps.value;
  if (c && controls.value !== "none" && !c.controls.includes(controls.value)) return { text: t("editor.tile.controls.not_offered"), warn: true };
  return { text: supports(0, 2, 19)
    ? t(taller.value ? "editor.tile.controls.tall_hint" : size.value === "full" ? "editor.tile.controls.full_hint" : "editor.tile.controls.wide_hint")
    : t("editor.tile.controls.needs_firmware"), warn: false };
});
// Perform action has a second step, the action: picking it opens the list, and only an action chosen there stores it
// (app 0.4.0, GitHub #47). Until then the tile keeps the tap choice it had.
const choosingAction = ref(false);
watch(() => props.tile.id, () => { choosingAction.value = false; });
const tap = computed(() => choosingAction.value ? "action" : current("tap", "auto") as string);
watch(() => props.tile.options?.tap, (stored) => { if (stored === "action") choosingAction.value = false; });
const taps = computed(() => {
  // An automation (firmware 0.7.0+): switch it on or off, or run its actions; holding the tile does the other one.
  if (domain.value === "automation") {
    const keys = ["auto", "run", "none", "action"];
    if (!keys.includes(tap.value)) keys.splice(2, 0, tap.value);
    return offer("tap", keys.map((key) => [key, t(key === "auto" ? "editor.tile.tap.toggle" : `editor.tile.tap.${key}`)] as [string, string]), tap.value);
  }
  const keys = ["auto", "detail", "none"];
  // On / off where Home Assistant can toggle the entity, such as a cover; a speaker without on and off gets none.
  if ((caps.value ? caps.value.toggle : TOGGLE_BEFORE.includes(domain.value)) || tap.value === "toggle") keys.push("toggle");
  keys.push("action");
  return offer("tap", keys.map((key) => [key, t(`editor.tile.tap.${key}`)] as [string, string]), tap.value);
});
function pickTap(value: string) {
  choosingAction.value = value === "action" && !props.tile.options?.action;
  if (choosingAction.value) state.actionPickerOpen = true;
  else setTileOption(props.tile, "tap", value);
}
// A lock's tile (firmware 0.5.0+): unlock after a second tap on it, or never unlock from this screen.
const guard = computed(() => current("guard", "confirm") as string);
const guards = computed(() => offer("guard", ["confirm", "lock_only"].map((key) => [key, t(`editor.tile.guard.${key}`)] as [string, string]), guard.value));
const tapHint = computed(() => {
  if (domain.value === "automation" && !supports(0, 7, 0)) return { text: t("editor.tile.tap.automation_needs_firmware"), warn: true };
  if (domain.value === "automation" && ["auto", "toggle", "run"].includes(tap.value))
    return { text: t(tap.value === "run" ? "editor.tile.tap.hold_toggle" : "editor.tile.tap.hold_run"), warn: false };
  if (tap.value === "toggle" && caps.value && !caps.value.toggle) return { text: t("editor.tile.tap.no_toggle"), warn: true };
  if (tap.value === "toggle" && !TOGGLE_BEFORE.includes(domain.value) && !supports(0, 2, 58)) return { text: t("editor.tile.tap.toggle_needs_firmware"), warn: false };
  if (tap.value === "detail" && SWITCHES_ON_TAP.includes(domain.value))
    return { text: t("editor.tile.tap.detail_no_toggle", { auto: t("editor.tile.tap.auto") }), warn: false };
  // A camera opens full screen either way; every other tile opens its card when held.
  if ((tap.value === "auto" && ACTS_ON_TAP.includes(domain.value)) || ((tap.value === "toggle" || tap.value === "action") && !["camera", "image"].includes(domain.value)))
    return { text: t(holdHintKey(domain.value)), warn: false };
  return null;
});
// ---- The second line (app 0.2.105, firmware 0.2.90+) ----
// Four ways to fill it: the line the screen works out itself, nothing at all, a value of the entity, or words of
// your own. The list of values is Home Assistant's, asked for the entity when this panel opens; an entity Home
// Assistant names no attribute of - a scene, a switch, a Go to page tile - simply offers the other three.
const sub = computed(() => current("sub", "auto") as string);
const subKind = computed(() => (sub.value.startsWith("attr:") ? "attr" : sub.value.startsWith("text:") || typing.value ? "text" : sub.value));
const subValues = computed(() => state.subtitleValues[props.tile.entity] ?? []);
if (state.subtitleValues[props.tile.entity] === undefined) loadSubtitleValues(props.tile.entity);
const subChoices = computed(() => {
  const keys = ["auto", "none"];
  if (subValues.value.length || subKind.value === "attr") keys.push("attr");
  keys.push("text");
  // A value of the entity and words of your own are tried with a sample of the second step they ask.
  const sample = (kind: string) => kind === "attr" ? `attr:${subAttribute.value || "state"}` : kind === "text" ? "text:x" : kind;
  return offer("sub", keys.map((key) => [key, t(`editor.tile.sub.${key}`)] as [string, string]), subKind.value, sample);
});
const subAttribute = computed(() => (sub.value.startsWith("attr:") ? sub.value.slice(5) : subValues.value[0]?.key ?? ""));
const subText = computed(() => (sub.value.startsWith("text:") ? sub.value.slice(5) : ""));
// "Own text" with nothing typed yet is a kind, not a stored value: writing "text:" with a blank in it would put
// that blank on the tile. The field opens empty and the option follows the first letter.
const typing = ref(false);
function pickSubKind(kind: string) {
  typing.value = kind === "text";
  if (kind === "attr") setTileOption(props.tile, "sub", subAttribute.value ? `attr:${subAttribute.value}` : "auto");
  else if (kind === "text") { if (subText.value) setTileOption(props.tile, "sub", `text:${subText.value}`); }
  else setTileOption(props.tile, "sub", kind);
}
function writeSubText(value: string) {
  const words = value.trim();
  // Typing words of your own is one step of undo, as typing the name is (app 0.4.2).
  setTileOption(props.tile, "sub", words ? `text:${words}` : "none", `sub:${props.tile.id}`);
}
const inline = computed(() => current("inline", "none") as string);
const showSlider = computed(() => !taller.value && SLIDER_DOMAINS.includes(domain.value) && (inline.value === "slider" ||
  ((!caps.value || caps.value.inline) && choiceOffered(props.tile, "inline", "slider", controlled.value))));
const sliderWarn = computed(() => inline.value === "slider" && caps.value && !caps.value.inline);
const history = computed(() => current("history_hours", 24) as number);
const backgrounds = computed(() => Object.entries(state.inventory.backgrounds || {}));
const fromHA = computed(() => Boolean(state.inventory.entities.find((e) => e.id === props.tile.entity)?.icon));
const showIcon = computed(() => Boolean(state.inventory.icons) && (domain.value !== "screen" || goesTo.value > 0) && !["forecast", "sunpath"].includes(display.value));
function inspect() {
  // This tile's own data: its entity may be on several tiles (firmware 0.16.0+).
  state.inspector = { kind: "inspect", entity: props.tile.entity, slot: props.tile.slot, key: props.tile.key };
}
// The way up in the head: the page the tile stands on opens that page's settings.
const pageId = computed(() => state.document?.pages.find((page) => page.tiles.some((item) => item.id === (holder.value || props.tile).id))?.id);
const crumbs = computed(() => [
  { text: t("editor.page.label", { page: pageHere.value }), open: pageId.value ? () => openPage(pageId.value!) : undefined },
  ...(holder.value ? [{ text: holder.value.name || screenBuiltinName(holder.value.entity) || entityName(holder.value.entity), open: () => openTile(holder.value!) }] : []),
  { text: props.tile.entity, mono: true },
]);
const lookShown = computed(() => !goesTo.value && !bedside.value && !key.value && (props.tile.entity !== "screen.settings" || display.value === "live" || domain.value === "sensor"));
const controlsShown = computed(() => (domain.value !== "screen" && !goesTo.value) || Boolean(catalogue.value && size.value !== "single" && !goesTo.value) || (showSlider.value && !goesTo.value));
// What the pointer rests on is drawn on the tile before it is picked (ChoiceField does the same for its lists).
const subSample = (kind: string) => kind === "attr" ? `attr:${subAttribute.value || "state"}` : kind === "text" ? `text:${subText.value || t("editor.tile.sub.text_placeholder")}` : kind;
const controlSample = (key: string) => domain.value === "cover" ? withCoverTilt(key, tiltSelected.value) : key;
function previewBackground(key: string | null) {
  if (key && props.tile.id && key !== (props.tile.options?.background || "auto")) state.optionPreview = { tileId: props.tile.id, key: "background", value: key };
  else if (state.optionPreview?.key === "background") state.optionPreview = null;
}
const backgroundName = computed(() => state.inventory.backgrounds?.[props.tile.options?.background || "auto"]?.label || "");
</script>

<template>
  <InspectorHead :title="tile.name || name" :code="tileIconCp(tile)" :tone="{ color: domainInfo(tile.entity)[2], background: domainInfo(tile.entity)[3] }" :crumbs="crumbs" kind="tile">
    <!-- The name is edited where it stands, as a title: empty is the name Home Assistant gives it. -->
    <template #title>
      <input id="tile-name" class="dr-title" :value="nameDraft.value.value" :placeholder="name" maxlength="60" :aria-label="t('editor.tile.name')" :title="t('editor.tile.name')"
        @focus="beginFieldEdit(`tile:${tile.id}`); nameDraft.focus()" @blur="endFieldEdit(); nameDraft.blur()" @keydown.enter="($event.target as HTMLInputElement).blur()"
        @input="nameDraft.input(($event.target as HTMLInputElement).value)" />
    </template>
    <template #actions>
      <UiMenu width="220px">
        <template #trigger><button type="button" class="icon-btn" id="tile-more" :aria-label="t('editor.screen_view.more')"><Icon name="dots-horizontal" /></button></template>
        <UiMenuItem v-if="domain !== 'screen'" icon="database-search-outline" @select="inspect">{{ t("editor.common.read_current_data") }}</UiMenuItem>
        <UiMenuSeparator v-if="domain !== 'screen'" />
        <UiMenuItem icon="delete-outline" danger hint="⌫" @select="removeTile(tile)">{{ t("editor.common.remove") }}</UiMenuItem>
      </UiMenu>
    </template>
  </InspectorHead>
  <div class="dr-body">
    <p v-if="bedside" class="hint">{{ t("editor.tile.keys.hint") }}</p>
    <p v-if="key" class="hint">{{ t("editor.tile.keys.under") }}</p>
    <!-- A key's name under its circle (firmware 0.17.0+): off leaves the circle alone, as a picture can drop its name. -->
    <Section v-if="key && supports(0, 17, 0)" :title="t('editor.tile.sections.look')">
      <SwitchRow class="key-name-choice" :label="t('editor.tile.keys.name_shown')" :description="t('editor.tile.keys.name_shown_hint')"
        :model-value="tile.options?.overlay !== 'none'" @update:model-value="(on) => setTileOption(tile, 'overlay', on ? 'name' : 'none')" />
    </Section>

    <!-- What the card shows first, then where it stands, what a finger does to it, and last its icon and colour. -->
    <template v-if="!phone || more">
    <Section v-if="lookShown || (!bedside && !key)" :title="t('editor.tile.sections.look')">
      <p v-if="energyTile" class="hint">{{ t(supports(0, 47, 0) ? "editor.tile.energy.hint" : "editor.tile.energy.needs_firmware") }}</p>
      <PropRow v-if="lookShown && tile.entity !== 'screen.settings' && !mapTile && !energyTile" :label="t('editor.tile.display.label')" icon="eye-outline" :hint="displayHint && !displayWarns ? displayHint : undefined">
        <ChoiceField :choices="displays" :value="display" :tile="tile" preview-key="display" :aria-label="t('editor.tile.display.label')" @pick="(v) => setTileOption(tile, 'display', v)" />
        <template v-if="displayHint && displayWarns" #note><small class="help warn">{{ displayHint }}</small></template>
      </PropRow>
      <!-- A bedside clock and its keys have no second line: the clock draws the time, a key its name alone. -->
      <PropRow v-if="!bedside && !key && !mapCard && !energyTile" :label="t('editor.tile.sub.label')" icon="text-short" :hint="t(`editor.tile.sub.hint_${subKind}`)">
        <ChoiceField :choices="subChoices" :value="subKind" :tile="tile" preview-key="sub" :sample="subSample" :aria-label="t('editor.tile.sub.label')" @pick="pickSubKind" />
        <template v-if="subKind === 'attr' || subKind === 'text'" #note>
          <UiSelect v-if="subKind === 'attr'" class="sub-value" :model-value="subAttribute" :options="subValues.map((value) => [value.key, value.name] as [string, string])"
            :aria-label="t('editor.tile.sub.value_aria')" @update:model-value="(key) => setTileOption(tile, 'sub', `attr:${key}`)" />
          <input v-else class="sub-text" :value="subText" maxlength="60"
            @focus="beginFieldEdit(`sub:${tile.id}`)" @blur="endFieldEdit()"
            :placeholder="t('editor.tile.sub.text_placeholder')" :aria-label="t('editor.tile.sub.text_aria')"
            @input="writeSubText(($event.target as HTMLInputElement).value)" />
        </template>
      </PropRow>
      <PropRow v-if="lookShown && display === 'live'" :label="t('editor.tile.refresh.label')" icon="refresh">
        <ChoiceField :choices="refreshChoices" :value="refresh" :aria-label="t('editor.tile.refresh.label')" @pick="(v) => setTileOption(tile, 'refresh', Number(v))" />
      </PropRow>
      <PropRow v-if="lookShown && pictureCard" :label="t('editor.tile.picture.fit.label')" icon="resize">
        <ChoiceField :choices="pictureChoices('fit')" :value="current('fit', 'fill')" :tile="tile" preview-key="fit" :aria-label="t('editor.tile.picture.fit.label')" @pick="(v) => setTileOption(tile, 'fit', v)" />
      </PropRow>
      <PropRow v-if="lookShown && pictureCard" :label="t('editor.tile.picture.overlay.label')" icon="format-title">
        <ChoiceField :choices="pictureChoices('overlay')" :value="current('overlay', 'name')" :tile="tile" preview-key="overlay" :aria-label="t('editor.tile.picture.overlay.label')" @pick="(v) => setTileOption(tile, 'overlay', v)" />
      </PropRow>
      <PropRow v-if="lookShown && domain === 'sensor'" :label="t('editor.tile.history.label')" icon="clock-outline">
        <ChoiceField :choices="historyChoices" :value="history" :tile="tile" preview-key="history_hours" :aria-label="t('editor.tile.history.label')" @pick="(v) => setTileOption(tile, 'history_hours', Number(v))" />
      </PropRow>
    </Section>


    <!-- A favourite (app 0.4.42): what it plays, from the player's library, and on which speaker. -->
    <Section v-if="lookShown && favoriteCard" :title="t('editor.tile.display.favorite')">
      <PropRow :label="t('editor.tile.favorite.plays')" icon="playlist-music">
        <div class="favorite-chosen">
          <span v-if="favoritePlay" class="favorite-title">{{ favoritePlay.title }}</span>
          <span v-else class="help warn">{{ t('editor.tile.favorite.none') }}</span>
          <button type="button" class="btn quiet mini" @click="choosing = !choosing">{{ t(choosing ? 'editor.tile.favorite.done' : 'editor.tile.favorite.choose') }}</button>
        </div>
        <template v-if="choosing || !favoritePlay" #note>
          <FavoritePicker :entity="tile.entity" :chosen="favoritePlay" @pick="pickFavorite" />
        </template>
      </PropRow>
      <PropRow :label="t('editor.tile.favorite.speaker')" icon="speaker" :hint="t('editor.tile.favorite.speaker_hint')">
        <UiSelect :model-value="(tile.options?.speaker as string) || ''" :options="speakers" :aria-label="t('editor.tile.favorite.speaker')" @update:model-value="pickSpeaker" />
      </PropRow>
    </Section>

    <!-- A map (app 0.4.33, the map tile and these choices 0.4.36): whom it follows, how it frames them, how it looks. -->
    <Section v-if="lookShown && mapCard" :title="t('editor.tile.display.map')">
      <p v-if="mapTile" class="hint">{{ t(supports(0, 21, 0) ? "editor.tile.display.map_hint" : "editor.tile.display.map_tile_needs_firmware") }}</p>
      <PropRow v-if="mapTile" :label="t('editor.tile.map.follow.label')" icon="account-eye-outline"
        :hint="mapFollow === 'everyone' ? t('editor.tile.map.follow.everyone_hint') : undefined">
        <ChoiceField :choices="mapChoices('follow')" :value="mapFollow" :tile="tile" preview-key="follow" :aria-label="t('editor.tile.map.follow.label')" @pick="(v) => setTileOption(tile, 'follow', v)" />
      </PropRow>
      <PropRow v-if="mapListed" :label="t(mapTile ? 'editor.tile.map.chosen.label' : 'editor.tile.map.with.label')" icon="account-multiple-outline"
        :hint="t(mapTile ? 'editor.tile.map.chosen.hint' : 'editor.tile.map.with.hint')">
        <div class="map-with">
          <span v-for="item in mapWith" :key="item" class="map-person">
            {{ entityName(item) }}
            <button type="button" class="map-remove" :aria-label="t('editor.tile.map.with.remove', { name: entityName(item) })" @click="removeMapEntity(item)"><Icon name="close" /></button>
          </span>
          <UiSelect v-if="!mapFull && mapOffered.length" class="map-add" :model-value="''" :options="mapOffered"
            :placeholder="t('editor.tile.map.with.add')" :aria-label="t('editor.tile.map.with.add')" @update:model-value="addMapEntity" />
        </div>
      </PropRow>
      <PropRow :label="t('editor.tile.map.framing.label')" icon="crosshairs-gps">
        <ChoiceField :choices="mapChoices('framing')" :value="mapFraming" :tile="tile" preview-key="framing" :aria-label="t('editor.tile.map.framing.label')" @pick="(v) => setTileOption(tile, 'framing', v)" />
      </PropRow>
      <PropRow v-if="mapFraming !== 'everyone'" :label="t('editor.tile.map.distance.label')" icon="magnify-plus-outline">
        <ChoiceField :choices="mapChoices('distance')" :value="current('distance', MAP?.distance[0])" :tile="tile" preview-key="distance" :aria-label="t('editor.tile.map.distance.label')" @pick="(v) => setTileOption(tile, 'distance', v)" />
      </PropRow>
      <PropRow :label="t('editor.tile.map.markers.label')" icon="account-circle-outline">
        <ChoiceField :choices="mapChoices('markers')" :value="current('markers', MAP?.markers[0])" :tile="tile" preview-key="markers" :aria-label="t('editor.tile.map.markers.label')" @pick="(v) => setTileOption(tile, 'markers', v)" />
      </PropRow>
      <PropRow :label="t('editor.tile.map.names.label')" icon="label-outline">
        <ChoiceField :choices="mapChoices('names')" :value="current('names', MAP?.names[0])" :tile="tile" preview-key="names" :aria-label="t('editor.tile.map.names.label')" @pick="(v) => setTileOption(tile, 'names', v)" />
      </PropRow>
      <PropRow :label="t('editor.tile.map.zones.label')" icon="map-marker-radius-outline">
        <ChoiceField :choices="mapChoices('zones')" :value="current('zones', MAP?.zones[0])" :tile="tile" preview-key="zones" :aria-label="t('editor.tile.map.zones.label')" @pick="(v) => setTileOption(tile, 'zones', v)" />
      </PropRow>
      <PropRow :label="t('editor.tile.map.streets.label')" icon="road-variant">
        <ChoiceField :choices="mapChoices('streets')" :value="current('streets', MAP?.streets[0])" :tile="tile" preview-key="streets" :aria-label="t('editor.tile.map.streets.label')" @pick="(v) => setTileOption(tile, 'streets', v)" />
      </PropRow>
      <PropRow :label="t('editor.tile.map.look.label')" icon="theme-light-dark">
        <ChoiceField :choices="mapChoices('look')" :value="current('look', MAP?.look[0])" :tile="tile" preview-key="look" :aria-label="t('editor.tile.map.look.label')" @pick="(v) => setTileOption(tile, 'look', v)" />
      </PropRow>
      <PropRow :label="t('editor.tile.picture.overlay.label')" icon="format-title">
        <ChoiceField :choices="pictureChoices('overlay')" :value="current('overlay', 'name')" :tile="tile" preview-key="overlay" :aria-label="t('editor.tile.picture.overlay.label')" @pick="(v) => setTileOption(tile, 'overlay', v)" />
      </PropRow>
    </Section>

    <!-- A tile's size is set on the tile itself, with its handles (app 0.4.32): the settings keep what it does. -->
    <Section v-if="controlsShown || goesTo" :title="t('editor.tile.sections.controls')">
      <PropRow v-if="goesTo" :label="t('editor.tile.goes_to.label')" icon="arrow-right" :hint="goesToHint && !goesToHint.warn ? goesToHint.text : undefined">
        <ChoiceField :choices="pages" :value="goesTo" :aria-label="t('editor.tile.goes_to.label')" @pick="(v) => retargetPageTile(tile, Number(v))" />
        <template v-if="goesToHint?.warn" #note><small class="help warn">{{ goesToHint.text }}</small></template>
      </PropRow>
      <PropRow v-if="domain !== 'screen' && !goesTo" :label="t('editor.tile.tap.label')" icon="gesture-tap">
        <ChoiceField :choices="taps" :value="tap" :aria-label="t('editor.tile.tap.label')" @pick="pickTap" />
        <template v-if="tapHint" #note>
          <small v-if="tapHint.warn" class="help warn">{{ tapHint.text }}</small>
          <span v-else class="gesture-note">{{ tapHint.text }}</span>
        </template>
      </PropRow>
      <ActionPicker v-if="domain !== 'screen' && !goesTo && tap === 'action'" :tile="tile" />
      <PropRow v-if="domain === 'lock'" :label="t('editor.tile.guard.label')" icon="check-circle" :hint="t(guard === 'lock_only' ? 'editor.tile.guard.lock_only_hint' : 'editor.tile.guard.confirm_hint')">
        <ChoiceField :choices="guards" :value="guard" :aria-label="t('editor.tile.guard.label')" @pick="(v) => setTileOption(tile, 'guard', v)" />
      </PropRow>
      <PropRow v-if="catalogue && size !== 'single' && !goesTo" :label="t('editor.tile.controls.label')" icon="tune-variant" :hint="controlHint && !controlHint.warn ? controlHint.text : undefined">
        <ChoiceField :choices="controlChoices" :value="primaryControl" :tile="tile" preview-key="controls" :sample="controlSample" :aria-label="t('editor.tile.controls.label')" @pick="pickControl" />
        <template v-if="controlHint?.warn" #note><small class="help warn">{{ controlHint.text }}</small></template>
      </PropRow>
      <SwitchRow v-if="offerTilt" class="tilt-choice" :label="t('editor.tile.controls.tilt')" :description="t('editor.tile.controls.tilt_hint')"
        :model-value="tiltSelected" @update:model-value="(on) => setTileOption(tile, 'controls', withCoverTilt(primaryControl, on))" />
      <SwitchRow v-if="showSlider && !goesTo && !key" class="slider-choice" :label="t('editor.tile.slider.label')"
        :model-value="inline === 'slider'" @update:model-value="(on) => setTileOption(tile, 'inline', on ? 'slider' : 'none')">
        <small v-if="sliderWarn" class="warn">{{ t("editor.tile.slider.nothing") }}</small>
      </SwitchRow>
    </Section>
    </template>

    <Section :title="t('editor.tile.sections.style')" class="style-section">
      <IconPicker v-if="showIcon" :tile="tile" :selected="tile.options?.icon || 'auto'" :automatic="automaticIcon(tile.entity)"
        :auto-label="t(fromHA ? 'editor.tile.icon.auto_ha' : 'editor.tile.icon.auto_default')"
        :note="supports(0, 2, 18) ? '' : t('editor.tile.icon.needs_firmware')"
        @pick="(n) => setTileOption(tile, 'icon', n)" />
      <PropRow v-if="!key" :label="t('editor.tile.background.label')" icon="palette-outline" stack>
        <template #aside>{{ backgroundName }}</template>
        <div class="sw" @pointerleave="previewBackground(null)">
          <button v-for="[key, choice] in backgrounds" :key="key" type="button" :aria-label="t('editor.tile.background.aria', { name: choice.label })" :title="choice.label"
            :aria-pressed="(tile.options?.background || 'auto') === key ? 'true' : 'false'" @pointerenter="previewBackground(key)" @click="previewBackground(null); setTileOption(tile, 'background', key)">
            <i :class="choice.color ? '' : key === 'none' ? 'none' : 'auto'" :style="choice.color ? { background: choice.color } : undefined"></i>
          </button>
        </div>
      </PropRow>
    </Section>
    <template v-if="phone">
      <button v-if="!more" type="button" class="phone-more" @click="more = true">
        <span><b>{{ t("editor.phone.more_settings") }}</b><small>{{ t("editor.phone.more_settings_hint") }}</small></span><Icon name="chevron-right" />
      </button>
      <div class="phone-tile-actions">
        <UiMenu v-if="!key && !bedside && otherPages.length" width="240px">
          <template #trigger><button type="button" class="btn"><Icon name="arrow-right" />{{ t("editor.phone.move") }}</button></template>
          <UiMenuItem v-for="page in otherPages" :key="page.index" icon="view-column-outline" @select="moveTile(page.index)">{{ page.name }}</UiMenuItem>
        </UiMenu>
        <button type="button" class="btn danger-soft" @click="removeTile(tile)"><Icon name="delete-outline" />{{ t("editor.common.remove") }}</button>
      </div>
    </template>
  </div>
</template>
