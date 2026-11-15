import VueI18n from "@intlify/unplugin-vue-i18n/vite";
import vue from "@vitejs/plugin-vue";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { defineConfig, type Plugin } from "vite";
import { pageTexts, TRANSLATIONS } from "./translations";
import { firmwareTheme } from "./firmware-theme";
import { previewAgePlugin } from "./preview-age";

// Before vue-i18n's plugin compiles a file into the page's messages: only its page part goes in. Every language's
// `_meta` (its name, plural rule, whether it is checked) comes with the page as virtual:esp-screens-languages, so the
// editor knows the languages before it loads one.
const LANGUAGES_ID = "virtual:esp-screens-languages";
export function editorTexts(): Plugin {
  return {
    name: "esp-screens-editor-texts",
    enforce: "pre",
    resolveId: (id) => (id === LANGUAGES_ID ? `\0${LANGUAGES_ID}` : null),
    load(id) {
      if (id !== `\0${LANGUAGES_ID}`) return null;
      const languages: Record<string, unknown> = {};
      for (const name of readdirSync(TRANSLATIONS).filter((file) => file.endsWith(".json")).sort()) {
        this.addWatchFile(join(TRANSLATIONS, name));
        languages[name.slice(0, -".json".length)] = JSON.parse(readFileSync(join(TRANSLATIONS, name), "utf8"))._meta;
      }
      return `export default ${JSON.stringify(languages)};`;
    },
    transform(code, id) {
      if (!/[\\/]screen_manager[\\/]translations[\\/][^\\/?]+\.json$/.test(id)) return null;
      return { code: JSON.stringify(pageTexts(JSON.parse(code))), map: null };
    },
  };
}
// vue-i18n compiles every text while building (app 0.2.90), so the page runs its runtime-only build without the message
// compiler, and no text is compiled in the browser. A text it can't read stops the build (tools/i18n.py check says so
// first). `runtimeOnly: false` for the tests, which add texts of their own.
export const translations = (runtimeOnly = true) =>
  VueI18n({ include: [join(TRANSLATIONS, "*.json")], runtimeOnly, compositionOnly: true, fullInstall: true, dropMessageCompiler: runtimeOnly });

// The add-on serves the built page from screen_manager/app/static behind Home Assistant ingress,
// which lives on a sub path with a token. Everything is relative so the page works there and on
// a bare http://127.0.0.1:8099 (SCREEN_DEV). The Python server keeps serving /api; only the static
// files change. `npm run dev` proxies /api to a running server (the demo home or SCREEN_DEV).
export default defineConfig({
  base: "./",
  plugins: [editorTexts(), firmwareTheme(), previewAgePlugin(), translations(), vue()],
  // No vue-i18n devtools in the build; its other switches come from the plugin above.
  define: { __INTLIFY_PROD_DEVTOOLS__: false },
  build: {
    outDir: "../screen_manager/app/static",
    emptyOutDir: false,
    target: "es2022",
  },
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8099", changeOrigin: false } },
    // The translations live beside the add-on, outside web/.
    fs: { allow: [".", "../screen_manager/translations"] },
  },
});
