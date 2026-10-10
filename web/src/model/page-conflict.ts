/** What a save sent, found again in the add-on's record. Resolving a conflict, which never changes the draft before an
 * authoritative response, is the document store's (stores/document.ts resolveLayoutConflict). */
import type { PageDocument, PageGrid, PageLayout, PageWorkspace, Screen } from '../types';
import { sameGrid, sameValue } from './pages';

// Whether the add-on holds what a save sent, after its answer was lost: the same layout and map, whatever the order the
// add-on wrote their keys in (sameValue), so a save that went through is never taken for a conflict.
export function savedDraft(record: Screen['page_document'], submitted: PageLayout, grid: PageGrid, workspace?: PageWorkspace): record is PageDocument {
  return record?.format === 'pages-v2' && sameGrid(record.sourceGrid, grid) && sameValue(record.layout, submitted) &&
    (!workspace || sameValue(record.workspace?.positions, workspace.positions));
}
