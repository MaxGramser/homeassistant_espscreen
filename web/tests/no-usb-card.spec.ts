// New screen's red card for a page that cannot reach a USB port (install/NoUsbCard.vue): it says why "In this computer"
// only makes a file here, and for a page on plain http it gives Chrome's setting that treats this Home Assistant's
// address as secure, with the setting's address and the page's own to copy.
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";
import NoUsbCard from "../src/components/install/NoUsbCard.vue";
import { t } from "../src/i18n";

beforeEach(() => setActivePinia(createPinia()));

describe("the card for a page without a USB port", () => {
  it("names a secure address and Chrome's setting on a page over plain http", async () => {
    const copied: string[] = [];
    vi.stubGlobal("isSecureContext", true);
    Object.defineProperty(navigator, "clipboard", { value: { writeText: (text: string) => { copied.push(text); return Promise.resolve(); } }, configurable: true });
    const card = mount(NoUsbCard, { props: { support: "insecure" } });
    expect(card.find("h2").text()).toContain(t("editor.installer.no_usb.insecure_title"));
    expect(card.text()).toContain(t("editor.installer.no_usb.https"));
    expect(card.find("#no-usb-flag-link").text()).toBe("chrome://flags/#unsafely-treat-insecure-origin-as-secure");
    expect(card.find("#no-usb-origin").text()).toBe(window.location.origin);
    await card.find("#no-usb-copy-flag").trigger("click");
    await card.find("#no-usb-copy-origin").trigger("click");
    await Promise.resolve();
    expect(copied).toEqual(["chrome://flags/#unsafely-treat-insecure-origin-as-secure", window.location.origin]);
  });
  it("names Chrome or Edge in a browser that has no USB, without the setting", () => {
    const card = mount(NoUsbCard, { props: { support: "browser" } });
    expect(card.find("h2").text()).toContain(t("editor.installer.no_usb.browser_title"));
    expect(card.find("#no-usb-flag").exists()).toBe(false);
    expect(card.text()).toContain(t("editor.installer.no_usb.else"));
  });
});
