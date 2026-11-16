// The rules the add-on and the editor both keep for plugins answer the same cases alike
// (tests/fixtures/plugin-conformance.json; the add-on's side is tests/test_plugins.py).
import { describe, expect, it } from "vitest";
import cases from "../../tests/fixtures/plugin-conformance.json";
import rules from "../src/model/page-rules.json";
import { entityFits, PLUGIN_LIST_MAX, PLUGIN_OPTION_MAX, PLUGIN_OPTIONS_BYTES } from "../src/model/plugins";

describe("which entity an option of kind entity is for", () => {
  it.each(cases.entity_fits.map((example) => [example.name, example] as const))("%s", (_name, example) => {
    const fact = { device_class: (example as { device_class?: string }).device_class, translation_key: (example as { translation_key?: string }).translation_key };
    expect(entityFits(example.option, example.entity, fact)).toBe(example.fits);
  });
});

it("takes a tile's limits from the add-on's rules, never from a number of its own", () => {
  expect([PLUGIN_OPTIONS_BYTES, PLUGIN_LIST_MAX, PLUGIN_OPTION_MAX]).toEqual([rules.plugins.optionsBytes, rules.plugins.listMax, rules.plugins.optionMax]);
  expect(PLUGIN_OPTIONS_BYTES).toBeGreaterThan(0);
});
