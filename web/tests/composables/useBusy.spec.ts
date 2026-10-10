// Work a part of the page waits for (composables/useBusy.ts).
import { describe, expect, it } from "vitest";
import { useBusy } from "../../src/composables/useBusy";

const later = () => { let done!: (value: string) => void; const promise = new Promise<string>((resolve) => { done = resolve; }); return { promise, done }; };

describe("busy work", () => {
  it("is busy while any of it runs, and not once the last ends, also when it fails", async () => {
    const { busy, run } = useBusy(), first = later(), second = later();
    const a = run(() => first.promise), b = run(() => second.promise);
    expect(busy.value).toBe(true);
    first.done("a");
    expect(await a).toBe("a");
    expect(busy.value).toBe(true);
    second.done("b");
    await b;
    expect(busy.value).toBe(false);
    await expect(run(() => Promise.reject(new Error("refused")))).rejects.toThrow("refused");
    expect(busy.value).toBe(false);
  });
  it("does nothing for a second press while the first runs", async () => {
    const { busy, runOnce } = useBusy(), first = later();
    let calls = 0;
    const a = runOnce(() => { calls++; return first.promise; });
    expect(await runOnce(async () => { calls++; return "second"; })).toBeUndefined();
    first.done("first");
    expect([await a, calls, busy.value]).toEqual(["first", 1, false]);
  });
});
