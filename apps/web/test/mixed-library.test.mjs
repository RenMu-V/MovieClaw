import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

test('mixed home-row keys retain the concrete TMDB namespace', () => {
  const text = readFileSync(new URL('../components/library-view.tsx', import.meta.url), 'utf8');
  const body = text.match(/export function libraryItemKey\(item: LibraryItem\): string \{([\s\S]*?)\n\}/)[1];
  const key = new Function('item', body);
  assert.notEqual(key({ kind: 'movie', tmdb_id: 200 }), key({ kind: 'tv', tmdb_id: 200 }));
  assert.equal(key({ kind: 'tv', tmdb_id: 200 }), 'tv:200');
});
