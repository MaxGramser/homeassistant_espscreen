/** Conflict recovery never changes the draft before an authoritative response. */
import type { PageDocument, PageGrid, PageLayout, PageWorkspace, Screen } from '../types';
import { sameGrid, sameValue } from './pages';

// Whether the add-on holds what a save sent, after its answer was lost: the same layout and map, whatever the order the
// add-on wrote their keys in (sameValue), so a save that went through is never taken for a conflict.
export function savedDraft(record: Screen['page_document'], submitted: PageLayout, grid: PageGrid, workspace?: PageWorkspace): record is PageDocument {
  return record?.format === 'pages-v2' && sameGrid(record.sourceGrid, grid) && sameValue(record.layout, submitted) &&
    (!workspace || sameValue(record.workspace?.positions, workspace.positions));
}

type State = { busy: boolean; conflict: boolean; reachable: boolean; selected: string | null;
  dirty: boolean; documentRevision: string | null; workspace: PageWorkspace };
type Services = { epoch: () => number; refresh: () => Promise<void>; screen: () => Screen | undefined;
  load: (screen: Screen) => void; acceptBase: (record: PageDocument) => void; save: () => Promise<void> };

export async function resolveConflict(choice: 'reload' | 'keep', state: State, services: Services) {
  if (state.busy || !state.conflict) return;
  const selected = state.selected, epoch = services.epoch();
  await services.refresh();
  if (!state.reachable || state.selected !== selected || services.epoch() !== epoch) return;
  const screen = services.screen(), record = screen?.page_document;
  if (!screen || record?.format !== 'pages-v2') return;
  if (choice === 'reload') {
    services.load(screen);
    state.dirty = false;
    return;
  }
  // Keep mine authorizes only this observed revision. A subsequent concurrent
  // save still fails the server's revision check.
  state.documentRevision = record.revision;
  state.workspace.revision = record.workspace?.revision || '';
  services.acceptBase(record);
  await services.save();
}
