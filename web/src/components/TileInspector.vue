<script setup lang="ts">
// One tile's settings. Every change applies live, so the card on the mockup shows the result while you pick. What each
// field offers and what it says of a choice is model/tile-options.ts, from the tile, what Home Assistant says the entity
// can do and the screen's firmware; a map's and a favourite's own settings are sections of their own (inspector/).
import { computed, ref, watch } from "vue";
import { t } from "../i18n";
import { domainInfo, entriesOf, inlineControlKind, pageTarget } from "../model/layout";
import { titleOf } from "../model/pages";
import PluginTileInspector from "./PluginTileInspector.vue";
import TileEntityFix from "./TileEntityFix.vue";
import type { Tile } from "../types";
import ActionPicker from "./ActionPicker.vue";
import IconPicker from "./IconPicker.vue";
import { coverPrimary, hasCoverTilt, withCoverTilt } from "../model/tall-controls";
import ChoiceField from "./ChoiceField.vue";
import FavoriteSection from "./inspector/FavoriteSection.vue";
import MapSection from "./inspector/MapSection.vue";
import NameField from "./inspector/NameField.vue";
import TitleButton from "./inspector/TitleButton.vue";
import PropRow from "./ui/PropRow.vue";
import Icon from "./ui/Icon.vue";
import InspectorHead from "./ui/InspectorHead.vue";
import Section from "./ui/Section.vue";
import SwitchRow from "./ui/SwitchRow.vue";
import UiSelect from "./ui/UiSelect.vue";
import UiMenu from "./ui/UiMenu.vue";
import UiMenuItem from "./ui/UiMenuItem.vue";
import UiMenuSeparator from "./ui/UiMenuSeparator.vue";
import rules from "../model/page-rules.json";
import { controlChoices, controlHint, displayChoices, displayHint, goesToChoices, goesToHint, offeredChoices, sliderOffered, subChoices,
  tapChoices, tapHint, tileControls, tileDisplay, tiltOffered, type TilePanel } from "../model/tile-options";
import { useUiStore } from "../stores/ui";
import { useRegionStore } from "../stores/region";
import { useEntitiesStore } from "../stores/entities";
import { usePluginsStore } from "../stores/plugins";
import { useScreenStore } from "../stores/screen";
import { useInventoryStore } from "../stores/inventory";
import { moveTileToPage, removeTile, retargetPageTile, setTileOption } from "../editor/tiles";
import { useDocumentStore } from "../stores/document";
import { useInspectorStore } from "../stores/inspector";

const ui = useUiStore();
const region = useRegionStore();
const entities = useEntitiesStore();
const plugins = usePluginsStore();
const scr = useScreenStore();
const inv = useInventoryStore();
const doc = useDocumentStore();
const insp = useInspectorStore();
const { grid, pageCount, pageOf } = doc.editorLayout;

const props = defineProps<{ tile: Tile }>();
// On a phone (app 0.4.40) the sheet starts with what a tile is changed for most: its name, icon and colour, then a way
// to move it or take it off. Everything else stands behind More settings, the same rows as on a wider page.
// Another tile opens its own inspector (Drawer keys it by the tile), so these start closed for every tile.
const more = ref(false);
// The tile goes to the first free cell of another page, and the sheet follows it there.
function moveTile(page: number) {
  const id = doc.document?.pages[page]?.id;
  if (moveTileToPage(props.tile, page) && id) doc.selectedPageId = id;
}
const otherPages = computed(() => (doc.document?.pages || []).map((page, index) => ({ index, name: titleOf(doc.document!, page) || t("editor.page.label", { page: index + 1 }) }))
  .filter((page) => page.index !== pageOf(props.tile.slot)));
const domain = computed(() => props.tile.entity.split(".")[0]);
// A plugin's tile (design) has an inspector of its own, built from the plugin's manifest.
const pluginTile = computed(() => Boolean(plugins.pluginTileOf(props.tile.entity)));
const name = computed(() => entities.entityName(props.tile.entity));
// A navigation tile (screen.page_<n>): the page it opens, its size, icon and colour; nothing else applies. Pages counted
// from 1: the pages the screen has and the empty one after them, where a sub-page starts (app 0.2.78).
const goesTo = computed(() => pageTarget(props.tile.entity));
const pageTotal = computed(() => (doc.layout ? pageCount(entriesOf(doc.layout), doc.layout.pages) : 1));
// A key stands on its clock's page (it has no cell of its own); the clock is on a screen once.
const holder = computed(() => props.tile.in !== undefined ? doc.layout?.tiles.find((item) => item.entity === props.tile.in && item.in === undefined) : undefined);
const pageHere = computed(() => pageOf((holder.value || props.tile).slot) + 1);
const pages = computed(() => goesToChoices(goesTo.value, pageTotal.value, grid.pages, (n) => !doc.layout?.tiles.some((t) => pageOf(t.slot) === n - 1)));
const goesHint = computed(() => goesToHint(goesTo.value, pageTotal.value, scr.fullPage));
const caps = computed(() => entities.capabilities[props.tile.entity]);
const current = (key: string, fallback: unknown) => props.tile.options?.[key] ?? fallback;
// The bedside clock (app 0.4.12): always the whole page, with no face to pick. Its keys are tiles of their own, set here
// like any tile but for what their clock decides for them: their size, their page and their card's colour.
const bedside = computed(() => props.tile.entity === "screen.nightstand");
const key = computed(() => props.tile.in !== undefined);
// What the panel's choices are worked out from (model/tile-options.ts): what Home Assistant says the entity can do, the
// screen's firmware and board, the domain's control sets, and what the entity reports now.
const catalogue = computed(() => inv.inventory.controls?.[domain.value]);
const panel = computed<TilePanel>(() => ({ caps: caps.value, supports: scr.supports, pictures: scr.pictures, catalogue: catalogue.value, columns: grid.columns,
  attributes: entities.liveOf(props.tile.entity)?.a || {}, rangeless: scr.currentScreen?.climate_range === false }));
// Every choice the panel shows is one the add-on saves (app 0.4.0, GitHub #47): tried the way the panel applies it,
// against the same card check the save runs. The tile's own choice always stays in sight.
const offer = <T extends string | number>(key: string, choices: [T, string][], now: unknown) => offeredChoices(props.tile, key, choices, now, Boolean(catalogue.value));
const display = computed(() => tileDisplay(props.tile));
const displays = computed(() => displayChoices(props.tile, panel.value));
const shownHint = computed(() => displayHint(props.tile, panel.value));
// A live camera fills its card on every size, whole or cut to fill it, its name on it or nothing.
const pictureCard = computed(() => display.value === "live");
// A map card (app 0.4.33) and the map tile of the screen's own cards (app 0.4.36): its own section.
const mapCard = computed(() => display.value === "map");
const mapTile = computed(() => props.tile.entity === "screen.map");
// The energy card (app 0.4.77) is its diagram: no face and no second line to choose, its sensors are Home Assistant's.
const energyTile = computed(() => props.tile.entity === "screen.energy");
// A favourite (app 0.4.42): what it plays and on which speaker, in its own section.
const favoriteCard = computed(() => display.value === "favorite" && domain.value === "media_player");
// How the energy card shows power along a line: running dots, or calm lines that grow with it and an arrow each.
const flowChoices = computed(() => offer("flow", rules.energyFlow.map((value) => [value, t(`editor.tile.energy.flow.${value}`)] as [string, string]), current("flow", rules.energyFlow[0])));
const pictureChoices = (key: "fit" | "overlay") => offer(key, rules.picture[key].map((value) => [value, t(`editor.tile.picture.${key}.${value}`)] as [string, string]), current(key, rules.picture[key][0]));
// A screen that streams a camera live (a P4, its hello's `live`): Live, pace 0, is a camera tile's first pace and its
// default there; anywhere else a tile keeps the paces in seconds, and the app sends such a screen 15 s for Live.
const liveCamera = computed(() => domain.value === "camera" && Boolean(scr.currentScreen?.live_camera));
const refresh = computed(() => current("refresh", liveCamera.value ? 0 : 15) as number);
const refreshChoices = computed(() => offer("refresh", rules.refresh.filter((seconds) => seconds !== 0 || liveCamera.value)
  .map((seconds) => [seconds, seconds === 0 ? t("editor.tile.refresh.live") : t("editor.tile.refresh.seconds", { n: seconds })] as [number, string]), refresh.value));
const history = computed(() => current("history_hours", 24) as number);
const historyChoices = computed(() => offer("history_hours", [1, 6, 24].map((hours) => [hours, t("editor.tile.history.hours", hours)] as [number, string]), history.value));
const size = computed(() => current("size", "single") as string);
const controls = computed(() => tileControls(props.tile, panel.value, inlineControlKind(domain.value)));
const primaryControl = computed(() => domain.value === 'cover' ? coverPrimary(controls.value) : controls.value);
const tiltSelected = computed(() => domain.value === 'cover' && hasCoverTilt(controls.value));
const offerTilt = computed(() => tiltOffered(props.tile, panel.value, controls.value));
function pickControl(value: string) {
  setTileOption(props.tile, 'controls', domain.value === 'cover' ? withCoverTilt(value, tiltSelected.value) : value);
}
const controlList = computed(() => controlChoices(props.tile, panel.value, controls.value));
const controlNote = computed(() => controlHint(props.tile, panel.value, controls.value));
// Perform action has a second step, the action: picking it opens the list, and only an action chosen there stores it
// (app 0.4.0, GitHub #47). Until then the tile keeps the tap choice it had.
const choosingAction = ref(false);
const tap = computed(() => choosingAction.value ? "action" : current("tap", "auto") as string);
watch(() => props.tile.options?.tap, (stored) => { if (stored === "action") choosingAction.value = false; });
// A plugin on this screen may offer a tap of its own for this kind of tile (docs/PLUGINS.md): a thermostat that opens its
// schedule.
const taps = computed(() => tapChoices(props.tile, panel.value, tap.value, plugins.pluginsEnabled ? plugins.tapActionsFor(scr.currentScreen, domain.value) : []));
function pickTap(value: string) {
  choosingAction.value = value === "action" && !props.tile.options?.action;
  if (choosingAction.value) insp.actionPickerOpen = true;
  else setTileOption(props.tile, "tap", value);
}
const tapNote = computed(() => tapHint(props.tile, panel.value, tap.value));
// A lock's tile (firmware 0.5.0+): unlock after a second tap on it, or never unlock from this screen.
const guard = computed(() => current("guard", "confirm") as string);
const guards = computed(() => offer("guard", ["confirm", "lock_only"].map((key) => [key, t(`editor.tile.guard.${key}`)] as [string, string]), guard.value));
// ---- The second line (app 0.2.105, firmware 0.2.90+) ----
// Four ways to fill it: the line the screen works out itself, nothing at all, a value of the entity, or words of
// your own. The list of values is Home Assistant's, asked for the entity when this panel opens; an entity Home
// Assistant names no attribute of - a scene, a switch, a Go to page tile - simply offers the other three.
const sub = computed(() => current("sub", "auto") as string);
const subKind = computed(() => (sub.value.startsWith("attr:") ? "attr" : sub.value.startsWith("text:") || typing.value ? "text" : sub.value));
const subValues = computed(() => entities.subtitleValues[props.tile.entity] ?? []);
if (entities.subtitleValues[props.tile.entity] === undefined) entities.loadSubtitleValues(props.tile.entity);
const subAttribute = computed(() => (sub.value.startsWith("attr:") ? sub.value.slice(5) : subValues.value[0]?.key ?? ""));
const subText = computed(() => (sub.value.startsWith("text:") ? sub.value.slice(5) : ""));
const subList = computed(() => subChoices(props.tile, panel.value, subKind.value, subValues.value.length, subAttribute.value));
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
const showSlider = computed(() => sliderOffered(props.tile, panel.value));
const sliderWarn = computed(() => inline.value === "slider" && caps.value && !caps.value.inline);
const backgrounds = computed(() => Object.entries(inv.inventory.backgrounds || {}));
const fromHA = computed(() => Boolean(inv.entityOf(props.tile.entity)?.icon));
const showIcon = computed(() => Boolean(inv.inventory.icons) && (domain.value !== "screen" || goesTo.value > 0) && !["forecast", "sunpath"].includes(display.value));
function inspect() {
  // This tile's own data: its entity may be on several tiles (firmware 0.16.0+).
  insp.inspector = { kind: "inspect", entity: props.tile.entity, slot: props.tile.slot, key: props.tile.key };
}
// The way up in the head: the page the tile stands on opens that page's settings.
const pageId = computed(() => doc.document?.pages.find((page) => page.tiles.some((item) => item.id === (holder.value || props.tile).id))?.id);
const crumbs = computed(() => [
  { text: t("editor.page.label", { page: pageHere.value }), open: pageId.value ? () => insp.openPage(pageId.value!) : undefined },
  ...(holder.value ? [{ text: holder.value.name || region.screenBuiltinName(holder.value.entity) || entities.entityName(holder.value.entity), open: () => insp.openTile(holder.value!) }] : []),
  { text: props.tile.entity, mono: true },
]);
const lookShown = computed(() => !goesTo.value && !bedside.value && !key.value && (props.tile.entity !== "screen.settings" || display.value === "live" || domain.value === "sensor"));
const controlsShown = computed(() => (domain.value !== "screen" && !goesTo.value) || Boolean(catalogue.value && size.value !== "single" && !goesTo.value) || (showSlider.value && !goesTo.value));
// What the pointer rests on is drawn on the tile before it is picked (ChoiceField does the same for its lists).
const subSample = (kind: string) => kind === "attr" ? `attr:${subAttribute.value || "state"}` : kind === "text" ? `text:${subText.value || t("editor.tile.sub.text_placeholder")}` : kind;
const controlSample = (key: string) => domain.value === "cover" ? withCoverTilt(key, tiltSelected.value) : key;
function previewBackground(key: string | null) {
  if (key && props.tile.id && key !== (props.tile.options?.background || "auto")) insp.optionPreview = { tileId: props.tile.id, key: "background", value: key };
  else if (insp.optionPreview?.key === "background") insp.optionPreview = null;
}
const backgroundName = computed(() => inv.inventory.backgrounds?.[props.tile.options?.background || "auto"]?.label || "");
</script>

<template>
  <PluginTileInspector v-if="pluginTile" :tile="tile" />
  <template v-else>
  <InspectorHead :title="tile.name || name" :code="entities.tileIconCp(tile)" :tone="{ color: domainInfo(tile.entity)[2], background: domainInfo(tile.entity)[3] }" :crumbs="crumbs" kind="tile">
    <!-- The title says the name; a click on it, like Rename in the menu, goes to the Name field under it. -->
    <template #title><TitleButton :text="tile.name || name" @rename="insp.renameTile(tile)" /></template>
    <template #actions>
      <UiMenu width="220px">
        <template #trigger><button type="button" class="icon-btn" id="tile-more" :aria-label="t('editor.screen_view.more')"><Icon name="dots-horizontal" /></button></template>
        <UiMenuItem id="tile-rename" icon="pencil-outline" @select="insp.renameTile(tile)">{{ t("editor.naming.rename") }}</UiMenuItem>
        <UiMenuItem v-if="domain !== 'screen'" icon="database-search-outline" @select="inspect">{{ t("editor.common.read_current_data") }}</UiMenuItem>
        <UiMenuItem v-if="domain !== 'screen'" icon="pencil-outline" @select="insp.entityPickerOpen = true">{{ t("editor.broken.change") }}</UiMenuItem>
        <UiMenuSeparator v-if="domain !== 'screen'" />
        <UiMenuItem icon="delete-outline" danger hint="⌫" @select="removeTile(tile)">{{ t("editor.common.remove") }}</UiMenuItem>
      </UiMenu>
    </template>
  </InspectorHead>
  <div class="dr-body">
    <!-- Its entity gone or away for a while, or another one asked for from the menu: the picker comes first. -->
    <TileEntityFix v-if="domain !== 'screen'" :tile="tile" />
    <NameField :tile="tile" :fallback="name" />
    <p v-if="bedside" class="hint">{{ t("editor.tile.keys.hint") }}</p>
    <p v-if="key" class="hint">{{ t("editor.tile.keys.under") }}</p>
    <!-- A key's name under its circle (firmware 0.17.0+): off leaves the circle alone, as a picture can drop its name. -->
    <Section v-if="key && scr.supports(0, 17, 0)" :title="t('editor.tile.sections.look')">
      <SwitchRow class="key-name-choice" :label="t('editor.tile.keys.name_shown')" :description="t('editor.tile.keys.name_shown_hint')"
        :model-value="tile.options?.overlay !== 'none'" @update:model-value="(on) => setTileOption(tile, 'overlay', on ? 'name' : 'none')" />
    </Section>

    <!-- What the card shows first, then where it stands, what a finger does to it, and last its icon and colour. -->
    <template v-if="!ui.phone || more">
    <Section v-if="lookShown || (!bedside && !key)" :title="t('editor.tile.sections.look')">
      <p v-if="energyTile" class="hint">{{ t(scr.supports(0, 47, 0) ? "editor.tile.energy.hint" : "editor.tile.energy.needs_firmware") }}</p>
      <PropRow v-if="energyTile" :label="t('editor.tile.energy.flow.label')" icon="flash" :hint="t('editor.tile.energy.flow.hint')">
        <ChoiceField :choices="flowChoices" :value="current('flow', rules.energyFlow[0])" :tile="tile" preview-key="flow" :aria-label="t('editor.tile.energy.flow.label')" @pick="(v) => setTileOption(tile, 'flow', v)" />
      </PropRow>
      <PropRow v-if="lookShown && tile.entity !== 'screen.settings' && !mapTile && !energyTile" :label="t('editor.tile.display.label')" icon="eye-outline" :hint="shownHint && !shownHint.warn ? shownHint.text : undefined">
        <ChoiceField :choices="displays" :value="display" :tile="tile" preview-key="display" :aria-label="t('editor.tile.display.label')" @pick="(v) => setTileOption(tile, 'display', v)" />
        <template v-if="shownHint?.warn" #note><small class="help warn">{{ shownHint.text }}</small></template>
      </PropRow>
      <!-- A bedside clock and its keys have no second line: the clock draws the time, a key its name alone. -->
      <PropRow v-if="!bedside && !key && !mapCard && !energyTile" :label="t('editor.tile.sub.label')" icon="text-short" :hint="t(`editor.tile.sub.hint_${subKind}`)">
        <ChoiceField :choices="subList" :value="subKind" :tile="tile" preview-key="sub" :sample="subSample" :aria-label="t('editor.tile.sub.label')" @pick="pickSubKind" />
        <template v-if="subKind === 'attr' || subKind === 'text'" #note>
          <UiSelect v-if="subKind === 'attr'" class="sub-value" :model-value="subAttribute" :options="subValues.map((value) => [value.key, value.name] as [string, string])"
            :aria-label="t('editor.tile.sub.value_aria')" @update:model-value="(key) => setTileOption(tile, 'sub', `attr:${key}`)" />
          <input v-else class="sub-text" :value="subText" maxlength="60"
            @focus="doc.beginFieldEdit(`sub:${tile.id}`)" @blur="doc.endFieldEdit()"
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
    <FavoriteSection v-if="lookShown && favoriteCard" :tile="tile" />

    <!-- A map (app 0.4.33, the map tile and these choices 0.4.36): whom it follows, how it frames them, how it looks. -->
    <MapSection v-if="lookShown && mapCard" :tile="tile" />

    <!-- A tile's size is set on the tile itself, with its handles (app 0.4.32): the settings keep what it does. -->
    <Section v-if="controlsShown || goesTo" :title="t('editor.tile.sections.controls')">
      <PropRow v-if="goesTo" :label="t('editor.tile.goes_to.label')" icon="arrow-right" :hint="!goesHint.warn ? goesHint.text : undefined">
        <ChoiceField :choices="pages" :value="goesTo" :aria-label="t('editor.tile.goes_to.label')" @pick="(v) => retargetPageTile(tile, Number(v))" />
        <template v-if="goesHint.warn" #note><small class="help warn">{{ goesHint.text }}</small></template>
      </PropRow>
      <PropRow v-if="domain !== 'screen' && !goesTo" :label="t('editor.tile.tap.label')" icon="gesture-tap">
        <ChoiceField :choices="taps" :value="tap" :aria-label="t('editor.tile.tap.label')" @pick="pickTap" />
        <template v-if="tapNote" #note>
          <small v-if="tapNote.warn" class="help warn">{{ tapNote.text }}</small>
          <span v-else class="gesture-note">{{ tapNote.text }}</span>
        </template>
      </PropRow>
      <ActionPicker v-if="domain !== 'screen' && !goesTo && tap === 'action'" :tile="tile" />
      <PropRow v-if="domain === 'lock'" :label="t('editor.tile.guard.label')" icon="check-circle" :hint="t(guard === 'lock_only' ? 'editor.tile.guard.lock_only_hint' : 'editor.tile.guard.confirm_hint')">
        <ChoiceField :choices="guards" :value="guard" :aria-label="t('editor.tile.guard.label')" @pick="(v) => setTileOption(tile, 'guard', v)" />
      </PropRow>
      <PropRow v-if="catalogue && size !== 'single' && !goesTo" :label="t('editor.tile.controls.label')" icon="tune-variant" :hint="!controlNote.warn ? controlNote.text : undefined">
        <ChoiceField :choices="controlList" :value="primaryControl" :tile="tile" preview-key="controls" :sample="controlSample" :aria-label="t('editor.tile.controls.label')" @pick="pickControl" />
        <template v-if="controlNote.warn" #note><small class="help warn">{{ controlNote.text }}</small></template>
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
      <IconPicker v-if="showIcon" :tile="tile" :selected="tile.options?.icon || 'auto'" :automatic="entities.automaticIcon(tile.entity)"
        :auto-label="t(fromHA ? 'editor.tile.icon.auto_ha' : 'editor.tile.icon.auto_default')"
        :note="scr.supports(0, 2, 18) ? '' : t('editor.tile.icon.needs_firmware')"
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
    <template v-if="ui.phone">
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
</template>
