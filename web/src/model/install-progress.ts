// ---- How far a new screen's installation is (app 0.4.32) ----
// The add-on runs ESPHome and hands the page its log; the browser flasher reports its own phase. Neither says "40 %",
// but both say enough to count: ESP-IDF's ninja numbers every step it builds ("[412/1024] Building C object ..."), and
// esptool prints how much it has written ("Writing at 0x00010000... (45 %)", ESPHome's "Uploading: [===   ] 45%").
// This turns that into the few steps a person follows, each with its own share of one bar. Nothing here guesses a
// time: a step without a count is simply running.

export type StepKey = "prepare" | "build" | "write" | "restart" | "done";
export type StepState = "waiting" | "running" | "done" | "failed";
export type Step = { key: StepKey; state: StepState; percent: number | null };
export type Progress = { steps: Step[]; percent: number; failed: boolean; done: boolean };

// What the add-on says about the memory a build has (build_memory.py, app 0.4.65): the machine's cores and free memory
// in MB, the compilers it runs at once, and why that is fewer than the cores, or why the build stopped.
export type MemoryReason = "low" | "tight" | "retry" | "out" | "limit";
export type BuildMemory = { cores: number; free_mb: number | null; need_mb: number; jobs: number; reason: MemoryReason | null };
type Job = { state?: string; stage?: string; action?: string; memory?: BuildMemory | null } | null | undefined;
type Flash = { phase: string; percent: number } | null | undefined;

/**
 * The note a build's memory earns, for the card the installer shows: the reason and the words' numbers, the memory in GB
 * to one decimal (as "1.2", for the page to write in its language). Nothing when the machine has room.
 */
export function memoryNote(job: Job): { reason: MemoryReason; free: string; need: string; jobs: number; cores: number } | null {
  const memory = job?.memory;
  if (!memory?.reason) return null;
  const gb = (mb: number | null | undefined) => (mb === null || mb === undefined ? "?" : (mb / 1024).toFixed(1));
  return { reason: memory.reason, free: gb(memory.free_mb), need: gb(memory.need_mb), jobs: memory.jobs, cores: memory.cores };
}

/** ninja's count in one run of ESPHome: (steps done, steps in all) of the largest total it counted; null without one. */
function ninjaCount(lines: readonly string[]): [number, number] | null {
  let total = 0, done = 0;
  for (const line of lines) {
    for (const part of line.split("\r")) {
      const found = /^\s*(?:\x1b\[[0-9;]*[A-Za-z])*\[(\d+)\/(\d+)\]/.exec(part);
      if (!found || Number(found[2]) <= 0) continue;
      if (Number(found[2]) >= total) { total = Number(found[2]); done = Number(found[1]); }
    }
  }
  return total ? [done, total] : null;
}

/**
 * How far the build is, as a share of 1; null before ninja counts. The build itself has the most steps of every count in
 * the log ("[412/1702]"): the bootloader beside it counts its own few ("[1/123]"), and ESPHome's size report after it
 * starts at "[0/2]", so the count of the largest total is the one to follow (app 0.4.63). A line from an older app can
 * still hold ninja's whole run of updates, each after a carriage return, so every part of a line counts.
 *
 * A build the add-on started again after the memory ran out (app 0.4.65) stands in the log as a second "ESPHome:
 * compile", and ninja counts only the steps left from one: what that run does fills the rest of the bar, after what the
 * first run got done, so the bar goes on instead of jumping back.
 */
export function buildShare(logs: readonly string[]): number | null {
  const runs: string[][] = [[]];
  for (const line of logs) {
    if (line === "ESPHome: compile" && runs[runs.length - 1].length) runs.push([]);
    else runs[runs.length - 1].push(line);
  }
  let share: number | null = null;
  for (const run of runs) {
    const count = ninjaCount(run);
    if (!count) continue;
    const part = Math.min(1, count[0] / count[1]);
    share = share === null ? part : share + (1 - share) * part;
  }
  if (share === null) return null;
  // The image is made and the factory file written: the build is done, whatever ninja counted last.
  if (logs.some((line) => /Creating factory\.bin|Successfully compiled program/.test(line))) return 1;
  return share;
}

// What ESPHome says on its way to the build, before ninja counts anything (app 0.4.63): a first build on a Raspberry Pi
// spends minutes here, setting ESP-IDF up and configuring CMake, and the bar should move while it does.
const GETTING_READY: [RegExp, number][] = [
  [/Reading configuration/, 0.1],
  [/Generating C\+\+ source/, 0.25],
  [/Compiling app/, 0.35],
  [/(Checking|Installing|Downloading) ESP-IDF/i, 0.45],
  [/^-- (The C compiler|Detecting C compiler)/, 0.6],
  [/^-- Building ESP-IDF components/, 0.75],
  [/^-- Configuring done/, 0.88],
  [/^-- Build files have been written/, 0.95],
];
/** How far ESPHome got with getting the build ready, as a share of 1; null before it says anything we know. */
export function readyShare(logs: readonly string[]): number | null {
  let share: number | null = null;
  for (const line of logs)
    for (const [pattern, value] of GETTING_READY)
      if (pattern.test(line) && (share === null || value > share)) share = value;
  return share;
}

/** How much of the image an upload over USB has written, from esptool's or ESPHome's own line; null before it writes. */
export function writeShare(logs: readonly string[]): number | null {
  for (let i = logs.length - 1; i >= 0; i--) {
    const line = logs[i];
    if (!/writing at|uploading|wrote /i.test(line)) continue;
    const found = /(\d{1,3}(?:\.\d+)?)\s*%/.exec(line);
    if (found) return Math.min(1, Number(found[1]) / 100);
    if (/^wrote /i.test(line.trim())) return 1;
  }
  return null;
}

// Each step's part of the one bar. Download has no writing: the build is the whole of it.
const SHARES: Record<"install" | "download", [StepKey, number][]> = {
  install: [["prepare", 0.08], ["build", 0.62], ["write", 0.25], ["restart", 0.05]],
  download: [["prepare", 0.08], ["build", 0.92]],
};

/**
 * The steps and the bar for a job of the add-on, and for this browser's own writing when it installs (`browser`).
 * `mode` "download" builds a file to download and stops there.
 */
export function installProgress(job: Job, logs: readonly string[], opts: { browser?: boolean; mode?: "install" | "download"; flash?: Flash } = {}): Progress {
  const mode = opts.mode ?? (opts.browser ? "install" : job?.action === "download" ? "download" : "install");
  const shares = SHARES[mode];
  const keys = shares.map(([key]) => key);
  const state = job?.state;
  const flash = opts.flash;
  const built = state === "success";
  const buildFailed = !!state && state !== "running" && state !== "success";
  const flashFailed = opts.browser && flash?.phase === "failed";
  const share = buildShare(logs);
  // Where the work stands, as the index of the step running now; the length of the list when all is done.
  let at = 0;
  let within: number | null = null;
  if (built && (!opts.browser || mode === "download")) at = keys.length;
  else if (built && opts.browser) {
    const phase = flash?.phase || "waiting";
    if (phase === "done") at = keys.length;
    else if (phase === "restarting") at = keys.indexOf("restart");
    else { at = keys.indexOf("write"); within = phase === "writing" ? (flash?.percent ?? 0) / 100 : phase === "erasing" ? 0 : null; }
  } else if (job?.stage === "upload") {
    at = keys.indexOf("write");
    within = writeShare(logs);
  } else if (share !== null) {
    at = keys.indexOf("build");
    within = share;
  } else if (state === "running") {
    within = readyShare(logs);
  }
  const failedAt = buildFailed || flashFailed ? Math.min(at, keys.length - 1) : -1;
  const steps: Step[] = shares.map(([key], index) => ({
    key,
    state: index === failedAt ? "failed" : index < at ? "done" : index === at ? (failedAt >= 0 ? "waiting" : "running") : "waiting",
    percent: index === at && within !== null ? Math.round(within * 100) : index < at ? 100 : null,
  }));
  let percent = 0;
  shares.forEach(([, part], index) => {
    if (index < at) percent += part;
    else if (index === at && within !== null) percent += part * within;
  });
  const done = at >= keys.length;
  return { steps: [...steps, { key: "done", state: done ? "done" : "waiting", percent: null }], percent: done ? 100 : Math.round(percent * 100), failed: failedAt >= 0, done };
}
