<script setup lang="ts">
// A to-do card's settings (docs/TODO.md): the order of its items, whether it shows what is done and due days, and what
// a finger may do on the screen: add an item with the keyboard, take a name it offers, remove what is done. What the
// add-on keeps is todo_feed.validate's; a default is never stored. The orders are Home Assistant's own, as its to-do
// list card names them.
import { computed } from "vue";
import { t } from "../../i18n";
import rules from "../../model/page-rules.json";
import { TODO_DEFAULTS } from "../../model/tile-options";
import type { Tile } from "../../types";
import ChoiceField from "../ChoiceField.vue";
import PropRow from "../ui/PropRow.vue";
import Section from "../ui/Section.vue";
import SwitchRow from "../ui/SwitchRow.vue";
import { setTileOption } from "../../editor/tiles";
import { useScreenStore } from "../../stores/screen";

const scr = useScreenStore();
const props = defineProps<{ tile: Tile }>();

const current = <T,>(key: string) => (props.tile.options?.[key] ?? TODO_DEFAULTS[key]) as T;
const set = (key: string, value: unknown) => setTileOption(props.tile, key, value);
const orders = computed(() => rules.todo.orders.map((value) => [value, t(`editor.tile.todo.order.${value}`)] as [string, string]));
// A board without the module (4 MB of flash) has no to-do tile: one that came with a copied page says so.
const plain = computed(() => scr.currentScreen?.todo_lists === false);
</script>

<template>
  <Section :title="t('editor.tile.todo.title')">
    <p v-if="plain" class="hint warn">{{ t("editor.tile.todo.plain") }}</p>
    <p v-else-if="!scr.supports(0, 61, 0)" class="hint warn">{{ t("editor.tile.todo.needs_firmware") }}</p>
    <PropRow v-if="!plain" :label="t('editor.tile.todo.order.label')" icon="format-list-bulleted" :hint="t('editor.tile.todo.order.hint')">
      <ChoiceField :choices="orders" :value="current<string>('todo_order')" :aria-label="t('editor.tile.todo.order.label')" @pick="(v) => set('todo_order', v)" />
    </PropRow>
    <SwitchRow v-if="!plain" :label="t('editor.tile.todo.completed')" :description="t('editor.tile.todo.completed_hint')"
      :model-value="current<boolean>('todo_completed')" @update:model-value="(on) => set('todo_completed', on)" />
    <SwitchRow v-if="!plain" :label="t('editor.tile.todo.due')" :description="t('editor.tile.todo.due_hint')"
      :model-value="current<boolean>('todo_due')" @update:model-value="(on) => set('todo_due', on)" />
  </Section>

  <Section v-if="!plain" :title="t('editor.tile.todo.screen')">
    <SwitchRow :label="t('editor.tile.todo.add')" :description="t('editor.tile.todo.add_hint')"
      :model-value="current<boolean>('todo_add')" @update:model-value="(on) => set('todo_add', on)" />
    <SwitchRow v-if="current<boolean>('todo_add')" :label="t('editor.tile.todo.suggest')" :description="t('editor.tile.todo.suggest_hint')"
      :model-value="current<boolean>('todo_suggest')" @update:model-value="(on) => set('todo_suggest', on)" />
    <SwitchRow :label="t('editor.tile.todo.clear')" :description="t('editor.tile.todo.clear_hint')"
      :model-value="current<boolean>('todo_clear')" @update:model-value="(on) => set('todo_clear', on)" />
  </Section>
</template>
