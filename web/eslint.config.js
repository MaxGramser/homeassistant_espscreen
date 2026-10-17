// ESLint for the editor (web/): the correctness rules of ESLint, typescript-eslint and eslint-plugin-vue, in Vue 3
// files as in TypeScript. `npm run lint` runs it, `npm run check` (and so `npm run build`) fails on an error, and
// tools/check.sh runs it as "Editor: lint (ESLint)" (docs/TESTING.md). Rules that only decide how a template is
// laid out are off: the editor is formatted by hand, and such a rule would mean rewriting hundreds of lines.
import js from "@eslint/js";
import { defineConfig, globalIgnores } from "eslint/config";
import pluginVue from "eslint-plugin-vue";
import globals from "globals";
import tseslint from "typescript-eslint";

export default defineConfig(
  // Build output and generated code: the page's bundle (vite build), the WASM preview Emscripten writes
  // (src/wasm/firmware_preview.js) and the fonts and profiles its build generates (wasm/generated).
  globalIgnores(["dist/", "node_modules/", "src/wasm/firmware_preview.js", "wasm/generated/"]),
  {
    files: ["**/*.{js,mjs,ts,vue}"],
    extends: [js.configs.recommended, tseslint.configs.recommended, pluginVue.configs["flat/recommended"]],
    languageOptions: {
      globals: { ...globals.browser },
      // The <script> of a .vue file is TypeScript.
      parserOptions: { parser: tseslint.parser },
    },
    rules: {
      // A variable, argument or caught error that starts with _ is unused on purpose.
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrorsIgnorePattern: "^_",
        // `const { o, ...rest } = x` names o only to leave it out of rest.
        ignoreRestSiblings: true }],
      // The API layer is typed in a later round; until then `any` marks what it still lacks.
      "@typescript-eslint/no-explicit-any": "off",
      // Layout of a template is a matter of hand formatting here, not of a rule: these would reflow every component.
      "vue/max-attributes-per-line": "off", // attributes stay on one line while they fit
      "vue/singleline-html-element-content-newline": "off", // a short element keeps its text on its line
      "vue/multiline-html-element-content-newline": "off", // as above, for an element with several attributes
      "vue/html-self-closing": "off", // <div /> and <div></div> both stay as written
      "vue/attributes-order": "off", // attributes are ordered by meaning, not by the plugin's list
      "vue/multi-word-component-names": "off", // Library.vue, Drawer.vue, Toast.vue are one word on purpose
      "vue/html-indent": "off", // indentation follows the file, not a rule
      "vue/first-attribute-linebreak": "off", // a long tag may break after its name or after its first attribute
      "vue/html-closing-bracket-newline": "off", // the > of a multi-line tag stays where it was written
      "vue/html-closing-bracket-spacing": "off", // as above, for the space before />
      "vue/require-default-prop": "off", // an optional prop without a default is `undefined`, which the code handles
    },
  },
  {
    // What runs under Node: the Vite and Vitest configs and their helpers, and the WASM preview's tests.
    files: ["*.ts", "*.js", "wasm/*.mjs", "wasm/*.js"],
    languageOptions: { globals: { ...globals.node } },
  },
);
