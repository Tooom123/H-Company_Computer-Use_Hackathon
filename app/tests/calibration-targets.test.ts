import { describe, expect, it } from 'vitest';
import { calibrationTargets, CALIBRATION_EDGE_MARGIN_PX, type CalibrationPhase } from '../src/lib/calibration-targets';

describe('calibration profiles in viewport pixels', () => {
  it('places wide eye and head targets near all four true screen corners with a visible ring', () => {
    const viewport = { width: 1470, height: 956 };
    const eyes = calibrationTargets('calibration', 'wide', viewport);
    const head = calibrationTargets('head-calibration', 'wide', viewport);
    expect(eyes).toHaveLength(9);
    expect(head).toHaveLength(5);
    for (const corner of [{ x: 48, y: 48 }, { x: 1422, y: 48 }, { x: 1422, y: 908 }, { x: 48, y: 908 }]) {
      expect(eyes).toContainEqual(corner);
      expect(head).toContainEqual(corner);
    }
    for (const target of [...eyes, ...head]) {
      expect(target.x - 42).toBeGreaterThanOrEqual(6);
      expect(target.y - 42).toBeGreaterThanOrEqual(6);
      expect(target.x + 42).toBeLessThanOrEqual(viewport.width - 6);
      expect(target.y + 42).toBeLessThanOrEqual(viewport.height - 6);
    }
  });

  it('adapts to viewport dimensions instead of assuming Retina or screenshot resolution', () => {
    for (const viewport of [{ width: 800, height: 600 }, { width: 1920, height: 1080 }, { width: 360, height: 280 }]) {
      const points = calibrationTargets('calibration', 'wide', viewport);
      expect(points[0]).toEqual({ x: CALIBRATION_EDGE_MARGIN_PX, y: CALIBRATION_EDGE_MARGIN_PX });
      expect(points[4]).toEqual({ x: viewport.width / 2, y: viewport.height / 2 });
      expect(points[8]).toEqual({ x: viewport.width - 48, y: viewport.height - 48 });
    }
  });

  it('keeps independent validation targets away from either training grid', () => {
    const viewport = { width: 1470, height: 956 };
    for (const profile of ['standard', 'wide'] as const) {
      const trained = [...calibrationTargets('calibration', profile, viewport), ...calibrationTargets('head-calibration', profile, viewport)];
      const heldOut = calibrationTargets('validation', profile, viewport);
      expect(heldOut).toHaveLength(4);
      expect(calibrationTargets('head-validation', profile, viewport)).toEqual(heldOut);
      for (const target of heldOut) expect(trained).not.toContainEqual(target);
    }
  });

  it('preserves the original standard profile for a reproducible comparison', () => {
    const viewport = { width: 1000, height: 1000 };
    expect(calibrationTargets('calibration', 'standard', viewport)[0]).toEqual({ x: 120, y: 180 });
    expect(calibrationTargets('head-calibration', 'standard', viewport)[1]).toEqual({ x: 180, y: 220 });
    expect(calibrationTargets('validation', 'standard', viewport)[0]).toEqual({ x: 300, y: 320 });
  });

  it('rejects unusable viewport dimensions rather than placing targets off screen', () => {
    for (const width of [0, NaN, Infinity, 100]) {
      expect(() => calibrationTargets('calibration', 'wide', { width, height: 600 })).toThrow();
    }
    for (const phase of ['calibration', 'validation', 'head-calibration', 'head-validation'] as CalibrationPhase[]) {
      const points = calibrationTargets(phase, 'wide', { width: 192, height: 192 });
      expect(points.every(point => point.x >= 0 && point.y >= 0 && point.x < 192 && point.y < 192)).toBe(true);
    }
  });
});
