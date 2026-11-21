import { describe, expect, it } from "vitest";
import { cardHead, cardLook } from "../src/model/card-layout";

describe("per-tile icon and text layout", () => {
  const shape = { width: 640, height: 180, dpi: 196, look: "compact" };
  const look = cardLook(shape);
  const room = { width: 125, height: 104, outer: 114, padY: 4 };

  it("stacks a short single-cell card only when requested", () => {
    expect(cardHead(shape, look, room, 0, "", true).title.center).toBeUndefined();
    const stack = cardHead(shape, look, room, 0, "", true, false, true, "vertical");
    expect(stack.title.center).toBe(true);
    expect(stack.title.y).toBeGreaterThan(stack.circle.y + stack.circle.size);
    expect(stack.value).not.toBeNull();
    expect(stack.value!.y + stack.value!.line).toBeLessThanOrEqual(room.height);
  });

  it("keeps the row when explicitly requested or when a stack would not fit", () => {
    const tall = { ...room, height: 145, outer: 155 };
    expect(cardHead(shape, look, tall, 0, "", true).title.center).toBe(true);
    expect(cardHead(shape, look, tall, 0, "", true, false, true, "horizontal").title.center).toBeUndefined();
    expect(cardHead(shape, look, { ...room, height: 34 }, 0, "", true, false, true, "vertical").title.center).toBeUndefined();
  });
});
