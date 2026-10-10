// A screen's settings as the settings page on the screen has them (model/settings.ts): the steps of a duration, a moment
// and a level, and the words of a row.
import { describe, expect, it } from "vitest";
import { durationText, ladderStep, momentText, rowText, SETTING_GROUPS, steppedSetting, type SettingRow } from "../src/model/settings";

const row = (key: string) => SETTING_GROUPS.flatMap((group) => group.rows as readonly SettingRow[]).find((item) => item.key === key)!;

describe("the screen's settings", () => {
  it("steps a duration as settings_screen.h: half minutes low down, half hours up top", () => {
    expect([299, 300, 899, 900, 3599, 3600, 7199, 7200].map(ladderStep)).toEqual([30, 60, 60, 300, 300, 900, 900, 1800]);
    const standby = row("standby_seconds");
    expect(steppedSetting(standby, 270, 1, false, {})).toBe(300);
    expect(steppedSetting(standby, 300, 1, false, {})).toBe(360);
    // Down from a step's edge takes the step below it, so up and down retrace each other.
    expect(steppedSetting(standby, 300, -1, false, {})).toBe(270);
    expect(steppedSetting(standby, 60, -1, false, {})).toBe(60);
    expect(steppedSetting(standby, 86400, 1, false, {})).toBe(86400);
  });

  it("steps a moment by the quarter, whole hours while held, round the clock", () => {
    const start = row("night_start");
    expect(steppedSetting(start, 1425, 1, false, {})).toBe(0);
    expect(steppedSetting(start, 0, -1, false, {})).toBe(1425);
    expect(steppedSetting(start, 440, 1, true, {})).toBe(480);
    expect(steppedSetting(start, 440, -1, true, {})).toBe(420);
    expect(steppedSetting(start, 420, 1, true, {})).toBe(480);
  });

  it("keeps a dim level at most the brightness, as the screen does", () => {
    const dim = row("standby_brightness");
    expect(steppedSetting(dim, 40, 1, false, { brightness: 40 })).toBe(40);
    expect(steppedSetting(dim, 40, 1, false, { brightness: 80 })).toBe(45);
    expect(steppedSetting(row("brightness"), 5, -1, false, {})).toBe(5);
  });

  it("says a row's value with its unit, a duration or a moment, and a dash for none", () => {
    expect(rowText(row("brightness"), { brightness: 60 }, true)).toBe("60%");
    expect(rowText(row("standby_seconds"), { standby_seconds: 5400 }, true)).toBe("1 h 30");
    expect(rowText(row("night_start"), { night_start: 1350 }, true)).toBe("22:30");
    expect(rowText(row("night_start"), { night_start: 1350 }, false)).toBe("10:30 PM");
    expect(rowText(row("night_end"), { night_end: null }, true)).toBe("—");
    expect([45, 120, 7200].map(durationText)).toEqual(["45 sec", "2 min", "2 h"]);
    expect(momentText(30, false)).toBe("12:30 AM");
  });
});
