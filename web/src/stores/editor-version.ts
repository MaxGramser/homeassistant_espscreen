// ---- An editor that is older than its app reloads itself (docs/BUILDS.md, "After an update of the app") ----
// The page keeps the editor it loaded. After an update of the app (or a rebuild of the dev app) the add-on serves a new
// one, but an open page goes on running the old editor against the new app, which may not know what the app sends.
// Every live answer names the editor the app serves (`editor`: its index-<hash>.js). When that is not the one this page
// runs, the page reloads itself as soon as nothing is in progress: no unsaved change of a screen, no plugin work this
// page holds (the tray, a change on its way), not in New screen or Firmware & USB (a browser flash would break off), not
// writing a troubleshooting report. Until then it says so once, with a key to reload now. It reloads at most once for
// one editor the app serves (kept for this tab), so an app that names one it cannot serve never loops the page.
import { watch } from "vue";
import { t } from "../i18n";
import { useDocumentStore } from "./document";
import { useInventoryStore } from "./inventory";
import { usePluginsStore } from "./plugins";
import { useUiStore } from "./ui";

/** The editor script this page runs, as its own index.html named it; null for the development server. */
export function ownBundle(doc: Document = document): string | null {
  const src = [...doc.querySelectorAll<HTMLScriptElement>("script[type=module][src]")].map((s) => s.getAttribute("src") || "")
    .find((src) => /assets\/index-[A-Za-z0-9_-]+\.js$/.test(src));
  return src ? src.split("/").pop()! : null;
}

/** Whether the app serves another editor than this page runs. */
export const stale = (own: string | null, served: string | null | undefined) => Boolean(own && served && own !== served);

// Where a reload would break something off.
const BUSY_ROUTES = ["#new-screen", "#firmware", "#report"];
// The editor this tab reloaded for last: never twice for the same one.
const RELOADED = "esp-screens.reloaded-for";

export function startEditorVersion(reload: () => void = () => window.location.reload()) {
  const inv = useInventoryStore();
  const doc = useDocumentStore();
  const plugins = usePluginsStore();
  const ui = useUiStore();
  const own = ownBundle();
  let told = false;
  const reloadFor = (served: string) => {
    sessionStorage.setItem(RELOADED, served);
    reload();
  };
  return watch(() => [inv.inventory.editor, doc.dirty, plugins.pending, ui.route] as const, ([served, dirty, pending, route]) => {
    if (!served || !stale(own, served) || sessionStorage.getItem(RELOADED) === served) return;
    if (!dirty && !pending && !BUSY_ROUTES.includes(route || "")) { reloadFor(served); return; }
    if (told) return;
    told = true;
    ui.toast(t("editor.update.editor_new"), { label: t("editor.update.editor_reload"), run: () => reloadFor(served) });
  }, { immediate: true });
}
