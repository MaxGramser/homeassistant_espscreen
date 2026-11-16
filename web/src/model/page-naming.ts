import type { Entity, Page } from '../types';
import { domainInfo } from './layout';
import { allTiles } from './page-tiles';

/** Suggest once, at creation. Later changes never overwrite a user's title.
 * Prefer a shared HA area, then a shared domain. Mixed content keeps the screen title.
 */
export function suggestedPageTitle(page: Page, entities: Entity[]): string | undefined {
  const ids = allTiles(page).flatMap(tile => tile.content.kind === 'entity' ? [tile.content.entityId] : []);
  if (!ids.length) return;
  const byId = new Map(entities.map(entity => [entity.id, entity]));
  const areas = ids.map(id => byId.get(id)?.area?.trim());
  const title = areas[0] && areas.every(area => area === areas[0]) ? areas[0]
    : ids.every(id => id.split('.')[0] === ids[0].split('.')[0]) ? domainInfo(ids[0])[0] : undefined;
  // HA names may exceed the device's bounded title field. Never truncate UTF-8 bytes mid-character.
  if (!title) return;
  let bounded = '';
  for (const char of title) {
    if (new TextEncoder().encode(bounded + char).length > 96) break;
    bounded += char;
  }
  return bounded.trim() || undefined;
}
