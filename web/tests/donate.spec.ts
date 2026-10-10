// The quiet ask for support on the overview (DonateCard): two days after the first visit, a week after Maybe later, a
// month after a link, never after I already donated, as this browser keeps it ("esp-screens.donate").
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import DonateCard from "../src/components/DonateCard.vue";
import { MOMENT, useFakeClock } from "./helpers/clock";

const DAY = 86_400_000;
const shown = () => mount(DonateCard).find(".donate").exists();

describe("the ask for support", () => {
  it("waits two days after the first visit, then a week after Maybe later", () => {
    useFakeClock();
    expect(shown()).toBe(false);
    expect(localStorage.getItem("esp-screens.donate")).toBe(String(MOMENT + 2 * DAY));
    vi.setSystemTime(MOMENT + 2 * DAY);
    const card = mount(DonateCard);
    expect(card.find(".donate").exists()).toBe(true);
    card.find(".donate-close").trigger("click");
    expect(localStorage.getItem("esp-screens.donate")).toBe(String(MOMENT + 9 * DAY));
    vi.setSystemTime(MOMENT + 8 * DAY);
    expect(shown()).toBe(false);
  });
  it("never comes back after I already donated, and asks nothing where the browser keeps nothing", async () => {
    useFakeClock();
    localStorage.setItem("esp-screens.donate", "0");
    const card = mount(DonateCard);
    await card.findAll(".donate-quiet .donate-link")[1].trigger("click");
    expect(localStorage.getItem("esp-screens.donate")).toBe("donated");
    vi.setSystemTime(MOMENT + 1000 * DAY);
    expect(shown()).toBe(false);
    const blocked = () => { throw new DOMException("The operation is insecure.", "SecurityError"); };
    vi.stubGlobal("localStorage", { getItem: blocked, setItem: blocked, removeItem: blocked });
    expect(shown()).toBe(false);
  });
});
