// What the editor starts once it is on the page (main.ts): the plugins' reactions, the click a finished drag swallows,
// the store's live stream, polls, clocks and page events, and the firmware job while something builds (its log).
// Importing a module starts nothing, so a test imports any of them and starts only what it tests. Started once; the
// returned function stops all of it again.
import { followBuilds } from "./composables/useFirmwareJob";
import { startDrag } from "./drag";
import { startPlugins } from "./plugin-state";
import { startStore } from "./store";

let running: (() => void) | null = null;
export function boot() {
  if (running) return running;
  const stops = [startPlugins(), startDrag(), startStore(), followBuilds()];
  running = () => { running = null; for (const stop of stops.reverse()) stop(); };
  return running;
}
