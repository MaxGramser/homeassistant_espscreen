import { createPinia } from "pinia";
import { createApp } from "vue";
import App from "./App.vue";
import "./styles/tokens.css";
import "./styles/app.css";
import { i18n, setEditorLanguage } from "./i18n";
import { boot } from "./boot";
import { restoreKeptRoute, router } from "./router";

// The page draws once its language is there, so it never flashes English first, and the first request already asks the
// add-on for that language (app 0.2.90), and once the router has read the address, so a reload on a screen never draws
// the overview first. The stores (Pinia) are there before the page mounts and before boot starts what they follow.
setEditorLanguage().finally(async () => {
  const app = createApp(App).use(createPinia()).use(i18n).use(router);
  await router.isReady();
  await restoreKeptRoute();
  app.mount("#app");
  boot();
});
