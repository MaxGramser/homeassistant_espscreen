// Exercise the production decoder through its session-based page protocol.
import assert from 'node:assert/strict';

export function connection(module, request = '1111111111111111', revision = '2222222222222222') {
  const raw = packet => module.ccall('preview_receive', 'string', ['string'], [JSON.stringify(packet)]);
  const granted = raw({ v: 2, op: 'hello', request });
  assert.match(granted, /^Session:[0-9a-f]{16}$/);
  let seq = 0;
  return packet => {
    const result = raw({ ...packet, v: 2, session: granted.slice(8), seq: ++seq, rev: revision });
    assert.ok(['Synced', 'Loading tiles'].includes(result), `${packet.op}: ${result}`);
    return result;
  };
}

// `sections`: the sections of the first page as its message carries them (docs/PAGES.md "Sections", "The protocol").
export function configure(receive, title, pages, tiles, sections) {
  receive({ op: 'begin', title, pages, tiles: tiles.length, home: 0, keepalive: 60 });
  for (let p = 0; p < pages; ++p) receive({ op: 'page', p, id: (p + 1).toString(16).padStart(16, '0'),
    title: '', home_control: false, excluded: false, items: [], ...(p === 0 && sections ? { sections } : {}) });
  tiles.forEach((tile, i) => receive({ ...tile, i, op: 'tile', o: tile.o ?? {} }));
  receive({ op: 'commit' });
}
