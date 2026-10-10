// A composable run the way a component runs it, without a component: inScope runs it in an effect scope whose stop is what
// an unmount does (every tryOnScopeDispose and watch goes), and withSetup in a small app of its own, mounted, for a
// composable that needs onMounted or the app's plugins (the texts, the stores). What a test leaves running is stopped
// after it (stopScopes, from tests/setup.ts), as the components it mounted are unmounted, so a shared composable never
// carries a follower into the next test.
import { getActivePinia } from "pinia";
import { createApp, defineComponent, effectScope, h, type App } from "vue";
import { i18n } from "../../src/i18n";

const running = new Set<() => void>();
const track = (stop: () => void) => {
  const once = () => { if (running.delete(once)) stop(); };
  running.add(once);
  return once;
};
/** Stops every scope and app a test started and left running (tests/setup.ts, after each test). */
export function stopScopes() {
  for (const stop of [...running].reverse()) stop();
}

/** Runs `composable` in an effect scope: its answer, and the stop that disposes everything it started. */
export function inScope<T>(composable: () => T): { result: T; stop: () => void } {
  const scope = effectScope();
  const result = scope.run(composable) as T;
  return { result, stop: track(() => scope.stop()) };
}

/** Runs `composable` in the setup of a mounted component, with the editor's texts and the active pinia. */
export function withSetup<T>(composable: () => T): { result: T; app: App; unmount: () => void } {
  let result!: T;
  const app = createApp(defineComponent({ setup() { result = composable(); return () => h("div"); } }));
  app.use(i18n);
  const pinia = getActivePinia();
  if (pinia) app.use(pinia);
  const host = document.createElement("div");
  document.body.append(host);
  app.mount(host);
  return { result, app, unmount: track(() => { app.unmount(); host.remove(); }) };
}
