// One screen's head (ScreenView): importing a layout from a file through the browser's file chooser (useFileDialog),
// past the editor's question when something is unsaved, and renaming on a phone through the editor's own field. The
// menu items call these; opening reka's menu itself takes jsdom far too long, so the tests call what the items call.
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ScreenView from "../src/components/ScreenView.vue";
import { select, setTileOption, state } from "../src/store";
import type { Inventory, Screen } from "../src/types";
import { answerDialogs } from "./helpers/dialogs";
import { fakeApi } from "./helpers/fake-api";
import { screenFixture } from "./page-fixtures";

beforeEach(() => {
  state.inventory = { csrf: "t", connected: true, entities: [], icons: { groups: [], weather: {}, sun: {}, defaults: {}, fallback: "F0335", builtin: {}, controls: {} },
    screens: [screenFixture({ id: "hall", name: "Hall", firmware: "0.4.0", online: true, in_sync: true,
      layout: { title: "Hall", tiles: [{ entity: "light.a", name: "A", slot: 0 }] } } as unknown as Screen)] } as unknown as Inventory;
  select("hall");
});
type Head = { pickFile: () => void; phoneRename: () => Promise<void> };

describe("a screen's head", () => {
  it("imports a chosen file, after asking when something is unsaved, and imports nothing when told no", async () => {
    const api = fakeApi({ "POST screens/:id/import": () => state.inventory.screens[0].page_document });
    let chooser: HTMLInputElement | null = null;
    vi.spyOn(HTMLInputElement.prototype, "click").mockImplementation(function (this: HTMLInputElement) { chooser = this; });
    const view = mount(ScreenView, { attachTo: document.body });
    setTileOption(state.layout!.tiles[0], "icon", "lightbulb");
    let yes = false;
    const asked = answerDialogs(() => yes);
    const choose = async () => {
      (view.vm as unknown as Head).pickFile();
      expect([chooser?.type, chooser?.accept, chooser?.multiple]).toEqual(["file", "application/json,.json", false]);
      // jsdom's File has no text(): the one a browser's chooser hands over does.
      const json = JSON.stringify({ esp_screens_layout: 2, sourceGrid: state.documentGrid, layout: state.document });
      const file = Object.assign(new File([json], "hall.layout.json"), { text: async () => json });
      Object.defineProperty(chooser!, "files", { configurable: true, value: [file] });
      chooser!.dispatchEvent(new Event("change"));
      await flushPromises();
    };
    await choose();
    expect(asked.map((question) => question.message)).toEqual(["Replace the unsaved layout with the imported one?"]);
    expect(api.count("POST screens/:id/import")).toBe(0);
    yes = true;
    await choose();
    expect(api.asked("POST screens/:id/import").map((call) => call.params.id)).toEqual(["hall"]);
  });

  it("renames the screen on a phone in the editor's own field", async () => {
    const api = fakeApi({ "PUT screens/:id/name": ({ body }) => ({ name: body.name }) });
    const asked = answerDialogs((question) => (question.kind === "prompt" ? "  Living room " : false));
    const view = mount(ScreenView, { attachTo: document.body });
    await (view.vm as unknown as Head).phoneRename();
    await flushPromises();
    expect(asked).toEqual([{ kind: "prompt", message: "Name in this app", value: "Hall" }]);
    expect(api.asked("PUT screens/:id/name")[0].body).toEqual({ name: "Living room" });
    expect(state.inventory.screens[0].name).toBe("Living room");
  });
});
