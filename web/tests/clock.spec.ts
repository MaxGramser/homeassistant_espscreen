// The editor's clocks at one moment (model/clock.ts): the top bar, the screensaver and a clock card's faces read the same
// sample, in the screens' language.
import { describe, expect, it } from "vitest";
import { clockSample, handAngles } from "../src/model/clock";

const evening = new Date(2026, 9, 10, 19, 5);

describe("a clock sample", () => {
  it("writes the time and the dates as the screens do, on either clock", () => {
    expect(clockSample(evening, true)).toMatchObject({ time: "19:05", digits: "19:05", date: "Sa 10 Oct", hours: "19", minutes: "05" });
    expect(clockSample(evening.getTime(), false)).toMatchObject({ time: "7:05 PM", digits: "7:05", hours: "7", amPm: "PM" });
    expect(clockSample(evening, true).longDate).toBe("Saturday 10 October");
    expect(clockSample(evening, true).flipDate).toBe("Saturday 10 Oct");
  });
  it("turns an analog clock's hands", () => {
    expect(clockSample(evening, true)).toMatchObject({ hourAngle: 7 * 30 + 2.5, minuteAngle: 30 });
    expect(clockSample(new Date(2026, 9, 10, 0, 0), false)).toMatchObject({ hours: "12", amPm: "AM", hourAngle: 0 });
    // The top bar's clock item turns the same hands.
    expect(handAngles(evening)).toEqual({ hour: 7 * 30 + 2.5, minute: 30 });
  });
});
