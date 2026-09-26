/** Canonical card and object checks. Choices are generated from Python's tables;
 * shared conformance fixtures keep the two document boundaries aligned.
 */
import { t } from '../i18n';
import rules from './page-rules.json';
import type { PageLayout, PageTile } from '../types';

const bytes = (s: string) => new TextEncoder().encode(s).length;
const matches = (pattern: RegExp, value: string) => value.match(pattern)?.[0] === value;
function fail(key = 'fields'): never { throw new Error(t(`addon.errors.pages.${key}`)); }
export function fields(value: any, allowed: string[], required = allowed) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).some(k => !allowed.includes(k)) ||
      required.some(k => !(k in value))) fail();
}
const entity = (value: any, domains: string[]) => typeof value === 'string' && value.length <= 120 &&
  matches(/^[a-z0-9_]+\.[a-z0-9_]+$/, value) && domains.includes(value.split('.')[0]);
const icon = (value: any, none = false) => value === 'auto' || (none && value === 'none') || rules.icons.includes(value);
const finite = (value: any): boolean => typeof value === 'number' ? Number.isFinite(value) :
  Array.isArray(value) ? value.every(finite) : value && typeof value === 'object' ? Object.values(value).every(finite) : true;

export function validatePageShape(layout: PageLayout) {
  fields(layout, ['title', 'homePageId', 'pages']);
  if (typeof layout.title !== 'string' || !layout.title.trim() || layout.title !== layout.title.trim() || bytes(layout.title) > 96)
    throw new Error(t('addon.errors.layout.title'));
  if (!Array.isArray(layout.pages)) fail();
  for (const page of layout.pages) {
    fields(page, ['id', 'navigation', 'topbar', 'tiles']);
    fields(page.navigation, ['excludeFromPagination']);
    const bar = page.topbar;
    fields(bar, ['leading', 'title', 'trailing']);
    fields(bar.title, bar.title?.source === 'screen' ? ['source'] : ['source', 'text']);
    if (!Array.isArray(bar.leading) || !Array.isArray(bar.trailing) || !Array.isArray(page.tiles)) fail();
    for (const control of bar.leading) fields(control, ['id', 'kind']);
    const seen = new Set<string>();
    for (const item of bar.trailing) {
      fields(item, ['id', 'type', 'entity', 'content', 'icon', 'show'], ['id', 'type']);
      let key: string;
      if (rules.headerBuiltin.includes(item.type)) {
        fields(item, ['id', 'type']); key = item.type;
      } else {
        if (['content', 'show', 'icon'].some(key => key in item && typeof (item as any)[key] !== 'string')) fail();
        if (item.type !== 'entity' || !entity(item.entity, rules.headerDomains) ||
            !rules.headerContents.includes(item.content ?? 'state') || !rules.headerShows.includes(item.show ?? 'always') ||
            !icon(item.icon ?? 'auto', true)) fail();
        key = JSON.stringify([item.type, item.entity, item.content ?? 'state', item.icon ?? 'auto', item.show ?? 'always']);
      }
      if (seen.has(key)) throw new Error(t('addon.errors.top_bar.twice'));
      seen.add(key);
    }
    for (const tile of page.tiles) {
      fields(tile, ['id', 'content', 'placement', 'appearance', 'interaction']);
      fields(tile.placement, ['row', 'column', 'columns', 'rows']);
      fields(tile.appearance, ['label', 'presentation', 'display', 'icon', 'background', 'historyHours', 'refresh', 'subtitle', 'fit', 'overlay'], ['label']);
      fields(tile.interaction, ['tap', 'inline', 'controls', 'action'], []);
      const content = tile.content;
      fields(content, ['kind', 'entityId', 'name', 'target'], ['kind']);
      if (content.kind === 'entity') {
        fields(content, ['kind', 'entityId']);
        if (!entity(content.entityId, rules.domains)) throw new Error(t('addon.errors.layout.unsupported'));
      } else if (content.kind === 'builtin') {
        fields(content, ['kind', 'name']);
        if (!['clock', 'settings'].includes(content.name)) fail();
      } else if (content.kind === 'navigation') {
        fields(content, ['kind', 'target']);
        fields(content.target, content.target?.kind === 'home' ? ['kind'] : ['kind', 'pageId']);
        if (!['home', 'page'].includes(content.target.kind)) fail();
      } else fail();
    }
  }
}

export function validateCardOptions(tile: PageTile, entityId: string, size: string) {
  const a = tile.appearance, i = tile.interaction, domain = entityId.split('.')[0];
  if ('presentation' in a && typeof a.presentation !== 'string') fail('size');
  if (typeof a.label !== 'string' || bytes(a.label) > 80 || a.label !== a.label.trim()) fail('normalization');
  const displays = (rules.displays as Record<string, string[]>)[domain] || ['standard', 'watch'];
  const controls = ['none', ...((rules.controls as Record<string, string[]>)[domain] || [])];
  for (const [value, choices] of [[a.display, displays], [a.background, rules.backgrounds], [a.historyHours, [1, 6, 24]],
    [i.tap, ['auto', 'detail', 'toggle', 'none', 'action']], [i.inline, ['none', 'slider']], [i.controls, controls]] as [any, any[]][])
    if (value !== undefined && !choices.includes(value)) fail();
  if (a.icon !== undefined && !icon(a.icon)) fail();
  if (rules.wideOnly.includes(a.display || '') && !['wide', 'square', 'full'].includes(size)) fail('normalization');
  if (tile.content.kind === 'navigation' && (size === 'full' || a.display !== undefined || i.inline !== undefined ||
      i.controls !== undefined || a.historyHours !== undefined)) fail('normalization');
  if (i.tap === 'toggle' && domain === 'screen') fail();
  if (i.inline === 'slider' && (!['light', 'fan', 'cover', 'number', 'input_number', 'media_player'].includes(domain) || a.display === 'watch')) fail();
  if (a.refresh !== undefined && (a.display !== 'live' || !rules.refresh.includes(a.refresh))) fail('normalization');
  // How a live picture fills a taller card (app 0.3.8): only with the live picture, and a default is never stored.
  for (const [key, choices] of Object.entries(rules.picture) as [('fit' | 'overlay'), string[]][])
    if (a[key] !== undefined && (a.display !== 'live' || !choices.includes(a[key]!) || a[key] === choices[0])) fail('normalization');
  if (a.subtitle !== undefined) {
    const sub = a.subtitle;
    if (typeof sub !== 'string' || bytes(sub) > 96 || sub === 'auto' ||
        !(sub === 'none' || (sub.startsWith('text:') && sub.length > 5 && !sub.includes('\n')) || matches(/^attr:[a-z_0-9]+$/, sub)) ||
        (sub.startsWith('text:') && (!sub.slice(5).trim() || sub.slice(5) !== sub.slice(5).trim()))) fail('normalization');
  }
  if (i.tap === 'action') {
    if (domain === 'screen') fail();
    const action = i.action;
    fields(action, ['action', 'data'], ['action']);
    if (!action || typeof action.action !== 'string' || action.action.length > 64 || !matches(/^[a-z0-9_]+\.[a-z0-9_]+$/, action.action)) fail();
    const data = action.data ?? {};
    fields(data, Object.keys(data), []);
    if (!finite(data) || Object.keys(data).length > 8 || (action.data !== undefined && !Object.keys(data).length)) fail('normalization');
    const strings: string[][] = [], templates: string[][] = [];
    for (const [key, value] of Object.entries(data)) {
      if (!matches(/^[a-z0-9_]{1,32}$/, key) || ['entity_id', 'device_id', 'area_id', 'floor_id', 'label_id'].includes(key)) fail();
      const serialized = JSON.stringify(JSON.stringify(value)).replace(/[^\x00-\x7f]/g, c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
      const text = typeof value === 'string' ? value : `{{ ${serialized} | from_json }}`;
      if (bytes(text) > 400) fail();
      (typeof value === 'string' ? strings : templates).push([key, text]);
    }
    if (bytes(JSON.stringify({ s: action.action, ...(strings.length ? { d: strings } : {}), ...(templates.length ? { t: templates } : {}) })) > 800) fail();
  } else if (i.action !== undefined) fail('normalization');
}
