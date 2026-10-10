<script setup lang="ts">
// Whether the editor reaches ESP Screen Manager (app 0.4.x): while the add-on cannot be reached (restarting, updating,
// Home Assistant's ingress away), a calm line over the page says so and that nothing is lost; when it is back, the line
// says "Connection restored" for a moment and goes. The inventory store says whether the add-on answers; its live stream
// opens again by itself (stores/inventory.ts).
import { useTimeoutFn } from "@vueuse/core";
import { ref, watch } from "vue";
import { t } from "../i18n";
import { useInventoryStore } from "../stores/inventory";
import Icon from "./ui/Icon.vue";

const inv = useInventoryStore();
const restored = ref(false);
const quiet = useTimeoutFn(() => { restored.value = false; }, 3000, { immediate: false });
watch(() => inv.reachable, (now, before) => {
  restored.value = now && before === false;
  if (restored.value) quiet.start(); else quiet.stop();
});
</script>

<template>
  <Transition name="conn-bar" mode="out-in">
    <div v-if="!inv.reachable" id="connection-bar" key="lost" class="conn-bar" role="status">
      <Icon name="wifi-off" /><span><b>{{ t("editor.connection.lost") }}</b> {{ t("editor.connection.lost_hint") }}</span>
    </div>
    <div v-else-if="restored" id="connection-bar" key="back" class="conn-bar back" role="status">
      <Icon name="check-circle" /><span>{{ t("editor.connection.restored") }}</span>
    </div>
  </Transition>
</template>

<style scoped>
.conn-bar { display: flex; align-items: center; justify-content: center; gap: 8px; min-height: 34px; padding: 7px 16px; flex: none;
  background: var(--surface-2); border-bottom: 1px solid var(--line); color: var(--ink-2); font-size: 12.5px; line-height: 1.4; text-align: center; }
.conn-bar .ui-icon { flex: none; font-size: 16px; color: var(--warn); }
.conn-bar b { font-weight: 600; color: var(--ink); }
.conn-bar.back { background: var(--good-soft); color: var(--ink); }
.conn-bar.back .ui-icon { color: var(--good); }
.conn-bar-enter-active, .conn-bar-leave-active { transition: opacity 0.2s ease, margin-top 0.2s ease; }
.conn-bar-enter-from, .conn-bar-leave-to { opacity: 0; margin-top: -34px; }
@media (prefers-reduced-motion: reduce) { .conn-bar-enter-active, .conn-bar-leave-active { transition: none; } }
</style>
