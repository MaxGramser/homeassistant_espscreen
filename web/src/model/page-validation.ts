/** Canonical card and object checks. Choices are generated from Python's tables;
 * shared conformance fixtures keep the two document boundaries aligned.
 */
import { t } from '../i18n';
import { isWideSize } from './sizes';
import { TILE, ofType, taps as catalogueTaps } from './catalogue';
import { PLUGIN_LIST_MAX, PLUGIN_OPTIONS_BYTES, PLUGIN_TILE } from './plugins';
import rules from './page-rules.json';
import type { PageLayout, PageTile } from '../types';

const bytes = (s: string) => new TextEncoder().encode(s).length;
const matches = (pattern: RegExp, value: string) => value.match(pattern)?.[0] === value;
function fail(key = 'fields'): never { throw new Error(t(`addon.errors.pages.${key}`)); }
export function fields(value: any, allowed: string[], required = allowed) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).some(k => !allowed.includes(k)) ||
      required.some(k => !(k in value))) fail();
}
// A calendar card's choices (firmware 0.56.0), as the page document names them.
const CALENDAR_FIELDS = ['calendarStyle', 'calendarEntities', 'calendarPlaces', 'calendarWords', 'calendarHideWords', 'calendarAllDay',
  'calendarTentative', 'calendarPrivate', 'calendarAhead', 'calendarSoon', 'calendarStartView'] as const;
// ... and its week and booking (the add-on's page_layout.APPEARANCE has them; calendar_feed.validate checks them).
const CALENDAR_MORE = ['calendarWeekStart', 'calendarHours', 'calendarWeekNumbers', 'calendarBookOn', 'calendarBookPlace', 'calendarBookTitle'] as const;
// A sensor's meter (firmware 0.56.0, meter.validate), as the page document names it.
const METER_FIELDS = ['meterStyle', 'meterMin', 'meterMax', 'meterSegments', 'meterColors', 'meterThresholds'] as const;
const entity = (value: any, domains: string[]) => typeof value === 'string' && value.length <= 120 &&
  matches(/^[a-z0-9_]+\.[a-z0-9_]+$/, value) && domains.includes(value.split('.')[0]);
const icon = (value: any, none = false) => value === 'auto' || (none && value === 'none') || rules.icons.includes(value);
// A plugin tile's options in their kept shape (the add-on's core.plugin_options): at most 12, each a short text, a
// number, true/false, a pick {value, label}, or a list of up to 16 texts or picks (plugin API 0.12), together at most
// PLUGIN_OPTIONS_BYTES of JSON. Whether a value fits its option is the plugin's manifest's.
const pluginText = (value: any, empty = true) => typeof value === 'string' && (empty || value !== '') && [...value].length <= 64;
const pluginPick = (value: any) => !!value && typeof value === 'object' && !Array.isArray(value) &&
  Object.keys(value).every((k) => k === 'value' || k === 'label') && pluginText(value.value, false) && pluginText(value.label ?? '');
export function pluginOptionsShape(options: any): boolean {
  if (!options || typeof options !== 'object' || Array.isArray(options) || Object.keys(options).length > 12) return false;
  for (const [key, value] of Object.entries(options)) {
    if (!/^[a-z][a-z0-9_]{0,31}$/.test(key)) return false;
    if (Array.isArray(value)) {
      if (value.length > PLUGIN_LIST_MAX || !value.every((item) => pluginText(item, false) || pluginPick(item))) return false;
    } else if (value && typeof value === 'object') {
      if (!pluginPick(value)) return false;
    } else if (typeof value === 'string') {
      if (!pluginText(value)) return false;
    } else if (!(typeof value === 'boolean' || (typeof value === 'number' && Number.isFinite(value)))) return false;
  }
  return bytes(JSON.stringify(options)) <= PLUGIN_OPTIONS_BYTES;
}
const finite = (value: any): boolean => typeof value === 'number' ? Number.isFinite(value) :
  Array.isArray(value) ? value.every(finite) : value && typeof value === 'object' ? Object.values(value).every(finite) : true;

// Plugin tiles and items are an experiment: the add-on accepts them only once it serves plugins (docs: the plugins
// proposal), which `plugins` says (the plugins store's pluginsEnabled, handed in with the grid, model/pages.ts).
export function validatePageShape(layout: PageLayout, plugins = false) {
  fields(layout, ['title', 'homePageId', 'pages']);
  // An empty title is a screen without one (firmware 0.17.0+): the top bar shows its home key alone.
  if (typeof layout.title !== 'string' || layout.title !== layout.title.trim() || bytes(layout.title) > 96)
    throw new Error(t('addon.errors.layout.title'));
  if (!Array.isArray(layout.pages)) fail();
  for (const page of layout.pages) {
    fields(page, ['id', 'navigation', 'topbar', 'tiles', 'icon'], ['id', 'navigation', 'topbar', 'tiles']);
    fields(page.navigation, ['excludeFromPagination', 'showInDock'], ['excludeFromPagination']);
    const bar = page.topbar;
    fields(bar, ['leading', 'title', 'trailing']);
    fields(bar.title, bar.title?.source === 'screen' ? ['source'] : ['source', 'text']);
    if (!Array.isArray(bar.leading) || !Array.isArray(bar.trailing) || !Array.isArray(page.tiles)) fail();
    for (const control of bar.leading) fields(control, ['id', 'kind']);
    const seen = new Set<string>();
    for (const item of bar.trailing) {
      fields(item, ['id', 'type', 'entity', 'content', 'icon', 'show', 'item'], ['id', 'type']);
      let key: string;
      if (item.type === 'plugin' && plugins) {
        // A plugin's item (docs/PLUGINS.md): it says itself what it shows, with its words or as its icon alone (0.8).
        fields(item, ['id', 'type', 'item', 'content'], ['id', 'type', 'item']);
        if (!/^plugin:[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$/.test(String(item.item))) fail();
        if (item.content !== undefined && !rules.pluginContents.includes(String(item.content))) fail();
        key = JSON.stringify(['plugin', item.item]);
      } else if (rules.headerBuiltin.includes(item.type) || item.type === rules.headerLink) {
        fields(item, ['id', 'type']); key = item.type;
      } else if (item.type === rules.headerWifi || item.type === rules.headerBattery) {
        // The screen's own Wi-Fi item (firmware 0.38.0) and its battery (firmware 0.41.0): what each shows beside its
        // icon, and when.
        fields(item, ['id', 'type', 'content', 'show'], ['id', 'type']);
        const [contents, shows] = item.type === rules.headerWifi ? [rules.wifiContents, rules.wifiShows] : [rules.batteryContents, rules.batteryShows];
        if (!contents.includes(item.content ?? 'icon') || !shows.includes(item.show ?? 'always')) fail();
        key = JSON.stringify([item.type, item.content ?? 'icon', item.show ?? 'always']);
      } else {
        if (['content', 'show', 'icon'].some(key => key in item && typeof (item as any)[key] !== 'string')) fail();
        if (item.type !== 'entity' || !entity(item.entity, rules.headerDomains) ||
            !rules.headerContents.includes(item.content ?? 'state') || !rules.headerShows.includes(item.show ?? 'always') ||
            !icon(item.icon ?? 'auto', true) || (item.content === 'icon' && item.icon === 'none')) fail();
        key = JSON.stringify([item.type, item.entity, item.content ?? 'state', item.icon ?? 'auto', item.show ?? 'always']);
      }
      if (seen.has(key)) throw new Error(t('addon.errors.top_bar.twice'));
      seen.add(key);
    }
    for (const tile of page.tiles) {
      fields(tile, ['id', 'content', 'placement', 'appearance', 'interaction', 'children'], ['id', 'content', 'placement', 'appearance', 'interaction']);
      fields(tile.placement, ['row', 'column', 'columns', 'rows']);
      fields(tile.appearance, ['label', 'presentation', 'display', 'icon', 'background', 'historyHours', 'refresh', 'subtitle', 'fit', 'overlay',
        'mapEntities', 'mapFraming', 'mapDistance', 'mapFollow', 'mapMarkers', 'mapNames', 'mapZones', 'mapStreets', 'mapLook', 'energyFlow',
        ...CALENDAR_FIELDS, ...CALENDAR_MORE, ...METER_FIELDS], ['label']);
      fields(tile.interaction, ['tap', 'inline', 'controls', 'action', 'guard', 'play', 'speaker', 'shuffle', 'repeat'], []);
      const content = tile.content;
      fields(content, ['kind', 'entityId', 'name', 'target', 'plugin', 'tile', 'options'], ['kind']);
      if (content.kind === 'entity') {
        fields(content, ['kind', 'entityId']);
        if (!entity(content.entityId, rules.domains)) throw new Error(t('addon.errors.layout.unsupported'));
      } else if (content.kind === 'builtin') {
        fields(content, ['kind', 'name']);
        if (!rules.builtins.includes(content.name)) fail();
      } else if (content.kind === 'navigation') {
        fields(content, ['kind', 'target']);
        fields(content.target, content.target?.kind === 'home' ? ['kind'] : ['kind', 'pageId']);
        if (!['home', 'page'].includes(content.target.kind)) fail();
      } else if (content.kind === 'plugin' && plugins) {
        // A plugin's tile type (design): a known plugin and tile, and options of plain values the manifest checks.
        fields(content, ['kind', 'plugin', 'tile', 'entityId', 'options'], ['kind', 'plugin', 'tile']);
        if (!/^[a-z0-9_]+$/.test(String(content.plugin)) || !/^[a-z0-9_]+$/.test(String(content.tile))) fail();
        if (content.entityId !== undefined && !/^[a-z0-9_]+\.[a-z0-9_]+$/.test(String(content.entityId))) fail();
        if (content.options !== undefined && !pluginOptionsShape(content.options)) fail();
      } else fail();
      // A bedside clock's keys (app 0.4.12): tiles without a place, at most three, only under the bedside clock.
      if (tile.children !== undefined) {
        const holds = content.kind === 'builtin' ? (rules.keyHolders as Record<string, number>)[`screen.${content.name}`] : undefined;
        if (!Array.isArray(tile.children) || !holds || tile.children.length > holds) fail();
        for (const child of tile.children) {
          fields(child, ['id', 'content', 'appearance', 'interaction']);
          fields(child.content, ['kind', 'entityId']);
          fields(child.appearance, ['label', 'icon', 'overlay'], ['label']);
          fields(child.interaction, ['tap', 'action', 'guard'], []);
          if (child.content.kind !== 'entity' || !entity(child.content.entityId, rules.keyDomains))
            throw new Error(t('addon.errors.layout.unsupported'));
        }
      }
    }
  }
}

export function validateCardOptions(tile: PageTile, entityId: string, size: string) {
  const a = tile.appearance, i = tile.interaction, domain = entityId.split('.')[0];
  if ('presentation' in a && typeof a.presentation !== 'string') fail('size');
  // A name too long for the screen says so (app 0.4.1): emoji and accents count their bytes, not their letters.
  if (typeof a.label === 'string' && bytes(a.label) > 80) throw new Error(t('addon.errors.layout.tile_name'));
  if (typeof a.label !== 'string' || a.label !== a.label.trim()) fail('normalization');
  // The map tile (app 0.4.36) is a map and nothing else.
  const displays = entityId === 'screen.map' ? ['map'] : (rules.displays as Record<string, string[]>)[domain] || ['standard', 'watch'];
  const controls = ['none', ...((rules.controls as Record<string, string[]>)[domain] || [])];
  // Every choice from the tile catalogue (model/catalogue.ts): a type's taps, its guards, the hours a graph shows.
  for (const [value, choices] of [[a.display, displays], [a.background, rules.backgrounds], [a.historyHours, TILE.history_hours],
    // A plugin's tap action (plugin:<plugin>.<action>, docs/PLUGINS.md) goes on any tile, as the add-on takes it
    // (core.validate_layout): which tiles it suits is its manifest's, and a screen without the plugin does nothing.
    [PLUGIN_TILE.test(String(i.tap ?? '')) ? undefined : i.tap, catalogueTaps(domain)], [i.inline, ['none', 'slider']], [i.controls, controls],
    [i.guard, ofType(domain)?.guards ?? []]] as [any, any[]][])
    if (value !== undefined && !choices.includes(value)) fail();
  if (a.icon !== undefined && !icon(a.icon)) fail();
  if (rules.wideOnly.includes(a.display || '') && !isWideSize(size)) fail('normalization');
  if (tile.content.kind === 'navigation' && (size === 'full' || a.display !== undefined || i.inline !== undefined ||
      i.controls !== undefined || a.historyHours !== undefined)) fail('normalization');
  if (i.tap === 'toggle' && domain === 'screen') fail();
  if (i.inline === 'slider' && (!ofType(domain)?.inline || a.display === 'watch')) fail();
  if (a.refresh !== undefined && (a.display !== 'live' || !rules.refresh.includes(a.refresh))) fail('normalization');
  // How a live picture fills a taller card (app 0.3.8): only with the live picture, and a default is never stored.
  for (const [key, choices] of Object.entries(rules.picture) as [('fit' | 'overlay'), string[]][])
    if (a[key] !== undefined && ((a.display !== 'live' && !(key === 'overlay' && a.display === 'map')) || !choices.includes(a[key]!) || a[key] === choices[0])) fail('normalization');
  // A map card (app 0.4.33): its framing and distance, defaults never stored, and who rides along beside its person.
  const map = ofType('person')?.map;
  for (const [value, choices] of [[a.mapFraming, map?.framing ?? []], [a.mapDistance, map?.distance ?? []], [a.mapFollow, map?.follow ?? []],
    [a.mapMarkers, map?.markers ?? []], [a.mapNames, map?.names ?? []], [a.mapZones, map?.zones ?? []], [a.mapStreets, map?.streets ?? []],
    [a.mapLook, map?.look ?? []]] as [string | undefined, string[]][])
    if (value !== undefined && (a.display !== 'map' || !choices.includes(value) || value === choices[0])) fail('normalization');
  // How the energy card shows power along a line: the energy card's own, the default (dots) never stored.
  if (a.energyFlow !== undefined && (entityId !== 'screen.energy' || !rules.energyFlow.includes(a.energyFlow) || a.energyFlow === rules.energyFlow[0])) fail('normalization');
  // A calendar card (firmware 0.56.0), as calendar_feed.validate checks it: its own choices, a default never stored.
  if (CALENDAR_FIELDS.some((key) => a[key] !== undefined)) {
    if (domain !== 'calendar') fail('normalization');
    const cal = rules.calendar;
    if (a.calendarStyle !== undefined && (!cal.styles.includes(a.calendarStyle) || a.calendarStyle === cal.styles[0])) fail('normalization');
    if (a.calendarStartView !== undefined && (!cal.startViews.includes(a.calendarStartView) || a.calendarStartView === cal.startViews[0])) fail('normalization');
    for (const [list, most, test] of [[a.calendarEntities, cal.calendars, (v: string) => matches(/^calendar\.[a-z0-9_]+$/, v) && v !== entityId && bytes(v) <= 128],
      [a.calendarPlaces, cal.words, (v: string) => bytes(v) <= 48], [a.calendarWords, cal.words, (v: string) => bytes(v) <= 48],
      [a.calendarHideWords, cal.words, (v: string) => bytes(v) <= 48]] as [unknown, number, (v: string) => boolean][]) {
      if (list === undefined) continue;
      if (!Array.isArray(list) || !list.length || list.length > most || new Set(list).size !== list.length ||
          list.some((v) => typeof v !== 'string' || !v.trim() || v !== v.trim() || !test(v))) fail('normalization');
    }
    for (const [value, fallback] of [[a.calendarAllDay, true], [a.calendarTentative, true], [a.calendarPrivate, false]] as [unknown, boolean][])
      if (value !== undefined && (typeof value !== 'boolean' || value === fallback)) fail('normalization');
    const whole = (value: unknown, least: number, most: number) => typeof value === 'number' && Number.isInteger(value) && value >= least && value <= most;
    if (a.calendarAhead !== undefined && (!whole(a.calendarAhead, 1, cal.ahead[1]) || a.calendarAhead === cal.ahead[0])) fail('normalization');
    if (a.calendarSoon !== undefined && (!whole(a.calendarSoon, 1, 120))) fail('normalization');
  }
  // A sensor's meter (firmware 0.56.0), as meter.validate checks it: with the meter alone, a default never stored.
  if (METER_FIELDS.some((key) => a[key] !== undefined)) {
    const m = rules.meter, number = (value: unknown) => typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= 1e9;
    if (a.display !== 'meter') fail('normalization');
    if (a.meterStyle !== undefined && (!m.styles.includes(a.meterStyle) || a.meterStyle === m.styles[0])) fail('normalization');
    if ((a.meterMin !== undefined || a.meterMax !== undefined) && !(number(a.meterMin) && number(a.meterMax) && a.meterMin! < a.meterMax!)) fail();
    const segments = a.meterSegments ?? 1;
    if (a.meterSegments !== undefined && (!m.segments.includes(a.meterSegments) || a.meterSegments === 1)) fail('normalization');
    const defaults = (m.defaultColors as Record<string, string[]>)[String(segments)];
    if (a.meterColors !== undefined && (!Array.isArray(a.meterColors) || a.meterColors.length !== segments || a.meterColors.some((name) => !(name in m.colors)))) fail();
    if (a.meterColors !== undefined && defaults && a.meterColors.join() === defaults.join()) fail('normalization');
    const values = a.meterThresholds;
    if (values !== undefined && (!Array.isArray(values) || !values.length || values.length !== segments - 1 || !values.every(number) ||
        values.some((value, i) => i > 0 && values[i - 1] >= value))) fail();
  }
  // A favourite (app 0.4.42): what it plays and its speaker, and its own shuffle and repeat (app 0.4.84), with the
  // favourite alone.
  if ((i.play !== undefined || i.speaker !== undefined || i.shuffle !== undefined || i.repeat !== undefined) && a.display !== 'favorite') fail('normalization');
  if (i.shuffle !== undefined && !rules.favoriteShuffles.includes(i.shuffle)) fail();
  if (i.repeat !== undefined && !rules.favoriteRepeats.includes(i.repeat)) fail();
  if (i.play !== undefined && (typeof i.play !== 'object' || !i.play || typeof i.play.id !== 'string' || typeof i.play.type !== 'string' || typeof i.play.title !== 'string')) fail();
  if (i.speaker !== undefined && (typeof i.speaker !== 'string' || !i.speaker.trim() || bytes(i.speaker) > 48)) fail();
  // The map tile (app 0.4.36) is a map, follows everyone or whom it lists, and alone has the choice.
  const mapTile = entityId === 'screen.map';
  if (mapTile && a.display !== 'map') fail('normalization');
  if (a.mapFollow !== undefined && !mapTile) fail('normalization');
  if (a.mapEntities !== undefined) {
    const list = a.mapEntities;
    if (a.display !== 'map' || !Array.isArray(list) || !list.length) fail('normalization');
    if (list.length > (map?.max ?? 8) - (mapTile ? 0 : 1) || new Set(list).size !== list.length ||
        list.some((id) => typeof id !== 'string' || !matches(/^[a-z0-9_]+\.[a-z0-9_]+$/, id) || !(map?.with ?? []).includes(id.split('.')[0]) || id === entityId)) fail();
  }
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
      // As core.action_for_screen writes it: JSON with ensure_ascii=False, so é counts its two UTF-8 bytes (app 0.4.1).
      const serialized = JSON.stringify(JSON.stringify(value));
      const text = typeof value === 'string' ? value : `{{ ${serialized} | from_json }}`;
      if (bytes(text) > 400) fail();
      (typeof value === 'string' ? strings : templates).push([key, text]);
    }
    if (bytes(JSON.stringify({ s: action.action, ...(strings.length ? { d: strings } : {}), ...(templates.length ? { t: templates } : {}) })) > 800) fail();
  } else if (i.action !== undefined) fail('normalization');
}
