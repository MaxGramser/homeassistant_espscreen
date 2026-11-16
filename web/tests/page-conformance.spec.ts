import { describe, expect, it } from 'vitest';
import cases from '../../tests/fixtures/page-conformance.json';
import { deletePage, pagination, projectLayout, validatePages } from '../src/model/pages';
import type { PageLayout } from '../src/types';

describe('shared canonical page documents', () => {
  for (const example of cases) it(example.name, () => {
    const doc = structuredClone(example.document) as PageLayout;
    if (example.valid) {
      expect(validatePages(doc, example.grid)).toEqual(doc);
      if ('pagination' in example) expect(pagination(doc)).toEqual(example.pagination);
      if ('compiled' in example) expect(projectLayout(doc, example.grid).tiles.map(t => [t.entity, t.slot])).toEqual(example.compiled);
      if ('delete' in example) {
        const operation = example.delete as { id: string; entities: string[] };
        const result = deletePage(doc, example.grid, operation.id);
        expect(projectLayout(result, example.grid).tiles.map(t => t.entity)).toEqual(operation.entities);
      }
    } else expect(() => validatePages(doc, example.grid)).toThrow();
    expect(doc).toEqual(example.document);
  });
});
