import { createPinia } from "pinia";
import { createApp } from "vue";
import App from "./App.vue";
import "./styles/tokens.css";
import "./styles/app.css";
import { i18n, setEditorLanguage } from "./i18n";
import { boot } from "./boot";

// The page draws once its language is there, so it never flashes English first, and the first request already asks the
// add-on for that language (app 0.2.90). The stores (Pinia) are there before the page mounts and before boot starts
// what they follow.
setEditorLanguage().finally(() => {
  createApp(App).use(createPinia()).use(i18n).mount("#app");
  boot();
});
