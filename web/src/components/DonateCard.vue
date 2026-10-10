<script setup lang="ts">
// A quiet ask for support on the home overview, never while a screen is being edited: a monthly membership first, a
// one-time coffee next to it. It waits two days after the first visit, comes back a week after "Maybe later", a month
// after either link, and never after "I already donated". Kept in this browser only: nothing goes into the screens' data or leaves the house.
import { ref } from "vue";
import { t } from "../i18n";
import { readStored, writeStored } from "../storage";
import { toast } from "../store";

const KEY = "esp-screens.donate";
const DAY = 86_400_000;
const MONTHLY = "https://buymeacoffee.com/f5j9jnkmhpv/membership";
const ONCE = "https://buymeacoffee.com/f5j9jnkmhpv";

function due() {
  const stored = readStored(KEY);
  if (stored === "donated") return false;
  if (!stored) { writeStored(KEY, String(Date.now() + 2 * DAY)); return false; }
  return Date.now() >= Number(stored);
}
const open = ref(due());

function hide(days: number | "donated") {
  open.value = false;
  writeStored(KEY, days === "donated" ? days : String(Date.now() + days * DAY));
}
function donated() {
  hide("donated");
  toast(t("editor.donate.thanks"));
}
</script>

<template>
  <aside v-if="open" class="donate" :aria-label="t('editor.donate.title')">
    <button type="button" class="donate-close" :aria-label="t('editor.donate.later')" @click="hide(7)">×</button>
    <div class="donate-head">
      <span class="donate-cup" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="20" height="20"><path fill="currentColor"
          d="M2,21H20V19H2M20,8H18V5H20M20,3H4V13A4,4 0 0,0 8,17H14A4,4 0 0,0 18,13V10H20A2,2 0 0,0 22,8V5C22,3.89 21.1,3 20,3Z" /></svg>
      </span>
      <strong>{{ t("editor.donate.title") }}</strong>
    </div>
    <p>{{ t("editor.donate.body") }}</p>
    <div class="donate-actions">
      <a class="donate-buy" :href="MONTHLY" target="_blank" rel="noopener" @click="hide(30)">{{ t("editor.donate.monthly") }}</a>
      <a class="donate-link" :href="ONCE" target="_blank" rel="noopener" @click="hide(30)">{{ t("editor.donate.once") }}</a>
    </div>
    <div class="donate-actions donate-quiet">
      <button type="button" class="donate-link" @click="hide(7)">{{ t("editor.donate.later") }}</button>
      <button type="button" class="donate-link" @click="donated">{{ t("editor.donate.donated") }}</button>
    </div>
  </aside>
</template>

<style scoped>
.donate { position: fixed; right: 24px; bottom: 24px; z-index: 40; width: 340px; padding: 20px; background: var(--surface);
  border: 1px solid var(--line); border-radius: 14px; box-shadow: var(--shadow); color: var(--ink); }
.donate-close { position: absolute; top: 8px; right: 10px; font-size: 20px; line-height: 1; padding: 4px 6px; color: var(--muted); }
.donate-close:hover { color: var(--ink); }
.donate-head { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.donate-head strong { font-size: 15px; }
.donate-cup { flex: none; width: 38px; height: 38px; border-radius: 10px; background: #ffc107; color: #16181d; display: grid; place-items: center; }
.donate p { margin: 0 0 16px; font-size: 13.5px; line-height: 1.5; color: var(--ink-2); }
.donate-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; }
.donate-buy { background: var(--ink); color: var(--surface); padding: 9px 14px; border-radius: 8px; font-weight: 600; font-size: 13.5px; text-decoration: none; }
.donate-buy:hover { opacity: 0.9; }
.donate-link { color: var(--accent); font-size: 13px; padding: 0; }
.donate-link:hover { text-decoration: underline; }
.donate-quiet { margin-top: 12px; }
.donate-quiet .donate-link { color: var(--muted); }
@media (max-width: 640px) {
  .donate { left: 12px; right: 12px; bottom: 12px; width: auto; }
}
</style>
