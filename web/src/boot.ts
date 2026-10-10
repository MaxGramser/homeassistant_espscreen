// What the editor starts once it is on the page (main.ts): everything the session starts (stores/session.ts start), the
// page around the screens, the screens' language, a screen setting still waiting when the page closes, the plugins'
// reactions, the click a finished drag swallows, the live stream, polls, clocks and page events, and the firmware job
// while something builds. Importing a module starts nothing, so a test imports any of them and starts only what it
// tests, and a store starts only through its start. Started once; the returned function stops all of it again.
import { useSessionStore } from "./stores/session";

export function boot() {
  return useSessionStore().start();
}
