import { flushPromises, mount, type VueWrapper } from "@vue/test-utils";
import { describe, expect, it } from "vitest";
import PluginDetail from "../src/components/PluginDetail.vue";
import PluginModelList from "../src/components/PluginModelList.vue";
import PluginOnScreens from "../src/components/plugins/PluginOnScreens.vue";
import PluginSettings from "../src/components/PluginSettings.vue";
import ScreenPluginsTab from "../src/components/ScreenPluginsTab.vue";
import { answer, question } from "../src/composables/useConfirm";
import { i18n } from "../src/i18n";
import type { Installed, Plugin, PluginBuildSetting } from "../src/model/plugins";
import { useInventoryStore } from "../src/stores/inventory";
import { usePluginsStore } from "../src/stores/plugins";
import { useScreenStore } from "../src/stores/screen";
import type { Screen } from "../src/types";
import { failure, fakeApi } from "./helpers/fake-api";
import { lastStream } from "./helpers/browser";

const setting: PluginBuildSetting = {
  id: "wake_models", kind: "micro_wake_word_models", label: { en: "Wake models" }, target: "wake", feature_step_size: 10,
  legacy_installed: ["nabu", "jarvis", "mycroft"], catalogue: [
    { id: "nabu", label: { en: "Okay Nabu" }, url: "https://models.example/nabu.json" },
    { id: "jarvis", label: { en: "Hey Jarvis" }, url: "https://models.example/jarvis.json" },
    { id: "mycroft", label: { en: "Hey Mycroft" }, url: "https://models.example/mycroft.json" },
  ],
};
const voice: Plugin = {
  id: "voice", name: { en: "Voice" }, summary: { en: "" }, icon: "F00E7", maintainer: "maker", tessera: true,
  version: "1.0.0", repo: "", origin: "github.com/maker/models", license: "MIT", type: "functions", boards: "any", requires: {}, flash_kb: 10,
  permissions: { home_assistant: [], network: [] }, readme: { en: "" }, languages: ["en"], attributes: [], source: "index", build_settings: [setting],
};
const hall = { id: "hall", node: "hall", name: "Hall", online: true, board: "guition", pictures: true,
  firmware: "0.52.0", layout: {}, update: { profile: "hall.yaml" } } as unknown as Screen;
const desk = { ...hall, id: "desk", node: "desk", name: "Desk" };
const alisa = { id: "ww_alisa", url: "https://models.example/alisa.json", label: "Алиса", snapshot: "a".repeat(64), model_bytes: 32, feature_step_size: 10 };
const record = (more: Partial<Installed> = {}): Installed => ({ id: voice.id, version: voice.version, source: "index", origin: voice.origin,
  state: "active", build_values: { wake_models: [alisa] }, installed_build_values: { wake_models: [alisa] }, build_confirmed: true, ...more });
const uploaded = { id: "ww_local", upload: "opaque-private-token", label: "Synthetic wake", snapshot: "b".repeat(64), model_bytes: 32, feature_step_size: 10 };
const importRoute = "POST screens/:id/plugins/:plugin/models/:setting/import";
async function chooseFiles(view: VueWrapper, manifestSize = 2, binarySize = 16) {
  const manifest = new File([new Uint8Array(manifestSize)], "synthetic.json", { type: "application/json" });
  const model = new File([new Uint8Array(binarySize)], "synthetic.tflite");
  for (const [selector, file] of [["[data-model-manifest]", manifest], ["[data-model-binary]", model]] as const) {
    const input = view.get(selector);
    Object.defineProperty(input.element, "files", { configurable: true, value: [file] });
    await input.trigger("change");
  }
  return { manifest, model };
}

function setup(have: Installed[] = [], screens: Screen[] = [hall]) {
  const plugins = usePluginsStore();
  useInventoryStore().inventory.screens = screens;
  useInventoryStore().inventory.builds = {};
  useScreenStore().selected = hall.id;
  plugins.index = [voice];
  plugins.installed = { hall: have };
  const api = fakeApi({
    "GET plugins": () => ({ plugins: plugins.index, installed: plugins.installed, secrets: {} }),
    "POST screens/:id/plugins/plan": { error: null, add: [{ id: voice.id, source: "index", auto: false, for: [], flash_kb: 10, permission_hash: "" }] },
    "POST screens/:id/plugins": {},
  });
  return { plugins, api };
}

describe("wake model GUI", () => {
  it("shows an unselected catalogue and requires exactly an explicit first choice before Install", async () => {
    const { plugins, api } = setup();
    const view = mount(PluginDetail, { props: { plugin: voice, screen: hall } });
    await flushPromises();
    expect(view.findAll(".model-catalogue li")).toHaveLength(3);
    expect(view.findAll(".model-desired li")).toHaveLength(0);
    expect(view.get("#plugin-install").attributes("disabled")).toBeDefined();
    await view.get(".model-url input").setValue(alisa.url);
    expect(api.count("POST screens/:id/plugins")).toBe(0);
    expect(plugins.modelsOn(hall, voice, setting)).toEqual([]);
    await view.get("[data-add-url]").trigger("click");
    expect(plugins.modelsOn(hall, voice, setting)).toEqual([{ url: alisa.url }]);
    expect(view.get("#plugin-install").attributes("disabled")).toBeUndefined();
    expect(api.count("POST screens/:id/plugins")).toBe(0);
    await view.get("[data-remove-model]").trigger("click");
    expect(view.get("#plugin-install").attributes("disabled")).toBeDefined();
    await view.get(".model-url input").setValue(alisa.url);
    await view.get("[data-add-url]").trigger("click");
    await view.get("#plugin-install").trigger("click");
    await flushPromises();
    await plugins.installTray();
    expect(api.count("POST screens/:id/plugins")).toBe(1);
    expect(api.asked("POST screens/:id/plugins")[0].body.add[0].build_values).toEqual({ wake_models: [{ url: alisa.url }] });
    expect(api.calls.every((call) => !call.path.includes("models.example"))).toBe(true);
  });

  it("adds catalogue entries only to the draft, blocks duplicate URLs, and cancels without a request", async () => {
    const { plugins, api } = setup([record()]);
    const view = mount(PluginDetail, { props: { plugin: voice, screen: hall } });
    expect(view.get("#plugin-settings-save").attributes("disabled")).toBeDefined();
    await view.get('[data-add-model="jarvis"]').trigger("click");
    expect(view.get('[data-add-model="jarvis"]').attributes("disabled")).toBeDefined();
    expect(view.get("#plugin-settings-save").attributes("disabled")).toBeUndefined();
    await view.get(".model-url input").setValue(setting.catalogue[1].url);
    await view.get("[data-add-url]").trigger("click");
    expect(view.text()).toContain(i18n.global.t("editor.plugins.models.duplicate"));
    expect(plugins.modelsOn(hall, voice, setting)).toHaveLength(2);
    expect(view.get("[data-installed-models]").text()).not.toContain("Hey Jarvis");
    await view.get("[data-cancel-models]").trigger("click");
    expect(plugins.modelsOn(hall, voice, setting)).toEqual([alisa]);
    expect(api.count("POST screens/:id/plugins")).toBe(0);
  });

  it("keeps a rejected desired set editable and distinguishes pending, installed and failed lists", async () => {
    const { plugins, api } = setup([record()]);
    const view = mount(PluginDetail, { props: { plugin: voice, screen: hall } });
    await view.get('[data-add-model="jarvis"]').trigger("click");
    api.on("POST screens/:id/plugins", failure(400, "Private model URL refused"));
    const held = api.defer("POST screens/:id/plugins");
    await view.get("#plugin-settings-save").trigger("click");
    expect(view.get("#plugin-settings-save").text()).toBe(i18n.global.t("editor.plugins.models.saving"));
    expect(view.get("#plugin-settings-save").attributes("disabled")).toBeDefined();
    held.resolve();
    await flushPromises();
    expect(view.text()).toContain("Private model URL refused");
    expect(plugins.modelsOn(hall, voice, setting)).toHaveLength(2);
    plugins.forgetDrafts(hall, voice);
    plugins.installed.hall = [record({ state: "building", build_revision: "desired", installed_build_revision: "previous",
      build_values: { wake_models: [{ id: "jarvis", url: setting.catalogue[1].url, label: "Hey Jarvis" }] } })];
    await flushPromises();
    expect(view.get(".model-desired").text()).toContain("Hey Jarvis");
    expect(view.get("[data-installed-models]").text()).toContain("Алиса");
    plugins.installed.hall = [record({ failed_update: { version: voice.version, reason: "Build failed", build_values: { wake_models: [] } } })];
    await flushPromises();
    expect(view.get("[data-failed-models]").text()).toContain(i18n.global.t("editor.plugins.models.manual_only"));
  });

  it("gates multi-screen choices separately and allows existing manual-only updates", async () => {
    const { plugins } = setup([], [hall, desk]);
    const view = mount(PluginOnScreens, { props: { plugin: voice } });
    await view.get('[data-screen="Hall"]').setValue(true);
    await view.get('[data-screen="Desk"]').setValue(true);
    await flushPromises();
    expect(view.get("#plugin-apply").attributes("disabled")).toBeDefined();
    plugins.setModels(hall, voice, setting, [{ url: alisa.url }]);
    await flushPromises();
    expect(view.get("#plugin-apply").attributes("disabled")).toBeDefined();
    plugins.setModels(desk, voice, setting, [{ url: alisa.url }]);
    await flushPromises();
    expect(view.get("#plugin-apply").attributes("disabled")).toBeUndefined();
    plugins.installed.hall = [record({ build_values: { wake_models: [] }, installed_build_values: { wake_models: [] } })];
    plugins.forgetDrafts(hall, voice);
    expect(plugins.setupReady(voice, [hall])).toBe(true);
  });

  it("does not reuse installed rows for an origin switch", async () => {
    const { plugins } = setup([record({ origin: "github.com/other/models" })]);
    const view = mount(PluginDetail, { props: { plugin: voice, screen: hall } });
    expect(view.get("#plugin-switch").attributes("disabled")).toBeDefined();
    expect(view.findAll(".model-desired li")).toHaveLength(0);
    await view.get('[data-add-model="jarvis"]').trigger("click");
    expect(view.get("#plugin-switch").attributes("disabled")).toBeUndefined();
    expect(plugins.modelsOn(hall, voice, setting)).toEqual([{ id: "jarvis", url: setting.catalogue[1].url }]);
  });

  it("keeps the Home Assistant Wake phrase control immediate and independent of build drafts", async () => {
    const { plugins, api } = setup([record()]);
    api.on("POST screens/:id/plugins/settings", {});
    const view = mount(PluginSettings, { props: { plugin: voice.id } });
    await flushPromises();
    const stream = lastStream()!;
    stream.open();
    stream.send([{ plugin: "voice", name: { en: "Voice" }, rows: [
      { key: "wake_phrase", entity: "select.hall_wake_phrase", kind: "select", label: { en: "Wake phrase" }, available: true,
        value: "Алиса", options: ["Алиса", "Hey Jarvis"] },
    ] }]);
    await flushPromises();
    const choices = view.findAll(".setting-choice button");
    expect(choices).toHaveLength(2);
    await choices[1].trigger("click");
    await flushPromises();
    expect(api.asked("POST screens/:id/plugins/settings")[0].body).toEqual({ entity: "select.hall_wake_phrase", value: "Hey Jarvis" });
    expect(api.count("POST screens/:id/plugins")).toBe(0);
    expect(plugins.setupChanged(hall, voice)).toBe(false);
  });

  it("renders manual-only installed state without defaulting to catalogue entries", () => {
    setup([record({ build_values: { wake_models: [] }, installed_build_values: { wake_models: [] } })]);
    const view = mount(PluginModelList, { props: { plugin: voice, screen: hall, setting } });
    expect(view.find("[data-model-required]").exists()).toBe(false);
    expect(view.findAll(".model-desired li")).toHaveLength(0);
    expect(view.get("[data-installed-models]").text()).toContain(i18n.global.t("editor.plugins.models.manual_only"));
  });

  it("requires both local files and enables first Install only after an accepted upload", async () => {
    const { plugins, api } = setup();
    api.on(importRoute, uploaded);
    const view = mount(PluginDetail, { props: { plugin: voice, screen: hall } });
    await flushPromises();
    expect(view.get("[data-upload-model]").attributes("disabled")).toBeDefined();
    expect(view.get("#plugin-install").attributes("disabled")).toBeDefined();
    await chooseFiles(view);
    expect(view.get("#plugin-install").attributes("disabled")).toBeDefined();
    await view.get("[data-upload-model]").trigger("click");
    await flushPromises();
    expect(view.get("#plugin-install").attributes("disabled")).toBeUndefined();
    expect(plugins.modelsOn(hall, voice, setting)).toEqual([uploaded]);
    expect(api.count("POST screens/:id/plugins")).toBe(0);
    await view.get("[data-remove-model]").trigger("click");
    expect(view.get("#plugin-install").attributes("disabled")).toBeDefined();
    expect(plugins.modelsOn(hall, voice, setting)).toEqual([]);
  });

  it("uploads two files only on request, shows the private label, and applies both source kinds once", async () => {
    const { plugins, api } = setup([record()]);
    api.on(importRoute, uploaded);
    const view = mount(PluginDetail, { props: { plugin: voice, screen: hall } });
    const files = await chooseFiles(view);
    expect(api.count(importRoute)).toBe(0);
    expect(plugins.modelsOn(hall, voice, setting)).toEqual([alisa]);
    const held = api.defer(importRoute);
    await view.get("[data-upload-model]").trigger("click");
    expect(view.get("[data-upload-model]").attributes("disabled")).toBeDefined();
    expect(view.get("[data-upload-model]").text()).toBe(i18n.global.t("editor.plugins.models.uploading"));
    const request = api.asked(importRoute)[0];
    expect(request.query.get("source")).toBe("index");
    expect(request.body).toBeInstanceOf(FormData);
    expect([...request.body.keys()]).toEqual(["manifest", "model"]);
    expect(request.body.get("manifest").name).toBe(files.manifest.name);
    expect(request.body.get("model").size).toBe(files.model.size);
    held.resolve();
    await flushPromises();
    expect(plugins.modelsOn(hall, voice, setting)).toEqual([alisa, uploaded]);
    expect(api.count("POST screens/:id/plugins")).toBe(0);
    expect(view.get(".model-desired").text()).toContain(uploaded.label);
    expect(view.get(".model-desired").text()).toContain(i18n.global.t("editor.plugins.models.uploaded"));
    expect(view.text()).not.toContain(uploaded.upload);
    expect(view.text()).not.toContain(uploaded.snapshot);
    expect(view.text()).not.toContain("undefined");
    expect(view.get("[data-upload-model]").attributes("disabled")).toBeDefined();
    expect(view.get("[data-installed-models]").text()).not.toContain(uploaded.label);
    await view.get("#plugin-settings-save").trigger("click");
    await flushPromises();
    expect(api.count("POST screens/:id/plugins")).toBe(1);
    expect(api.asked("POST screens/:id/plugins")[0].body.add[0].build_values).toEqual({
      wake_models: [{ id: alisa.id, url: alisa.url }, { id: uploaded.id, upload: uploaded.upload }],
    });
  });

  it("keeps files and model drafts after import errors and rejects a repeated imported pair", async () => {
    const { plugins, api } = setup([record()]);
    api.on(importRoute, failure(400, "Incompatible feature step"));
    const view = mount(PluginModelList, { props: { plugin: voice, screen: hall, setting } });
    await chooseFiles(view);
    await view.get("[data-upload-model]").trigger("click");
    await flushPromises();
    expect(view.get("[data-upload-error]").text()).toBe("Incompatible feature step");
    expect(view.get("[data-upload-model]").attributes("disabled")).toBeUndefined();
    expect(plugins.modelsOn(hall, voice, setting)).toEqual([alisa]);
    api.on(importRoute, uploaded);
    await view.get("[data-upload-model]").trigger("click");
    await flushPromises();
    await chooseFiles(view);
    await view.get("[data-upload-model]").trigger("click");
    await flushPromises();
    expect(view.get("[data-upload-error]").text()).toBe(i18n.global.t("editor.plugins.models.duplicate"));
    expect(plugins.modelsOn(hall, voice, setting)).toEqual([alisa, uploaded]);
    expect(view.get("[data-upload-model]").attributes("disabled")).toBeUndefined();
    await view.get(`[data-remove-model="${uploaded.id}"]`).trigger("click");
    expect(plugins.modelsOn(hall, voice, setting)).toEqual([alisa]);
    expect(plugins.setupChanged(hall, voice)).toBe(false);
    expect(api.count("POST screens/:id/plugins")).toBe(0);
  });

  it.each([[65537, 16], [2, 2097153]])("refuses oversized files before upload (%i, %i)", async (jsonSize, modelSize) => {
    const { api } = setup();
    const view = mount(PluginModelList, { props: { plugin: voice, screen: hall, setting } });
    await chooseFiles(view, jsonSize, modelSize);
    expect(view.get("[data-upload-error]").text()).toBe(i18n.global.t("editor.plugins.models.upload_size"));
    expect(view.get("[data-upload-model]").attributes("disabled")).toBeDefined();
    expect(api.count(importRoute)).toBe(0);
  });

  it("accepts exact file limits, but not a seventeenth model", async () => {
    const { plugins, api } = setup();
    api.on(importRoute, uploaded);
    const view = mount(PluginModelList, { props: { plugin: voice, screen: hall, setting } });
    await chooseFiles(view, 65536, 2097152);
    expect(view.find("[data-upload-error]").exists()).toBe(false);
    await view.get("[data-upload-model]").trigger("click");
    await flushPromises();
    expect(plugins.modelsOn(hall, voice, setting)).toEqual([uploaded]);
    plugins.setModels(hall, voice, setting, Array.from({ length: 16 }, (_, i) => ({ url: `https://models.example/${i}.json` })));
    await chooseFiles(view);
    expect(view.get("[data-upload-model]").attributes("disabled")).toBeDefined();
    expect(api.count(importRoute)).toBe(1);
  });

  it.each(["remove", "cancel", "unmount"])("does not resurrect a draft after %s during import", async (action) => {
    const { plugins, api } = setup([record()]);
    api.on(importRoute, uploaded);
    const held = api.defer(importRoute);
    const view = mount(PluginModelList, { props: { plugin: voice, screen: hall, setting } });
    await chooseFiles(view);
    await view.get("[data-upload-model]").trigger("click");
    if (action === "remove") await view.get("[data-remove-model]").trigger("click");
    else if (action === "cancel") await view.get("[data-cancel-models]").trigger("click");
    else view.unmount();
    held.resolve();
    await flushPromises();
    expect(plugins.modelsOn(hall, voice, setting)).toEqual(action === "remove" ? [] : [alisa]);
    expect(api.count("POST screens/:id/plugins")).toBe(0);
    if (action === "remove") expect(view.get("[data-upload-error]").text()).toBe(i18n.global.t("editor.plugins.models.upload_changed"));
  });
});

describe("installed plugin dependency and recovery controls", () => {
  it("shows a failed-switch Retry only for the failed origin and confirms that source before submitting", async () => {
    const fork = { ...voice, origin: "github.com/fork/models", source: "branch" as const };
    const { plugins, api } = setup([record({ failed_update: {
      version: fork.version, origin: fork.origin, build_values: { wake_models: [{ ...alisa, id: "ww_fork_alisa" }] },
    } })]);
    const view = mount(PluginDetail, { props: { plugin: voice, screen: hall } });
    expect(view.find("#plugin-retry").exists()).toBe(false);
    expect(view.find("[data-failed-models]").exists()).toBe(false);
    await view.setProps({ plugin: fork });
    expect(view.find("#plugin-retry").exists()).toBe(true);
    await view.get("#plugin-retry").trigger("click");
    expect(question.value?.kind).toBe("confirm");
    expect(plugins.modelsOn(hall, fork, setting)[0].id).toBe("ww_fork_alisa");
    expect(api.count("POST screens/:id/plugins")).toBe(0);
    answer(false);
    await flushPromises();
    expect(api.count("POST screens/:id/plugins")).toBe(0);
    await view.get("#plugin-retry").trigger("click");
    answer(true);
    await flushPromises();
    expect(api.count("POST screens/:id/plugins")).toBe(1);
    expect(api.asked("POST screens/:id/plugins")[0].body.add[0]).toMatchObject({
      source: "branch", switch: true, build_values: { wake_models: [{ id: "ww_fork_alisa", url: alisa.url }] },
    });
  });

  it.each(["update", "switch"] as const)("exposes and submits a new model dependency during an installed plugin %s", async (mode) => {
    const main: Plugin = { ...voice, id: "main", name: { en: "Main" }, version: "1.1.0", origin: "github.com/maker/main",
      requires: { plugins: ["voice"] }, build_settings: [] };
    const { plugins, api } = setup([{ id: main.id, version: "1.0.0", source: "index", state: "active",
      origin: mode === "switch" ? "github.com/old/main" : main.origin }]);
    plugins.index = [main, voice];
    api.on("POST screens/:id/plugins/plan", { error: null, add: [
      { id: main.id, source: "index", auto: false, for: [], flash_kb: 10, permission_hash: "" },
      { id: voice.id, source: "index", auto: true, for: [main.id], flash_kb: 10, permission_hash: "" },
    ] });
    const view = mount(PluginDetail, { props: { plugin: main, screen: hall } });
    await flushPromises();
    const action = mode === "switch" ? "#plugin-switch" : "#plugin-update";
    expect(view.find("[data-model-setting]").exists()).toBe(true);
    expect(view.get(action).attributes("disabled")).toBeDefined();
    await view.get(".model-url input").setValue(alisa.url);
    await view.get("[data-add-url]").trigger("click");
    expect(view.get(action).attributes("disabled")).toBeUndefined();
    expect(api.count("POST screens/:id/plugins")).toBe(0);
    await view.get(action).trigger("click");
    await flushPromises();
    expect(api.count("POST screens/:id/plugins")).toBe(1);
    const additions = api.asked("POST screens/:id/plugins")[0].body.add;
    expect(Boolean(additions[0].switch)).toBe(mode === "switch");
    expect(additions[1]).toMatchObject({ id: voice.id, auto: true, build_values: { wake_models: [{ url: alisa.url }] } });
  });

  it("offers dependency model choices before Update all on this screen", async () => {
    const main: Plugin = { ...voice, id: "main", version: "1.1.0", requires: { plugins: ["voice"] }, build_settings: [] };
    const { plugins, api } = setup([{ id: main.id, version: "1.0.0", source: "index", state: "active", origin: main.origin }]);
    plugins.index = [main, voice];
    plugins.loaded = true;
    api.on("POST screens/:id/plugins/plan", { error: null, add: [
      { id: main.id, source: "index", auto: false, for: [], flash_kb: 10, permission_hash: "" },
      { id: voice.id, source: "index", auto: true, for: [main.id], flash_kb: 10, permission_hash: "" },
    ] });
    const view = mount(ScreenPluginsTab);
    await flushPromises();
    expect(view.get("#screen-plugin-update-all").attributes("disabled")).toBeDefined();
    await view.get(".model-url input").setValue(alisa.url);
    await view.get("[data-add-url]").trigger("click");
    expect(view.get("#screen-plugin-update-all").attributes("disabled")).toBeUndefined();
    await view.get("#screen-plugin-update-all").trigger("click");
    await flushPromises();
    expect(api.asked("POST screens/:id/plugins")[0].body.add[1]).toMatchObject({
      id: voice.id, auto: true, build_values: { wake_models: [{ url: alisa.url }] },
    });
  });

  it("loads isolated recovery diagnostics and permits unchanged Apply to repair only that screen", async () => {
    const { plugins, api } = setup([record()], [hall, desk]);
    api.on("GET plugins", () => ({ plugins: plugins.index, installed: plugins.installed, secrets: {},
      recovery: { hall: { file: "hall.yaml", reason: "Resolve the model ownership conflict, then Apply again." } } }));
    await plugins.reloadPlugins();
    const view = mount(PluginDetail, { props: { plugin: voice, screen: hall } });
    expect(plugins.setupChanged(hall, voice)).toBe(false);
    expect(view.get("[data-plugin-recovery]").text()).toContain("hall.yaml");
    expect(view.get("#plugin-settings-save").attributes("disabled")).toBeUndefined();
    expect(plugins.recovery.desk).toBeUndefined();
    api.on("GET plugins", () => ({ plugins: plugins.index, installed: plugins.installed, secrets: {} }));
    await view.get("#plugin-settings-save").trigger("click");
    await flushPromises();
    expect(api.asked("POST screens/:id/plugins")[0].body.add[0].build_values).toEqual({
      wake_models: [{ id: alisa.id, url: alisa.url }],
    });
    expect(view.find("[data-plugin-recovery]").exists()).toBe(false);
  });
});
