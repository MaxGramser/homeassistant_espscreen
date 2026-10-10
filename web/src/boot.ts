// What the editor starts once it is on the page (main.ts): the page around the screens (the address, the width of a
// phone), the screens' language, the plugins' reactions, the click a finished drag swallows, the store's live stream,
// polls, clocks and page events, and the firmware job while something builds (its log). Importing a module starts
// nothing, so a test imports any of them and starts only what it tests, and a store starts only through its start, here.
// Started once; the returned function stops all of it again.
import { followBuilds } from "./composables/useFirmwareJob";
import { startDrag } from "./drag";
import { startPlugins } from "./plugin-state";
import { startStore } from "./store";
import { useRegionStore } from "./stores/region";
import { useUiStore } from "./stores/ui";

let running: (() => void) | null = null;
export function boot() {
  if (running) return running;
  const stops = [useUiStore().start(), useRegionStore().start(), startPlugins(), startDrag(), startStore(), followBuilds()];
  running = () => { running = null; for (const stop of stops.reverse()) stop(); };
  return running;
}
