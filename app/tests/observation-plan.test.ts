import { expect, it } from 'vitest';
import { planObservationRegion } from '../electron/observation-plan.mjs';

const source = { width: 1470, height: 956 };
const screenBounds = { x: 0, y: 0, ...source };
const settings = { selection: 'gaze', roiWidth: 896, roiHeight: 704, includeGlobal: true, overlay: true };
const selection = { point: { x: 735, y: 478 }, fallbackReason: null, gazeAgeMs: 290 };
const plan = (overrides = {}) => planObservationRegion({ source, screenBounds, settings, selection, ...overrides });

it.each([
  [{ x: 735, y: 478 }, { x: 287, y: 126, width: 896, height: 704 }],
  [{ x: 0, y: 0 }, { x: 0, y: 0, width: 896, height: 704 }],
  [{ x: 1469, y: 955 }, { x: 574, y: 252, width: 896, height: 704 }],
])('keeps the applied 896 × 704 region at %j', (point, expected) => {
  expect(plan({ selection: { ...selection, point } })).toMatchObject({
    cropRect: expected, requestedRegion: { width: 896, height: 704 },
    regionDisposition: 'crop', includeGlobal: true, gazeAgeMs: 290,
  });
});

it('identifies oversized settings instead of mislabelling them as gaze fallback', () => {
  expect(plan({ settings: { ...settings, roiWidth: 1600, roiHeight: 1216 } })).toMatchObject({
    cropRect: { x: 0, y: 0, ...source }, requestedRegion: { width: 1600, height: 1216 },
    regionDisposition: 'full-size', fallbackReason: null, includeGlobal: false,
  });
});

it('distinguishes explicit full screen from unavailable gaze and omits a redundant overview', () => {
  expect(plan({ settings: { ...settings, selection: 'full' } })).toMatchObject({
    regionDisposition: 'full-requested', fallbackReason: null, includeGlobal: false,
  });
  expect(plan({ selection: { point: null, gazeAgeMs: 1700, fallbackReason: 'Regard trop ancien' } })).toMatchObject({
    cropRect: { x: 0, y: 0, ...source }, regionDisposition: 'full-fallback',
    fallbackReason: 'Regard trop ancien', gazeAgeMs: 1700, includeGlobal: false,
  });
});

it('fails to an explicit full-screen fallback when no point or reason was supplied', () => {
  expect(plan({ selection: { point: null, fallbackReason: null, gazeAgeMs: null } })).toMatchObject({
    regionDisposition: 'full-fallback', fallbackReason: 'Position indisponible : plein écran', includeGlobal: false,
  });
});

it('keeps a valid crop without an overview when the option is disabled', () => {
  expect(plan({ settings: { ...settings, includeGlobal: false } })).toMatchObject({
    regionDisposition: 'crop', includeGlobal: false,
  });
});

const windowSettings = { ...settings, regionScope: 'window' };
const front = { id: 12, appName: 'Odoo dialog', bounds: { x: 500, y: 300, width: 400, height: 300 } };
const behind = { id: 7, appName: 'Browser', bounds: { x: 100, y: 100, width: 1200, height: 800 } };

it('chooses the first visible window at the fixation and keeps a small window whole', () => {
  expect(plan({ settings: windowSettings, windows: [front, behind] })).toMatchObject({
    selectedWindow: front, cropRect: { x: 500, y: 300, width: 400, height: 300 }, regionDisposition: 'crop',
  });
  expect(plan({ settings: windowSettings, windows: [behind, front] }).selectedWindow?.id).toBe(behind.id);
});

it('translates a crop at a window edge without leaking beyond the window', () => {
  const window = { id: 2, appName: 'Browser', bounds: { x: 100, y: 100, width: 1000, height: 800 } };
  expect(plan({ settings: windowSettings, windows: [window], selection: { ...selection, point: { x: 1090, y: 880 } } }).cropRect)
    .toEqual({ x: 204, y: 196, width: 896, height: 704 });
});

it('maps window bounds using actual image scale and nonzero desktop origins', () => {
  const window = { id: 3, appName: 'Browser', bounds: { x: -1300, y: 220, width: 500, height: 400 } };
  expect(plan({ settings: windowSettings, windows: [window],
    source: { width: 2880, height: 1800 }, screenBounds: { x: -1440, y: 120, width: 1440, height: 900 },
    selection: { ...selection, point: { x: -900, y: 500 } },
  }).cropRect).toEqual({ x: 384, y: 296, width: 896, height: 704 });
});

it('clips a partially offscreen window to the visible desktop image', () => {
  const window = { id: 4, appName: 'Browser', bounds: { x: -100, y: -80, width: 500, height: 400 } };
  expect(plan({ settings: windowSettings, windows: [window],
    selection: { ...selection, point: { x: 200, y: 100 } },
  })).toMatchObject({ selectedWindow: window, cropRect: { x: 0, y: 0, width: 400, height: 320 } });
});

it('reports missing window metadata while retaining a valid screen crop', () => {
  const invalid = { id: 5, appName: 'Invalid', bounds: { x: NaN, y: 0, width: 1000, height: 1000 } };
  expect(plan({ settings: windowSettings, windows: [invalid] })).toMatchObject({
    cropRect: { x: 287, y: 126, width: 896, height: 704 }, fallbackReason: null, regionDisposition: 'crop',
    windowFallbackReason: 'Aucune fenêtre visible sous la position : région limitée à l’écran.',
  });
  expect(plan({ settings: windowSettings, windows: [] }).selectedWindow).toBeUndefined();
});

it('ignores window metadata for screen scope, explicit full screen and lost gaze', () => {
  expect(plan({ windows: [front] }).cropRect).toEqual({ x: 287, y: 126, width: 896, height: 704 });
  const full = plan({ settings: { ...windowSettings, selection: 'full' }, windows: [front] });
  expect(full.regionDisposition).toBe('full-requested');
  expect(full.selectedWindow).toBeUndefined();
  const lost = plan({ settings: windowSettings, windows: [front], selection: { point: null, gazeAgeMs: null, fallbackReason: 'Perdu' } });
  expect(lost.regionDisposition).toBe('full-fallback');
  expect(lost.selectedWindow).toBeUndefined();
});
