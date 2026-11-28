<script setup lang="ts">
// The automations of Tessera of one kind (useAutomations): each with whether it is on, a link to it in Home Assistant, and
// Remove for one this app made. Empty, it says how to make the first.
import { onMounted } from "vue";
import { useConfirm } from "../../composables/useConfirm";
import { automationLink, type ListedAutomation } from "../../composables/useAutomations";
import { t } from "../../i18n";

const props = defineProps<{ listed: ListedAutomation[]; empty: string; refresh: () => Promise<void>; remove: (id: string) => Promise<void> }>();
const { confirm } = useConfirm();
onMounted(props.refresh);
async function drop(item: ListedAutomation) {
  if (!item.id || !(await confirm(t("editor.events.install.remove_confirm", { name: item.name }), { confirm: t("editor.events.install.remove"), danger: true }))) return;
  await props.remove(item.id);
}
</script>

<template>
  <div class="automation-list">
    <p v-if="!listed.length" class="hint">{{ empty }}</p>
    <div v-for="item in listed" :key="item.entity" class="automation-row" :data-id="item.id">
      <span class="dot" :class="{ off: !item.on }" :title="item.on ? t('editor.events.install.on') : t('editor.events.install.off')" />
      <span class="automation-name">{{ item.name }}</span>
      <a v-if="item.id" class="btn quiet mini" :href="automationLink(item.id)" target="_top">{{ t("editor.events.install.open") }}</a>
      <button v-if="item.kind" type="button" class="btn quiet mini" @click="drop(item)">{{ t("editor.events.install.remove") }}</button>
    </div>
  </div>
</template>

<style scoped>
.automation-list { display: grid; gap: 6px; }
.automation-row { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border: 1px solid var(--line); border-radius: 10px; }
.automation-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--good, var(--accent)); flex: none; }
.dot.off { background: var(--muted); }
</style>
