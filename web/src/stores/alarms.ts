// ---- The alarm panels of Home Assistant as the screens follow them (screen_manager/app/alarm_screens.py, api/alarms) ----
// One view for the page: the Events list says how many panels there are, the Alarm part sets per panel which screens
// open the keypad and after how many digits a code sends itself. Asked once a view shows it; a change is the add-on's
// answer, which every view reads at once.
import { defineStore } from "pinia";
import { ref } from "vue";
import { getJson, send } from "../api";

export type Alarm = { entity: string; name: string; code: boolean; screens: "all" | string[]; send_after: string };
export type AlarmsView = { alarms: Alarm[]; send_after: string[] };

export const useAlarmsStore = defineStore("alarms", () => {
  const view = ref<AlarmsView | null>(null);
  let loading: Promise<void> | null = null;
  /** The view, asked once a view needs it (again with `force`). */
  function load(force = false) {
    if (view.value && !force) return Promise.resolve();
    return (loading ??= getJson<AlarmsView>("alarms").then((answer) => { view.value = answer; }).finally(() => { loading = null; }));
  }
  /** One panel's choices, kept by the add-on; its answer is the view from then on. */
  async function save(alarm: Alarm, change: Partial<Pick<Alarm, "screens" | "send_after">>) {
    view.value = await send<AlarmsView>("alarms", "PUT", { entity: alarm.entity, screens: alarm.screens, send_after: alarm.send_after, ...change });
  }
  return { view, load, save };
});
