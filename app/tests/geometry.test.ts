import { describe, expect, it } from 'vitest';
import {
  boundedRect,
  captureRectToDisplay,
  normalizedPointToScreen,
  screenPointToCapture,
  screenRectToCapture,
  validateSettings,
} from '../electron/geometry.mjs';

describe('capture geometry', () => {
  it('preserves crop area at all screen edges and clamps oversized crops', () => {
    const source = { width: 1920, height: 1080 };
    const size = { width: 800, height: 600 };
    expect(boundedRect({ x: 0, y: 0 }, size, source)).toEqual({ x: 0, y: 0, ...size });
    expect(boundedRect({ x: 1920, y: 1080 }, size, source)).toEqual({ x: 1120, y: 480, ...size });
    expect(boundedRect({ x: -500, y: 2000 }, size, source)).toEqual({ x: 0, y: 480, ...size });
    expect(boundedRect({ x: 960, y: 540 }, { width: 8192, height: 8192 }, source))
      .toEqual({ x: 0, y: 0, width: 1920, height: 1080 });
  });

  it('always returns integer, nonempty rectangles contained within the source', () => {
    const source = { width: 101, height: 99 };
    expect(boundedRect({ x: 50.5, y: 49.5 }, { width: 0.1, height: 0.9 }, source))
      .toEqual({ x: 50, y: 49, width: 1, height: 1 });
    for (const x of [-100, 0, 50.5, 100, 200]) {
      for (const y of [-100, 0, 49.5, 98, 200]) {
        const r = boundedRect({ x, y }, { width: 32.8, height: 24.2 }, source);
        expect(Object.values(r).every(Number.isInteger)).toBe(true);
        expect(r.width * r.height).toBe(33 * 24);
        expect(r.x).toBeGreaterThanOrEqual(0);
        expect(r.y).toBeGreaterThanOrEqual(0);
        expect(r.x + r.width).toBeLessThanOrEqual(source.width);
        expect(r.y + r.height).toBeLessThanOrEqual(source.height);
      }
    }
  });

  it('uses actual image dimensions for Retina and a negative display origin', () => {
    const bounds = { x: -1440, y: 120, width: 1440, height: 900 };
    const source = { width: 2880, height: 1800 };
    expect(screenPointToCapture({ x: -720, y: 570 }, bounds, source)).toEqual({ x: 1440, y: 900 });
    expect(captureRectToDisplay({ x: 1200, y: 600, width: 800, height: 600 }, source, bounds))
      .toEqual({ x: 600, y: 300, width: 400, height: 300 });
    expect(normalizedPointToScreen({ x: 500, y: 500 }, { x: 1200, y: 600, width: 800, height: 600 }, source, bounds))
      .toEqual({ x: -640, y: 570 });
  });

  it('does not assume equal X/Y scale factors or clamp outside gaze into the display', () => {
    const bounds = { x: 100, y: -80, width: 1000, height: 800 };
    const source = { width: 1500, height: 1600 };
    expect(screenPointToCapture({ x: 600, y: 320 }, bounds, source)).toEqual({ x: 750, y: 800 });
    expect(screenPointToCapture({ x: 0, y: -180 }, bounds, source)).toEqual({ x: -150, y: -200 });
    expect(captureRectToDisplay({ x: 300, y: 400, width: 600, height: 800 }, source, bounds))
      .toEqual({ x: 200, y: 200, width: 400, height: 400 });
  });

  it('clips desktop windows to a display and maps their bounds to actual source pixels', () => {
    const bounds = { x: 100, y: -80, width: 1000, height: 800 };
    const source = { width: 2000, height: 1000 };
    expect(screenRectToCapture({ x: 50, y: -180, width: 300, height: 400 }, bounds, source))
      .toEqual({ x: 0, y: 0, width: 500, height: 375 });
    expect(screenRectToCapture({ x: 1100, y: -80, width: 300, height: 400 }, bounds, source)).toBeNull();
    expect(screenRectToCapture({ x: 100.25, y: -79.8, width: 3, height: 3 }, bounds, source))
      .toEqual({ x: 1, y: 1, width: 5, height: 3 });
  });

  it('maps normalized extrema to pixels inside the crop, including a single-pixel crop', () => {
    const source = { width: 2000, height: 1000 };
    const bounds = { x: 0, y: 0, width: 1000, height: 500 };
    const crop = { x: 1700, y: 800, width: 300, height: 200 };
    expect(normalizedPointToScreen({ x: 0, y: 0 }, crop, source, bounds)).toEqual({ x: 850, y: 400 });
    expect(normalizedPointToScreen({ x: 1000, y: 1000 }, crop, source, bounds))
      .toEqual({ x: 999.5, y: 499.5 });
    expect(normalizedPointToScreen({ x: 1000, y: 1000 }, { x: 0, y: 0, width: 1, height: 1 }, source, bounds))
      .toEqual({ x: 0, y: 0 });
  });

  it('rejects malformed model coordinates instead of turning them into a click', () => {
    const source = { width: 1920, height: 1080 };
    const bounds = { x: 0, y: 0, ...source };
    const crop = { x: 10, y: 10, width: 100, height: 100 };
    for (const x of [NaN, Infinity, -1, 1001]) {
      expect(() => normalizedPointToScreen({ x, y: 500 }, crop, source, bounds)).toThrow();
    }
    expect(() => normalizedPointToScreen({ x: 500, y: NaN }, crop, source, bounds)).toThrow();
    expect(() => normalizedPointToScreen({ x: 500, y: 500 }, { ...crop, x: 1900 }, source, bounds)).toThrow();
  });

  it('rejects nonfinite geometry and zero, negative or fractional source dimensions', () => {
    const source = { width: 1920, height: 1080 };
    for (const value of [NaN, Infinity, -Infinity]) {
      expect(() => boundedRect({ x: value, y: 0 }, { width: 800, height: 600 }, source)).toThrow();
      expect(() => boundedRect({ x: 0, y: 0 }, { width: value, height: 600 }, source)).toThrow();
    }
    for (const width of [0, -1, 1920.5, Infinity]) {
      expect(() => boundedRect({ x: 0, y: 0 }, { width: 100, height: 100 }, { width, height: 1080 })).toThrow();
    }
    expect(() => screenPointToCapture({ x: 0, y: 0 }, { x: 0, y: 0, width: 0, height: 1080 }, source)).toThrow();
    expect(() => captureRectToDisplay({ x: 0.5, y: 0, width: 100, height: 100 }, source, { x: 0, y: 0, ...source })).toThrow();
  });
});

describe('renderer settings boundary', () => {
  const valid = { selection: 'gaze', roiWidth: 800, roiHeight: 600, includeGlobal: true, overlay: false };

  it('returns only supported fields without mutating the caller', () => {
    const input = Object.freeze({ ...valid, arbitraryEndpoint: 'https://example.com' });
    expect(validateSettings(input)).toEqual(valid);
    expect(input.arbitraryEndpoint).toBe('https://example.com');
  });

  it('rejects missing, coercible and out-of-range values', () => {
    for (const settings of [null, [], {}, { ...valid, selection: 'whatever' },
      { ...valid, roiWidth: '800' }, { ...valid, roiWidth: NaN },
      { ...valid, roiHeight: 8193 }, { ...valid, roiHeight: 63 },
      { ...valid, roiWidth: 800.5 }, { ...valid, includeGlobal: 1 },
      { ...valid, overlay: 'false' }, { ...valid, regionScope: 'application' }]) {
      expect(() => validateSettings(settings)).toThrow();
    }
  });

  it('accepts window scope while keeping omitted scope backward compatible', () => {
    expect(validateSettings(valid)).toEqual(valid);
    expect(validateSettings({ ...valid, regionScope: 'window' })).toEqual({ ...valid, regionScope: 'window' });
    expect(validateSettings({ ...valid, regionScope: 'screen' })).toEqual({ ...valid, regionScope: 'screen' });
  });
});
