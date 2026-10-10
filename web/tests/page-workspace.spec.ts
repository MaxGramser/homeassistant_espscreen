import { afterEach, expect, it, vi } from 'vitest';
import { workspaceSaver } from '../src/model/page-workspace';
import type { PageLayout, PageWorkspace } from '../src/types';
import examples from '../../tests/fixtures/page-conformance.json';

afterEach(() => vi.useRealTimers());

it('saves a newly selected screen when its timer overlapped an older pending request', async () => {
  vi.useFakeTimers();
  const document = structuredClone(examples[0].document) as PageLayout;
  const id = document.pages[0].id;
  let selected = 'first';
  const state = { busy: false, conflict: false, workspaceDirty: true, documentRevision: 'doc1',
    workspace: { revision: 'map1', positions: { [id]: { x: 1, y: 1 } } } as PageWorkspace };
  let epoch = 1, finish!: (value: PageWorkspace) => void;
  const put = vi.fn().mockImplementationOnce(() => new Promise<PageWorkspace>(resolve => { finish = resolve; }))
    .mockImplementationOnce(async (_screen, _revision, workspace) => ({ ...workspace, revision: 'saved-second' }));
  const saver = workspaceSaver(state, { epoch: () => epoch, selected: () => selected, committed: () => document, put, error: vi.fn() });
  const first = saver.save();
  selected = 'second'; state.documentRevision = 'doc2'; epoch++;
  state.workspace = { revision: 'map2', positions: { [id]: { x: 3, y: 2 } } };
  saver.schedule();
  await vi.advanceTimersByTimeAsync(400);
  expect(put).toHaveBeenCalledTimes(1);
  finish({ revision: 'saved-first', positions: { [id]: { x: 1, y: 1 } } });
  await first;
  expect(state.workspace.revision).toBe('map2');
  await vi.advanceTimersByTimeAsync(400);
  expect(put).toHaveBeenLastCalledWith('second', 'doc2', { revision: 'map2', positions: { [id]: { x: 3, y: 2 } } });
  expect(state.workspace.revision).toBe('saved-second');
  expect(state.workspaceDirty).toBe(false);
});
