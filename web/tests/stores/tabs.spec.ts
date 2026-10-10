// A second tab knows (stores/drafts.ts): tabs of one browser that edit the same screen hear of each other over a
// BroadcastChannel before anyone saves. The tab whose change is older says so, with Take over here (the other draft
// becomes this one, one step of undo) and Keep mine; a tab that closes, saves or opens another screen stops counting,
// and a tab shown again asks who is still there.
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import LayoutView from "../../src/components/LayoutView.vue";
import { setTileName } from "../../src/editor/tiles";
import { keptKey, writeKept } from "../../src/model/kept-draft";
import { clone } from "../../src/model/pages";
import { useDocumentStore } from "../../src/stores/document";
import { useDraftsStore } from "../../src/stores/drafts";
import { useInventoryStore } from "../../src/stores/inventory";
import { useSessionStore } from "../../src/stores/session";
import type { Inventory, PageLayout, Screen } from "../../src/types";
import { FakeBroadcastChannel, setHidden } from "../helpers/browser";
import { fakeApi } from "../helpers/fake-api";
import { screenFixture } from "../helpers/fixtures";

const screen = (id: string) => screenFixture({ id, name: id, online: true, firmware: "0.53.0",
  layout: { title: id, tiles: [{ entity: "light.a", name: "Lamp", slot: 0 }] } } as unknown as Screen);
function page() {
  fakeApi({ states: { states: {} }, capabilities: { capabilities: {} }, "POST header-preview": { items: [] } });
  useInventoryStore().inventory = { connected: true, entities: [], screens: [screen("hall"), screen("desk")] } as unknown as Inventory;
  const drafts = useDraftsStore(), stop = drafts.start();
  useSessionStore().select("hall");
  return { doc: useDocumentStore(), drafts, stop };
}
// Another tab of the same browser, as the channel carries it: what it says and what it hears.
function otherTab(id = "other-tab") {
  const channel = new FakeBroadcastChannel("esp-screens.editor"), heard: any[] = [];
  channel.onmessage = (event) => heard.push(event.data);
  const say = async (message: object) => { channel.postMessage({ tab: id, ...message }); await flushPromises(); };
  return { heard, say, editing: (at: number, screen = "hall") => say({ type: "state", screen, dirty: true, at }) };
}
const lamp = () => useDocumentStore().layout!.tiles[0];

describe("another tab editing the same screen", () => {
  it("is said before anyone saves, and its draft taken over here as one step of undo", async () => {
    const { doc, drafts } = page();
    const other = otherTab();
    await other.editing(Date.now());
    expect(drafts.elsewhere?.tab).toBe("other-tab");
    const view = mount(LayoutView, { attachTo: document.body });
    await nextTick();
    expect(view.find("#other-tab .notice-text").text()).toBe("This screen is being edited in another tabIts changes are not saved yet.");
    // Take over here asks the other tab for its draft, and its answer becomes the draft.
    await view.find("#take-over").trigger("click");
    await flushPromises();
    const want = other.heard.find((message) => message.type === "want");
    expect(want).toMatchObject({ to: "other-tab", screen: "hall", tab: drafts.tab });
    const theirs: PageLayout = clone(doc.document!);
    theirs.pages[0].tiles[0].appearance.label = "Their lamp";
    await other.say({ type: "draft", to: drafts.tab, screen: "hall", draft: { layout: theirs, grid: { columns: 2, rows: 3 }, upright: null, revision: doc.documentRevision } });
    await nextTick();
    expect([lamp().name, doc.dirty, doc.conflict, doc.undoWhat, drafts.elsewhere]).toEqual(["Their lamp", true, false, "changes from the other tab taken over", null]);
    expect(view.find("#other-tab").exists()).toBe(false);
    // This tab's change is now the newest, as the other tab hears.
    expect(other.heard.at(-1)).toMatchObject({ type: "state", screen: "hall", dirty: true, at: doc.editedAt });
  });

  it("is quiet when this tab changed something since, and after Keep mine until the other saves", async () => {
    vi.useFakeTimers({ now: 1000, toFake: ["Date"] });
    const { drafts } = page();
    const other = otherTab();
    await other.editing(1000);
    vi.setSystemTime(2000);
    setTileName(lamp(), "Mine");
    expect(drafts.elsewhere).toBeNull();
    await other.editing(3000);
    expect(drafts.elsewhere?.at).toBe(3000);
    drafts.keepMine();
    await other.editing(4000);
    expect(drafts.elsewhere).toBeNull();
    // Saved there: no longer unsaved, and a new change counts again.
    await other.say({ type: "state", screen: "hall", dirty: false, at: 0 });
    await other.editing(5000);
    expect(drafts.elsewhere?.at).toBe(5000);
  });

  it("stops counting when that tab closes or opens another screen, and a tab shown again asks who is there", async () => {
    const { drafts, stop } = page();
    const other = otherTab();
    await other.editing(Date.now());
    await other.say({ type: "bye" });
    expect(drafts.elsewhere).toBeNull();
    await other.editing(Date.now(), "desk");
    expect(drafts.elsewhere).toBeNull();
    await other.editing(Date.now());
    other.heard.length = 0;
    setHidden(true);
    setHidden(false);
    await flushPromises();
    // Shown again: who is still there answers; one that crashed never does.
    expect(drafts.elsewhere).toBeNull();
    expect(other.heard.map((message) => message.type)).toEqual(["hello", "state"]);
    // Closing says goodbye.
    stop();
    await flushPromises();
    expect(other.heard.at(-1)).toMatchObject({ type: "bye", tab: drafts.tab });
  });

  it("tells a new tab what it edits, and hands its draft to the tab that asks", async () => {
    const { doc, drafts } = page();
    setTileName(lamp(), "Mine");
    await flushPromises();
    const other = otherTab();
    await other.say({ type: "hello" });
    expect(other.heard).toEqual([{ type: "state", tab: drafts.tab, screen: "hall", dirty: true, at: doc.editedAt }]);
    await other.say({ type: "want", to: drafts.tab, screen: "hall" });
    expect(other.heard.at(-1)).toMatchObject({ type: "draft", to: "other-tab", screen: "hall", draft: { layout: doc.document, revision: doc.documentRevision } });
  });

  it("leaves the draft another open tab keeps to that tab's bar, and offers it once that tab closed", async () => {
    const { doc, drafts } = page();
    const other = otherTab();
    await other.editing(Date.now());
    const theirs = clone(doc.document!);
    theirs.title = "Theirs";
    localStorage.setItem(keptKey("hall"), writeKept({ v: 1, tab: "other-tab", revision: doc.documentRevision, at: Date.now(), layout: theirs, grid: { columns: 2, rows: 3 }, upright: null }));
    drafts.opened();
    expect([drafts.offer, drafts.elsewhere?.tab]).toEqual([null, "other-tab"]);
    await other.say({ type: "bye" });
    expect([drafts.offer?.layout.title, drafts.elsewhere]).toEqual(["Theirs", null]);
  });
});
