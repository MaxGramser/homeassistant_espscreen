import { createApp } from "vue";
import App from "./App.vue";
import "./styles/tokens.css";
import "./styles/app.css";
import { i18n, setEditorLanguage } from "./i18n";
import { boot } from "./boot";

// The page draws once its language is there, so it never flashes English first, and the first request already asks the
// add-on for that language (app 0.2.90).
setEditorLanguage().finally(() => {
  createApp(App).use(i18n).mount("#app");
  boot();
});
