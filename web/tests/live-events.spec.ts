import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { liveEvents } from '../src/live-events';

class Socket {
  static all: Socket[] = [];
  onopen?: () => void;
  onmessage?: (event: { data: string }) => void;
  onclose?: () => void;
  onerror?: () => void;
  close = vi.fn();
  constructor(public url: URL) { Socket.all.push(this); }
}
beforeEach(() => { vi.useFakeTimers(); Socket.all = []; vi.stubGlobal('WebSocket', Socket); });
afterEach(() => { document.querySelector('base')?.remove(); vi.unstubAllGlobals(); vi.useRealTimers(); });

it('uses the ingress path, reconnects, and ignores events from closed connections', () => {
  const base = document.createElement('base'); base.href = 'https://ha.example/api/hassio_ingress/example/'; document.head.append(base);
  const message = vi.fn(), status = vi.fn();
  const stream = liveEvents('api/events?language=en', message, status);
  const first = Socket.all[0];
  expect(first.url.href).toBe('wss://ha.example/api/hassio_ingress/example/api/events?language=en');
  first.onopen!(); first.onmessage!({ data: 'updated' });
  expect(status).toHaveBeenLastCalledWith(true);
  expect(message).toHaveBeenLastCalledWith('updated');
  first.onclose!(); expect(status).toHaveBeenLastCalledWith(false);
  vi.advanceTimersByTime(2000);
  expect(Socket.all).toHaveLength(2);
  first.onmessage!({ data: 'stale' });
  expect(message).toHaveBeenCalledTimes(1);
  stream.close(); expect(Socket.all[1].close).toHaveBeenCalledOnce();
  Socket.all[1].onclose!(); vi.advanceTimersByTime(10000);
  expect(Socket.all).toHaveLength(2);
});

it('cancels a pending reconnect when its preview unmounts', () => {
  const stream = liveEvents('api/events', vi.fn());
  Socket.all[0].onclose!(); stream.close(); vi.advanceTimersByTime(10000);
  expect(Socket.all).toHaveLength(1);
});
