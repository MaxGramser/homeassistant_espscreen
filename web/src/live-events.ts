// Updates use WebSockets so several previews or tabs cannot fill the HTTP/1
// connection pool and block commands. Callers retain their polling fallback.
export function liveEvents(path: string, message: (data: string) => void, status: (open: boolean) => void = () => {}) {
  let socket: WebSocket | null = null, stopped = false;
  let retry: ReturnType<typeof setTimeout> | undefined;
  const url = new URL(path, document.baseURI);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  function connect() {
    if (stopped || typeof WebSocket === 'undefined') return;
    const current = new WebSocket(url);
    socket = current;
    current.onopen = () => { if (socket === current) status(true); };
    current.onmessage = event => { if (socket === current) message(event.data); };
    current.onerror = () => { if (socket === current) status(false); };
    current.onclose = () => {
      if (socket !== current) return;
      socket = null;
      status(false);
      if (!stopped) retry = setTimeout(connect, 2000);
    };
  }
  connect();
  return { close() {
    stopped = true; clearTimeout(retry);
    const current = socket; socket = null;
    current?.close();
  } };
}
