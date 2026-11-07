import { expect, it } from 'vitest';
import { windowIdsFromMediaSources } from '../electron/window-ids.mjs';

it('extracts and deduplicates native CGWindowIDs, not content IDs', () => {
  expect(windowIdsFromMediaSources(['window:8123:0', 'window:8124:90', 'window:8123:2'])).toEqual([8123, 8124]);
});
it('rejects absent or non-window sources instead of silently capturing the overlay', () => {
  for (const input of [[], null, ['screen:8123:0'], ['window:0:0'], ['window:-12:0'], ['window:4294967296:0'], ['window:12.5:0']]) {
    expect(() => windowIdsFromMediaSources(input)).toThrow();
  }
});
