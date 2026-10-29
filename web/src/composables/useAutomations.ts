// The automations of Tessera in Home Assistant, of one kind of Events (screen_manager/app/automations.py): the list the
// page shows, saving the one a wizard built (a new one, or the same one again), and removing one this app made. Home
// Assistant's own page of an automation is in the frame around the editor (ingress), so its address is the same origin.
import { ref } from "vue";
import { getJson, send } from "../api";
import type { Automation } from "../model/automation";

export type ListedAutomation = { entity: string; id: string | null; kind: string | null; name: string; on: boolean; last?: string | null };
export const automationLink = (id: string) => `/config/automation/edit/${encodeURIComponent(id)}`;

export function useAutomations(kind: "doorbell" | "alert") {
  const listed = ref<ListedAutomation[]>([]);
  async function refresh() {
    try { listed.value = (await getJson<{ automations: ListedAutomation[] }>(`automations?kind=${kind}`)).automations || []; } catch { listed.value = []; }
  }
  /** Saves `automation`; `id` saves one of ours again. The new entity is in Home Assistant's states a moment later. */
  async function save(automation: Automation, id?: string | null) {
    const saved = await send<{ id: string; path: string }>("automations", "POST", { kind, id: id || undefined, config: automation });
    setTimeout(refresh, 1500);
    return saved;
  }
  async function remove(id: string) {
    await send(`automations/${encodeURIComponent(id)}`, "DELETE");
    listed.value = listed.value.filter((item) => item.id !== id);
  }
  return { listed, refresh, save, remove };
}
