// Every mounted component gets the editor's texts, as main.ts gives the page (app 0.2.90).
import { config, enableAutoUnmount } from "@vue/test-utils";
import { afterEach, vi } from "vitest";
import { defineComponent, h } from "vue";
import { i18n } from "../src/i18n";
import { resetAll } from "../src/resets";
import { installBrowser, resetBrowser } from "./helpers/browser";

config.global.plugins = [i18n];
installBrowser();
// Every test starts where the page starts, whatever ran before it (npm run test:shuffle runs them in another order each
// time): real timers, nothing stubbed, an empty storage, page and address, and every module's state as it loaded
// (src/resets.ts). Registered before the unmount below, so it runs after it: hooks after a test run last first.
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  try { localStorage.clear(); sessionStorage.clear(); } catch { /* a test made storage throw */ }
  if (location.hash) history.replaceState(null, "", location.pathname + location.search);
  document.body.innerHTML = "";
  document.body.removeAttribute("style");
  document.documentElement.removeAttribute("lang");
  resetBrowser();
  resetAll();
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
