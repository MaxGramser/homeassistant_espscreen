// Builds seen everywhere (BuildIndicator, ui/ProgressRing, the sidebar's rows and the overview's cards): a ring per
// screen that builds, one in the head while anything does, with each screen's step in its list.
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import BuildIndicator from "../src/components/BuildIndicator.vue";
import BuildList from "../src/components/BuildList.vue";
import HomeView from "../src/components/HomeView.vue";
import Sidebar from "../src/components/Sidebar.vue";
import ProgressRing from "../src/components/ui/ProgressRing.vue";
import { t } from "../src/i18n";
import { useInventoryStore } from "../src/stores/inventory";
import { useScreenStore } from "../src/stores/screen";
import type { Screen } from "../src/types";
import { screenFixture } from "./helpers/fixtures";

const screen = (id: string, name: string) => screenFixture({ id, name, online: true, firmware: "0.53.0", layout: { title: name, tiles: [] } } as unknown as Screen);
beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new Error("offline"))));
  useInventoryStore().inventory = { connected: true, screens: [screen("living", "Living room"), screen("hall", "Hall"), screen("desk", "Desk")], entities: [],
    builds: { living: { by: "update", state: "running", phase: "install", stage: "compile", file: "living.yaml" }, hall: { by: "plugins", state: "queued", file: "hall.yaml" } } } as any;
  useScreenStore().selected = null;
});

describe("a build's ring", () => {
  it("fills as the build goes, waits empty, and turns without a number", () => {
    const ring = (percent: number | null) => mount(ProgressRing, { props: { percent, label: "Living room" } });
    expect(ring(40).attributes()).toMatchObject({ role: "progressbar", "aria-valuenow": "40", "aria-label": "Living room" });
    const length = 2 * Math.PI * 6;
    expect(Number(ring(40).find(".ring-arc").attributes("stroke-dashoffset"))).toBeCloseTo(length * 0.6);
    expect(ring(0).classes()).toContain("ring-waiting");
    expect(ring(null).classes()).toContain("ring-turning");
    expect(ring(null).attributes("aria-valuenow")).toBeUndefined();
  });
});

describe("the builds in the head", () => {
  it("shows nothing while nothing builds", () => {
    useInventoryStore().inventory.builds = {};
    expect(mount(BuildIndicator).find("#builds").exists()).toBe(false);
  });

  it("is one ring for every build together, their count beside it", () => {
    const button = mount(BuildIndicator).find("#builds");
    expect(button.attributes("aria-label")).toBe(t("editor.build.count", 2));
    expect(button.find(".builds-count").text()).toBe("2");
    // The running one is at 40 %, the waiting one at nothing yet: 20 % together.
    expect(button.find(".ring").attributes("aria-valuenow")).toBe("20");
  });

  it("lists each screen's step, running first; a row opens its screen and the last row the log", async () => {
    const list = mount(BuildList);
    const rows = list.findAll(".builds-row");
    expect(rows.map((row) => row.find("strong").text())).toEqual(["Living room", "Hall"]);
    expect(rows[0].find(".builds-name small").text()).toBe(t("editor.update.building"));
    expect(rows[0].find(".builds-percent").text()).toBe("40 %");
    expect(rows[1].find(".builds-name small").text()).toBe(t("editor.build.waiting"));
    expect(rows[1].find(".builds-percent").text()).toBe("");
    await rows[0].trigger("click");
    await flushPromises();
    expect(useScreenStore().selected).toBe("living");
    await list.find(".builds-log").trigger("click");
    expect(location.hash).toBe("#firmware");
    expect(list.emitted("done")).toHaveLength(2);
  });

  it("names the one screen that builds", () => {
    useInventoryStore().inventory.builds = { living: { by: "update", state: "running", phase: "verify" } };
    const button = mount(BuildIndicator).find("#builds");
    expect(button.attributes("aria-label")).toBe(`Living room · ${t("editor.update.phases.verify")}`);
    expect(button.find(".builds-count").exists()).toBe(false);
  });
});

describe("a ring per screen", () => {
  it("stands on the sidebar's row of a screen that builds", () => {
    const rows = mount(Sidebar).findAll("#screens .screen-item");
    expect(rows[0].find(".row-ring").attributes("aria-valuenow")).toBe("40");
    expect(rows[0].find(".spin").exists()).toBe(false);
    expect(rows[2].find(".row-ring").exists()).toBe(false);
  });

  it("stands where an overview card's light is, its step under the name", () => {
    const cards = mount(HomeView).findAll(".home-card");
    expect(cards[0].find(".home-ring").attributes("aria-valuenow")).toBe("40");
    expect(cards[0].find(".led").exists()).toBe(false);
    expect(cards[0].find(".home-name small").text()).toBe(`40 % · ${t("editor.update.building")}`);
    expect(cards[1].find(".home-ring").attributes("aria-valuenow")).toBe("0");
    expect(cards[1].find(".home-name small").text()).toBe(t("editor.build.waiting"));
    expect(cards[2].find(".home-ring").exists()).toBe(false);
    expect(cards[2].find(".led").exists()).toBe(true);
  });
});
