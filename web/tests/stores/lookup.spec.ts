// A store's lookups (stores/lookup.ts): getters whose value is the function, so a card that asks one while it is drawn
// pays no action's bookkeeping, and what the function reads is followed by whoever calls it.
import { defineStore } from "pinia";
import { describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";
import { lookups } from "../../src/stores/lookup";
import { useEntitiesStore } from "../../src/stores/entities";

const useNames = defineStore("lookup-test", () => {
  const names = ref<Record<string, string>>({ a: "Lamp" });
  const nameOf = (id: string) => names.value[id] || id;
  function rename(id: string, name: string) { names.value[id] = name; }
  return { names, ...lookups({ nameOf }), rename };
});

describe("a store's lookups", () => {
  it("are no actions: calling one tells no $onAction, an action still does", () => {
    const store = useNames(), heard = vi.fn();
    store.$onAction(({ name }) => heard(name));
    expect(store.nameOf("a")).toBe("Lamp");
    expect(heard).not.toHaveBeenCalled();
    store.rename("a", "Light");
    expect(heard).toHaveBeenCalledWith("rename");
  });

  it("are the same function every time, and what they read is followed by the one who calls them", () => {
    const store = useNames();
    expect(store.nameOf).toBe(store.nameOf);
    const shown = computed(() => store.nameOf("a"));
    expect(shown.value).toBe("Lamp");
    store.rename("a", "Light");
    expect(shown.value).toBe("Light");
  });

  it("are what the cards read of the entities store", () => {
    const entities = useEntitiesStore(), heard = vi.fn();
    entities.$onAction(heard);
    entities.entityName("light.a");
    entities.tileIconCp({ entity: "light.a", name: "", slot: 0 });
    entities.liveOf("light.a");
    expect(heard).not.toHaveBeenCalled();
  });
});
