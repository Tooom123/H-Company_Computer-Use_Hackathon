import { describe, expect, it } from 'vitest';
import { acceptGazeSample, acceptHeadSample, calibratedForSelection, headDiagnostics, selectAttention } from '../electron/attention-selection.mjs';

const bounds = { x: -1200, y: 100, width: 1200, height: 800 };
const tracker = { state: 'tracking', gazeCalibrated: true, headCalibrated: true };
const gaze = { x: 200, y: 300, receivedAt: 9500 };
const head = { point: { x: 800, y: 500 }, pose: { yaw: 10, pitch: -5, roll: 2 }, receivedAt: 9900 };
const select = (mode: string, patch: Record<string, unknown> = {}) => selectAttention({
  mode, bounds, tracker, gaze, head, cursor: null, now: 10000, ...patch,
});
const diagnose = (patch: Record<string, unknown>) => {
  const result = select('head', patch);
  if (!('headDiagnostic' in result)) throw new Error('Missing head diagnostic');
  return result.headDiagnostic;
};

describe('tracked-signal IPC boundary', () => {
  it('copies only finite in-screen measurements and timestamps receipt in main', () => {
    expect(acceptGazeSample({ x: 200, y: 300, emittedAt: -123, receivedAt: 900000 }, bounds, 42))
      .toEqual({ x: 200, y: 300, receivedAt: 42 });
    const accepted = acceptHeadSample({ ...head, emittedAt: -123 }, bounds, 42)!;
    expect(accepted).toEqual({ ...head, receivedAt: 42 });
    expect(accepted.point).not.toBe(head.point);
    expect(accepted.pose).not.toBe(head.pose);
  });

  it('keeps raw orientation when no calibrated screen point is available', () => {
    expect(acceptHeadSample({ point: null, pose: head.pose }, bounds, 42))
      .toEqual({ point: null, pose: head.pose, receivedAt: 42 });
    expect(select('head', { head: { ...head, point: null } }).signalUsed).toBe('full');
  });

  it('rejects invalid packets instead of pinning them to a screen edge', () => {
    for (const point of [null, {}, { x: -1, y: 20 }, { x: 1200, y: 20 }, { x: 20, y: 800 }, { x: NaN, y: 20 }, { x: 20, y: Infinity }]) {
      expect(acceptGazeSample(point, bounds, 42)).toBeNull();
      if (point !== null) expect(acceptHeadSample({ point, pose: head.pose }, bounds, 42)).toBeNull();
    }
    for (const sample of [null, {}, { point: head.point }, { point: head.point, pose: { ...head.pose, yaw: 181 } }, { point: head.point, pose: { ...head.pose, pitch: NaN } }]) {
      expect(acceptHeadSample(sample, bounds, 42)).toBeNull();
    }
    expect(acceptHeadSample(head, bounds, NaN)).toBeNull();
  });
});

describe('independent head and gaze selection', () => {
  it('distinguishes a fresh rejected projection from an expired or missing pose', () => {
    const rejected = acceptHeadSample({ point: null, pose: head.pose,
      reason: 'outside-calibration-domain', rawPoint: { x: 1300, y: -25 } }, bounds, 9994);
    const result = select('head', { head: rejected });
    expect(result).toMatchObject({ signalUsed: 'full', headAgeMs: 6,
      headDiagnostic: { reason: 'outside-calibration-domain', rawPoint: { x: 1300, y: -25 } } });
    expect(result.fallbackReason).not.toContain('ancienne');
    expect(diagnose({ head: { ...rejected, receivedAt: 8000 } }).reason).toBe('stale');
    expect(diagnose({ head: null }).reason).toBe('no-pose');
    expect(diagnose({ tracker: { ...tracker, headCalibrated: false } }).reason).toBe('uncalibrated');
    rejected!.rawPoint!.x = 1;
    if (!('headDiagnostic' in result)) throw new Error('Missing head diagnostic');
    expect(result.headDiagnostic.rawPoint.x).toBe(1300);
  });

  it('accepts only enumerated diagnostics and finite raw coordinates at the IPC boundary', () => {
    const packet = acceptHeadSample({ ...head, reason: 'arbitrary', rawPoint: { x: Infinity, y: 1 } }, bounds, 9994)!;
    expect(packet).not.toHaveProperty('reason');
    expect(packet).not.toHaveProperty('rawPoint');
    expect(diagnose({ head: { ...packet, point: null } }).reason).toBe('point-rejected');
    expect(diagnose({ head: { ...packet, point: null, reason: 'outside-screen' } }).reason).toBe('outside-screen');
  });
  it('uses the requested signal and maps local points to the display origin', () => {
    expect(select('gaze')).toMatchObject({ point: { x: -1000, y: 400 }, signalUsed: 'gaze', gazeAgeMs: 500, headAgeMs: 100, fallbackReason: null });
    expect(select('head')).toMatchObject({ point: { x: -400, y: 600 }, signalUsed: 'head', fallbackReason: null });
    expect(select('hybrid')).toMatchObject({ point: { x: -820, y: 460 }, signalUsed: 'hybrid', signalReason: expect.stringContaining('70 %'), fallbackReason: null });
  });

  it('never substitutes gaze in head-only mode, nor head in gaze-only mode', () => {
    expect(select('head', { head: null })).toMatchObject({ point: null, signalUsed: 'full', fallbackReason: expect.stringContaining('Tête') });
    expect(select('gaze', { gaze: null })).toMatchObject({ point: null, signalUsed: 'full', fallbackReason: expect.stringContaining('Regard') });
  });

  it('reports the actual remaining signal in hybrid mode when one source is lost', () => {
    expect(select('hybrid', { head: null })).toMatchObject({ point: { x: -1000, y: 400 }, signalUsed: 'gaze', signalReason: expect.stringContaining('regard seul'), fallbackReason: null });
    expect(select('hybrid', { gaze: null, tracker: { ...tracker, state: 'lost' } })).toMatchObject({ point: { x: -400, y: 600 }, signalUsed: 'head', signalReason: expect.stringContaining('tête seule'), fallbackReason: null });
    expect(select('hybrid', { gaze: null, head: null })).toMatchObject({ point: null, signalUsed: 'full', fallbackReason: expect.any(String) });
  });

  it('rejects stale or future samples independently and allows the exact age boundary', () => {
    expect(select('head', { head: { ...head, receivedAt: 8500 } }).signalUsed).toBe('head');
    expect(select('head', { head: { ...head, receivedAt: 8499 } }).signalUsed).toBe('full');
    expect(select('hybrid', { head: { ...head, receivedAt: 8499 } }).signalUsed).toBe('gaze');
    expect(select('hybrid', { gaze: { ...gaze, receivedAt: 8499 } }).signalUsed).toBe('head');
    expect(select('head', { head: { ...head, receivedAt: 10001 } }).signalUsed).toBe('full');
    expect(select('gaze', { gaze: { ...gaze, receivedAt: NaN } }).signalUsed).toBe('full');
  });

  it('cannot use uncalibrated or stopped sources even when samples still exist', () => {
    expect(select('head', { tracker: { ...tracker, headCalibrated: false } }).signalUsed).toBe('full');
    expect(select('gaze', { tracker: { ...tracker, gazeCalibrated: false } }).signalUsed).toBe('full');
    for (const state of ['off', 'calibrating', 'error']) {
      expect(select('hybrid', { tracker: { ...tracker, state } }).signalUsed).toBe('full');
    }
    expect(select('gaze', { tracker: { state: 'tracking' } }).signalUsed).toBe('gaze');
    expect(select('head', { tracker: { state: 'tracking' } }).signalUsed).toBe('full');
  });

  it('keeps the frozen decision immutable when later input coordinates change', () => {
    const nextHead = { ...head, point: { ...head.point } };
    const selected = select('head', { head: nextHead });
    nextHead.point.x = 100;
    expect(selected.point).toEqual({ x: -400, y: 600 });
  });

  it('keeps cursor and explicit full-screen independent of tracking', () => {
    expect(select('cursor', { tracker: { state: 'off' }, cursor: { x: -500, y: 400 } }))
      .toMatchObject({ point: { x: -500, y: 400 }, signalUsed: 'cursor', gazeAgeMs: null, headAgeMs: null });
    expect(select('cursor', { cursor: { x: 0, y: 400 } }).signalUsed).toBe('full');
    expect(select('full')).toEqual({ point: null, signalUsed: 'full', fallbackReason: null, gazeAgeMs: null, headAgeMs: null });
  });
});

it('gates observation start on the calibrations needed by each requested mode', () => {
  expect(calibratedForSelection('gaze', { state: 'tracking' })).toBe(true);
  expect(calibratedForSelection('head', { state: 'tracking' })).toBe(false);
  expect(calibratedForSelection('hybrid', { state: 'tracking', gazeCalibrated: true })).toBe(false);
  expect(calibratedForSelection('hybrid', tracker)).toBe(true);
  expect(calibratedForSelection('head', { ...tracker, gazeCalibrated: false })).toBe(true);
  expect(calibratedForSelection('hybrid', { ...tracker, gazeCalibrated: false })).toBe(false);
  expect(calibratedForSelection('head', { ...tracker, state: 'lost' })).toBe(true);
  expect(calibratedForSelection('head', { ...tracker, state: 'off' })).toBe(false);
  expect(calibratedForSelection('cursor', { state: 'off' })).toBe(true);
});

it('clears orientation values after its receipt becomes stale', () => {
  expect(headDiagnostics(head, 10000)).toEqual({ available: true, ageMs: 100, ...head.pose });
  expect(headDiagnostics(head, 11401)).toEqual({ available: false, ageMs: 1501, yaw: null, pitch: null, roll: null });
  expect(headDiagnostics(null, 10000)).toEqual({ available: false, ageMs: null, yaw: null, pitch: null, roll: null });
});
