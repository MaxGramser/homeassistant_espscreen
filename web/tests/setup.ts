// Every mounted component gets the editor's texts and the stores, as main.ts gives the page (app 0.2.90).
import { config, enableAutoUnmount } from "@vue/test-utils";
import { afterEach, beforeEach, vi } from "vitest";
import { defineComponent, h } from "vue";
import { cancelQuestions } from "../src/composables/useConfirm";
import { resetDrag } from "../src/drag";
import { i18n, resetLanguages } from "../src/i18n";
import { installBrowser, resetBrowser } from "./helpers/browser";
import { disposePinia, freshPinia } from "./helpers/pinia";
import { stopScopes } from "./helpers/with-setup";

config.global.plugins = [i18n];
installBrowser();
// A pinia of its own for every test: the active one, and the one a mounted component gets (tests/helpers/pinia.ts).
beforeEach(() => { freshPinia(); });
// Every test starts where the page starts, whatever ran before it (npm run test:shuffle runs them in another order each
// time): no composable a test left running, real timers, nothing stubbed, an empty storage, page and address, no
// question left open, the languages of the files in English, no drag in the air, and the stores of the test stopped
// (their timers, what their start began), the next test getting a pinia of its own. Registered before the unmount
// below, so it runs after it: hooks after a test run last first.
afterEach(() => {
  stopScopes();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  try { localStorage.clear(); sessionStorage.clear(); } catch { /* a test made storage throw */ }
  if (location.hash) history.replaceState(null, "", location.pathname + location.search);
  document.body.innerHTML = "";
  document.body.removeAttribute("style");
  document.documentElement.removeAttribute("lang");
  resetBrowser();
  cancelQuestions();
  resetLanguages();
  resetDrag();
  disposePinia();
});
enableAutoUnmount(afterEach);
// jsdom does not draw glyphs or implement modal dialogs. Geometry is verified
// with the real fonts in the browser and the firmware host renders.
HTMLCanvasElement.prototype.getContext = vi.fn(() => null) as any;
HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
// A setting's choices open in a popover when they don't fit side by side (ChoiceField, app 0.4.32); jsdom can't place
// one, so the tests see every choice as a button in a row, as the side-by-side form draws them.
config.global.stubs = {
  ChoiceField: defineComponent({
    props: ["choices", "value", "disabled"],
    emits: ["pick"],
    setup(props: any, { emit }) {
      return () => h("div", { class: "seg" }, (props.choices as [unknown, string][]).map(([key, text]) => h("button", {
        key: String(key), type: "button", disabled: props.disabled, "aria-pressed": String(key) === String(props.value) ? "true" : "false",
        onClick: () => emit("pick", key),
      }, text)));
    },
  }),
};
