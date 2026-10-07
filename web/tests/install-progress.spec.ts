// How far a new screen's installation is (app 0.4.32): counted from ESPHome's own log and the browser flasher's phase,
// never guessed.
import { describe, expect, it } from "vitest";
import { buildShare, installProgress, memoryNote, readyShare, writeShare } from "../src/model/install-progress";

const states = (p: ReturnType<typeof installProgress>) => p.steps.map((step) => `${step.key}:${step.state}${step.percent !== null ? `:${step.percent}` : ""}`);

describe("the steps of an installation", () => {
  it("reads ninja's count while it builds, and esptool's percentage while it writes", () => {
    expect(buildShare(["INFO Compiling app...", "[312/1184] Building C object a.c.obj", "[592/1184] Building C object b.c.obj"])).toBe(0.5);
    expect(buildShare(["INFO Reading configuration"])).toBeNull();
    expect(writeShare(["Connecting....", "Writing at 0x00064000... (58 %)"])).toBe(0.58);
    expect(writeShare(["Uploading: [=====     ] 45%"])).toBe(0.45);
    expect(writeShare(["Wrote 1581184 bytes"])).toBe(1);
    expect(writeShare(["Chip is ESP32-S3"])).toBeNull();
  });

  it("gets ready, builds and writes over USB on the Home Assistant machine, one bar for all of it", () => {
    const job = { state: "running", stage: "compile", action: "install" };
    expect(states(installProgress(job, ["INFO Reading configuration"]))).toEqual(["prepare:running:10", "build:waiting", "write:waiting", "restart:waiting", "done:waiting"]);
    const building = installProgress(job, ["[592/1184] Building"]);
    expect(states(building)).toEqual(["prepare:done:100", "build:running:50", "write:waiting", "restart:waiting", "done:waiting"]);
    expect(building.percent).toBe(39);
    const writing = installProgress({ ...job, stage: "upload" }, ["[1184/1184] Linking", "Writing at 0x1000... (40 %)"]);
    expect(states(writing)[2]).toBe("write:running:40");
    expect(writing.percent).toBe(80);
    const done = installProgress({ state: "success", stage: "upload", action: "install" }, ["Wrote 1 bytes"]);
    expect(done.done).toBe(true);
    expect(done.percent).toBe(100);
  });

  it("follows the build itself, not the bootloader beside it or the size report after it (app 0.4.63)", () => {
    // ninja rewrites one line in place; an older app kept the whole run of updates in one line of the log.
    expect(buildShare(["[0/2] Re-checking\x1b[K\r[1/1702] Performing build step for 'bootloader'\x1b[K\r[851/1702] Building C object x.c.obj\x1b[K"])).toBe(0.5);
    expect(buildShare(["[851/1702] Building C object x.c.obj", "[1/123] Building C object esp-idf/log/util.c.obj", "[60/123] b"])).toBe(0.5);
    expect(buildShare(["[1701/1702] Linking", "Executing \"ninja -j 4 size\"...", "[0/2] Re-checking globbed directories...", "[4/5] Completed 'bootloader'"])).toBeCloseTo(1701 / 1702);
    expect(buildShare(["[1701/1702] Linking", "[0/2] Re-checking", "INFO Creating factory.bin..."])).toBe(1);
    const job = { state: "running", stage: "compile", action: "install" };
    expect(states(installProgress(job, ["[1702/1702] done", "[0/2] Re-checking"]))[1]).toBe("build:running:100");
  });

  it("moves through getting ready before ninja counts anything (app 0.4.63)", () => {
    expect(readyShare(["INFO ESPHome 2026.9.0"])).toBeNull();
    expect(readyShare(["INFO Reading configuration x.yaml...", "INFO Generating C++ source...", "INFO Compiling app... Build path: /data"])).toBe(0.35);
    expect(readyShare(["INFO Checking ESP-IDF 5.5.5 framework ...", "-- Configuring done (13.4s)"])).toBe(0.88);
    const job = { state: "running", stage: "compile", action: "install" };
    expect(states(installProgress(job, ["INFO Compiling app...", "-- Build files have been written to: /data/build"]))[0]).toBe("prepare:running:95");
  });

  it("goes on from where a build stopped when the add-on starts it again with one compiler (app 0.4.65)", () => {
    // The memory ran out at step 851 of 1702; ninja counts the 851 that are left from one in the second run.
    const first = ["ESPHome: compile", "[851/1702] Building CXX object main.cpp.obj", "xtensa-esp-elf-g++: fatal error: Killed signal terminated program cc1plus"];
    expect(buildShare(first)).toBe(0.5);
    expect(buildShare([...first, "ESPHome: compile", "INFO Compiling app..."])).toBe(0.5);
    expect(buildShare([...first, "ESPHome: compile", "[1/11] Performing build step for 'bootloader'"])).toBeCloseTo(0.5 + 0.5 / 11);
    expect(buildShare([...first, "ESPHome: compile", "[1/11] bootloader", "[425/851] Building CXX object page_receiver.cpp.obj"])).toBeCloseTo(0.75, 2);
    expect(buildShare([...first, "ESPHome: compile", "[851/851] Linking", "INFO Creating factory.bin..."])).toBe(1);
    // One run, as it always was.
    expect(buildShare(["ESPHome: compile", "[312/1184] a", "[592/1184] b"])).toBe(0.5);
  });

  it("tells what the add-on found out about the machine's memory, in GB to one decimal (app 0.4.65)", () => {
    expect(memoryNote({ state: "running", memory: { cores: 4, free_mb: 8000, need_mb: 1500, jobs: 4, reason: null } })).toBeNull();
    expect(memoryNote({ state: "running" })).toBeNull();
    expect(memoryNote({ state: "running", memory: { cores: 4, free_mb: 1258, need_mb: 1500, jobs: 1, reason: "tight" } }))
      .toEqual({ reason: "tight", free: "1.2", need: "1.5", jobs: 1, cores: 4 });
    expect(memoryNote({ state: "failed", memory: { cores: 4, free_mb: null, need_mb: 1500, jobs: 1, reason: "out" } })?.free).toBe("?");
  });

  it("marks the step it stopped in when it fails, and keeps the rest waiting", () => {
    const failed = installProgress({ state: "failed", stage: "compile", action: "install" }, ["[980/1184] Building", "error: expected ;"]);
    expect(failed.failed).toBe(true);
    expect(states(failed)).toEqual(["prepare:done:100", "build:failed:83", "write:waiting", "restart:waiting", "done:waiting"]);
  });

  it("only builds for a download, and follows the browser's own writing when this computer installs", () => {
    expect(installProgress({ state: "running", stage: "compile", action: "download" }, ["[1/2] a"]).steps.map((s) => s.key)).toEqual(["prepare", "build", "done"]);
    const job = { state: "success", stage: "compile", action: "download" };
    expect(states(installProgress(job, [], { browser: true, flash: { phase: "writing", percent: 30 } }))[2]).toBe("write:running:30");
    expect(states(installProgress(job, [], { browser: true, flash: { phase: "restarting", percent: 100 } }))[3]).toBe("restart:running");
    expect(installProgress(job, [], { browser: true, flash: { phase: "done", percent: 100 } }).done).toBe(true);
    expect(installProgress(job, [], { browser: true, flash: { phase: "failed", percent: 12 } }).failed).toBe(true);
  });
});
