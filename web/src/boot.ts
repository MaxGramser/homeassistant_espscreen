// What the editor starts once it is on the page (main.ts): the plugins' reactions, the click a finished drag swallows,
// and the store's live stream, polls, clocks and page events. Importing a module starts nothing, so a test imports any
// of them and starts only what it tests. Started once; the returned function stops all of it again.
import { startDrag } from "./drag";
import { startPlugins } from "./plugin-state";
import { startStore } from "./store";

let running: (() => void) | null = null;
export function boot() {
  if (running) return running;
  const stops = [startPlugins(), startDrag(), startStore()];
  running = () => { running = null; for (const stop of stops.reverse()) stop(); };
  return running;
}
