// The icons a screen takes on top of the fixed set (docs/ICONS.md): what the add-on says of the open screen
// (screen_icons.py), the table of every icon there is, asked the first time the page opens, and the changes. A change
// to the list applies at once; it reaches the glass with the build the page asks for.
import { computed, ref, watch } from "vue";
import { defineStore } from "pinia";
import { getJson, send } from "../api";
import { knowInk } from "../model/card-layout";
import { useScreenStore } from "./screen";
import { useUiStore } from "./ui";

// [codepoint, xMin, yMin, xMax, yMax], as tile_icons.mdi() keeps them.
export type IconRow = [string, number, number, number, number];
export type ScreenIconsView = {
  room: number; most: number; fixed: number; chosen: string[]; built: string[]; waiting: string[]; leaving: string[];
  building: boolean; own_yaml: boolean; icons: Record<string, IconRow>; suggested: string[];
};
export type EverywhereResult = { queued: string[]; off: string[]; own_yaml: string[]; view: ScreenIconsView };
export type OwnYaml = { own_yaml: true; file: string; content: string; line: string };

const labelOf = (name: string) => name.replaceAll("-", " ");

export const useScreenIconsStore = defineStore("screenIcons", () => {
  const scr = useScreenStore();
  const ui = useUiStore();
  const view = ref<ScreenIconsView | null>(null);
  const table = ref<Record<string, IconRow> | null>(null);
  const screenId = computed(() => ui.iconsScreen || scr.selected || "");
  const path = (id: string) => `screens/${encodeURIComponent(id)}/icons`;

  function took(next: ScreenIconsView) {
    view.value = next;
    for (const row of Object.values(next.icons)) knowInk(row[0], row.slice(1) as number[]);
  }
  async function load(id = screenId.value) {
    if (!id) { view.value = null; return; }
    try {
      const next = await getJson<ScreenIconsView>(path(id));
      if (id === screenId.value) took(next);
    } catch { if (id === screenId.value) view.value = null; }
  }
  watch(screenId, () => { view.value = null; void load(); }, { immediate: true });

  /** Every icon there is, the first time the page asks for it. */
  async function loadTable() {
    if (!table.value) table.value = (await getJson<{ icons: Record<string, IconRow> }>("icons")).icons;
  }

  // The icons of this screen as the pickers list them: those on the glass and those on their way.
  const own = computed(() => view.value
    ? [...new Set([...view.value.built, ...view.value.chosen])].filter((name) => view.value!.icons[name])
        .map((name) => ({ name, cp: view.value!.icons[name][0], label: labelOf(name) }))
    : []);

  async function setList(names: string[]) {
    try { took(await send<ScreenIconsView>(path(screenId.value), "PUT", { icons: names })); }
    catch (error: any) { ui.toast(error.message); }
  }
  const add = (names: string[]) => setList([...(view.value?.chosen || []), ...names]);
  const remove = (name: string) => setList((view.value?.chosen || []).filter((other) => other !== name));

  /** The file for a screen built from its own YAML, null for a build that went into the line. */
  async function build(): Promise<OwnYaml | null> {
    try {
      const outcome = await send<(OwnYaml | { queued: number }) & { view: ScreenIconsView }>(`${path(screenId.value)}/build`, "POST");
      took(outcome.view);
      return "own_yaml" in outcome ? outcome : null;
    } catch (error: any) { ui.toast(error.message); return null; }
  }
  async function everywhere(): Promise<EverywhereResult | null> {
    try {
      const outcome = await send<EverywhereResult>(`${path(screenId.value)}/everywhere`, "POST");
      took(outcome.view);
      return outcome;
    } catch (error: any) { ui.toast(error.message); return null; }
  }

  return { view, table, screenId, own, load, loadTable, add, remove, build, everywhere };
});
