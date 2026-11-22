<script setup lang="ts">
// Calls, a part of Events (EventsView, docs/SOUNDS.md): what rings on a screen when another screen calls it, chosen as
// every kind of sound is (SoundPicker): one for every screen, a screen's own, or one cut from a file of one's own. A
// call's ring holds its own pause and plays back to back until someone answers.
import { t } from "../i18n";
import { glyph } from "../model/topbar";
import SoundPicker from "./sounds/SoundPicker.vue";

const RING = glyph("F11AB");
</script>

<template>
  <div class="calls" id="calls-part">
    <section class="card event-create" id="calls-hero">
      <div class="event-create-text">
        <h2>{{ t("editor.calls.hero_title") }}</h2>
        <p>{{ t("editor.calls.hero_text") }}</p>
      </div>
      <span class="mdi calls-mark" aria-hidden="true">{{ RING }}</span>
    </section>
    <SoundPicker kind="call" />
  </div>
</template>

<style scoped>
.calls { display: grid; gap: 14px; }
.calls h2 { font-size: 15px; margin: 0 0 10px; }
.calls-mark { display: grid; place-items: center; width: 96px; height: 96px; border-radius: 50%; background: var(--surface-2); font-size: 48px; color: var(--accent); }
</style>
