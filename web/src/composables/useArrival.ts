// After the firmware is on a new screen: whether it reached the Wi-Fi (model/installer.ts arrivalOf), from the moment
// New screen waits for it, with the inventory asked again every five seconds the page is in sight until it is paired.
import { computed, ref, watch, type Ref } from "vue";
import { arrivalOf } from "../model/installer";
import { useInventoryStore } from "../stores/inventory";
import { useVisibleInterval } from "./useVisibleInterval";

/** `waiting`: the firmware is on and the page waits for the screen; `file`: its profile; `now`: the page's clock. */
export function useArrival(waiting: () => boolean, file: () => string | null, now: Ref<number>) {
  const inv = useInventoryStore();
  const doneAt = ref(0);
  watch(waiting, (waits) => { if (waits && !doneAt.value) doneAt.value = Date.now(); });
  const arrival = computed(() => (waiting() ? arrivalOf(inv.inventory, file() || "", now.value - doneAt.value) : null));
  useVisibleInterval(() => inv.refresh(false), 5000, { when: () => Boolean(arrival.value) && arrival.value !== "paired" });
  /** Waiting again from the next time the firmware is on (another network, the same installation again). */
  const restart = () => { doneAt.value = 0; };
  return { arrival, restart };
}
