<script setup lang="ts">
import { editorLayout } from "../store";
const { grid, pageCount, pageOf } = editorLayout;

import { tileSizeChoices } from "../store";
import HelpTip from "./HelpTip.vue";
// One tile's settings. Every change applies live, so the card on the mockup shows the result while you pick.
import { computed, ref, toRaw } from "vue";
import { t } from "../i18n";
import { beginFieldEdit, endFieldEdit } from '../store';
import { domainInfo, entriesOf, inlineControlKind, pageTarget, SLIDER_DOMAINS, TOGGLE_BEFORE } from "../model/layout";
import { glyph } from "../model/topbar";
import { currentScreen, automaticIcon, closeInspector, entityName, fullPage, loadSubtitleValues, setTileName, moveTileToPage, pictures, removeTile, retargetPageTile, setTileOption, state, supports, tileIconCp } from "../store";
import type { Tile } from "../types";
import ActionPicker from "./ActionPicker.vue";
import IconPicker from "./IconPicker.vue";
import { coverPrimary, hasCoverTilt, withCoverTilt } from "../model/tall-controls";
import Segmented from "./Segmented.vue";
import { textDraft } from '../model/text-draft';
import rules from "../model/page-rules.json";

const props = defineProps<{ tile: Tile }>();
const nameDraft = textDraft(() => props.tile.name, value => setTileName(props.tile, value));
const domain = computed(() => props.tile.entity.split(".")[0]);
const name = computed(() => entityName(props.tile.entity));
// A navigation tile (screen.page_<n>): the page it opens, its size, icon and colour; nothing else applies.
const goesTo = computed(() => pageTarget(props.tile.entity));
// Pages counted from 1. "Goes to page" offers the pages the screen has and the empty one after them, where a sub-page
// starts (app 0.2.78), and keeps a target beyond those so the choice stays visible.
const pageTotal = computed(() => (state.layout ? pageCount(entriesOf(state.layout), state.layout.pages) : 1));
const pageHere = computed(() => pageOf(props.tile.slot) + 1);
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
// Moving the tile without a drag (app 0.2.78): another page, or a new one after the last. A tile alone on the last page
// gets no "New page", which would only leave an empty page behind; with nowhere to go the row stays hidden.
const alone = computed(() => !state.layout?.tiles.some((t) => toRaw(t) !== toRaw(props.tile) && pageOf(t.slot) === pageHere.value - 1));
const onPage = computed(() => {
  const list = Array.from({ length: pageTotal.value }, (_, i) => [i + 1, String(i + 1)] as [number, string]);
  if (pageTotal.value < grid.pages && !(alone.value && pageHere.value === pageTotal.value)) list.push([pageTotal.value + 1, t("editor.tile.page.new")]);
  return list;
});
const sizes = computed<[string, string][]>(() => tileSizeChoices(props.tile).map(key => [key, t(`editor.tile.size.${key}`)]));
const sizeHint = computed(() => ["tall", "square"].includes(String(props.tile.options?.size)) ? t("editor.tile.size.rectangle_hint") : goesTo.value ? "" : fullPage.value ? t("editor.tile.size.full_hint") : t("editor.tile.size.needs_firmware"));
const caps = computed(() => state.capabilities[props.tile.entity]);
const current = (key: string, fallback: unknown) => props.tile.options?.[key] ?? fallback;
const clock = computed(() => props.tile.entity === "screen.clock");
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
    return true;
  });
  return keys.map((key) => [key, t(`editor.tile.display.${key}`)] as [string, string]);
});
// A live camera on a 1x2 or 2x2 tile fills the card (app 0.3.8, firmware 0.3.3): whole or cut to fill it, its name on it or nothing.
const pictureCard = computed(() => display.value === "live" && taller.value);
// A hint is a warning unless the screen's firmware already does what it describes.
const clockFace = computed(() => clock.value && ["dial", "flip"].includes(display.value));
const displayWarns = computed(() => !(display.value === "live" && (pictureCard.value ? supports(0, 3, 3) : supports(0, 2, 77))) && !(display.value === "cover" && supports(0, 2, 78)) && !(clockFace.value && supports(0, 3, 6)));
const pictureChoices = (key: "fit" | "overlay") => rules.picture[key].map((value) => [value, t(`editor.tile.picture.${key}.${value}`)] as [string, string]);
const displayHint = computed(() => {
  const c = caps.value;
  if (c && display.value === "graph" && !c.displays.includes("graph")) return t("editor.tile.display.no_graph");
  if (c && display.value === "forecast" && !c.displays.includes("forecast")) return t("editor.tile.display.no_forecast");
  if (display.value === "live" && taller.value) return t(supports(0, 3, 3) ? "editor.tile.display.live_card_hint" : "editor.tile.display.live_card_needs_firmware");
  if (display.value === "live") return t(supports(0, 2, 77) ? "editor.tile.display.live_hint" : "editor.tile.display.live_needs_firmware");
  if (display.value === "cover" && taller.value) return t("editor.tile.display.tall_cover_hint");
  if (display.value === "cover") return t(supports(0, 2, 78) ? "editor.tile.display.cover_hint" : "editor.tile.display.cover_needs_firmware");
  // The calm dial and the flip clock (firmware 0.3.6): an older screen shows the digital clock until it is updated.
  if (clockFace.value && !supports(0, 3, 6)) return t("editor.tile.display.face_needs_firmware");
  return "";
});
const refresh = computed(() => current("refresh", 15) as number);
const size = computed(() => current("size", "single") as string);
const taller = computed(() => ["tall", "square"].includes(size.value));
const catalogue = computed(() => state.inventory.controls?.[domain.value]);
const controls = computed(() => taller.value && current("inline", "none") === "slider" ? inlineControlKind(domain.value) : current("controls", ["tall", "full"].includes(size.value) ? "none" : catalogue.value?.default) as string);
const primaryControl = computed(() => domain.value === 'cover' ? coverPrimary(controls.value) : controls.value);
const tiltSelected = computed(() => domain.value === 'cover' && hasCoverTilt(controls.value));
const offerTilt = computed(() => domain.value === 'cover' && ['tall', 'square', 'full'].includes(size.value)
  && (tiltSelected.value || caps.value?.controls.includes('tilt')));
function pickControl(value: string) {
  setTileOption(props.tile, 'controls', domain.value === 'cover' ? withCoverTilt(value, tiltSelected.value) : value);
}
const controlChoices = computed(() => {
  const c = caps.value;
  // Temperature and mode need a second row: offered on 1 x 2, 2 x 2 and full-page cards only.
  return (catalogue.value?.choices || []).filter(ch => domain.value !== "cover" || !hasCoverTilt(ch.key))
    .filter(ch => ch.key !== "setpoint_mode" || ["tall", "square", "full"].includes(size.value)).filter((ch) => !c || ch.key === "none" || ch.key === primaryControl.value || c.controls.includes(ch.key)).map((ch) => [ch.key, ch.label] as [string, string]);
});
const controlHint = computed(() => {
  const c = caps.value;
  if (c && controls.value !== "none" && !c.controls.includes(controls.value)) return { text: t("editor.tile.controls.not_offered"), warn: true };
  return { text: supports(0, 2, 19)
    ? t(taller.value ? "editor.tile.controls.tall_hint" : size.value === "full" ? "editor.tile.controls.full_hint" : "editor.tile.controls.wide_hint")
    : t("editor.tile.controls.needs_firmware"), warn: false };
});
const tap = computed(() => current("tap", "auto") as string);
const taps = computed(() => {
  const keys = ["auto", "detail", "none"];
  // On / off where Home Assistant can toggle the entity, such as a cover; a speaker without on and off gets none.
  if ((caps.value ? caps.value.toggle : TOGGLE_BEFORE.includes(domain.value)) || tap.value === "toggle") keys.push("toggle");
  keys.push("action");
  return keys.map((key) => [key, t(`editor.tile.tap.${key}`)] as [string, string]);
});
const tapHint = computed(() => {
  if (tap.value === "toggle" && caps.value && !caps.value.toggle) return { text: t("editor.tile.tap.no_toggle"), warn: true };
  if (tap.value === "toggle" && !TOGGLE_BEFORE.includes(domain.value) && !supports(0, 2, 58)) return { text: t("editor.tile.tap.toggle_needs_firmware"), warn: false };
  if (tap.value === "toggle") return { text: t("editor.tile.tap.hold"), warn: false };
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
  return keys.map((key) => [key, t(`editor.tile.sub.${key}`)] as [string, string]);
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
  setTileOption(props.tile, "sub", words ? `text:${words}` : "none");
}
const inline = computed(() => current("inline", "none") as string);
const showSlider = computed(() => !taller.value && SLIDER_DOMAINS.includes(domain.value) && (!caps.value || caps.value.inline || inline.value === "slider"));
const sliderWarn = computed(() => inline.value === "slider" && caps.value && !caps.value.inline);
const history = computed(() => current("history_hours", 24) as number);
const backgrounds = computed(() => Object.entries(state.inventory.backgrounds || {}));
const fromHA = computed(() => Boolean(state.inventory.entities.find((e) => e.id === props.tile.entity)?.icon));
const showIcon = computed(() => Boolean(state.inventory.icons) && (domain.value !== "screen" || goesTo.value > 0) && !["forecast", "sunpath"].includes(display.value));
function inspect() {
  state.inspector = { kind: "inspect", entity: props.tile.entity };
}
</script>

<template>
  <div class="dr-head">
    <span class="av mdi" :style="{ color: domainInfo(tile.entity)[2], background: domainInfo(tile.entity)[3] }">{{ glyph(tileIconCp(tile)) }}</span>
    <span class="tx"><b>{{ tile.name || name }}</b><small class="mono">{{ tile.entity }}</small></span>
    <button type="button" class="icon-btn" :aria-label="t('editor.common.close')" @click="closeInspector">✕</button>
  </div>
  <div class="dr-body">
    <div class="f">
      <label class="f-label" for="tile-name">{{ t("editor.tile.name") }}</label>
      <input id="tile-name" :value="nameDraft.value.value" :placeholder="name" maxlength="60"
        @focus="beginFieldEdit(`tile:${tile.id}`); nameDraft.focus()" @blur="endFieldEdit(); nameDraft.blur()"
        @input="nameDraft.input(($event.target as HTMLInputElement).value)" />
    </div>
    <IconPicker v-if="showIcon" :selected="tile.options?.icon || 'auto'" :automatic="automaticIcon(tile.entity)"
      :auto-label="t(fromHA ? 'editor.tile.icon.auto_ha' : 'editor.tile.icon.auto_default')"
      :note="supports(0, 2, 18) ? '' : t('editor.tile.icon.needs_firmware')"
      @pick="(n) => setTileOption(tile, 'icon', n)" />
    <div v-if="goesTo" class="f">
      <span class="f-label">{{ t("editor.tile.goes_to.label") }}</span>
      <Segmented :choices="pages" :value="goesTo" @pick="(v) => retargetPageTile(tile, Number(v))" />
      <template v-if="goesToHint"><small v-if="goesToHint.warn" class="warn">{{ goesToHint.text }}</small><HelpTip v-else :text="goesToHint.text" /></template>
    </div>
    <div v-else-if="tile.entity !== 'screen.settings'" class="f">
      <span class="f-label">{{ t("editor.tile.display.label") }}</span>
      <Segmented :choices="displays" :value="display" @pick="(v) => setTileOption(tile, 'display', v)" />
      <small v-if="displayHint" :class="{ warn: displayWarns }">{{ displayHint }}</small>
    </div>
    <div v-if="display === 'live'" class="f">
      <span class="f-label">{{ t("editor.tile.refresh.label") }}</span>
      <Segmented :choices="[15, 30].map((seconds) => [seconds, t('editor.tile.refresh.seconds', { n: seconds })] as [number, string])" :value="refresh" @pick="(v) => setTileOption(tile, 'refresh', Number(v))" />
    </div>
    <div v-if="pictureCard" class="f">
      <span class="f-label">{{ t("editor.tile.picture.fit.label") }}</span>
      <Segmented :choices="pictureChoices('fit')" :value="current('fit', 'fill')" @pick="(v) => setTileOption(tile, 'fit', v)" />
    </div>
    <div v-if="pictureCard" class="f">
      <span class="f-label">{{ t("editor.tile.picture.overlay.label") }}</span>
      <Segmented :choices="pictureChoices('overlay')" :value="current('overlay', 'name')" @pick="(v) => setTileOption(tile, 'overlay', v)" />
    </div>
    <div class="f">
      <span class="f-label">{{ t("editor.tile.size.label") }}</span>
      <Segmented :choices="sizes" :value="size" @pick="(v) => setTileOption(tile, 'size', v)" />
      <HelpTip v-if="sizeHint" :text="sizeHint" />
    </div>
    <div v-if="onPage.length > 1" class="f">
      <span class="f-label">{{ t("editor.tile.page.label") }}</span>
      <Segmented :choices="onPage" :value="pageHere" @pick="(v) => moveTileToPage(tile, Number(v) - 1)" />
    </div>
    <div v-if="catalogue && ['wide', 'tall', 'square', 'full'].includes(size) && !goesTo" class="f">
      <span class="f-label">{{ t("editor.tile.controls.label") }}</span>
      <Segmented :choices="controlChoices" :value="primaryControl" @pick="pickControl" />
      <template v-if="controlHint"><small v-if="controlHint.warn" class="warn">{{ controlHint.text }}</small><HelpTip v-else :text="controlHint.text" /></template>
    </div>
    <div v-if="offerTilt" class="f">
      <label class="check tilt-choice"><input type="checkbox" :checked="tiltSelected" @change="setTileOption(tile, 'controls', withCoverTilt(primaryControl, !tiltSelected))" /> {{ t('editor.tile.controls.tilt') }}</label>
      <HelpTip :text="t('editor.tile.controls.tilt_hint')" />
    </div>
    <div v-if="domain !== 'screen' && !goesTo" class="f">
      <span class="f-label">{{ t("editor.tile.tap.label") }}</span>
      <Segmented :choices="taps" :value="tap" @pick="(v) => setTileOption(tile, 'tap', v)" />
      <template v-if="tapHint"><small v-if="tapHint.warn" class="warn">{{ tapHint.text }}</small><HelpTip v-else :text="tapHint.text" /></template>
    </div>
    <ActionPicker v-if="domain !== 'screen' && !goesTo && tap === 'action'" :tile="tile" />
    <div class="f">
      <span class="f-label">{{ t("editor.tile.sub.label") }}</span>
      <Segmented :choices="subChoices" :value="subKind" @pick="pickSubKind" />
      <select v-if="subKind === 'attr'" class="sub-value" :value="subAttribute"
        :aria-label="t('editor.tile.sub.value_aria')" @change="setTileOption(tile, 'sub', `attr:${($event.target as HTMLSelectElement).value}`)">
        <option v-for="value in subValues" :key="value.key" :value="value.key">{{ value.name }}</option>
      </select>
      <input v-if="subKind === 'text'" class="sub-text" :value="subText" maxlength="60"
        :placeholder="t('editor.tile.sub.text_placeholder')" :aria-label="t('editor.tile.sub.text_aria')"
        @input="writeSubText(($event.target as HTMLInputElement).value)" />
      <HelpTip :text="t(`editor.tile.sub.hint_${subKind}`)" />
    </div>
    <div v-if="showSlider && !goesTo" class="f">
      <span class="f-label">{{ t("editor.tile.slider.label") }}</span>
      <Segmented :choices="[['none', t('editor.tile.slider.no')], ['slider', t('editor.tile.slider.yes')]]" :value="inline" @pick="(v) => setTileOption(tile, 'inline', v)" />
      <small v-if="sliderWarn" class="warn">{{ t("editor.tile.slider.nothing") }}</small>
    </div>
    <div v-if="domain === 'sensor' && !goesTo" class="f">
      <span class="f-label">{{ t("editor.tile.history.label") }}</span>
      <Segmented :choices="[1, 6, 24].map((hours) => [hours, t('editor.tile.history.hours', hours)] as [number, string])" :value="history" @pick="(v) => setTileOption(tile, 'history_hours', Number(v))" />
    </div>
    <div class="f">
      <span class="f-label">{{ t("editor.tile.background.label") }}</span>
      <div class="sw">
        <button v-for="[key, choice] in backgrounds" :key="key" type="button" :aria-label="t('editor.tile.background.aria', { name: choice.label })"
          :aria-pressed="(tile.options?.background || 'auto') === key ? 'true' : 'false'" @click="setTileOption(tile, 'background', key)">
          <i :class="choice.color ? '' : key === 'none' ? 'none' : 'auto'" :style="choice.color ? { background: choice.color } : undefined"></i>{{ choice.label }}
        </button>
      </div>
    </div>
  </div>
  <div class="dr-foot">
    <button type="button" class="btn danger" @click="removeTile(tile)">{{ t("editor.common.remove") }}</button>
    <span class="spacer"></span>
    <button v-if="domain !== 'screen'" type="button" class="btn quiet" @click="inspect">{{ t("editor.common.read_current_data") }}</button>
  </div>
</template>
