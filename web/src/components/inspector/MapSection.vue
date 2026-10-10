<script setup lang="ts">
// A map card's settings (app 0.4.33, docs/MAP.md; the map tile and these choices 0.4.36): whom it follows, who rides
// along beside the tile's own person, how it frames them and how far a fixed view reaches, how it looks, and its name on
// the picture. The choices are the catalogue's (catalogue/person.yaml), the first of each the default.
import { computed } from "vue";
import { t } from "../../i18n";
import { ofType } from "../../model/catalogue";
import rules from "../../model/page-rules.json";
import { offeredChoices } from "../../model/tile-options";
import type { Tile } from "../../types";
import ChoiceField from "../ChoiceField.vue";
import Icon from "../ui/Icon.vue";
import PropRow from "../ui/PropRow.vue";
import Section from "../ui/Section.vue";
import UiSelect from "../ui/UiSelect.vue";
import { setTileOption } from "../../editor/tiles";
import { useEntitiesStore } from "../../stores/entities";
import { useInventoryStore } from "../../stores/inventory";
import { useScreenStore } from "../../stores/screen";

const entities = useEntitiesStore();
const inv = useInventoryStore();
const scr = useScreenStore();
const props = defineProps<{ tile: Tile }>();

const MAP = ofType("person")?.map;
const current = (key: string, fallback: unknown) => props.tile.options?.[key] ?? fallback;
const controlled = computed(() => Boolean(inv.inventory.controls?.[props.tile.entity.split(".")[0]]));
const mapWith = computed(() => (props.tile.options?.map as string[] | undefined) ?? []);
// The map tile of the screen's own cards (app 0.4.36): no person of its own, following everyone or whom it lists.
const mapTile = computed(() => props.tile.entity === "screen.map");
const follow = computed(() => current("follow", MAP?.follow[0]) as string);
const listed = computed(() => !mapTile.value || follow.value === "chosen");
const full = computed(() => mapWith.value.length >= (MAP?.max ?? 8) - (mapTile.value ? 0 : 1));
const offered = computed(() => [...(inv.inventory.entities || []), ...(inv.inventory.trackers || [])]
  .filter((item) => (MAP?.with ?? []).includes(item.id.split(".")[0]) && item.id !== props.tile.entity && !mapWith.value.includes(item.id))
  .map((item) => [item.id, item.name || item.id] as [string, string]));
const framing = computed(() => current("framing", MAP?.framing[0]) as string);
type MapChoice = "framing" | "distance" | "follow" | "markers" | "names" | "zones" | "streets" | "look";
const choices = (key: MapChoice) => offeredChoices(props.tile, key, (MAP?.[key] ?? [])
  // Around this person is a person's map: the map tile has no person of its own.
  .filter((value) => !(key === "framing" && value === "person" && mapTile.value))
  .map((value) => [value, t(`editor.tile.map.${key}.${value}`)] as [string, string]), current(key, MAP?.[key][0]), controlled.value);
const overlay = computed(() => offeredChoices(props.tile, "overlay", rules.picture.overlay.map((value) => [value, t(`editor.tile.picture.overlay.${value}`)] as [string, string]),
  current("overlay", rules.picture.overlay[0]), controlled.value));
function add(id: string) { if (id) setTileOption(props.tile, "map", [...mapWith.value, id]); }
function remove(id: string) { setTileOption(props.tile, "map", mapWith.value.filter((item) => item !== id)); }
</script>

<template>
  <Section :title="t('editor.tile.display.map')">
    <p v-if="mapTile" class="hint">{{ t(scr.supports(0, 21, 0) ? "editor.tile.display.map_hint" : "editor.tile.display.map_tile_needs_firmware") }}</p>
    <PropRow v-if="mapTile" :label="t('editor.tile.map.follow.label')" icon="account-eye-outline"
      :hint="follow === 'everyone' ? t('editor.tile.map.follow.everyone_hint') : undefined">
      <ChoiceField :choices="choices('follow')" :value="follow" :tile="tile" preview-key="follow" :aria-label="t('editor.tile.map.follow.label')" @pick="(v) => setTileOption(tile, 'follow', v)" />
    </PropRow>
    <PropRow v-if="listed" :label="t(mapTile ? 'editor.tile.map.chosen.label' : 'editor.tile.map.with.label')" icon="account-multiple-outline"
      :hint="t(mapTile ? 'editor.tile.map.chosen.hint' : 'editor.tile.map.with.hint')">
      <div class="map-with">
        <span v-for="item in mapWith" :key="item" class="map-person">
          {{ entities.entityName(item) }}
          <button type="button" class="map-remove" :aria-label="t('editor.tile.map.with.remove', { name: entities.entityName(item) })" @click="remove(item)"><Icon name="close" /></button>
        </span>
        <UiSelect v-if="!full && offered.length" class="map-add" :model-value="''" :options="offered"
          :placeholder="t('editor.tile.map.with.add')" :aria-label="t('editor.tile.map.with.add')" @update:model-value="add" />
      </div>
    </PropRow>
    <PropRow :label="t('editor.tile.map.framing.label')" icon="crosshairs-gps">
      <ChoiceField :choices="choices('framing')" :value="framing" :tile="tile" preview-key="framing" :aria-label="t('editor.tile.map.framing.label')" @pick="(v) => setTileOption(tile, 'framing', v)" />
    </PropRow>
    <PropRow v-if="framing !== 'everyone'" :label="t('editor.tile.map.distance.label')" icon="magnify-plus-outline">
      <ChoiceField :choices="choices('distance')" :value="current('distance', MAP?.distance[0])" :tile="tile" preview-key="distance" :aria-label="t('editor.tile.map.distance.label')" @pick="(v) => setTileOption(tile, 'distance', v)" />
    </PropRow>
    <PropRow :label="t('editor.tile.map.markers.label')" icon="account-circle-outline">
      <ChoiceField :choices="choices('markers')" :value="current('markers', MAP?.markers[0])" :tile="tile" preview-key="markers" :aria-label="t('editor.tile.map.markers.label')" @pick="(v) => setTileOption(tile, 'markers', v)" />
    </PropRow>
    <PropRow :label="t('editor.tile.map.names.label')" icon="label-outline">
      <ChoiceField :choices="choices('names')" :value="current('names', MAP?.names[0])" :tile="tile" preview-key="names" :aria-label="t('editor.tile.map.names.label')" @pick="(v) => setTileOption(tile, 'names', v)" />
    </PropRow>
    <PropRow :label="t('editor.tile.map.zones.label')" icon="map-marker-radius-outline">
      <ChoiceField :choices="choices('zones')" :value="current('zones', MAP?.zones[0])" :tile="tile" preview-key="zones" :aria-label="t('editor.tile.map.zones.label')" @pick="(v) => setTileOption(tile, 'zones', v)" />
    </PropRow>
    <PropRow :label="t('editor.tile.map.streets.label')" icon="road-variant">
      <ChoiceField :choices="choices('streets')" :value="current('streets', MAP?.streets[0])" :tile="tile" preview-key="streets" :aria-label="t('editor.tile.map.streets.label')" @pick="(v) => setTileOption(tile, 'streets', v)" />
    </PropRow>
    <PropRow :label="t('editor.tile.map.look.label')" icon="theme-light-dark">
      <ChoiceField :choices="choices('look')" :value="current('look', MAP?.look[0])" :tile="tile" preview-key="look" :aria-label="t('editor.tile.map.look.label')" @pick="(v) => setTileOption(tile, 'look', v)" />
    </PropRow>
    <PropRow :label="t('editor.tile.picture.overlay.label')" icon="format-title">
      <ChoiceField :choices="overlay" :value="current('overlay', 'name')" :tile="tile" preview-key="overlay" :aria-label="t('editor.tile.picture.overlay.label')" @pick="(v) => setTileOption(tile, 'overlay', v)" />
    </PropRow>
  </Section>
</template>
