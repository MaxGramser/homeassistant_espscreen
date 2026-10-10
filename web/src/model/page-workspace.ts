/** Editor-only map positions and their independent, revision-checked save queue. */
import type { PageLayout, PageWorkspace } from '../types';
import { clone, initialPositions } from './pages';

export function completePositions(document: PageLayout | null, existing: PageWorkspace['positions']) {
  if (!document) return {};
  const positions = clone(existing), defaults = initialPositions(document);
  const occupied = new Set(Object.values(positions).map(point => `${point.x},${point.y}`));
  for (const page of document.pages) if (!positions[page.id]) {
    const point = { ...defaults[page.id] };
    while (occupied.has(`${point.x},${point.y}`)) {
      point.x++;
      if (point.x > 100) { point.x = 0; point.y++; }
    }
    positions[page.id] = point;
    occupied.add(`${point.x},${point.y}`);
  }
  return positions;
}

type State = { busy: boolean; conflict: boolean; workspaceDirty: boolean; selected: string | null;
  documentRevision: string | null; workspace: PageWorkspace };
type Services = { epoch: () => number; committed: () => PageLayout | null;
  put: (screen: string, revision: string, workspace: PageWorkspace) => Promise<PageWorkspace>;
  error: (error: unknown) => void };

export function workspaceSaver(state: State, services: Services) {
  let timer = 0, flight = false;
  function schedule() {
    clearTimeout(timer);
    timer = window.setTimeout(save, 400);
  }
  async function save() {
    const committed = services.committed();
    if (flight || state.busy || state.conflict || !state.workspaceDirty || !state.selected || !state.documentRevision || !committed) return;
    const ids = new Set(committed.pages.map(page => page.id));
    if (Object.keys(state.workspace.positions).some(id => !ids.has(id))) return;
    const screen = state.selected, epoch = services.epoch(), workspace = clone(state.workspace), revision = state.documentRevision;
    flight = true;
    try {
      const saved = await services.put(screen, revision, workspace);
      if (state.selected === screen && services.epoch() === epoch) {
        state.workspace.revision = saved.revision;
        state.workspaceDirty = JSON.stringify(state.workspace.positions) !== JSON.stringify(saved.positions);
        if (state.workspaceDirty) schedule();
      }
    } catch (error) { services.error(error); }
    finally {
      flight = false;
      // A timer for a newly selected screen may have fired while the old
      // request was pending. It still deserves its own save afterwards.
      if (services.epoch() !== epoch && state.workspaceDirty) schedule();
    }
  }
  // Drops a save still waiting for its pause (the store when a test starts again).
  function cancel() { clearTimeout(timer); }
  return { schedule, save, cancel };
}
