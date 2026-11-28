import { describe, expect, it } from 'vitest';
import cases from '../../tests/fixtures/page-conformance.json';
import { changePages, repairPages, validatePages } from '../src/model/pages';
import type { PageLayout } from '../src/types';

// A page the editor refuses names the tile and its page, and a tile it would refuse that the edit did not touch never
// blocks a save or a delete (0.4.92: two lamps' presets in the add-on's key order blocked every save of their screen).
const named = Object.fromEntries(cases.map((example) => [example.name, example]));
const grid = named['minimal canonical page'].grid;

function withStaleTile(): PageLayout {
  const doc = structuredClone(named['minimal canonical page'].document) as PageLayout;
  const second = structuredClone(named['stale refresh'].document.pages[0]) as PageLayout['pages'][number];
  second.id = '0000000000000002';
  second.tiles[0].id = 'lamp';
  for (const item of [...second.topbar.leading, ...second.topbar.trailing]) item.id += '-2';
  second.tiles[0].appearance.label = 'Reading lamp';
  doc.pages.push(second);
  return doc;
}

describe('refused tiles', () => {
  it('names the tile and its page', () => {
    expect(() => validatePages(withStaleTile(), grid)).toThrow(/Page 2, tile .Reading lamp./);
  });

  it('lets an edit elsewhere and a delete through while that tile stays as it was', () => {
    const doc = withStaleTile();
    const renamed = changePages(doc, grid, (draft) => { draft.pages[0].tiles[0].appearance.label = 'Desk lamp'; });
    expect(renamed.pages[0].tiles[0].appearance.label).toBe('Desk lamp');
    const deleted = changePages(doc, grid, (draft) => { draft.pages[1].tiles = []; });
    expect(deleted.pages[1].tiles).toEqual([]);
  });

  it('still refuses the tile once the edit changes it', () => {
    const doc = withStaleTile();
    expect(() => changePages(doc, grid, (draft) => { draft.pages[1].tiles[0].appearance.label = 'Lamp'; }))
      .toThrow(/Page 2, tile .Lamp./);
  });

  it('takes out what does not fit instead of refusing, and says which tile and what', () => {
    const doc = withStaleTile(), repairs: string[] = [];
    const next = changePages(doc, grid, (draft) => { draft.pages[1].tiles[0].appearance.label = 'Lamp'; }, repairs);
    expect(() => validatePages(next, grid)).not.toThrow();
    expect(repairs).toHaveLength(1);
    expect(repairs[0]).toMatch(/Page 2, tile .Lamp.: .*refresh/);
    expect(next.pages[1].tiles[0].appearance.refresh).toBeUndefined();
  });

  it('leaves a tile that fits alone', () => {
    const doc = structuredClone(named['minimal canonical page'].document) as PageLayout;
    expect(repairPages(doc, grid)).toEqual([]);
    expect(doc).toEqual(named['minimal canonical page'].document);
  });
});
