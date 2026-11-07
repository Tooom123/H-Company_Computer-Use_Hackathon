import { describe, expect, it } from 'vitest';
import { generateTarget, evaluateTargetFrame, summarizeTargetScores, TARGET_SETTLE_MS } from '../electron/target-benchmark.mjs';

const bounds = { width: 1440, height: 900 };
const target = { id: 'test:0', index: 0, seed: 'test', x: 500, y: 300, radius: 12, zone: 'interior' as const };
const source = { width: 2880, height: 1800 };
const input = { target, bounds, source, cropRect: { x: 800, y: 400, width: 400, height: 400 },
  presentedAt: 1000, selectionAt: 2000, captureCompletedAt: 2450, stable: true,
  mode: 'hybrid', signalUsed: 'hybrid', regionDisposition: 'crop' };

describe('independent reproducible target sequence', () => {
  it('replays the exact seed/index and varies the seed without using camera input', () => {
    const a = Array.from({ length: 24 }, (_, index) => generateTarget({ seed: 'repeat-42', index, bounds }));
    const b = Array.from({ length: 24 }, (_, index) => generateTarget({ seed: 'repeat-42', index, bounds }));
    const c = Array.from({ length: 24 }, (_, index) => generateTarget({ seed: 'repeat-43', index, bounds }));
    expect(a).toEqual(b); expect(a).not.toEqual(c);
    expect(new Set(a.map(point => point.id)).size).toBe(24);
  });

  it('covers edges and interior in each block while keeping the entire target visible', () => {
    for (const size of [bounds, { width: 1920, height: 1080 }, { width: 60, height: 40 }]) {
      const points = Array.from({ length: 12 }, (_, index) => generateTarget({ seed: 42, index, bounds: size }));
      expect(points.filter(p => p.zone === 'edge')).toHaveLength(8);
      expect(points.filter(p => p.zone === 'interior')).toHaveLength(4);
      for (const p of points) {
        expect(p.x - p.radius).toBeGreaterThanOrEqual(0);
        expect(p.y - p.radius).toBeGreaterThanOrEqual(0);
        expect(p.x + p.radius).toBeLessThanOrEqual(size.width);
        expect(p.y + p.radius).toBeLessThanOrEqual(size.height);
      }
      const corners = points.filter(p => (p.x < size.width * .3 || p.x > size.width * .7)
        && (p.y < size.height * .3 || p.y > size.height * .7));
      expect(corners.length).toBeGreaterThanOrEqual(4);
    }
  });

  it('rejects missing seeds, nonfinite sizes and invalid target indices', () => {
    expect(() => generateTarget({ seed: '', index: 0, bounds })).toThrow();
    expect(() => generateTarget({ seed: 'x', index: -1, bounds })).toThrow();
    expect(() => generateTarget({ seed: 'x', index: .5, bounds })).toThrow();
    expect(() => generateTarget({ seed: 'x', index: 0, bounds: { width: NaN, height: 100 } })).toThrow();
  });
});

describe('geometric target coverage of a frozen screenshot', () => {
  it('uses actual image scale, including anisotropic size, not a presumed Retina factor', () => {
    expect(evaluateTargetFrame(input)).toMatchObject({ scorable: true, centerContained: true, fullContained: true,
      targetPixels: { x: 1000, y: 600, radiusX: 24, radiusY: 24 }, fullFrame: false });
    const actual = evaluateTargetFrame({ ...input, source: { width: 1440, height: 1800 }, cropRect: { x: 450, y: 550, width: 100, height: 100 } });
    expect(actual.targetPixels).toEqual({ x: 500, y: 600, radiusX: 12, radiusY: 24 });
    expect(actual.fullContained).toBe(true);
    expect(actual.areaFraction).toBeCloseTo(10000 / (1440 * 1800));
  });

  it('does not apply a global desktop offset twice to display-local target positions', () => {
    const shiftedBounds = { ...bounds, x: -1440, y: 120 };
    expect(evaluateTargetFrame({ ...input, bounds: shiftedBounds }).targetPixels).toEqual(evaluateTargetFrame(input).targetPixels);
  });

  it('distinguishes a center hit from clipping the red disc and honors half-open bounds', () => {
    expect(evaluateTargetFrame({ ...input, cropRect: { x: 1000, y: 600, width: 100, height: 100 } }))
      .toMatchObject({ centerContained: true, fullContained: false });
    expect(evaluateTargetFrame({ ...input, cropRect: { x: 900, y: 500, width: 100, height: 100 } }))
      .toMatchObject({ centerContained: false, fullContained: false });
    expect(evaluateTargetFrame({ ...input, cropRect: { x: 976, y: 576, width: 48, height: 48 } }).fullContained).toBe(true);
  });

  it('excludes transitions, absent presentation acknowledgements and unstable capture intervals', () => {
    expect(evaluateTargetFrame({ ...input, presentedAt: null })).toMatchObject({ scorable: false, reason: 'unpresented', fullContained: null });
    expect(evaluateTargetFrame({ ...input, selectionAt: 1000 + TARGET_SETTLE_MS - 1 }))
      .toMatchObject({ scorable: false, reason: 'transition', centerContained: null });
    expect(evaluateTargetFrame({ ...input, selectionAt: 1000 + TARGET_SETTLE_MS }).scorable).toBe(true);
    expect(evaluateTargetFrame({ ...input, stable: false })).toMatchObject({ scorable: false, reason: 'unstable' });
    expect(evaluateTargetFrame({ ...input, presentedAt: 2100 })).toMatchObject({ scorable: false, reason: 'transition' });
    expect(evaluateTargetFrame({ ...input, captureCompletedAt: 1900 })).toMatchObject({ scorable: false, reason: 'invalid-timing' });
  });

  it('freezes target metadata and refuses malformed capture geometry', () => {
    const mutable = { ...target };
    const score = evaluateTargetFrame({ ...input, target: mutable });
    mutable.x = 999;
    expect(score.target.x).toBe(500);
    expect(() => evaluateTargetFrame({ ...input, cropRect: { x: -1, y: 0, width: 100, height: 100 } })).toThrow();
    expect(() => evaluateTargetFrame({ ...input, target: { ...target, x: 1 } })).toThrow();
    expect(() => evaluateTargetFrame({ ...input, cropRect: { x: 0, y: 0, width: 3000, height: 100 } })).toThrow();
  });
});

it('separates full-screen returns from crop hits, signals, transitions and edge performance', () => {
  const hit = evaluateTargetFrame(input);
  const miss = evaluateTargetFrame({ ...input, cropRect: { x: 0, y: 0, width: 100, height: 100 }, mode: 'gaze', signalUsed: 'gaze' });
  const fallback = evaluateTargetFrame({ ...input, cropRect: { x: 0, y: 0, ...source }, regionDisposition: 'full-fallback', signalUsed: 'full' });
  const requestedFull = evaluateTargetFrame({ ...input, cropRect: { x: 0, y: 0, ...source }, mode: 'full', regionDisposition: 'full-requested', signalUsed: 'full' });
  const unsettled = evaluateTargetFrame({ ...input, target: { ...target, zone: 'edge' }, presentedAt: null });
  const result = summarizeTargetScores([hit, miss, fallback, requestedFull, unsettled]);
  expect(result).toMatchObject({ total: 5, scored: 4, unscored: 1, centerHits: 3, fullHits: 3,
    croppedScored: 2, croppedFullHits: 1, fullFrames: 2, fullFallbacks: 1,
    edge: { total: 1, scored: 0, unscored: 1, meanAreaFraction: null }, interior: { scored: 4 } });
  expect(result.byMode.hybrid).toMatchObject({ total: 3, scored: 2, fullHits: 2, croppedScored: 1, croppedFullHits: 1, fullFallbacks: 1 });
  expect(result.bySignal.full).toMatchObject({ total: 2, fullFrames: 2 });
  expect(summarizeTargetScores([])).toMatchObject({ total: 0, scored: 0, meanAreaFraction: null, byMode: {}, bySignal: {} });
});
