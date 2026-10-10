<script setup lang="ts">
// A tile's name (app 0.4.x), the first thing its drawer offers: a field under the word Name, with the name the tile has
// without one of its own (Home Assistant's, a plugin's, a built-in card's) in grey, and a key back to that name once
// another is typed. People looked for it in vain when it was only the drawer's title. It is the one place the name is
// changed; the drawer's title, the tile's menu, Rename on the phone and a double click on the name on the mockup all
// bring the focus here (stores/inspector.ts rename). Typing is one step of undo (app 0.4.2).
import { ref, watch } from "vue";
import { t } from "../../i18n";
import { useTextDraft } from "../../composables/useTextDraft";
import { setTileName } from "../../editor/tiles";
import { useDocumentStore } from "../../stores/document";
import { useInspectorStore } from "../../stores/inspector";
import type { Tile } from "../../types";
import Icon from "../ui/Icon.vue";

const props = defineProps<{ tile: Tile; fallback: string }>();
const doc = useDocumentStore();
const insp = useInspectorStore();
const field = ref<HTMLInputElement | null>(null);
const draft = useTextDraft(() => props.tile.name, (value) => setTileName(props.tile, value));
// Asked to rename this tile: the field takes the focus with its text selected, ready to be typed over.
// Asked before the drawer was on the page, it waits for the field to be there.
watch(() => [insp.naming, field.value] as const, ([asked, input]) => {
  if (!asked || asked.kind !== "tile" || asked.id !== props.tile.id || !input) return;
  insp.naming = null;
  input.focus();
  input.select();
}, { immediate: true, flush: "post" });
function useFallback() {
  setTileName(props.tile, "");
  draft.blur();
  field.value?.focus();
}
</script>

<template>
  <section class="insp-sec name-sec">
    <div class="insp-sec-head"><h3><label for="tile-name">{{ t("editor.tile.name") }}</label></h3></div>
    <div class="insp-sec-body">
      <div class="name-input">
        <input id="tile-name" ref="field" :value="draft.value.value" :placeholder="fallback" maxlength="60" autocomplete="off" spellcheck="false"
          @focus="doc.beginFieldEdit(`tile:${tile.id}`); draft.focus()" @blur="doc.endFieldEdit(); draft.blur()"
          @keydown.enter="($event.target as HTMLInputElement).blur()" @input="draft.input(($event.target as HTMLInputElement).value)" />
        <button v-if="tile.name" type="button" id="tile-name-reset" class="icon-btn name-reset" :aria-label="t('editor.naming.reset', { name: fallback })"
          :title="t('editor.naming.reset', { name: fallback })" @click="useFallback"><Icon name="undo" /></button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.name-input { position: relative; }
.name-input input { font-size: 13.5px; height: 34px; }
.name-input:has(.name-reset) input { padding-right: 36px; }
.name-reset { position: absolute; top: 3px; right: 3px; width: 28px; height: 28px; border-radius: 6px; color: var(--muted); }
.name-reset:hover { color: var(--ink); background: var(--surface-2); }
</style>
