import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";
import { editorTexts, translations } from "./vite.config";
import { firmwareTheme } from "./firmware-theme";

// Unit and component tests of the editor: the grid rules, the top bar rules, the store and the components,
// in jsdom. `npm test` runs them; `npm run test:watch` while developing. The components mount with the
// editor's texts (tests/setup.ts), in English, compiled as for the page; vue-i18n keeps its compiler here, for the
// texts the tests add themselves.
export default defineConfig({
  plugins: [editorTexts(), firmwareTheme(), translations(false), vue()],
  test: {
    environment: "jsdom",
    include: ["tests/**/*.spec.ts"],
    setupFiles: ["tests/setup.ts"],
    // What a test stubs or spies on is undone before the next one, so no test depends on the order they run in.
    restoreMocks: true,
    unstubGlobals: true,
    unstubEnvs: true,
  },
});
