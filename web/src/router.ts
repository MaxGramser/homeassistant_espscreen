// The editor's address (vue-router, hash history): the page lives in Home Assistant's ingress iframe, where only the
// hash is the page's own, so every view is `#/...`. The address is the one place that says what is open: the overview,
// a screen, a page of the app, or a screen's Override YAML. A reload opens the same again, the browser's Back and
// Forward walk through what was open, and a link to a screen or an override can be kept. The hashes from before the
// router (`#settings`, `#plugins`) still work: vue-router reads `#settings` as `/settings`.
//
// App.vue chooses what to draw from the route's name and the stores (a screen route draws the screen once its layout
// is there, the overview when there are screens, else the empty page), so every route carries the same empty component.
import { createRouter, createWebHashHistory, START_LOCATION, type RouteLocationRaw } from "vue-router";

const Nothing = { render: () => null };

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", name: "home", component: Nothing },
    // A screen by its inbox entity id (text.kitchen_tile_settings): what the inventory calls it.
    { path: "/screens/:id", name: "screen", component: Nothing },
    { path: "/settings", name: "settings", component: Nothing },
    { path: "/new-screen", name: "new-screen", component: Nothing },
    { path: "/firmware", name: "firmware", component: Nothing },
    { path: "/alerts", name: "alerts", component: Nothing },
    { path: "/plugins", name: "plugins", component: Nothing },
    // The Override YAML of a screen's ESPHome profile (kitchen.yaml); without a profile the page says so.
    { path: "/override/:profile?", name: "override", component: Nothing },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
});

// Every new view starts at the top, as a page does.
router.afterEach((to, from) => { if (to.path !== from.path) window.scrollTo(0, 0); });

// Home Assistant's sidebar shows the editor in an iframe: the route lives on the iframe's address, which nobody sees,
// and Home Assistant makes the iframe anew on every reload of its page, at the editor's bare address. So the route is
// mirrored into the hash of the page around it (same origin through ingress, so the browser allows it; replaceState,
// so Back and Forward stay the iframe's own): the address bar reads /app/<slug>#/screens/..., can be copied, and a page
// that starts at the overview goes back to what that hash, or else what this tab last had (sessionStorage), says.
// An address the iframe itself has (#/screens/..., an old #settings) wins: it is there, and nothing is restored over
// it; a tab whose last address was the overview stays there. (The router has already read the iframe's address when
// restoreKeptRoute runs: a bare one is `/` by then.) Outside a frame, and in a frame of another origin, only the tab's
// storage is used.
const KEPT = "esp-screens.route";
const outer = (() => {
  try { return window.top && window.top !== window && window.top.location.origin === location.origin ? window.top : null; } catch { return null; }
})();
router.afterEach((to, from) => {
  // The router's first navigation reads the address the page started with: a bare one is the overview, and keeping that
  // would write over the address this tab had before the reload, which restoreKeptRoute is about to read.
  if (from === START_LOCATION && to.path === "/") return;
  try { sessionStorage.setItem(KEPT, to.fullPath); } catch { /* storage may be off */ }
  try { outer?.history.replaceState(outer.history.state, "", `${outer.location.pathname}${outer.location.search}#${to.fullPath}`); } catch { /* not ours to write */ }
});
export async function restoreKeptRoute() {
  if (router.currentRoute.value.path !== "/") return;
  let kept: string | null = null;
  try { const hash = outer?.location.hash ?? ""; if (hash.startsWith("#/")) kept = hash.slice(1); } catch { /* not ours to read */ }
  if (!kept) { try { kept = sessionStorage.getItem(KEPT); } catch { /* storage may be off */ } }
  if (kept && kept !== "/") await router.replace(kept);
}

export const screenRoute = (id: string): RouteLocationRaw => ({ name: "screen", params: { id } });
export const overrideRoute = (profile: string | null): RouteLocationRaw => ({ name: "override", params: { profile: profile ?? "" } });
