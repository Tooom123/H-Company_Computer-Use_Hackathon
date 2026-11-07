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
