/** Editor-only map positions: where each page of the map stands, a new page placed where nothing stands yet. The save of
 * the map, revision-checked and on its own, is the document store's (stores/document.ts saveWorkspace). */
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
