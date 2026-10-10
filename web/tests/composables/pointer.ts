// Pointer events as a browser sends them, for the tests of the drags (jsdom has no PointerEvent).
export function pointer(type: string, at: { x?: number; y?: number; id?: number; kind?: string; button?: number } = {}) {
  return Object.assign(new Event(type, { bubbles: true, cancelable: true }),
    { clientX: at.x ?? 0, clientY: at.y ?? 0, pointerId: at.id ?? 1, pointerType: at.kind ?? "mouse", button: at.button ?? 0 }) as unknown as PointerEvent;
}
