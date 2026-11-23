// ---- The automations of Tessera in Home Assistant, by kind (screen_manager/app/automations.py) ----
// One list per kind of Events (an alert, a doorbell's ring) for the whole page: the Events list says how many there are,
// a part of Events lists them, and a wizard's save shows in both. Asked when a view needs them (refresh); a view that
// asks again within FRESH_MS gets the list there is. Home Assistant's own page of an automation is in the frame around
// the editor (ingress), so its address is the same origin.
import { defineStore } from "pinia";
import { ref } from "vue";
import { getJson, send } from "../api";
import type { Automation } from "../model/automation";

export type AutomationKind = "doorbell" | "alert";
export type ListedAutomation = { entity: string; id: string | null; kind: string | null; name: string; on: boolean; last?: string | null };
export const automationLink = (id: string) => `/config/automation/edit/${encodeURIComponent(id)}`;
const FRESH_MS = 3000;

export const useAutomationsStore = defineStore("automations", () => {
  const listed = ref<Record<AutomationKind, ListedAutomation[]>>({ alert: [], doorbell: [] });
  /** Whether a kind's list was asked for at least once: a count before that is not known. */
  const known = ref<Record<AutomationKind, boolean>>({ alert: false, doorbell: false });
  const asked: Record<AutomationKind, number> = { alert: 0, doorbell: 0 };
  const flight: Partial<Record<AutomationKind, Promise<void>>> = {};

  function refresh(kind: AutomationKind, force = true) {
    if (!force && known.value[kind] && Date.now() - asked[kind] < FRESH_MS) return Promise.resolve();
    if (flight[kind]) return flight[kind]!;
    asked[kind] = Date.now();
    return (flight[kind] = getJson<{ automations: ListedAutomation[] }>(`automations?kind=${kind}`)
      .then((answer) => { listed.value[kind] = answer.automations || []; })
      .catch(() => { listed.value[kind] = []; })
      .finally(() => { known.value[kind] = true; delete flight[kind]; }));
  }
  /** Saves `automation`; `id` saves one of ours again. The new entity is in Home Assistant's states a moment later. */
  async function save(kind: AutomationKind, automation: Automation, id?: string | null) {
    const saved = await send<{ id: string; path: string }>("automations", "POST", { kind, id: id || undefined, config: automation });
    setTimeout(() => void refresh(kind), 1500);
    return saved;
  }
  async function remove(kind: AutomationKind, id: string) {
    await send(`automations/${encodeURIComponent(id)}`, "DELETE");
    listed.value[kind] = listed.value[kind].filter((item) => item.id !== id);
  }
  return { listed, known, refresh, save, remove };
});
