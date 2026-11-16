// The Alerts page (AlertsView, a part of Events): the cheatsheet for writing an alert by hand, built from what the add-on
// says of alerts. It is mounted with the add-on's own reference, tests/fixtures/alert-reference.json, which
// tests/test_alerts_reference.py keeps equal to core.alert_reference() and to the firmware it describes. Took the place of
// tests that looked for ids and lines in the editor's source (docs/TESTING.md, "A test reads behaviour, not lines").
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import reference from "../../tests/fixtures/alert-reference.json";
import AlertsView from "../src/components/AlertsView.vue";
import EventsView from "../src/components/EventsView.vue";
import Sidebar from "../src/components/Sidebar.vue";
import { t } from "../src/i18n";
import { useInventoryStore } from "../src/stores/inventory";
import { useUiStore } from "../src/stores/ui";

const texts = (page: ReturnType<typeof mount>, selector: string) => page.findAll(selector).map((node) => node.text());

beforeEach(() => {
  const inv = useInventoryStore().inventory as any;
  inv.alerts = structuredClone(reference);
  inv.screens = [
    { id: "text.hall_tiles", name: "Hall", online: true, firmware: "0.4.0", board: "guition", node: "hall", area: "Hallway",
      pictures: true, layout: { title: "Hall", tiles: [] }, alert_action: "esphome.hall_show_alert", dismiss_action: "esphome.hall_dismiss_alert" },
    { id: "text.old_tiles", name: "Old screen", online: true, firmware: "", board: "cyd", layout: { title: "Old", tiles: [] },
      alert_action: null, dismiss_action: null },
  ];
  inv.icons = { ...(inv.icons || {}), groups: [{ label: "Doors", icons: [{ name: "doorbell", cp: "F12E6" }] }] };
});

function clipboard() {
  const write = vi.fn(() => Promise.resolve());
  vi.stubGlobal("navigator", { clipboard: { writeText: write } });
  vi.stubGlobal("isSecureContext", true);
  return write;
}

describe("the Alerts page", () => {
  it("is a part of Events, which the sidebar opens and its Back closes", async () => {
    const ui = useUiStore();
    await mount(Sidebar).find("#open-events").trigger("click");
    await flushPromises();
    expect(ui.route).toBe("#events");
    const events = mount(EventsView);
    expect(events.find("#alerts-dialog").exists()).toBe(true);
    await events.find("#close-events").trigger("click");
    await flushPromises();
    expect(ui.route).toBe("");
  });

  it("has every section its bar names", () => {
    const page = mount(AlertsView);
    const jumps = page.findAll("[data-jump]").map((button) => button.attributes("data-jump")!);
    expect(jumps).toContain("alerts-all");
    expect(jumps).toContain("alerts-one");
    for (const id of jumps) expect(page.find(`#${id}`).exists(), id).toBe(true);
    expect(page.find("[data-jump='alerts-all']").text()).toBe("All screens");
    expect(page.find("[data-jump='alerts-one']").text()).toBe("One screen");
  });

  it("gives each screen its actions to copy, and an example for the first that has them", async () => {
    const page = mount(AlertsView);
    const write = clipboard();
    const hall = page.findAll("#alerts-screen-list .alert-screen")[0];
    expect(hall.text()).toContain("esphome.hall_show_alert");
    expect(hall.text()).toContain("esphome.hall_dismiss_alert");
    await hall.find(".copy-line button").trigger("click");
    expect(write).toHaveBeenCalledWith("esphome.hall_show_alert");
    expect(page.find("#alerts-example").text()).toMatch(/^action: esphome\.hall_show_alert\ndata:\n {2}title: /);
  });

  it("lists every field, colour and icon of the reference", () => {
    const page = mount(AlertsView);
    const fields = page.findAll("#alerts-field-table td:first-child code").map((code) => code.text());
    expect(fields).toEqual([...reference.fields.map((f) => f.name), ...reference.choice.fields.map((f) => f.name),
      reference.choice.action2.name, reference.camera.name, reference.screen.name]);
    expect(texts(page, "#alerts-swatches code")).toEqual(["empty", ...reference.colors.map((c) => c.name)]);
    expect(texts(page, "#alerts-suggested code")).toEqual(reference.suggested_icons.map((i) => i.name));
    // The screens' icons, and the few more an alert takes, each a key that copies its name.
    const groups = page.findAll("#alerts-icon-groups .alert-icon-grid");
    expect(groups.length).toBe(2);
    expect(texts(page, "#alerts-icon-groups .subhead")).toEqual(["Doors · 1", `${t("editor.alerts.icons.extra")} · ${reference.extra_icons.length}`]);
    expect(groups[1].findAll("code").map((code) => code.text())).toEqual(reference.extra_icons.map((i) => i.name));
  });

  it("explains the event for every screen, and copies its YAML", async () => {
    const page = mount(AlertsView);
    const write = clipboard();
    expect(page.find("#alerts-all-event").text()).toBe(reference.broadcast.show);
    expect(page.find("#alerts-all-dismiss").text()).toBe(reference.broadcast.dismiss);
    const yaml = page.find("#alerts-all-example").text();
    expect(yaml.startsWith(`event: ${reference.broadcast.show}\n`)).toBe(true);
    await page.find("#alerts-all-copy").trigger("click");
    expect(write).toHaveBeenCalledWith(yaml);
    // One screen through the same event: what goes after `screen:` for each, and its example.
    expect(page.find("#alerts-one-example").text()).toContain("screen: hall");
    expect(page.find("#alerts-tips").text()).toContain("Settings → Claude");
  });
});
