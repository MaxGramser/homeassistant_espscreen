import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { nextTick } from "vue";
import { readFileSync } from "node:fs";
import { mount } from "@vue/test-utils";
import PageWizard from "../src/components/PageWizard.vue";
import LayoutView from "../src/components/LayoutView.vue";
import NavigationPreview from '../src/components/NavigationPreview.vue';
import PageInspector from '../src/components/PageInspector.vue';
import TopbarInspector from '../src/components/TopbarInspector.vue';
import { placeTile, dismissMigrationNote, pageReady, removeTile, resolveLayoutConflict, addPage, movePage } from '../src/store';
import { addPage, addTile, connectTile, copyLayoutFrom, importLayout, layoutJson, movePage, moveWorkspacePage, redo,
  acceptGridReview, gridChanged, refresh, reviewScreenGrid, save, saveWorkspace, select, setEditorMode, setHomePage, setPageExcluded, setPageTitle, setTopbarItems, state, undo, workspacePositions } from "../src/store";
import { documentFixture, screenFixture } from "./page-fixtures";
import type { PageDocument, Screen } from "../src/types";

const record = () => state.inventory.screens[0].page_document as PageDocument;
const reply = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const preferences = new Map<string, string>();
  vi.stubGlobal("localStorage", { getItem: (key: string) => preferences.get(key) ?? null, setItem: (key: string, value: string) => preferences.set(key, value) });
  state.dirty = false; state.busy = false; state.workspaceDirty = false;
  state.inventory = { connected: true, screens: [screenFixture({ id: "test", name: "Test", firmware: "0.3.0", online: true,
    board: "guition", shape: { columns: 2, rows: 3, width: 480, height: 480 },
    layout: { title: "Home", pages: 2, tiles: [{ entity: "screen.page_2", name: "Controls", slot: 0 }] },
  } as Screen)], entities: [], icons: { groups: [], defaults: {}, weather: {}, sun: {}, controls: {}, fallback: "F0335" } } as any;
  state.selected = null;
  vi.stubGlobal("fetch", vi.fn(async () => reply({ states: {}, previews: [], capabilities: {} })));
  select("test");
});
afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); });

describe("one draft in both editor modes", () => {
  it('keeps spaces and temporary empty titles while storing valid text with one undo step', async () => {
    const view = mount(PageInspector, { props: { id: state.document!.pages[0].id } });
    await view.find('.disclosure').trigger('click');
    const input = view.find('#screen-title');
    const original = state.document!.title;
    await input.trigger('focus');
    await input.setValue('');
    expect((input.element as HTMLInputElement).value).toBe('');
    expect(state.document!.title).toBe(original);
    await input.setValue('Living ');
    expect((input.element as HTMLInputElement).value).toBe('Living ');
    expect(state.document!.title).toBe('Living');
    await input.setValue('Living room');
    await input.trigger('blur');
    expect(state.document!.title).toBe('Living room');
    expect(state.undoCount).toBe(1);
    undo(); expect(state.document!.title).toBe(original);
  });
  it('skips map history in Simple and never restores an invisible map position', () => {
    setEditorMode('advanced');
    const id = state.document!.pages[0].id;
    const original = workspacePositions()[id];
    setPageTitle(0, 'Changed');
    moveWorkspacePage(id, 8, 8);
    setEditorMode('simple');
    expect(state.undoCount).toBe(1);
    undo();
    expect(state.document!.pages[0].topbar.title).not.toEqual({ source: 'text', text: 'Changed' });
    expect(workspacePositions()[id]).toEqual({ x: 8, y: 8 });
    expect(state.undoCount).toBe(0);
    redo();
    expect(workspacePositions()[id]).toEqual({ x: 8, y: 8 });
    setEditorMode('advanced');
    // The most recently redone document change comes first, then the map move.
    undo(); undo();
    expect(workspacePositions()[id]).toEqual(original);
  });
  it('groups typing until blur and gives the next focus its own undo step', async () => {
    const view = mount(PageInspector, { props: { id: state.document!.pages[0].id } });
    const input = view.find('#owned-page-title');
    const original = JSON.stringify(state.document!.pages[0].topbar.title);
    await input.trigger('focus');
    for (const text of ['K', 'Ki', 'Kitchen']) await input.setValue(text);
    await input.trigger('blur');
    expect(state.undoCount).toBe(1);
    await input.trigger('focus');
    for (const text of ['Kitchen ', 'Kitchen lights']) await input.setValue(text);
    await input.trigger('blur');
    expect(state.undoCount).toBe(2);
    undo(); expect(state.document!.pages[0].topbar.title).toEqual({ source: 'text', text: 'Kitchen' });
    undo(); expect(JSON.stringify(state.document!.pages[0].topbar.title)).toBe(original);
    redo(); expect(state.document!.pages[0].topbar.title).toEqual({ source: 'text', text: 'Kitchen' });
  });
  it('keeps verified page editing available offline without asking for an update', () => {
    Object.assign(state.inventory.screens[0], { online: false, page_capability: 'offline', page_last_capability: 'ready' });
    const view = mount(LayoutView);
    expect(pageReady.value).toBe(true);
    expect(view.text()).not.toContain('Update screen to use the new titlebar and layout');
    expect(view.text()).toContain('Waiting for the screen to reconnect');
  });
  it('retires a removal undo toast when a later edit becomes the history head', () => {
    const tile = state.layout!.tiles[0];
    removeTile(tile);
    expect(state.toast?.action).toBeDefined();
    setPageTitle(0, 'Later edit');
    expect(state.toast).toBeNull();
    undo();
    expect(state.layout!.tiles).toHaveLength(0);
    undo();
    expect(state.layout!.tiles[0].id).toBe(tile.id);
  });
  it('offers participation in dots and swipes as a switch that starts on', async () => {
    const view = mount(PageInspector, { props: { id: state.document!.pages[0].id } });
    const toggle = view.find('.page-check [role=switch]');
    expect(toggle.attributes('aria-checked')).toBe('true');
    await toggle.trigger('click');
    expect(state.document!.pages[0].navigation.excludeFromPagination).toBe(true);
    await toggle.trigger('click');
    expect(state.document!.pages[0].navigation.excludeFromPagination).toBe(false);
  });
  it('adds a library item only to the selected page and leaves other pages alone when full', () => {
    state.selectedPageId = state.document!.pages[1].id;
    addTile('light.selected');
    expect(state.document!.pages[0].tiles).toHaveLength(1);
    expect(state.document!.pages[1].tiles[0].content).toEqual({ kind: 'entity', entityId: 'light.selected' });
    for (let i = 0; i < 5; i++) addTile(`sensor.filling_${i}`);
    const before = JSON.stringify(state.document);
    addTile('sensor.overflow');
    expect(JSON.stringify(state.document)).toBe(before);
  });
  it('uses a page picker and named routes at phone widths without shrinking the map', async () => {
    const width = window.innerWidth;
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 });
    const view = mount(LayoutView);
    try {
      expect(view.findAll('#layout-preview .device')).toHaveLength(1);
      await view.findAll('.page-pills button')[1].trigger('click');
      expect(view.find('#layout-preview .page').attributes('data-page-id')).toBe(state.document!.pages[1].id);
      setEditorMode('advanced'); await nextTick();
      expect(view.find('.map-list').exists()).toBe(true);
      expect(view.find('.map-scroll').exists()).toBe(false);
      expect(view.findAll('.map-list-route')).toHaveLength(2);
      expect(view.find('#library').exists()).toBe(true);
    } finally { Object.defineProperty(window, 'innerWidth', { configurable: true, value: width }); view.unmount(); }
  });
  it('reviews a changed grid before applying it, and undo restores the source geometry', () => {
    const original = JSON.stringify(state.document), revision = state.documentRevision;
    Object.assign(state.inventory.screens[0].shape!, { columns: 1, rows: 4 });
    expect(gridChanged.value).toBe(true);
    reviewScreenGrid();
    expect(state.gridReview?.target).toEqual({ columns: 1, rows: 4 });
    expect(state.documentGrid).toEqual({ columns: 2, rows: 3 });
    expect(JSON.stringify(state.document)).toBe(original);
    expect(state.dirty).toBe(false);
    acceptGridReview();
    expect(state.documentGrid).toEqual({ columns: 1, rows: 4 });
    expect(state.documentRevision).toBe(revision);
    expect(state.dirty).toBe(true);
    undo();
    expect(state.documentGrid).toEqual({ columns: 2, rows: 3 });
    expect(JSON.stringify(state.document)).toBe(original);
    expect(state.dirty).toBe(false);
    redo(); expect(state.documentGrid).toEqual({ columns: 1, rows: 4 });
  });
  it('previews navigation locally without modifying the draft, selection, or calling HA', async () => {
    vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(() => {});
    const document = JSON.stringify(state.document), selected = state.selectedTile;
    const view = mount(NavigationPreview);
    await nextTick();
    vi.mocked(fetch).mockClear();
    expect(view.findAll('.remove')).toHaveLength(0);
    expect(view.find('.page-navigation span').text()).toBe('1 / 2');
    await view.find('.tile').trigger('click');
    expect(view.find('.page-navigation span').text()).toBe('2 / 2');
    await view.find('.preview-home').trigger('click');
    expect(view.find('.page-navigation span').text()).toBe('1 / 2');
    expect(state.selectedTile).toBe(selected);
    expect(JSON.stringify(state.document)).toBe(document);
    expect(state.dirty).toBe(false);
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
    state.document!.pages[1].navigation.excludeFromPagination = true;
    const view = mount(NavigationPreview);
    expect(view.find('.page-navigation').exists()).toBe(true);
    await view.find('.tile').trigger('click');
    expect(view.find('.page-back').exists()).toBe(true);
    expect(view.find('.page-navigation').text()).not.toContain('/');
    await view.find('.page-back').trigger('click');
    expect(view.find('.page').attributes('data-page-id')).toBe(state.document!.homePageId);
  });
  it('replaces Home with Back when the footer is hidden, even if Home was disabled', async () => {
    state.document!.pages[1].navigation.excludeFromPagination = true;
    state.inventory.screens[0].settings = { values: { page_buttons: false, home_button: false } } as any;
    const view = mount(NavigationPreview);
    expect(view.find('.page-navigation').exists()).toBe(false);
    expect(view.find('.preview-home').exists()).toBe(false);
    await view.find('.tile').trigger('click');
    expect(view.find('.page-navigation').exists()).toBe(false);
    expect(view.find('.preview-home').attributes('aria-label')).toMatch(/Back|Terug/);
    await view.find('.preview-home').trigger('click');
    expect(view.find('.page').attributes('data-page-id')).toBe(state.document!.homePageId);
  });
  it("changes only editor state when switching modes and retains the same undo history", () => {
    const home = state.document!.homePageId;
    setHomePage(state.document!.pages[1].id);
    const draft = JSON.stringify(state.document), count = state.undoCount;
    setEditorMode("advanced"); setEditorMode("simple");
    expect(JSON.stringify(state.document)).toBe(draft);
    expect(state.undoCount).toBe(count);
    undo(); expect(state.document!.homePageId).toBe(home);
    redo(); expect(JSON.stringify(state.document)).toBe(draft);
  });
  it("unmounts every connection and port when returning to Simple", async () => {
    setEditorMode("advanced");
    const view = mount(LayoutView);
    expect(view.find(".map-links").exists()).toBe(true);
    state.connectingTileId = state.layout!.tiles[0].id!;
    setEditorMode("simple"); await nextTick();
    expect(view.find(".map-links").exists()).toBe(false);
    expect(view.find(".connection-port").exists()).toBe(false);
    expect(state.connectingTileId).toBeNull();
    expect(view.find("#library").exists()).toBe(true);
  });
  it("keeps Home, links, exclusions and per-page bars attached through a reorder and undo", () => {
    const [home, controls] = state.document!.pages.map((page) => page.id);
    setHomePage(controls); setPageExcluded(controls, true);
    state.selectedPageId = state.document!.pages[1].id; setTopbarItems([{ type: "date" }]);
    const before = JSON.stringify(state.document);
    movePage(1, 0);
    expect(state.document!.homePageId).toBe(controls);
    expect(state.document!.pages[0]).toMatchObject({ id: controls, navigation: { excludeFromPagination: true }, topbar: { trailing: [{ type: "date" }] } });
    expect(state.document!.pages[1]).toMatchObject({ id: home, tiles: [{ content: { target: { pageId: controls } } }] });
    expect(state.barPage).toBe(0);
    undo(); expect(JSON.stringify(state.document)).toBe(before);
  });
  it("creates a navigation destination and tile together and undoes both together", () => {
    const before = JSON.stringify(state.document);
    addTile("screen.page_5");
    expect(state.document!.pages).toHaveLength(5);
    expect(state.document!.pages[0].tiles[1].content).toEqual({ kind: "navigation", target: { kind: "page", pageId: state.document!.pages[4].id } });
    undo(); expect(JSON.stringify(state.document)).toBe(before);
  });
  it("keeps the saved old-screen notice until the actual capability arrives", async () => {
    state.inventory.screens[0].page_capability = "update_screen";
    const view = mount(LayoutView);
    expect(view.text()).toContain("Update screen to use the new titlebar and layout");
    const before = JSON.stringify(state.document);
    state.inventory.screens[0].page_capability = "ready"; await nextTick();
    expect(view.text()).not.toContain("Update screen to use the new titlebar and layout");
    expect(JSON.stringify(state.document)).toBe(before);
    expect(state.dirty).toBe(false);
  });
  it('preserves an unsaved draft when one of two screens upgrades a week later', async () => {
    const original = JSON.parse(JSON.stringify(state.inventory.screens[0]));
    state.inventory.screens[0].page_capability = 'update_screen';
    setPageTitle(1, 'Unsent title');
    setEditorMode('advanced');
    const selected = state.document!.pages[1].id;
    state.selectedPageId = selected;
    moveWorkspacePage(selected, 3, 2);
    const draft = JSON.stringify(state.document), workspace = JSON.stringify(state.workspace);
    vi.setSystemTime(Date.now() + 7 * 24 * 60 * 60 * 1000);
    const fetch = vi.fn(async (_url: string) => reply({ connected: true, screens: [
      { ...original, firmware: '0.3.0', page_capability: 'ready' },
      { ...original, id: 'other', firmware: '0.2.104', page_capability: 'update_screen' },
    ] }));
    vi.stubGlobal('fetch', fetch);
    await refresh(false);
    expect(JSON.stringify(state.document)).toBe(draft);
    expect(JSON.stringify(state.workspace)).toBe(workspace);
    expect(state.selectedPageId).toBe(selected);
    expect(state.dirty).toBe(true);
    expect(state.workspaceDirty).toBe(true);
    expect(state.inventory.screens.map((screen) => screen.page_capability)).toEqual(['ready', 'update_screen']);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0]?.[0]).toBe('api/inventory?light=1');
  });
});

describe("editor positions never alter firmware configuration", () => {
  it("materializes positions once and keeps them stable when Home, links or order change", () => {
    setEditorMode("advanced");
    const before = workspacePositions(), second = state.document!.pages[1].id;
    setHomePage(second); connectTile(state.layout!.tiles[0].id!, "home"); movePage(0, 1);
    expect(workspacePositions()).toEqual(before);
    addPage();
    expect(Object.fromEntries(Object.entries(workspacePositions()).filter(([id]) => id in before))).toEqual(before);
  });
  it("saves a map move through the workspace endpoint, with both expected revisions and no layout", async () => {
    setEditorMode("advanced");
    const layout = JSON.stringify(state.document), revision = state.documentRevision;
    moveWorkspacePage(state.document!.homePageId, 3, 2);
    expect(state.dirty).toBe(false);
    const fetch = vi.fn(async (url: string, options?: RequestInit) => {
      expect(url).toBe("api/screens/test/workspace");
      const body = JSON.parse(String(options?.body));
      expect(body).toEqual({ revision, workspace: state.workspace });
      return reply({ ...body.workspace, revision: "new-workspace" });
    });
    vi.stubGlobal("fetch", fetch);
    await saveWorkspace();
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(state.workspaceDirty).toBe(false);
    expect(state.documentRevision).toBe(revision);
    expect(JSON.stringify(state.document)).toBe(layout);
  });
  it("rejects overlapping map positions without changing the document or positions", () => {
    setEditorMode("advanced");
    const before = JSON.stringify(state.workspace.positions), [first, second] = state.document!.pages;
    const destination = workspacePositions()[second.id];
    moveWorkspacePage(first.id, destination.x, destination.y);
    expect(JSON.stringify(state.workspace.positions)).toBe(before);
    expect(state.dirty).toBe(false);
  });
});

describe("revisions and portable layouts", () => {
  it('acknowledges dropped tiles without discarding a current draft', async () => {
    record().migration = { droppedTiles: [{ entity: 'light.missing', name: 'Missing lamp', reason: 'invalid_legacy_tile' }] };
    addPage(); const draft = JSON.stringify(state.document);
    const view = mount(LayoutView);
    expect(view.text()).toContain('Missing lamp');
    const acknowledged = JSON.parse(JSON.stringify(record())); delete acknowledged.migration;
    const fetch = vi.fn(async (url: string, options?: RequestInit) => {
      if (options?.method === 'POST') {
        expect(url).toBe('api/screens/test/migration/dismiss');
        expect(JSON.parse(String(options.body))).toEqual({ revision: record().revision });
        return reply(acknowledged);
      }
      return reply({ screens: [{ ...state.inventory.screens[0], page_document: acknowledged }] });
    });
    vi.stubGlobal('fetch', fetch);
    await dismissMigrationNote(); await nextTick();
    expect(view.text()).not.toContain('Missing lamp');
    expect(JSON.stringify(state.document)).toBe(draft);
    expect(state.dirty).toBe(true);
  });
  it('reloads the competing saved document only when explicitly chosen', async () => {
    addPage(); state.conflict = true;
    const other = { ...record(), revision: 'newer' };
    vi.stubGlobal('fetch', vi.fn(async () => reply({ screens: [{ ...state.inventory.screens[0], page_document: other }] })));
    await resolveLayoutConflict('reload');
    expect(state.document).toEqual(other.layout);
    expect(state.dirty).toBe(false);
    expect(state.conflict).toBe(false);
    expect(state.undoCount).toBe(0);
  });
  it('keeps the draft and uses the latest revision for an explicit overwrite', async () => {
    addPage(); state.conflict = true;
    const draft = JSON.parse(JSON.stringify(state.document));
    let other = { ...record(), revision: 'newer' };
    const fetch = vi.fn(async (_url: string, options?: RequestInit) => {
      if (options?.method === 'PUT') {
        const body = JSON.parse(String(options.body));
        expect(body.revision).toBe('newer'); expect(body.layout).toEqual(draft);
        other = { ...other, revision: 'saved', layout: body.layout };
        return reply({ saved: true, document: other });
      }
      return reply({ screens: [{ ...state.inventory.screens[0], page_document: other }] });
    });
    vi.stubGlobal('fetch', fetch);
    await resolveLayoutConflict('keep');
    expect(state.document).toEqual(draft);
    expect(state.dirty).toBe(false);
    expect(state.conflict).toBe(false);
    expect(state.documentRevision).toBe('saved');
  });
  it('preserves the destination screen title when copying another layout', () => {
    state.document!.title = 'Destination';
    const source = screenFixture({ ...state.inventory.screens[0], id: 'source', name: 'Source' });
    (source.page_document as PageDocument).layout.title = 'Source title';
    state.inventory.screens.push(source);
    copyLayoutFrom('source');
    expect(state.document!.title).toBe('Destination');
    expect((source.page_document as PageDocument).layout.title).toBe('Source title');
  });
  it("keeps a rejected save as a draft and exposes the competing revision", async () => {
    addPage(); const draft = JSON.stringify(state.document);
    const other = { ...record(), revision: "changed-elsewhere" };
    vi.stubGlobal("fetch", vi.fn(async (_url: string, options?: RequestInit) => options?.method === "PUT"
      ? reply({ error: "Layout changed" }, 409) : reply({ screens: [{ ...state.inventory.screens[0], page_document: other }] })));
    await save();
    expect(JSON.stringify(state.document)).toBe(draft);
    expect(state.dirty).toBe(true); expect(state.conflict).toBe(true);
    expect(state.documentRevision).toBe(record().revision);
  });
  it("recovers a committed save whose HTTP response was lost without resending it", async () => {
    addPage(); const draft = JSON.parse(JSON.stringify(state.document));
    const server = { ...record(), revision: "committed", layout: draft };
    const fetch = vi.fn(async (_url: string, options?: RequestInit) => {
      if (options?.method === "PUT") throw new Error("Connection lost");
      return reply({ screens: [{ ...state.inventory.screens[0], page_document: server }] });
    });
    vi.stubGlobal("fetch", fetch); await save();
    expect(state.dirty).toBe(false); expect(state.documentRevision).toBe("committed");
    expect(fetch.mock.calls.filter(([, options]) => options?.method === "PUT")).toHaveLength(1);
  });
  it("exports only portable layout and editor placement, and copies with fresh IDs", () => {
    (state.inventory.screens[0] as any).api_key = "private-key-never-export";
    state.inventory.screens.push(screenFixture({ ...state.inventory.screens[0], id: "source", name: "Source" }));
    const source = state.inventory.screens[1].page_document as PageDocument;
    copyLayoutFrom("source");
    const exported = JSON.parse(layoutJson());
    expect(Object.keys(exported).sort()).toEqual(["editor", "esp_screens_layout", "layout", "sourceGrid"]);
    expect(layoutJson()).not.toContain("private-key-never-export");
    expect(state.document!.pages[0].id).not.toBe(source.layout.pages[0].id);
    expect(state.document!.pages[0].tiles[0].content).toEqual({ kind: "navigation", target: { kind: "page", pageId: state.document!.pages[1].id } });
  });
  it("does not apply an import response to a different screen opened while it was checked", async () => {
    let resolve!: (value: Response) => void;
    const imported = documentFixture({ title: "Imported", tiles: [] });
    vi.stubGlobal("fetch", vi.fn((url: string) => url.endsWith("/import") ? new Promise<Response>((done) => { resolve = done; }) : Promise.resolve(reply({}))));
    const pending = importLayout(JSON.stringify({ esp_screens_layout: 2, sourceGrid: imported.sourceGrid, layout: imported.layout }));
    state.inventory.screens.push(screenFixture({ ...state.inventory.screens[0], id: "other", name: "Other" }));
    select("other"); const before = JSON.stringify(state.document);
    resolve(reply(imported)); await pending;
    expect(JSON.stringify(state.document)).toBe(before); expect(state.dirty).toBe(false);
  });
});


describe('creating a page', () => {
  it('cancels the wizard without a layout mutation or undo entry', async () => {
    const before = JSON.stringify(state.document);
    const view = mount(PageWizard);
    await view.find('#new-page-title').setValue('Unfinished');
    await view.find('footer button[type=button]').trigger('click');
    expect(view.emitted('close')).toHaveLength(1);
    expect(JSON.stringify(state.document)).toBe(before);
    expect(state.undoCount).toBe(0);
  });
  it('creates a configured independent bar and undoes the whole creation in one step', async () => {
    state.inventory.entities = [{ id: 'sensor.room', name: 'Temperature', area: 'Study' }];
    const before = JSON.stringify(state.document);
    const view = mount(PageWizard);
    await view.find('#new-page-title').setValue('Study');
    await view.find('.home-choice [role=switch]').trigger('click');
    await view.find('.entity-option').trigger('click');
    await view.find('form').trigger('submit');
    const page = state.document!.pages.at(-1)!;
    expect(page.topbar.title).toEqual({ source: 'text', text: 'Study' });
    expect(page.topbar.leading).toEqual([]);
    expect(page.topbar.trailing.map(item => item.type)).toEqual(['clock', 'entity']);
    expect(state.selectedPageId).toBe(page.id);
    expect(view.emitted('close')).toHaveLength(1);
    undo(); expect(JSON.stringify(state.document)).toBe(before);
  });
  it('offers only what a top bar can show: never a camera (app 0.4.1)', async () => {
    state.inventory.entities = [{ id: 'sensor.room', name: 'Temperature', area: '' }, { id: 'camera.door', name: 'Door', area: '' }];
    const view = mount(PageWizard);
    expect(view.findAll('.entity-option').map((row) => row.text())).toEqual([expect.stringContaining('Temperature')]);
  });
  it('gives a new page the shared bar on a screen whose firmware still shares one (app 0.4.1)', async () => {
    state.inventory.screens[0].page_capability = 'update_screen';
    const first = state.document!.pages[0].topbar;
    const view = mount(PageWizard);
    expect(view.find('.home-choice').exists()).toBe(false);
    await view.find('#new-page-title').setValue('Study');
    await view.find('form').trigger('submit');
    const page = state.document!.pages.at(-1)!;
    expect(page.topbar.title).toEqual({ source: 'text', text: 'Study' });
    expect(page.topbar.leading.map((item) => item.kind)).toEqual(first.leading.map((item) => item.kind));
    expect(page.topbar.trailing.map(({ id: _, ...item }) => item)).toEqual(first.trailing.map(({ id: _, ...item }) => item));
    expect(view.emitted('close')).toHaveLength(1);
  });
  it('keeps the home page first on a screen whose firmware starts on page 1 (app 0.4.1)', () => {
    state.inventory.screens[0].page_capability = 'update_screen';
    while (state.document!.pages.length < 3) addPage();
    const order = state.document!.pages.map((page) => page.id);
    expect(movePage(0, 1)).toBe(false);
    expect(movePage(2, 0)).toBe(false);
    expect(state.toast?.message).toBe('Update screen to use the new titlebar and layout');
    expect(movePage(2, 1)).toBe(true);
    expect(state.document!.pages[0].id).toBe(order[0]);
  });
  it('names a drop-created page once and preserves it when more entities are added', () => {
    state.inventory.entities = [{ id: 'light.study', name: 'Desk', area: 'Study' }];
    const count = state.document!.pages.length;
    expect(placeTile({ entity: 'light.study', name: '', slot: -1 }, count * 6)).toBe(true);
    expect(state.document!.pages.at(-1)!.topbar.title).toEqual({ source: 'text', text: 'Study' });
    expect(placeTile({ entity: 'sensor.outside', name: '', slot: -1 }, count * 6 + 1)).toBe(true);
    expect(state.document!.pages.at(-1)!.topbar.title).toEqual({ source: 'text', text: 'Study' });
  });
});
