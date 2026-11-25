// ---- The steps of a build, as every place that shows one says them (docs/BUILDS.md, "Following a build") ----
// Waits its turn, builds (on the build server or here), sends it to the screen, the screen restarts and says it runs
// what was built. A build that runs is at one step; one that ended has every step done, or the step it stopped at
// failed. The add-on says the ESPHome step it is at (`stage`: compile, upload) and the build's own phase (`verify`: the
// screen restarts), and for one that ended the step it got to and whether the screen confirmed (`verified`).
import type { Build, LineBuild } from "../types";

export type StepKey = "wait" | "build" | "send" | "confirm";
export type StepState = "done" | "now" | "todo" | "failed" | "skipped" | "waits";
export type Step = { key: StepKey; state: StepState };

const ORDER: StepKey[] = ["wait", "build", "send", "confirm"];

/** Which step a build is at, by what the add-on says of it. */
function stepAt(build: Pick<LineBuild, "state" | "stage" | "phase"> & { remote?: string | null }): StepKey {
  if (build.state === "queued") return "wait";
  if (build.phase === "verify") return "confirm";
  if (build.stage === "upload") return "send";
  return "build";
}

/** The steps of a build, or none before it is known. `verified` (an ended build's): false is a screen that came back
 * without what was built, null one that could not tell (the step is skipped, not failed). */
export function stepsOf(build: (Build | LineBuild) & { verified?: boolean | null } | null | undefined): Step[] {
  if (!build) return [];
  const state = build.state as string;
  if (state === "success") {
    return ORDER.map((key) => ({ key, state: key === "confirm" ? (build.verified === false ? "failed" : build.verified ? "done" : "skipped") : "done" }));
  }
  // Built ahead in a round: built, and its install waits for the screens before it to pass their check.
  if (state === "running" && build.phase === "ready")
    return ORDER.map((key) => ({ key, state: key === "wait" || key === "build" ? "done" : key === "send" ? "waits" : "todo" }));
  const at = stepAt(build as LineBuild);
  const index = ORDER.indexOf(at);
  // How the step it got to ended: failed; goes once more at the end of the line (retry: it waits); left out because its
  // round stopped before its turn (skipped: nothing failed here).
  const stopped: StepState | null = state === "failed" || state === "interrupted" ? "failed" : state === "retry" ? "waits"
    : state === "skipped" ? "skipped" : null;
  return ORDER.map((key, i) => ({
    key,
    state: i < index ? "done" : i === index ? (stopped ?? "now") : stopped ? "skipped" : "todo",
  }));
}
