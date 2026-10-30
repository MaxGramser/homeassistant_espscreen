<script setup lang="ts">
// Tessera looks for funding (2026-10-30): on the home overview, before the support card, with a button that mails Max.
// "Not now" or the mail puts it away for a week, kept in this browser only like the support card.
import { computed } from "vue";
import { t } from "../i18n";
import { usePreference } from "../composables/usePreference";

const DAY = 86_400_000;
const MAIL = "mailto:maxgramser@gmail.com?subject=" + encodeURIComponent("Funding for Tessera");

const until = usePreference<number>("esp-screens.funding", 0, { serializer: { read: Number, write: String } });
const open = computed(() => Date.now() >= until.value);
function hide() { until.value = Date.now() + 7 * DAY; }
defineExpose({ open });
</script>

<template>
  <aside v-if="open" class="funding" :aria-label="t('editor.funding.title')">
    <button type="button" class="funding-close" :aria-label="t('editor.funding.later')" @click="hide">×</button>
    <strong class="funding-title">{{ t("editor.funding.title") }}</strong>
    <p>{{ t("editor.funding.body") }}</p>
    <div class="funding-actions">
      <a class="funding-mail" :href="MAIL" @click="hide">{{ t("editor.funding.mail") }}</a>
      <button type="button" class="funding-later" @click="hide">{{ t("editor.funding.later") }}</button>
    </div>
  </aside>
</template>

<style scoped>
.funding { position: fixed; right: 24px; bottom: 24px; z-index: 40; width: 360px; padding: 20px; background: var(--surface);
  border: 1px solid var(--line); border-left: 4px solid #ffc107; border-radius: 14px; box-shadow: var(--shadow); color: var(--ink); }
.funding-close { position: absolute; top: 8px; right: 10px; font-size: 20px; line-height: 1; padding: 4px 6px; color: var(--muted); }
.funding-close:hover { color: var(--ink); }
.funding-title { display: block; margin: 0 24px 10px 0; font-size: 19px; font-weight: 800; letter-spacing: 0.03em; text-transform: uppercase; }
.funding p { margin: 0 0 16px; font-size: 13.5px; line-height: 1.5; color: var(--ink-2); }
.funding-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; }
.funding-mail { background: #ffc107; color: #16181d; padding: 9px 16px; border-radius: 8px; font-weight: 700; font-size: 13.5px; text-decoration: none; }
.funding-mail:hover { opacity: 0.9; }
.funding-later { color: var(--muted); font-size: 13px; padding: 0; }
.funding-later:hover { text-decoration: underline; }
@media (max-width: 640px) {
  .funding { left: 12px; right: 12px; bottom: 12px; width: auto; }
}
</style>
