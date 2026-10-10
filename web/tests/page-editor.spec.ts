import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { readFileSync } from "node:fs";
import { mount } from "@vue/test-utils";
import PageWizard from "../src/components/PageWizard.vue";
import LayoutView from "../src/components/LayoutView.vue";
import NavigationPreview from '../src/components/NavigationPreview.vue';
import PageInspector from '../src/components/PageInspector.vue';
import TopbarInspector from '../src/components/TopbarInspector.vue';
import { documentFixture, screenFixture } from "./helpers/fixtures";
import { answerDialogs } from "./helpers/dialogs";
import { setMedia } from "./helpers/browser";
import type { PageDocument, Screen } from "../src/types";
import { useUiStore } from "../src/stores/ui";
import { useScreenStore } from "../src/stores/screen";
import { useSessionStore } from "../src/stores/session";
import { useTopbarStore } from "../src/stores/topbar";
import { useInventoryStore } from "../src/stores/inventory";
import { placeTile, removeTile, addTile } from "../src/editor/tiles";
import { addPage, movePage, addPage, connectTile, movePage, setHomePage, setPageExcluded, setPageTitle } from "../src/editor/pages";
import { useDocumentStore } from "../src/stores/document";

let doc: ReturnType<typeof useDocumentStore>;
beforeEach(() => { doc = useDocumentStore(); });

const record = () => useInventoryStore().inventory.screens[0].page_document as PageDocument;
const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
beforeEach(() => {
  vi.useFakeTimers();
  answerDialogs(true);
  const preferences = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (key: string) => preferences.get(key) ?? null, setItem: (key: string, value: string) => preferences.set(key, value) });
  useInventoryStore().inventory = { connected: true, screens: [screenFixture({ id: "test", name: "Test", firmware: "0.3.0", online: true,
    board: "guition", shape: { columns: 2, rows: 3, width: 480, height: 480 },
    layout: { title: "Home", pages: 2, tiles: [{ entity: "screen.page_2", name: "Controls", slot: 0 }] },
  } as Screen)], entities: [], icons: { groups: [], defaults: {}, weather: {}, sun: {}, controls: {}, fallback: "F0335" } } as any;
  useScreenStore().selected = null;
  vi.stubGlobal("fetch", vi.fn(async () => reply({ states: {}, previews: [], capabilities: {} })));
  useSessionStore().select("test");
});
afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); });

describe("one draft in both editor modes", () => {
  it('keeps spaces and temporary empty titles while storing valid text with one undo step', async () => {
    const view = mount(PageInspector, { props: { id: doc.document!.pages[0].id } });
    await view.find('.disclosure').trigger('click');
    const input = view.find('#screen-title');
    const original = doc.document!.title;
    await input.trigger('focus');
    await input.setValue('');
    expect((input.element as HTMLInputElement).value).toBe('');
    expect(doc.document!.title).toBe(original);
    await input.setValue('Living ');
    expect((input.element as HTMLInputElement).value).toBe('Living ');
    expect(doc.document!.title).toBe('Living');
    await input.setValue('Living room');
    await input.trigger('blur');
    expect(doc.document!.title).toBe('Living room');
    expect(doc.undoCount).toBe(1);
    doc.undo(); expect(doc.document!.title).toBe(original);
  });
  it('skips map history in Simple and never restores an invisible map position', () => {
    doc.setEditorMode('advanced');
    const id = doc.document!.pages[0].id;
    const original = doc.workspacePositions()[id];
    setPageTitle(0, 'Changed');
    doc.moveWorkspacePage(id, 8, 8);
    doc.setEditorMode('simple');
    expect(doc.undoCount).toBe(1);
    doc.undo();
    expect(doc.document!.pages[0].topbar.title).not.toEqual({ source: 'text', text: 'Changed' });
    expect(doc.workspacePositions()[id]).toEqual({ x: 8, y: 8 });
    expect(doc.undoCount).toBe(0);
    doc.redo();
    expect(doc.workspacePositions()[id]).toEqual({ x: 8, y: 8 });
    doc.setEditorMode('advanced');
    // The most recently redone document change comes first, then the map move.
    doc.undo(); doc.undo();
    expect(doc.workspacePositions()[id]).toEqual(original);
  });
  it('groups typing until blur and gives the next focus its own undo step', async () => {
    const view = mount(PageInspector, { props: { id: doc.document!.pages[0].id } });
    const input = view.find('#owned-page-title');
    const original = JSON.stringify(doc.document!.pages[0].topbar.title);
    await input.trigger('focus');
    for (const text of ['K', 'Ki', 'Kitchen']) await input.setValue(text);
    await input.trigger('blur');
    expect(doc.undoCount).toBe(1);
    await input.trigger('focus');
    for (const text of ['Kitchen ', 'Kitchen lights']) await input.setValue(text);
    await input.trigger('blur');
    expect(doc.undoCount).toBe(2);
    doc.undo(); expect(doc.document!.pages[0].topbar.title).toEqual({ source: 'text', text: 'Kitchen' });
    doc.undo(); expect(JSON.stringify(doc.document!.pages[0].topbar.title)).toBe(original);
    doc.redo(); expect(doc.document!.pages[0].topbar.title).toEqual({ source: 'text', text: 'Kitchen' });
  });
  it('keeps verified page editing available offline without asking for an update', () => {
    Object.assign(useInventoryStore().inventory.screens[0], { online: false, page_capability: 'offline', page_last_capability: 'ready' });
    const view = mount(LayoutView);
    expect(useScreenStore().pageReady).toBe(true);
    expect(view.text()).not.toContain('Update screen to use the new titlebar and layout');
    expect(view.text()).toContain('Waiting for the screen to reconnect');
  });
  it('lets a screen whose taps Home Assistant ignored perform actions with one click', async () => {
    // Home Assistant refused a tap (its repair issue, app 0.4.63); the notice offers its Configure switch (app 0.4.73).
    Object.assign(useInventoryStore().inventory.screens[0], { actions_blocked: true });
    const fetch = vi.fn(async () => reply({ allowed: true, name: 'Test' }));
    vi.stubGlobal('fetch', fetch);
    const view = mount(LayoutView);
    expect(view.find('#actions-blocked').exists()).toBe(true);
    await view.find('#allow-actions').trigger('click');
    await vi.waitFor(() => expect(view.find('#actions-blocked').exists()).toBe(false));
    const calls = fetch.mock.calls.map(([url, init]: any) => [String(url), init?.method]);
    expect(calls).toContainEqual(['api/screens/test/allow-actions', 'POST']);
    expect(useUiStore().notice?.message).toBe('Test may now control your devices.');
  });
  it('keeps the notice when Home Assistant does not take it, and says why', async () => {
    Object.assign(useInventoryStore().inventory.screens[0], { actions_blocked: true });
    vi.stubGlobal('fetch', vi.fn(async () => reply({ error: 'Home Assistant didn\'t take it.' }, 400)));
    const view = mount(LayoutView);
    await view.find('#allow-actions').trigger('click');
    await vi.waitFor(() => expect(useScreenStore().allowing).toBeNull());
    expect(view.find('#actions-blocked').exists()).toBe(true);
    expect(useUiStore().notice?.message).toContain("Home Assistant didn't take it.");
  });
  it('retires a removal undo toast when a later edit becomes the history head', () => {
    const tile = doc.layout!.tiles[0];
    removeTile(tile);
    expect(useUiStore().notice?.action).toBeDefined();
    setPageTitle(0, 'Later edit');
    expect(useUiStore().notice).toBeNull();
    doc.undo();
    expect(doc.layout!.tiles).toHaveLength(0);
    doc.undo();
    expect(doc.layout!.tiles[0].id).toBe(tile.id);
  });
  it('offers participation in dots and swipes as a switch that starts on', async () => {
    const view = mount(PageInspector, { props: { id: doc.document!.pages[0].id } });
    const toggle = view.find('.page-check [role=switch]');
    expect(toggle.attributes('aria-checked')).toBe('true');
    await toggle.trigger('click');
    expect(doc.document!.pages[0].navigation.excludeFromPagination).toBe(true);
    await toggle.trigger('click');
    expect(doc.document!.pages[0].navigation.excludeFromPagination).toBe(false);
  });
  it('adds a library item only to the selected page and leaves other pages alone when full', () => {
    doc.selectedPageId = doc.document!.pages[1].id;
    addTile('light.selected');
    expect(doc.document!.pages[0].tiles).toHaveLength(1);
    expect(doc.document!.pages[1].tiles[0].content).toEqual({ kind: 'entity', entityId: 'light.selected' });
    for (let i = 0; i < 5; i++) addTile(`sensor.filling_${i}`);
    const before = JSON.stringify(doc.document);
    addTile('sensor.overflow');
    expect(JSON.stringify(doc.document)).toBe(before);
  });
  it('uses a page picker and named routes at phone widths without shrinking the map', async () => {
    setMedia('(max-width: 700px)', true);
    const view = mount(LayoutView);
    try {
      expect(view.findAll('#layout-preview .device')).toHaveLength(1);
      await view.findAll('.page-pills button')[1].trigger('click');
      expect(view.find('#layout-preview .page').attributes('data-page-id')).toBe(doc.document!.pages[1].id);
      doc.setEditorMode('advanced'); await nextTick();
      expect(view.find('.map-list').exists()).toBe(true);
      expect(view.find('.map-scroll').exists()).toBe(false);
      expect(view.findAll('.map-list-route')).toHaveLength(2);
      expect(view.find('#library').exists()).toBe(true);
    } finally { view.unmount(); }
  });
  it('goes to the next page with a finger swiped sideways on a phone, and not with a slow one or a scroll', async () => {
    useUiStore().narrowPhone = true;
    const view = mount(LayoutView);
    await nextTick();
    const pagesView = view.find('#layout-preview').element;
    const touch = (type: string, x: number, y: number) => pagesView.dispatchEvent(Object.assign(new Event(type, { bubbles: true }),
      { touches: type === 'touchend' ? [] : [{ clientX: x, clientY: y }], changedTouches: [{ clientX: x, clientY: y }] }));
    const swipe = async (dx: number, dy: number, ms = 100) => {
      touch('touchstart', 200, 300); touch('touchmove', 200 + dx, 300 + dy);
      await vi.advanceTimersByTimeAsync(ms);
      touch('touchend', 200 + dx, 300 + dy);
    };
    const [first, second] = doc.document!.pages.map((page) => page.id);
    await swipe(-80, 10);
    expect(doc.selectedPageId).toBe(second);
    await swipe(80, 70);
    await swipe(80, 0, 800);
    expect(doc.selectedPageId).toBe(second);
    await swipe(80, 0);
    expect(doc.selectedPageId).toBe(first);
    view.unmount();
  });
  it('reviews a changed grid before applying it, and undo restores the source geometry', () => {
    const original = JSON.stringify(doc.document), revision = doc.documentRevision;
    Object.assign(useInventoryStore().inventory.screens[0].shape!, { columns: 1, rows: 4 });
    expect(doc.gridChanged).toBe(true);
    doc.reviewScreenGrid();
    expect(doc.gridReview?.target).toEqual({ columns: 1, rows: 4 });
    expect(doc.documentGrid).toEqual({ columns: 2, rows: 3 });
    expect(JSON.stringify(doc.document)).toBe(original);
    expect(doc.dirty).toBe(false);
    doc.acceptGridReview();
    expect(doc.documentGrid).toEqual({ columns: 1, rows: 4 });
    expect(doc.documentRevision).toBe(revision);
    expect(doc.dirty).toBe(true);
    doc.undo();
    expect(doc.documentGrid).toEqual({ columns: 2, rows: 3 });
    expect(JSON.stringify(doc.document)).toBe(original);
    expect(doc.dirty).toBe(false);
    doc.redo(); expect(doc.documentGrid).toEqual({ columns: 1, rows: 4 });
  });
  it('previews navigation locally without modifying the draft, selection, or calling HA', async () => {
    vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(() => {});
    const document = JSON.stringify(doc.document), selected = doc.selectedTileId;
    const view = mount(NavigationPreview);
    await nextTick();
    vi.mocked(fetch).mockClear();
    expect(view.findAll('.remove')).toHaveLength(0);
    expect(view.find('.page-navigation span').text()).toBe('1 / 2');
    await view.find('.tile').trigger('click');
    expect(view.find('.page-navigation span').text()).toBe('2 / 2');
    await view.find('.preview-home').trigger('click');
    expect(view.find('.page-navigation span').text()).toBe('1 / 2');
    expect(doc.selectedTileId).toBe(selected);
    expect(JSON.stringify(doc.document)).toBe(document);
    expect(doc.dirty).toBe(false);
    expect(fetch).not.toHaveBeenCalled();
  });
  it('gives the Preview dialog no class the app styles globally', () => {
    // app.css styles `.live` as a grid card; on the dialog it stretched the Preview to the window's height (0.4.20).
    const source = readFileSync('src/components/NavigationPreview.vue', 'utf8');
    const global = new Set([...readFileSync('src/styles/app.css', 'utf8').matchAll(/^\.([\w-]+)\s*[{,]/gm)].map((m) => m[1]));
    const classes = [...source.matchAll(/<dialog[^>]*?:class="\{([^}]*)\}"/g)].flatMap((m) => [...m[1].matchAll(/([\w-]+)\s*:/g)].map((c) => c[1]));
    expect(classes.length).toBeGreaterThan(0);
    expect(classes.filter((name) => global.has(name))).toEqual([]);
  });
  it('keeps the footer on detail pages and returns without needing a tile', async () => {
    doc.document!.pages[1].navigation.excludeFromPagination = true;
    const view = mount(NavigationPreview);
    expect(view.find('.page-navigation').exists()).toBe(true);
    await view.find('.tile').trigger('click');
    expect(view.find('.page-back').exists()).toBe(true);
    expect(view.find('.page-navigation').text()).not.toContain('/');
    await view.find('.page-back').trigger('click');
    expect(view.find('.page').attributes('data-page-id')).toBe(doc.document!.homePageId);
  });
  it('replaces Home with Back when the footer is hidden, even if Home was disabled', async () => {
    doc.document!.pages[1].navigation.excludeFromPagination = true;
    useInventoryStore().inventory.screens[0].settings = { values: { page_buttons: false, home_button: false } } as any;
    const view = mount(NavigationPreview);
    expect(view.find('.page-navigation').exists()).toBe(false);
    expect(view.find('.preview-home').exists()).toBe(false);
    await view.find('.tile').trigger('click');
    expect(view.find('.page-navigation').exists()).toBe(false);
    expect(view.find('.preview-home').attributes('aria-label')).toMatch(/Back|Terug/);
    await view.find('.preview-home').trigger('click');
    expect(view.find('.page').attributes('data-page-id')).toBe(doc.document!.homePageId);
  });
  it("changes only editor state when switching modes and retains the same undo history", () => {
    const home = doc.document!.homePageId;
    setHomePage(doc.document!.pages[1].id);
    const draft = JSON.stringify(doc.document), count = doc.undoCount;
    doc.setEditorMode("advanced"); doc.setEditorMode("simple");
    expect(JSON.stringify(doc.document)).toBe(draft);
    expect(doc.undoCount).toBe(count);
    doc.undo(); expect(doc.document!.homePageId).toBe(home);
    doc.redo(); expect(JSON.stringify(doc.document)).toBe(draft);
  });
  it("unmounts every connection and port when returning to Simple", async () => {
    doc.setEditorMode("advanced");
    const view = mount(LayoutView);
    expect(view.find(".map-links").exists()).toBe(true);
    doc.connectingTileId = doc.layout!.tiles[0].id!;
    doc.setEditorMode("simple"); await nextTick();
    expect(view.find(".map-links").exists()).toBe(false);
    expect(view.find(".connection-port").exists()).toBe(false);
    expect(doc.connectingTileId).toBeNull();
    expect(view.find("#library").exists()).toBe(true);
  });
  it("keeps Home, links, exclusions and per-page bars attached through a reorder and undo", () => {
    const [home, controls] = doc.document!.pages.map((page) => page.id);
    setHomePage(controls); setPageExcluded(controls, true);
    doc.selectedPageId = doc.document!.pages[1].id; useTopbarStore().setTopbarItems([{ type: "date" }]);
    const before = JSON.stringify(doc.document);
    movePage(1, 0);
    expect(doc.document!.homePageId).toBe(controls);
    expect(doc.document!.pages[0]).toMatchObject({ id: controls, navigation: { excludeFromPagination: true }, topbar: { trailing: [{ type: "date" }] } });
    expect(doc.document!.pages[1]).toMatchObject({ id: home, tiles: [{ content: { target: { pageId: controls } } }] });
    expect(doc.barPage).toBe(0);
    doc.undo(); expect(JSON.stringify(doc.document)).toBe(before);
  });
  it("creates a navigation destination and tile together and undoes both together", () => {
    const before = JSON.stringify(doc.document);
    addTile("screen.page_5");
    expect(doc.document!.pages).toHaveLength(5);
    expect(doc.document!.pages[0].tiles[1].content).toEqual({ kind: "navigation", target: { kind: "page", pageId: doc.document!.pages[4].id } });
    doc.undo(); expect(JSON.stringify(doc.document)).toBe(before);
  });
  it("keeps the saved old-screen notice until the actual capability arrives", async () => {
    useInventoryStore().inventory.screens[0].page_capability = "update_screen";
    const view = mount(LayoutView);
    expect(view.text()).toContain("Update screen to use the new titlebar and layout");
    const before = JSON.stringify(doc.document);
    useInventoryStore().inventory.screens[0].page_capability = "ready"; await nextTick();
    expect(view.text()).not.toContain("Update screen to use the new titlebar and layout");
    expect(JSON.stringify(doc.document)).toBe(before);
    expect(doc.dirty).toBe(false);
  });
  it('preserves an unsaved draft when one of two screens upgrades a week later', async () => {
    const original = JSON.parse(JSON.stringify(useInventoryStore().inventory.screens[0]));
    useInventoryStore().inventory.screens[0].page_capability = 'update_screen';
    setPageTitle(1, 'Unsent title');
    doc.setEditorMode('advanced');
    const selected = doc.document!.pages[1].id;
    doc.selectedPageId = selected;
    doc.moveWorkspacePage(selected, 3, 2);
    const draft = JSON.stringify(doc.document), workspace = JSON.stringify(doc.workspace);
    vi.setSystemTime(Date.now() + 7 * 24 * 60 * 60 * 1000);
    const fetch = vi.fn(async (_url: string) => reply({ connected: true, screens: [
      { ...original, firmware: '0.3.0', page_capability: 'ready' },
      { ...original, id: 'other', firmware: '0.2.104', page_capability: 'update_screen' },
    ] }));
    vi.stubGlobal('fetch', fetch);
    await useInventoryStore().refresh(false);
    expect(JSON.stringify(doc.document)).toBe(draft);
    expect(JSON.stringify(doc.workspace)).toBe(workspace);
    expect(doc.selectedPageId).toBe(selected);
    expect(doc.dirty).toBe(true);
    expect(doc.workspaceDirty).toBe(true);
    expect(useInventoryStore().inventory.screens.map((screen) => screen.page_capability)).toEqual(['ready', 'update_screen']);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0]?.[0]).toBe('api/inventory?light=1');
  });
});

describe("editor positions never alter firmware configuration", () => {
  it("materializes positions once and keeps them stable when Home, links or order change", () => {
    doc.setEditorMode("advanced");
    const before = doc.workspacePositions(), second = doc.document!.pages[1].id;
    setHomePage(second); connectTile(doc.layout!.tiles[0].id!, "home"); movePage(0, 1);
    expect(doc.workspacePositions()).toEqual(before);
    addPage();
    expect(Object.fromEntries(Object.entries(doc.workspacePositions()).filter(([id]) => id in before))).toEqual(before);
  });
  it("saves a map move through the workspace endpoint, with both expected revisions and no layout", async () => {
    doc.setEditorMode("advanced");
    const layout = JSON.stringify(doc.document), revision = doc.documentRevision;
    doc.moveWorkspacePage(doc.document!.homePageId, 3, 2);
    expect(doc.dirty).toBe(false);
    const fetch = vi.fn(async (url: string, options?: RequestInit) => {
      expect(url).toBe("api/screens/test/workspace");
      const body = JSON.parse(String(options?.body));
      expect(body).toEqual({ revision, workspace: doc.workspace });
      return reply({ ...body.workspace, revision: "new-workspace" });
    });
    vi.stubGlobal("fetch", fetch);
    await doc.saveWorkspace();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(doc.workspaceDirty).toBe(false);
    expect(doc.documentRevision).toBe(revision);
    expect(JSON.stringify(doc.document)).toBe(layout);
  });
  it("rejects overlapping map positions without changing the document or positions", () => {
    doc.setEditorMode("advanced");
    const before = JSON.stringify(doc.workspace.positions), [first, second] = doc.document!.pages;
    const destination = doc.workspacePositions()[second.id];
    doc.moveWorkspacePage(first.id, destination.x, destination.y);
    expect(JSON.stringify(doc.workspace.positions)).toBe(before);
    expect(doc.dirty).toBe(false);
  });
});

describe("revisions and portable layouts", () => {
  it('acknowledges dropped tiles without discarding a current draft', async () => {
    record().migration = { droppedTiles: [{ entity: 'light.missing', name: 'Missing lamp', reason: 'invalid_legacy_tile' }] };
    addPage(); const draft = JSON.stringify(doc.document);
    const view = mount(LayoutView);
    expect(view.text()).toContain('Missing lamp');
    const acknowledged = JSON.parse(JSON.stringify(record())); delete acknowledged.migration;
    const fetch = vi.fn(async (url: string, options?: RequestInit) => {
      if (options?.method === 'POST') {
        expect(url).toBe('api/screens/test/migration/dismiss');
        expect(JSON.parse(String(options.body))).toEqual({ revision: record().revision });
        return reply(acknowledged);
      }
      return reply({ screens: [{ ...useInventoryStore().inventory.screens[0], page_document: acknowledged }] });
    });
    vi.stubGlobal('fetch', fetch);
    await doc.dismissMigrationNote(); await nextTick();
    expect(view.text()).not.toContain('Missing lamp');
    expect(JSON.stringify(doc.document)).toBe(draft);
    expect(doc.dirty).toBe(true);
  });
  it('reloads the competing saved document only when explicitly chosen', async () => {
    addPage(); doc.conflict = true;
    const other = { ...record(), revision: 'newer' };
    vi.stubGlobal('fetch', vi.fn(async () => reply({ screens: [{ ...useInventoryStore().inventory.screens[0], page_document: other }] })));
    await doc.resolveLayoutConflict('reload');
    expect(doc.document).toEqual(other.layout);
    expect(doc.dirty).toBe(false);
    expect(doc.conflict).toBe(false);
    expect(doc.undoCount).toBe(0);
  });
  it('keeps the draft and uses the latest revision for an explicit overwrite', async () => {
    addPage(); doc.conflict = true;
    const draft = JSON.parse(JSON.stringify(doc.document));
    let other = { ...record(), revision: 'newer' };
    const fetch = vi.fn(async (_url: string, options?: RequestInit) => {
      if (options?.method === 'PUT') {
        const body = JSON.parse(String(options.body));
        expect(body.revision).toBe('newer'); expect(body.layout).toEqual(draft);
        other = { ...other, revision: 'saved', layout: body.layout };
        return reply({ saved: true, document: other });
      }
      return reply({ screens: [{ ...useInventoryStore().inventory.screens[0], page_document: other }] });
    });
    vi.stubGlobal('fetch', fetch);
    await doc.resolveLayoutConflict('keep');
    expect(doc.document).toEqual(draft);
    expect(doc.dirty).toBe(false);
    expect(doc.conflict).toBe(false);
    expect(doc.documentRevision).toBe('saved');
  });
  it('preserves the destination screen title when copying another layout', () => {
    doc.document!.title = 'Destination';
    const source = screenFixture({ ...useInventoryStore().inventory.screens[0], id: 'source', name: 'Source' });
    (source.page_document as PageDocument).layout.title = 'Source title';
    useInventoryStore().inventory.screens.push(source);
    doc.copyLayoutFrom('source');
    expect(doc.document!.title).toBe('Destination');
    expect((source.page_document as PageDocument).layout.title).toBe('Source title');
  });
  it("keeps a rejected save as a draft and exposes the competing revision", async () => {
    addPage(); const draft = JSON.stringify(doc.document);
    const other = { ...record(), revision: "changed-elsewhere" };
    vi.stubGlobal("fetch", vi.fn(async (_url: string, options?: RequestInit) => options?.method === "PUT"
      ? reply({ error: "Layout changed" }, 409) : reply({ screens: [{ ...useInventoryStore().inventory.screens[0], page_document: other }] })));
    await doc.save();
    expect(JSON.stringify(doc.document)).toBe(draft);
    expect(doc.dirty).toBe(true); expect(doc.conflict).toBe(true);
    expect(doc.documentRevision).toBe(record().revision);
  });
  it("recovers a committed save whose HTTP response was lost without resending it", async () => {
    addPage(); const draft = JSON.parse(JSON.stringify(doc.document));
    const server = { ...record(), revision: "committed", layout: draft };
    const fetch = vi.fn(async (_url: string, options?: RequestInit) => {
      if (options?.method === "PUT") throw new Error("Connection lost");
      return reply({ screens: [{ ...useInventoryStore().inventory.screens[0], page_document: server }] });
    });
    vi.stubGlobal("fetch", fetch); await doc.save();
    expect(doc.dirty).toBe(false); expect(doc.documentRevision).toBe("committed");
    expect(fetch.mock.calls.filter(([, options]) => options?.method === "PUT")).toHaveLength(1);
  });
  it("recovers a committed save whose answer was lost when the add-on wrote its keys in another order", async () => {
    // The add-on keeps a tile's fields in an order of its own (app 0.4.1): the same layout, not another one.
    const reversed = (value: unknown): unknown => Array.isArray(value) ? value.map(reversed)
      : value && typeof value === "object" ? Object.fromEntries(Object.entries(value).reverse().map(([key, item]) => [key, reversed(item)])) : value;
    addPage(); doc.moveWorkspacePage(doc.document!.pages[0].id, 3, 4);
    const draft = JSON.parse(JSON.stringify(doc.document));
    const server = { ...record(), revision: "committed", layout: reversed(draft), workspace: reversed({ revision: "w2", positions: doc.workspace.positions }) };
    vi.stubGlobal("fetch", vi.fn(async (_url: string, options?: RequestInit) => {
      if (options?.method === "PUT") throw new Error("Connection lost");
      return reply({ screens: [{ ...useInventoryStore().inventory.screens[0], page_document: server }] });
    }));
    await doc.save();
    expect(doc.conflict).toBe(false);
    expect(doc.dirty).toBe(false); expect(doc.documentRevision).toBe("committed");
  });
  it("exports only portable layout and editor placement, and copies with fresh IDs", () => {
    (useInventoryStore().inventory.screens[0] as any).api_key = "private-key-never-export";
    useInventoryStore().inventory.screens.push(screenFixture({ ...useInventoryStore().inventory.screens[0], id: "source", name: "Source" }));
    const source = useInventoryStore().inventory.screens[1].page_document as PageDocument;
    doc.copyLayoutFrom("source");
    const exported = JSON.parse(doc.layoutJson());
    expect(Object.keys(exported).sort()).toEqual(["editor", "esp_screens_layout", "layout", "sourceGrid"]);
    expect(doc.layoutJson()).not.toContain("private-key-never-export");
    expect(doc.document!.pages[0].id).not.toBe(source.layout.pages[0].id);
    expect(doc.document!.pages[0].tiles[0].content).toEqual({ kind: "navigation", target: { kind: "page", pageId: doc.document!.pages[1].id } });
  });
  it("does not apply an import response to a different screen opened while it was checked", async () => {
    let resolve!: (value: Response) => void;
    const imported = documentFixture({ title: "Imported", tiles: [] });
    vi.stubGlobal("fetch", vi.fn((url: string) => url.endsWith("/import") ? new Promise<Response>((done) => { resolve = done; }) : Promise.resolve(reply({}))));
    const pending = doc.importLayout(JSON.stringify({ esp_screens_layout: 2, sourceGrid: imported.sourceGrid, layout: imported.layout }));
    useInventoryStore().inventory.screens.push(screenFixture({ ...useInventoryStore().inventory.screens[0], id: "other", name: "Other" }));
    useSessionStore().select("other"); const before = JSON.stringify(doc.document);
    resolve(reply(imported)); await pending;
    expect(JSON.stringify(doc.document)).toBe(before); expect(doc.dirty).toBe(false);
  });
});


describe('creating a page', () => {
  it('cancels the wizard without a layout mutation or undo entry', async () => {
    const before = JSON.stringify(doc.document);
    const view = mount(PageWizard);
    await view.find('#new-page-title').setValue('Unfinished');
    await view.find('footer button[type=button]').trigger('click');
    expect(view.emitted('close')).toHaveLength(1);
    expect(JSON.stringify(doc.document)).toBe(before);
    expect(doc.undoCount).toBe(0);
  });
  it('creates a configured independent bar and undoes the whole creation in one step', async () => {
    useInventoryStore().inventory.entities = [{ id: 'sensor.room', name: 'Temperature', area: 'Study' }];
    const before = JSON.stringify(doc.document);
    const view = mount(PageWizard);
    await view.find('#new-page-title').setValue('Study');
    await view.find('.home-choice [role=switch]').trigger('click');
    await view.find('.entity-option').trigger('click');
    await view.find('form').trigger('submit');
    const page = doc.document!.pages.at(-1)!;
    expect(page.topbar.title).toEqual({ source: 'text', text: 'Study' });
    expect(page.topbar.leading).toEqual([]);
    expect(page.topbar.trailing.map(item => item.type)).toEqual(['clock', 'entity']);
    expect(doc.selectedPageId).toBe(page.id);
    expect(view.emitted('close')).toHaveLength(1);
    doc.undo(); expect(JSON.stringify(doc.document)).toBe(before);
  });
  it('offers only what a top bar can show: never a camera (app 0.4.1)', async () => {
    useInventoryStore().inventory.entities = [{ id: 'sensor.room', name: 'Temperature', area: '' }, { id: 'camera.door', name: 'Door', area: '' }];
    const view = mount(PageWizard);
    expect(view.findAll('.entity-option').map((row) => row.text())).toEqual([expect.stringContaining('Temperature')]);
  });
  it('gives a new page the shared bar on a screen whose firmware still shares one (app 0.4.1)', async () => {
    useInventoryStore().inventory.screens[0].page_capability = 'update_screen';
    const first = doc.document!.pages[0].topbar;
    const view = mount(PageWizard);
    expect(view.find('.home-choice').exists()).toBe(false);
    await view.find('#new-page-title').setValue('Study');
    await view.find('form').trigger('submit');
    const page = doc.document!.pages.at(-1)!;
    expect(page.topbar.title).toEqual({ source: 'text', text: 'Study' });
    expect(page.topbar.leading.map((item) => item.kind)).toEqual(first.leading.map((item) => item.kind));
    expect(page.topbar.trailing.map(({ id: _, ...item }) => item)).toEqual(first.trailing.map(({ id: _, ...item }) => item));
    expect(view.emitted('close')).toHaveLength(1);
  });
  it('keeps the home page first on a screen whose firmware starts on page 1 (app 0.4.1)', () => {
    useInventoryStore().inventory.screens[0].page_capability = 'update_screen';
    while (doc.document!.pages.length < 3) addPage();
    const order = doc.document!.pages.map((page) => page.id);
    expect(movePage(0, 1)).toBe(false);
    expect(movePage(2, 0)).toBe(false);
    expect(useUiStore().notice?.message).toBe('Update screen to use the new titlebar and layout');
    expect(movePage(2, 1)).toBe(true);
    expect(doc.document!.pages[0].id).toBe(order[0]);
  });
  it('names a drop-created page once and preserves it when more entities are added', () => {
    useInventoryStore().inventory.entities = [{ id: 'light.study', name: 'Desk', area: 'Study' }];
    const count = doc.document!.pages.length;
    expect(placeTile({ entity: 'light.study', name: '', slot: -1 }, count * 6)).toBe(true);
    expect(doc.document!.pages.at(-1)!.topbar.title).toEqual({ source: 'text', text: 'Study' });
    expect(placeTile({ entity: 'sensor.outside', name: '', slot: -1 }, count * 6 + 1)).toBe(true);
    expect(doc.document!.pages.at(-1)!.topbar.title).toEqual({ source: 'text', text: 'Study' });
  });
});
