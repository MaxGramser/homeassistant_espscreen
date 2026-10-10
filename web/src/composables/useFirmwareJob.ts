// The add-on's firmware job (api/firmware), followed by whoever shows it: New screen, Firmware & USB, a YAML check and,
// while something builds, the store for the build log. One poll for all of them (createSharedComposable): it asks every
// few seconds while one of them follows and the page is in sight, as often as the most eager one wants (a YAML check
// every 1.2 seconds, the rest every three), and stops when the last one goes. Its answers reach every follower
// (onAnswer), so a build is followed with one request at a time however many views show it. A request of a view's own
// (its first look, a choice that needs fresh ports) goes through the builds store's fetchFirmware, which shares an answer
// on its way, and reaches the followers the same way.
import { createSharedComposable, tryOnScopeDispose, useDocumentVisibility, useTimeoutPoll } from "@vueuse/core";
import { computed, effectScope, shallowReactive, toValue, watch, type MaybeRefOrGetter } from "vue";
import { FIRMWARE_POLL_MS, useBuildsStore } from "../stores/builds";

export type FirmwareFollower = {
  /** How often this one wants a new answer, in ms; three seconds unless it says otherwise. */
  interval?: MaybeRefOrGetter<number>;
  /** Whether it follows now (a check that runs, a build); always unless it says otherwise. */
  active?: MaybeRefOrGetter<boolean>;
  /** Every new answer, whoever asked for it. */
  onAnswer?: (data: any) => void;
  /** A poll that failed (the add-on away for a moment); the next one tries again. */
  onError?: (error: Error) => void;
};

const useFirmwarePoll = createSharedComposable(() => {
  const builds = useBuildsStore();
  const followers = shallowReactive(new Set<FirmwareFollower>());
  const active = computed(() => [...followers].filter((follower) => toValue(follower.active ?? true)));
  const interval = computed(() => Math.min(FIRMWARE_POLL_MS, ...active.value.map((follower) => toValue(follower.interval ?? FIRMWARE_POLL_MS))));
  const visible = useDocumentVisibility();
  async function ask() {
    // A failure goes to whoever follows, and the next turn comes all the same.
    try { await builds.fetchFirmware(); } catch (error) { for (const follower of active.value) follower.onError?.(error as Error); }
  }
  const poll = useTimeoutPoll(ask, interval, { immediate: false });
  watch(() => visible.value === "visible" && active.value.length > 0, (on) => (on ? poll.resume() : poll.pause()), { immediate: true });
  // A more eager follower that joins takes its turn from now, not after the turn already waiting.
  watch(interval, () => { if (poll.isActive.value) { poll.pause(); poll.resume(); } });
  return followers;
});

/** Follows the firmware job while the calling component or scope lives. `refresh` asks at once, for a view's first look. */
export function useFirmwareJob(follower: FirmwareFollower = {}) {
  const builds = useBuildsStore();
  const followers = useFirmwarePoll();
  followers.add(follower);
  tryOnScopeDispose(() => followers.delete(follower));
  if (follower.onAnswer) watch(() => builds.answer, (data) => { if (data) follower.onAnswer!(data); });
  return { refresh: () => builds.fetchFirmware(), answer: () => builds.answer };
}

/** The builds' part (boot.ts): while something builds, the job is followed for its log (BuildLog), which stays after a
 * build that failed so it can still be read. Returns the stop. */
export function followBuilds() {
  const builds = useBuildsStore();
  const scope = effectScope(true);
  scope.run(() => useFirmwareJob({ active: () => builds.anyBuilding }));
  return () => scope.stop();
}
