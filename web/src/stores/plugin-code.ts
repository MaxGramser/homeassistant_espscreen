// The plugins' own code for the firmware preview (docs/EMULATOR_ARCHITECTURE.md, "Plugins"): for each screen, the
// modules of the plugins it runs that the add-on has for this preview (api/plugins/modules), fetched once and shared by
// every preview of that screen on the page. A plugin without a module is no error: the preview draws its tile as a
// screen without that plugin does, and the page's own mockup keeps its placeholder.
import { defineStore } from "pinia";
import { shallowReactive } from "vue";
import { api, getJson } from "../api";
import { nodeOf, pluginOfTile } from "../model/plugins";
import type { Screen } from "../types";
import type { PluginCode } from "../wasm/load";
import renderer from "../wasm/renderer.json";
import { usePluginsStore } from "./plugins";

// The number a module must carry to be loaded into this editor's preview (web/wasm/toolchain.py plugin_abi).
export const PREVIEW_NUMBER: string = (renderer as { plugin_abi?: string }).plugin_abi || "";

export const usePluginCodeStore = defineStore("plugin-code", () => {
  const plugins = usePluginsStore();
  const kept = new Map<string, Promise<PluginCode[]>>();
  const bytes = new Map<string, Promise<Uint8Array | null>>();
  // Per screen, the plugins whose code the preview has, each with its version: known once the add-on has answered.
  const coded = shallowReactive(new Map<string, Map<string, string>>());

  // What the screen runs, as one word: another version of a plugin is other code. The add-on lists what is installed
  // under the key every part of the editor reads it by (model/plugins.ts nodeOf), never under a name of this file's own.
  const runs = (screen: Screen) => (plugins.installed[nodeOf(screen)] || [])
    .filter((item) => item.state !== "failed").map((item) => `${item.id}@${item.version}`).sort().join(",");
  // A preview screen runs no plugin, and nothing is asked while plugins are off or this editor's preview takes none.
  const takes = (screen: Screen | undefined | null): screen is Screen =>
    Boolean(screen && !screen.virtual && plugins.pluginsEnabled && PREVIEW_NUMBER);

  /** What a screen's preview is loaded with, as one word: "" for a screen that takes no plugin's code, and until the
   * add-on's plugins are in. Whoever keeps a preview running follows it (GlassFaces.vue), so a plugin that was added
   * or updated, or that is only now known, gives that preview its code. */
  const runsOn = (screen: Screen | undefined | null) => (takes(screen) ? runs(screen) : "");

  async function read(screen: Screen): Promise<PluginCode[]> {
    const listed = await getJson<{ id: string; version: string; url: string }[]>(
      `plugins/modules?abi=${PREVIEW_NUMBER}&screen=${encodeURIComponent(screen.id)}`);
    const found = await Promise.all(listed.map(async (item) => {
      const url = item.url.replace(/^api\//, "");
      if (!bytes.has(url)) bytes.set(url, api(url).then(async (response) => new Uint8Array(await response.arrayBuffer())).catch(() => null));
      const body = await bytes.get(url)!;
      return body ? { id: item.id, version: item.version, bytes: body } : null;
    }));
    const have = found.filter((item) => item !== null);
    coded.set(screen.id, new Map(have.map((item) => [item.id, item.version])));
    return have.map(({ id, bytes: body }) => ({ id, bytes: body }));
  }

  // The modules for a screen's preview; none for a preview screen (it runs no plugin) or while plugins are off. What a
  // screen runs is known once the add-on's plugins are in, so a preview that starts with the page waits for them here
  // instead of starting without its plugins' code.
  async function codeFor(screen: Screen | undefined | null): Promise<PluginCode[]> {
    if (!takes(screen)) return [];
    await plugins.loadPlugins();
    const what = runs(screen);
    if (!what) return [];
    const key = `${screen.id}|${what}`;
    if (!kept.has(key)) kept.set(key, read(screen).catch(() => { kept.delete(key); return []; }));
    return kept.get(key)!;
  }

  /** Whether the editor's firmware draws this tile's card, and with what: the one place that decides which tiles take
   * a firmware-drawn face (stores/faces.ts). Today a plugin's tile whose plugin has code in this screen's preview; the
   * answer names that code (the plugin, its version, the preview's own number), so a card drawn by another version is
   * another card. Null for a tile the editor draws itself, and until the add-on has said which plugins have code. */
  function drawnBy(screen: Screen | undefined | null, entity: string): string | null {
    const plugin = pluginOfTile(entity), version = plugin && screen ? coded.get(screen.id)?.get(plugin) : undefined;
    return version ? `${plugin}@${version}#${PREVIEW_NUMBER}` : null;
  }

  return { codeFor, drawnBy, runsOn };
});
