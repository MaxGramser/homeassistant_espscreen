<script setup lang="ts">
// A favourite's settings (app 0.4.42): what it plays, chosen in the player's library, on which speaker (or where it
// plays), and its own shuffle and repeat as it starts (app 0.4.84), offered where Home Assistant lists the action for the
// player (catalogue/media_player.yaml `favorite`), or wherever that is not known yet; a stored one always shows. "keep"
// stores nothing: the player keeps its own.
import { computed, ref } from "vue";
import { t } from "../../i18n";
import { ofType } from "../../model/catalogue";
import rules from "../../model/page-rules.json";
import { offeredChoices } from "../../model/tile-options";
import type { FavoritePlay, Tile } from "../../types";
import ChoiceField from "../ChoiceField.vue";
import FavoritePicker from "../FavoritePicker.vue";
import PropRow from "../ui/PropRow.vue";
import Section from "../ui/Section.vue";
import UiSelect from "../ui/UiSelect.vue";
import { setTileOption } from "../../editor/tiles";
import { useEntitiesStore } from "../../stores/entities";
import { useInventoryStore } from "../../stores/inventory";

const entities = useEntitiesStore();
const inv = useInventoryStore();
const props = defineProps<{ tile: Tile }>();

const domain = computed(() => props.tile.entity.split(".")[0]);
const current = (key: string, fallback: unknown) => props.tile.options?.[key] ?? fallback;
const controlled = computed(() => Boolean(inv.inventory.controls?.[domain.value]));
const play = computed(() => props.tile.options?.play as FavoritePlay | undefined);
const choosing = ref(false);
const speakers = computed(() => {
  // The rows of the player's speaker menu (app speakers.py), or its sources from an app before them.
  const live = entities.liveOf(props.tile.entity)?.a;
  const listed = ((live?.speakers ?? live?.source_list) as string[] | undefined) ?? [];
  const chosen = props.tile.options?.speaker as string | undefined;
  const names = chosen && !listed.includes(chosen) ? [...listed, chosen] : listed;
  return [["", t("editor.tile.favorite.speaker_now")] as [string, string], ...names.map((name) => [name, name] as [string, string])];
});
function pick(next: FavoritePlay) { setTileOption(props.tile, "play", next); choosing.value = false; }
function pickSpeaker(name: string) { setTileOption(props.tile, "speaker", name || undefined); }
const caps = computed(() => entities.capabilities[props.tile.entity]);
const sets = (key: "shuffle" | "repeat") => props.tile.options?.[key] !== undefined ||
  (caps.value ? (caps.value.favorite ?? []).includes(key) : (ofType(domain.value)?.favorite ?? []).some((item) => item.key === key));
const keepOr = (value: string) => value === "keep" ? undefined : value;
const choicesOf = (key: "shuffle" | "repeat", values: string[]) => offeredChoices(props.tile, key, (["keep", ...values])
  .map((value) => [value, t(`editor.tile.favorite.${key}_${value}`)] as [string, string]), current(key, "keep"), controlled.value, keepOr);
const shuffles = computed(() => choicesOf("shuffle", rules.favoriteShuffles as string[]));
const repeats = computed(() => choicesOf("repeat", rules.favoriteRepeats as string[]));
</script>

<template>
  <Section :title="t('editor.tile.display.favorite')">
    <PropRow :label="t('editor.tile.favorite.plays')" icon="playlist-music">
      <div class="favorite-chosen">
        <span v-if="play" class="favorite-title">{{ play.title }}</span>
        <span v-else class="help warn">{{ t('editor.tile.favorite.none') }}</span>
        <button type="button" class="btn quiet mini" @click="choosing = !choosing">{{ t(choosing ? 'editor.tile.favorite.done' : 'editor.tile.favorite.choose') }}</button>
      </div>
      <template v-if="choosing || !play" #note>
        <FavoritePicker :entity="tile.entity" :chosen="play" @pick="pick" />
      </template>
    </PropRow>
    <PropRow :label="t('editor.tile.favorite.speaker')" icon="speaker" :hint="t('editor.tile.favorite.speaker_hint')">
      <UiSelect :model-value="(tile.options?.speaker as string) || ''" :options="speakers" :aria-label="t('editor.tile.favorite.speaker')" @update:model-value="pickSpeaker" />
    </PropRow>
    <PropRow v-if="sets('shuffle')" :label="t('editor.tile.favorite.shuffle')" icon="shuffle-variant" :hint="t('editor.tile.favorite.shuffle_hint')">
      <ChoiceField :choices="shuffles" :value="current('shuffle', 'keep')" :aria-label="t('editor.tile.favorite.shuffle')" @pick="(v) => setTileOption(tile, 'shuffle', keepOr(v))" />
    </PropRow>
    <PropRow v-if="sets('repeat')" :label="t('editor.tile.favorite.repeat')" icon="repeat" :hint="t('editor.tile.favorite.repeat_hint')">
      <ChoiceField :choices="repeats" :value="current('repeat', 'keep')" :aria-label="t('editor.tile.favorite.repeat')" @pick="(v) => setTileOption(tile, 'repeat', keepOr(v))" />
    </PropRow>
  </Section>
</template>
