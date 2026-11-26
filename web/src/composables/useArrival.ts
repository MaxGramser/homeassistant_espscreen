// After the firmware is on a new screen: whether it reached the Wi-Fi (model/installer.ts arrivalOf), from the moment
// New screen waits for it, with the inventory asked again every five seconds the page is in sight until it is paired.
import { computed, ref, watch, type Ref } from "vue";
import { arrivalOf } from "../model/installer";
import { useInventoryStore } from "../stores/inventory";
import { useVisibleInterval } from "./useVisibleInterval";

/** `waiting`: the firmware is on and the page waits for the screen; `file`: its profile; `now`: the page's clock;
 * `patient`: the person puts the firmware on it themselves (a download), so it is never late. */
export function useArrival(waiting: () => boolean, file: () => string | null, now: Ref<number>, patient: () => boolean = () => false) {
  const inv = useInventoryStore();
  const doneAt = ref(0);
  watch(waiting, (waits) => { if (waits && !doneAt.value) doneAt.value = Date.now(); });
  // What Home Assistant says of it now, and the furthest it got: between "found on the network" and "in Home
  // Assistant" there is a moment in which Home Assistant lists it as neither, and the page went back to "starting up"
  // for it (seen on a SenseCAP, 2026-11-26). The way there only goes forward.
  const FAR: Record<string, number> = { waiting: 0, seen: 1, paired: 2, ready: 3 };
  const reached = ref<"waiting" | "seen" | "paired" | "ready">("waiting");
  const seenNow = computed(() => (waiting() ? arrivalOf(inv.inventory, file() || "", now.value - doneAt.value, patient()) : null));
  watch(seenNow, (state) => { if (state && state in FAR && FAR[state] > FAR[reached.value]) reached.value = state as typeof reached.value; });
  const arrival = computed(() => {
    const state = seenNow.value;
    if (!state || state === "failed") return state;
    // Not on the network after three minutes only counts for a screen that was never found.
    if (state === "missing") return reached.value === "waiting" ? state : reached.value;
    return FAR[state] >= FAR[reached.value] ? state : reached.value;
  });
  useVisibleInterval(() => inv.refresh(false), 5000, { when: () => Boolean(arrival.value) && arrival.value !== "ready" });
  /** Waiting again from the next time the firmware is on (another network, the same installation again). */
  const restart = () => { doneAt.value = 0; reached.value = "waiting"; };
  return { arrival, restart };
}
