/// <reference types="vite/client" />
declare module "virtual:esp-screens-theme" {
  const theme: { ha: Record<string, number>; roles: Record<string, { light: number; dark: number }>;
    keys: { name: string; key: number; text: number }[]; iconBase: number; iconWeight: number };
  export default theme;
}
declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<object, object, any>;
  export default component;
}
// Every language's _meta by its code, from screen_manager/translations (vite.config.ts, app 0.2.90).
declare module "virtual:esp-screens-languages" {
  const languages: Record<string, { name: string; english: string; script?: string; plural: string; clock?: string; checked: boolean }>;
  export default languages;
}
