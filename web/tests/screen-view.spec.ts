// One screen's head (ScreenView): importing a layout from a file through the browser's file chooser (useFileDialog),
// past the editor's question when something is unsaved, and renaming on a phone through the editor's own field. The
// menu items call these; opening reka's menu itself takes jsdom far too long, so the tests call what the items call.
import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ScreenView from "../src/components/ScreenView.vue";
import type { Inventory, Screen } from "../src/types";
import { answerDialogs } from "./helpers/dialogs";
import { fakeApi } from "./helpers/fake-api";
import { screenFixture } from "./helpers/fixtures";
import { useSessionStore } from "../src/stores/session";
import { useInventoryStore } from "../src/stores/inventory";
import { setTileOption } from "../src/editor/tiles";
import { useDocumentStore } from "../src/stores/document";
import { useInspectorStore } from "../src/stores/inspector";
import { forgetCopied } from "../src/editor/clipboard";

let doc: ReturnType<typeof useDocumentStore>;
beforeEach(() => { doc = useDocumentStore(); });

beforeEach(() => {
  useInventoryStore().inventory = { csrf: "t", connected: true, entities: [], icons: { groups: [], weather: {}, sun: {}, defaults: {}, fallback: "F0335", builtin: {}, controls: {} },
    screens: [screenFixture({ id: "hall", name: "Hall", firmware: "0.4.0", online: true, in_sync: true,
      layout: { title: "Hall", tiles: [{ entity: "light.a", name: "A", slot: 0 }] } } as unknown as Screen)] } as unknown as Inventory;
  useSessionStore().select("hall");
});
type Head = { pickFile: () => void; phoneRename: () => Promise<void> };

describe("a screen's head", () => {
  it("imports a chosen file, after asking when something is unsaved, and imports nothing when told no", async () => {
    const api = fakeApi({ "POST screens/:id/import": () => useInventoryStore().inventory.screens[0].page_document });
    // The spy keeps what it was called on: the input the head clicked.
    const click = vi.spyOn(HTMLInputElement.prototype, "click").mockImplementation(() => {});
    const view = mount(ScreenView, { attachTo: document.body });
    setTileOption(doc.layout!.tiles[0], "icon", "lightbulb");
    let yes = false;
    const asked = answerDialogs(() => yes);
    const choose = async () => {
      (view.vm as unknown as Head).pickFile();
      const chooser = click.mock.contexts.at(-1) as HTMLInputElement | undefined;
      expect([chooser?.type, chooser?.accept, chooser?.multiple]).toEqual(["file", "application/json,.json", false]);
      // jsdom's File has no text(): the one a browser's chooser hands over does.
      const json = JSON.stringify({ esp_screens_layout: 2, sourceGrid: doc.documentGrid, layout: doc.document });
      const file = Object.assign(new File([json], "hall.layout.json"), { text: async () => json });
      Object.defineProperty(chooser!, "files", { configurable: true, value: [file] });
      chooser!.dispatchEvent(new Event("change"));
      await flushPromises();
    };
    await choose();
    expect(asked).toEqual([{ kind: "confirm", message: "Replace the unsaved layout with the imported one?", confirm: "Replace layout", danger: true }]);
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
    expect(asked).toEqual([{ kind: "prompt", message: "Name in this app", value: "Hall", confirm: "Rename" }]);
    expect(api.asked("PUT screens/:id/name")[0].body).toEqual({ name: "Living room" });
    expect(useInventoryStore().inventory.screens[0].name).toBe("Living room");
  });
});

// ⌘A, ⌘C, ⌘V and Delete on the layout (app 0.4.x): the page's tiles chosen, copied, pasted beside them and removed
// together; in a field the keys stay the field's.
describe("the layout's keys", () => {
  const key = (key: string, target: Element = document.body, meta = true) => {
    const event = new KeyboardEvent("keydown", { key, metaKey: meta, bubbles: true, cancelable: true });
    target.dispatchEvent(event);
    return event;
  };
  it("chooses, copies, pastes and removes tiles", async () => {
    fakeApi({ states: { states: {} }, capabilities: { capabilities: {} } });
    // A screen that takes an entity on several tiles (firmware 0.16.0+); an older one leaves the copy out.
    useInventoryStore().inventory.screens[0].firmware = "0.56.0";
    const view = mount(ScreenView, { attachTo: document.body });
    forgetCopied();
    const insp = useInspectorStore();
    expect(key("a").defaultPrevented).toBe(true);
    expect(insp.chosenTiles.map((tile) => tile.entity)).toEqual(["light.a"]);
    key("c");
    key("v");
    await flushPromises();
    expect(doc.layout!.tiles.map((tile) => [tile.entity, tile.slot])).toEqual([["light.a", 0], ["light.a", 1]]);
    key("a");
    expect(insp.inspector).toEqual({ kind: "tiles" });
    key("Backspace", document.body, false);
    expect(doc.layout!.tiles).toEqual([]);
    // A field keeps its own keys.
    doc.undo();
    const field = document.createElement("input");
    document.body.append(field);
    expect(key("a", field).defaultPrevented).toBe(false);
    view.unmount();
  });
});
