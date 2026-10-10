// A screen as the sidebar and the overview tell it (model/screen-status.ts, model/overview.ts): the status line, the
// light, what an update brings and the home page the overview draws, from the screen and the facts handed in.
import { describe, expect, it } from "vitest";
import { t } from "../src/i18n";
import { homeView, SMALLEST } from "../src/model/overview";
import { buildProgress, firmwareVersion, languageOnly, needsAttention, screenLight, screenSubline, updateState, whatsNew,
  type StatusFacts } from "../src/model/screen-status";
import type { Screen } from "../src/types";
import { screenFixture } from "./helpers/fixtures";

const NOW = Date.UTC(2026, 9, 10);
const quiet: StatusFacts = { build: null, asked: false, language: "Nederlands", now: NOW };
const screen = (more: Partial<Screen> = {}) => ({ id: "hall", name: "Hall", online: true, firmware: "0.50.0", board: "guition",
  layout: { title: "Hall", tiles: [] }, update: { profile: "hall.yaml" }, ...more }) as Screen;

describe("a screen's status", () => {
  it("is quiet for a healthy screen, and down when it is away", () => {
    expect(updateState(screen(), quiet)).toBeNull();
    expect(screenLight(screen(), quiet)).toBe("ok");
    expect(screenSubline(screen(), quiet)).toBeNull();
    expect(screenLight(screen({ online: false }), quiet)).toBe("down");
    expect(screenSubline(screen({ online: false }), quiet)).toEqual({ kind: "down", text: t("editor.common.offline") });
    expect(needsAttention(screen({ online: false }), quiet)).toBe(true);
    expect(screenLight(screen({ virtual: true, online: false }), quiet)).toBe("ok");
  });

  it("offers an update, names a new language alone by its name, and says why one cannot be built here", () => {
    const update = { profile: "hall.yaml", available: true, target: "0.51.0" };
    expect(updateState(screen({ update }), quiet)).toEqual({ kind: "available", text: t("editor.sidebar.update.available", { version: "0.51.0" }) });
    const language = screen({ firmware: "0.51.0", update: { profile: "hall.yaml", language: true, target: "0.51.0" } });
    expect(languageOnly(language)).toBe(true);
    expect(updateState(language, quiet)?.text).toBe(t("editor.update.new_language", { name: "Nederlands" }));
    const foreign = screen({ update: { available: true, target: "0.51.0" } });
    expect(updateState(foreign, quiet)?.kind).toBe("blocked");
    expect(screenSubline(foreign, quiet)).toEqual({ kind: "update", text: t("editor.sidebar.update.available", { version: "0.51.0" }) });
    expect(screenLight(foreign, quiet)).toBe("update");
  });

  it("follows a build: asked for, queued, running with its stage, and the result of a day", () => {
    expect(updateState(screen(), { ...quiet, asked: true })?.kind).toBe("running");
    expect(updateState(screen(), { ...quiet, build: { by: "update", state: "queued" } })?.kind).toBe("queued");
    const running = { ...quiet, build: { by: "plugins" as const, state: "running" as const, stage: "upload" } };
    expect(updateState(screen(), running)).toEqual({ kind: "running", text: t("editor.build.plugins") });
    expect(buildProgress(screen(), running)).toEqual({ percent: 66, text: t("editor.update.writing") });
    expect(buildProgress(screen(), quiet)).toBeNull();
    const failed = screen({ update: { profile: "hall.yaml", result: { state: "failed", message: "Out of memory", time: NOW / 1000 - 60 } } });
    expect(updateState(failed, quiet)).toEqual({ kind: "failed", text: "Out of memory" });
    expect(screenLight(failed, quiet)).toBe("down");
    expect(updateState(failed, { ...quiet, now: NOW + 86400000 })).toBeNull();
  });

  it("goes by the firmware the add-on worked out, and lists what an update brings to this board", () => {
    expect(firmwareVersion(screen({ firmware: "0.50.0 (dev)", firmware_known: "0.50.0" } as Partial<Screen>))).toBe("0.50.0");
    expect(firmwareVersion(screen({ firmware: "0.49.0" }))).toBe("0.49.0");
    const changelog = [
      { app: "0.4.90", firmware: "0.52.0", lines: ["Later."] },
      { app: "0.4.89", firmware: "0.51.0", lines: ["Shared.", "Both."] },
      { app: "0.4.88", firmware: "0.50.1", lines: ["CYD only.", "Both."], boards: ["cyd"] },
      { app: "0.4.87", firmware: "0.50.0", lines: ["Already there."] },
    ];
    expect(whatsNew(screen({ update: { target: "0.51.0" } }), changelog)).toEqual(["Shared.", "Both."]);
    expect(whatsNew(screen({ board: "cyd" }), changelog, "0.51.0")).toEqual(["Shared.", "Both.", "CYD only."]);
    expect(whatsNew(screen(), undefined, "0.51.0")).toEqual([]);
    expect(whatsNew(screen(), changelog)).toEqual([]);
  });
});

describe("the overview's home page of a screen", () => {
  it("draws the home page on its own grid and glass, with its keys, its title and the home key", () => {
    const hall = screenFixture(screen({ firmware: "0.3.0", shape: { width: 800, height: 480, columns: 3, rows: 2, dpi: 133, look: "standard" },
      layout: { title: "Hall", page_titles: ["", "Lights"], tiles: [{ entity: "light.a", name: "", slot: 0 }, { entity: "light.b", name: "", slot: 6 }] } }));
    const view = homeView(hall)!;
    expect(view.tiles.map(({ tile }) => tile.entity)).toEqual(["light.a"]);
    expect(view.grid).toEqual({ columns: 3, rows: 2, slots: 6 });
    expect(view.title).toBe("Hall");
    expect(view.compact).toBe(false);
    expect(view.style["--mockup-width"]).toBe("500px");
    expect(view.home).toBe(true);
    expect(homeView({ ...hall, settings: { values: { home_button: false } } } as Screen)!.home).toBe(false);
    expect(homeView({ ...hall, firmware: "0.2.99" })!.home).toBe(false);
    const record = hall.page_document as any;
    record.layout.homePageId = record.layout.pages[1].id;
    expect(homeView(hall)!.tiles.map(({ tile }) => tile.entity)).toEqual(["light.b"]);
    expect(homeView(hall)!.title).toBe("Lights");
  });

  it("draws a screen of no known shape as the smallest one, and none without a page document", () => {
    const bare = screenFixture(screen({ shape: undefined }));
    expect(homeView(bare)!.shape).toEqual(SMALLEST);
    expect(homeView(bare)!.compact).toBe(true);
    expect(homeView(screen())).toBeNull();
  });
});
