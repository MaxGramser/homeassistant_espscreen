// What New screen and Firmware & USB both say of the firmware job (model/firmware-job.ts).
import { describe, expect, it } from "vitest";
import { i18n } from "../src/i18n";
import { afterBrowserBuild, errorLine, firmwareImage, memoryText, usbTarget } from "../src/model/firmware-job";

describe("the firmware job, said once", () => {
  it("says what memory the build has, in the editor's words, and nothing when it has room", () => {
    expect(memoryText({ memory: { cores: 4, free_mb: 1229, need_mb: 2048, jobs: 1, reason: "low" } })).toMatchObject({ reason: "low" });
    expect(memoryText({ memory: { cores: 4, free_mb: 1229, need_mb: 2048, jobs: 1, reason: "low" } })!.text).toContain("1.2 GB");
    expect(memoryText({ memory: { cores: 4, free_mb: 8000, need_mb: 2048, jobs: 4, reason: null } })).toBeNull();
    expect(memoryText(null)).toBeNull();
    expect(i18n.global.locale.value).toBe("en");
  });
  it("names the image a build leaves", () => {
    expect(firmwareImage("hall screen.yaml")).toEqual({ href: "api/firmware/profiles/hall%20screen.yaml/download", name: "hall screen.factory.bin" });
  });
  it("writes the image once the build succeeded and the port waits, and lets go of it when the build failed", () => {
    expect(afterBrowserBuild("running", "waiting")).toBeNull();
    expect(afterBrowserBuild("success", "waiting")).toBe("write");
    expect(afterBrowserBuild("failed", "waiting")).toBe("release");
    expect(afterBrowserBuild("success", "writing")).toBeNull();
    expect(afterBrowserBuild(undefined, "waiting")).toBeNull();
  });
  it("keeps a USB port while it is plugged in, and takes the first one there is otherwise", () => {
    expect(usbTarget("/dev/ttyUSB0", ["/dev/ttyUSB0", "/dev/ttyUSB1"])).toBe("/dev/ttyUSB0");
    expect(usbTarget("/dev/ttyUSB2", ["/dev/ttyUSB1"])).toBe("/dev/ttyUSB1");
    expect(usbTarget("/dev/ttyUSB2", [])).toBe("usb");
    expect(usbTarget("usb", ["/dev/ttyUSB1"])).toBe("/dev/ttyUSB1");
    expect(usbTarget("ota", [])).toBe("ota");
  });
  it("finds the line that says what went wrong", () => {
    expect(errorLine(["INFO Reading", "ERROR display: unknown model", "Failed config"])).toBe("ERROR display: unknown model");
    expect(errorLine(["INFO Reading", "Compile failed"])).toBe("Compile failed");
    expect(errorLine(["INFO Done"])).toBeUndefined();
  });
});
