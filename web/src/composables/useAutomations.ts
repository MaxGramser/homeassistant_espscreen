// One kind of the automations of Tessera (stores/automations.ts, the one list of the page), in the shape a part of
// Events uses: its list, asking for it again, saving the one a wizard built, removing one this app made.
import { computed } from "vue";
import type { Automation } from "../model/automation";
import { automationLink, useAutomationsStore, type AutomationKind, type ListedAutomation } from "../stores/automations";

export { automationLink, type ListedAutomation };

export function useAutomations(kind: AutomationKind) {
  const store = useAutomationsStore();
  return {
    listed: computed(() => store.listed[kind]),
    refresh: () => store.refresh(kind),
    save: (automation: Automation, id?: string | null) => store.save(kind, automation, id),
    remove: (id: string) => store.remove(kind, id),
  };
}
