// The stores of a test (Pinia): every test starts with an empty pinia of its own (tests/setup.ts calls freshPinia before
// each), so no store keeps what the test before it left. testingPinia is the one for a test that watches the actions:
// each is a vi.fn spy, and by default it still runs, since the editor's tests follow a whole flow through its stores.
import { createTestingPinia, type TestingOptions, type TestingPinia } from "@pinia/testing";
import { config } from "@vue/test-utils";
import { createPinia, getActivePinia, setActivePinia, type Pinia, type StoreGeneric } from "pinia";
import { vi } from "vitest";

/** A new, empty pinia: the active one, and the one every component a test mounts gets. */
export function freshPinia(): Pinia {
  const pinia = createPinia();
  setActivePinia(pinia);
  usePiniaInMounts(pinia);
  return pinia;
}

/** Stops what the stores of the active pinia keep running (a timer still waiting, what their start began), as closing the
 * page would, so a test's stores never reach into the next one (tests/setup.ts, after each test). */
export function disposePinia() {
  const pinia = getActivePinia() as (Pinia & { _s: Map<string, StoreGeneric> }) | undefined;
  for (const store of [...(pinia?._s.values() || [])]) store.$dispose();
}

/** A pinia whose actions are spies (vi.fn). `stubActions: true` (or a list of names) replaces them instead of running them. */
export function testingPinia(options: TestingOptions = {}): TestingPinia {
  const pinia = createTestingPinia({ createSpy: vi.fn, stubActions: false, ...options });
  setActivePinia(pinia);
  usePiniaInMounts(pinia);
  return pinia;
}

// The plugins every mounted component gets: the editor's texts as the page has them, and this pinia instead of the last.
function usePiniaInMounts(pinia: Pinia) {
  const others = (config.global.plugins || []).filter((plugin) => !isPinia(plugin));
  config.global.plugins = [...others, pinia];
}
const isPinia = (plugin: unknown) => Boolean(plugin && typeof plugin === "object" && "_s" in plugin && "state" in plugin);
