// The screens' language, clock and numbers (stores/region.ts): what the add-on says of them, saving a choice, and the
// screens' language loading once its start follows it.
import { flushPromises } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { i18n, te } from "../../src/i18n";
import { useRegionStore } from "../../src/stores/region";
import { useUiStore } from "../../src/stores/ui";
import type { Languages } from "../../src/types";
import { failure, fakeApi } from "../helpers/fake-api";
import { useInventoryStore } from "../../src/stores/inventory";

const language = (extra: Partial<Languages> = {}) => ({
  setting: "auto", effective: "nl", ha: "nl", clock: "auto", clock_effective: "24", numbers: "auto", numbers_effective: "comma",
  clock_auto: "24", numbers_auto: "point", group_min: 2, group_min_auto: 1, percent_space: true,
  languages: [{ code: "nl", name: "Nederlands", english: "Dutch", checked: true }], ...extra,
}) as Languages;

describe("the screens' language and region", () => {
  it("follows what the add-on says, and English, a 24-hour clock and 1,234.5 until it says anything", () => {
    const region = useRegionStore();
    expect([region.screenLanguage, region.clock24, region.numberMarks.from, region.unitSuffix("%")]).toEqual(["en", true, 4, "%"]);
    useInventoryStore().inventory = { screens: [], entities: [], language: language({ clock_effective: "12" }) } as any;
    expect([region.screenLanguage, region.clock24, region.languageName("nl"), region.languageName("de")]).toEqual(["nl", false, "Nederlands", "Deutsch"]);
    expect(region.numberMarks).toMatchObject({ from: 5 });
    expect(region.autoMarks).toMatchObject({ from: 4 });
    expect([region.unitSuffix("%"), region.unitSuffix("°"), region.unitSuffix("kWh"), region.unitSuffix(undefined)]).toEqual([" %", "°", " kWh", ""]);
  });

  it("saves a choice: the add-on's answer, a word about it and the inventory read again; a refusal changes nothing", async () => {
    useInventoryStore().inventory = { screens: [], entities: [], language: language() } as any;
    const api = fakeApi({
      "PUT language": (request) => ({ language: language({ setting: request.body.setting, effective: request.body.setting }) }),
      "GET inventory": { screens: [], entities: [], language: language({ setting: "de", effective: "de" }) },
    });
    const region = useRegionStore();
    expect(await region.saveLanguage({ setting: "de" })).toBe(true);
    expect(useInventoryStore().inventory.language?.effective).toBe("de");
    expect(useUiStore().notice?.message).toBe(i18n.global.t("editor.settings.language.saved_language"));
    expect(api.calls.map((r) => `${r.method} ${r.path}`)).toEqual(["PUT language", "GET inventory"]);
    api.on("PUT language", failure(400, "No such language"));
    expect(await region.saveLanguage({ clock: "13" })).toBe(false);
    expect(useInventoryStore().inventory.language?.effective).toBe("de");
    expect(useUiStore().notice?.message).toBe("No such language");
  });

  it("loads the screens' language once its start follows it, and not after it stopped", async () => {
    const region = useRegionStore();
    useInventoryStore().inventory = { screens: [], entities: [], language: language({ effective: "de" }) } as any;
    expect(te("editor.common.ok", "de")).toBe(false);
    const stop = region.start();
    expect(region.start()).toBe(stop);
    await flushPromises();
    await vi.waitFor(() => expect(te("editor.common.ok", "de")).toBe(true));
    stop();
    useInventoryStore().inventory.language = language({ effective: "fr" });
    await flushPromises();
    expect(te("editor.common.ok", "fr")).toBe(false);
  });
});
