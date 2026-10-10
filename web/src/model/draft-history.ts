/** Bounded history with independent document and editor-map actions.
 * Simple mode skips map actions; restoring either scope leaves the other alone. Each step carries what it did in words
 * (model/change-label.ts), which goes with it from undo to redo and back, so both buttons can say what they do.
 */
import type { ChangeLabel } from './change-label';

export type HistoryScope = 'document' | 'workspace';
type Entry<T> = { value: T; scope: HistoryScope; label?: ChangeLabel };
export class DraftHistory<T> {
  private past: Entry<T>[] = [];
  private future: Entry<T>[] = [];
  clear() { this.past = []; this.future = []; }
  remember(value: T, scope: HistoryScope = 'document', label?: ChangeLabel) {
    this.past.push({ value, scope, ...(label ? { label } : {}) });
    if (this.past.length > 100) this.past.shift();
    this.future = [];
  }
  counts(advanced: boolean) {
    const visible = (entry: Entry<T>) => advanced || entry.scope === 'document';
    return { undo: this.past.filter(visible).length, redo: this.future.filter(visible).length };
  }
  /** What the next undo or redo would take back or do again, in words; none when there is nothing or it has none. */
  peek(direction: 'undo' | 'redo', advanced: boolean): ChangeLabel | undefined {
    const source = direction === 'undo' ? this.past : this.future;
    return source.findLast((entry) => advanced || entry.scope === 'document')?.label;
  }
  step(direction: 'undo' | 'redo', current: T, advanced: boolean): Entry<T> | undefined {
    const source = direction === 'undo' ? this.past : this.future;
    const target = direction === 'undo' ? this.future : this.past;
    const index = source.findLastIndex((entry) => advanced || entry.scope === 'document');
    if (index < 0) return;
    const [entry] = source.splice(index, 1);
    target.push({ value: current, scope: entry.scope, ...(entry.label ? { label: entry.label } : {}) });
    return entry;
  }
}
