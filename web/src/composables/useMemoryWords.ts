// The words for how much of the screen's memory for tiles the draft takes (model/memory.ts, docs/TILE_MEMORY.md): the
// share in a few characters and the lines that explain it. The meter beside a count (MemoryMeter.vue) shows the share
// and keeps the lines in its title; the pill in a screen's head (ScreenStatus.vue) writes them out.
import { computed } from "vue";
import { t } from "../i18n";
import { kilobytes, noRoom } from "../model/memory";
import { useDocumentStore } from "../stores/document";
import { useScreenStore } from "../stores/screen";

export function useMemoryWords() {
  const scr = useScreenStore(), doc = useDocumentStore();
  const percent = computed(() => (doc.memory ? Math.min(999, Math.round(doc.memory.share * 100)) : 0));
  // A screen with no room to speak of says so in words rather than a share past ten times the room.
  const none = computed(() => !!doc.memory && noRoom(doc.memory));
  const text = computed(() => (scr.memoryMeasuring ? t("editor.memory.measuring") : none.value ? t("editor.memory.none") : t("editor.memory.share", { n: percent.value })));
  const lines = computed<string[]>(() => {
    const use = doc.memory, said = scr.screenMemory;
    if (!said) return [];
    if (scr.memoryMeasuring) return [t("editor.memory.measuring_title")];
    if (!use) return [];
    const out = [none.value ? t("editor.memory.none_title") : t("editor.memory.title", { need: kilobytes(use.need, true), room: kilobytes(use.room) })];
    if (use.level === "over" && !none.value) out.push(t("editor.memory.over"));
    if (said.short) out.push(t("editor.memory.short"));
    if (said.live === false) out.push(t("editor.memory.last_known"));
    return out;
  });
  return { percent, none, text, lines };
}
