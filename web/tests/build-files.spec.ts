// The build files (BuildFilesCard, stores/builds.ts, the add-on's build_files.py): the sizes in words, the clean-up
// only after its question says what it costs, never while something builds, the automatic clean-up with its downside
// beside it, and the offer after a build only when the build folders grew large, once a page.
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import BuildFilesCard from "../src/components/BuildFilesCard.vue";
import { i18n } from "../src/i18n";
import { freedBy, sizeText, type BuildFilesView } from "../src/model/build-files";
import { useBuildsStore } from "../src/stores/builds";
import { useInventoryStore } from "../src/stores/inventory";
import { useUiStore } from "../src/stores/ui";
import type { Screen } from "../src/types";
import { answerDialogs } from "./helpers/dialogs";
import { fakeApi } from "./helpers/fake-api";

const t = (key: string, named: Record<string, unknown> = {}) => i18n.global.t(key, named);
const GB = 1024 ** 3;
const files = (folders: number, more: Partial<BuildFilesView> = {}): BuildFilesView => ({
  sizes: { folders, screens: 3, cache: GB, tools: 2 * GB, total: folders + 3 * GB, at: 1 }, auto: false, offer: false,
  cleaning: null, last: null, offer_bytes: 4 * GB, ...more,
});
const add = (build_files: BuildFilesView | undefined, line: any[] = []) => {
  useInventoryStore().inventory = { screens: [], entities: [], line, build_files } as any;
};

describe("the sizes", () => {
  it("are said in GB from one on, else in MB", () => {
    expect(sizeText(6.24 * GB)).toBe("6.2 GB");
    expect(sizeText(350 * 1024 ** 2)).toBe("350 MB");
    expect(sizeText(0)).toBe("0 MB");
    expect(freedBy(files(5 * GB).sizes, "folders")).toBe(5 * GB);
    expect(freedBy(files(5 * GB).sizes, "all")).toBe(8 * GB);
    expect(freedBy(null, "all")).toBe(0);
  });
});

describe("the Build files card", () => {
  it("shows each kind, and Measuring before the add-on measured", () => {
    add(files(5 * GB, { sizes: null }));
    expect(mount(BuildFilesCard).text()).toContain(t("editor.settings.build_files.measuring"));
    add(files(5 * GB));
    const card = mount(BuildFilesCard);
    expect(card.find("#build-files-total").text()).toBe(t("editor.settings.build_files.total", { size: "8.0 GB" }));
    expect(card.find("#build-files-folders").text()).toContain("5.0 GB");
    expect(card.find("#build-files-folders").text()).toContain("3 screens");
    expect(card.find("#build-files-tools").text()).toContain("2.0 GB");
    // The automatic clean-up says what it costs beside it, not in a tooltip.
    expect(card.text()).toContain(t("editor.settings.build_files.auto_hint"));
  });

  it("cleans up only after its question says what it frees and costs", async () => {
    add(files(5 * GB));
    const api = fakeApi({ "POST build-files/clean": files(0, { last: { level: "folders", at: 2, freed: 5 * GB, automatic: false } }) });
    let yes = false;
    const asked = answerDialogs(() => yes);
    const card = mount(BuildFilesCard);
    await card.find("#build-files-clean").trigger("click");
    await flushPromises();
    expect(asked[0]).toMatchObject({ kind: "confirm", message: t("editor.settings.build_files.clean_confirm", { size: "5.0 GB" }), confirm: t("editor.settings.build_files.clean_go") });
    expect(api.count("POST build-files/clean")).toBe(0);
    yes = true;
    await card.find("#build-files-clean").trigger("click");
    await flushPromises();
    expect(api.asked("POST build-files/clean")[0].body).toEqual({ level: "folders" });
    expect(useUiStore().notice?.message).toBe(t("editor.settings.build_files.cleaned", { size: "5.0 GB" }));
    expect(useInventoryStore().inventory.build_files?.sizes?.folders).toBe(0);
    // Everything, in red: the cache and ESP-IDF come back only with a download.
    await card.find("#build-files-clean-all").trigger("click");
    await flushPromises();
    expect(asked.at(-1)).toMatchObject({ danger: true, message: t("editor.settings.build_files.clean_all_confirm", { size: "3.0 GB" }) });
    expect(api.asked("POST build-files/clean")[1].body).toEqual({ level: "all" });
  });

  it("is not offered while a build runs or waits", () => {
    add(files(5 * GB), [{ id: 1, state: "queued", by: "update", file: "hall.yaml" }]);
    const card = mount(BuildFilesCard);
    expect(card.find("#build-files-clean").attributes("disabled")).toBeDefined();
    expect(card.find("#build-files-busy").exists()).toBe(true);
  });

  it("turns the automatic clean-up on and off, and Not now goes to the add-on", async () => {
    add(files(6 * GB, { offer: true }));
    const api = fakeApi({ "PUT build-files": files(6 * GB, { auto: true }), "POST build-files/decline": files(6 * GB) });
    const card = mount(BuildFilesCard);
    expect(card.find("#build-files-large").exists()).toBe(true);
    await card.find("#build-files-not-now").trigger("click");
    await flushPromises();
    expect(api.count("POST build-files/decline")).toBe(1);
    expect(card.find("#build-files-large").exists()).toBe(false);
    await useBuildsStore().setAutoClean(true);
    expect(api.asked("PUT build-files")[0].body).toEqual({ auto: true });
    expect(useInventoryStore().inventory.build_files?.auto).toBe(true);
  });
});

describe("the offer after a build", () => {
  const living = (time: number) => ({ id: "text.living", name: "Living room", online: true, layout: {},
    update: { profile: "living.yaml", host: "10.0.0.2", result: { message: "", state: "success", time } } }) as unknown as Screen;
  const arrive = (screen: Screen, build_files: BuildFilesView, builds: Record<string, any> = {}) => {
    useInventoryStore().inventory = { screens: [screen], entities: [], builds, line: [], build_files } as any;
    useBuildsStore().prune();
  };
  const build = { "text.living": { by: "update", state: "running", file: "living.yaml", phase: "install" } };

  it("comes with the build's own words only when the add-on offers it, and once a page", async () => {
    arrive(living(10), files(2 * GB), build);
    arrive(living(20), files(2 * GB));
    await Promise.resolve();
    expect(useUiStore().notice?.action).toBeUndefined();
    arrive(living(20), files(6 * GB, { offer: true }), build);
    arrive(living(30), files(6 * GB, { offer: true }));
    await Promise.resolve();
    expect(useUiStore().notice).toMatchObject({ message: t("editor.build.ready", { name: "Living room" }), action: { label: t("editor.settings.build_files.offer", { size: "6.0 GB" }) } });
    useUiStore().dismissToast();
    arrive(living(30), files(7 * GB, { offer: true }), build);
    arrive(living(40), files(7 * GB, { offer: true }));
    await Promise.resolve();
    expect(useUiStore().notice?.action).toBeUndefined();
  });
});
