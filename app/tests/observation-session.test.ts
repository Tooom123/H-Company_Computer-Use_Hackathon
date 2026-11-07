import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ObservationSession, validateObservationOptions } from '../electron/observation-session.mjs';

function wait(ms: number, signal: AbortSignal) {
  return new Promise<undefined>((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(signal.reason); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(undefined); }, ms);
    if (signal.aborted) abort(); else signal.addEventListener('abort', abort, { once: true });
  });
}
let serial = 0;
const frame = () => ({
  frameId: `test-${++serial}`, capturedAt: new Date().toISOString(),
  cropRect: { x: 0, y: 0, width: 800, height: 600 }, sourceWidth: 1470, sourceHeight: 956,
  preparationMs: 300, gazeAgeMs: 10, fallbackReason: null, regionDisposition: 'crop',
  detail: { dataUrl: 'local-detail' }, global: null, reference: { dataUrl: 'local-reference' },
});
const options = { durationSeconds: 15, showOverlay: false };
const make = (overrides: Record<string, unknown> = {}) => new ObservationSession({
  capture: async () => frame(), now: () => Date.now(), wait, ...overrides,
});
beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(0); serial = 0; });
afterEach(() => vi.useRealTimers());

it('waits for the user to return to the software, then stops at the selected duration', async () => {
  const capture = vi.fn(async () => frame());
  const finish = vi.fn();
  const session = make({ capture, onFinish: finish });
  session.start(options);
  await vi.advanceTimersByTimeAsync(2999);
  expect(capture).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(15002);
  await session.finished;
  expect(session.state).toMatchObject({ status: 'stopped', stopReason: 'duration', sampleCount: 15 });
  expect(finish).toHaveBeenCalledOnce();
  expect(JSON.stringify(session.list())).not.toContain('local-reference');
  expect(JSON.stringify(session.list())).not.toContain('local-detail');
});

it('never overlaps slow captures or queues missed deadlines', async () => {
  let active = 0, maximum = 0;
  const capture = vi.fn(async (signal: AbortSignal) => {
    active++; maximum = Math.max(maximum, active);
    try { await wait(1600, signal); return frame(); } finally { active--; }
  });
  const session = make({ capture });
  session.start(options);
  await vi.advanceTimersByTimeAsync(18001);
  await session.finished;
  expect(maximum).toBe(1);
  expect(capture.mock.calls.length).toBeLessThanOrEqual(8);
  expect(session.state.status).toBe('stopped');
});

it('rejects a late completed capture after Stop and restores the panel only once', async () => {
  let complete: (value: ReturnType<typeof frame>) => void = () => {};
  const finish = vi.fn();
  const session = make({ capture: () => new Promise(resolve => { complete = resolve; }), onFinish: finish });
  session.start(options);
  await vi.advanceTimersByTimeAsync(3001);
  const stopped = session.stop('user');
  expect(session.state.status).toBe('stopping');
  complete(frame());
  await stopped;
  expect(session.list()).toHaveLength(0);
  expect(finish).toHaveBeenCalledOnce();
});

it('bounds retained image memory and reports the reason', async () => {
  const session = make({ maxBytes: 1100 });
  session.start(options);
  await vi.advanceTimersByTimeAsync(5000);
  await session.finished;
  expect(session.state).toMatchObject({ status: 'stopped', stopReason: 'memory-limit', sampleCount: 1 });
});

it('stops on capture failure instead of silently sampling errors forever', async () => {
  const session = make({ capture: async () => { throw new Error('Permission manquante'); } });
  session.start(options);
  await vi.advanceTimersByTimeAsync(3001);
  await session.finished;
  expect(session.state).toMatchObject({ status: 'stopped', stopReason: 'error', error: 'Permission manquante' });
});

it('reviews exact frames, annotates only known images and replaces old sessions', async () => {
  const session = make();
  session.start(options);
  expect(() => session.clear()).toThrow('Arrêtez');
  expect(() => session.start(options)).toThrow('déjà');
  await vi.advanceTimersByTimeAsync(3001);
  await session.stop();
  const first = session.list()[0];
  expect(session.select(first.frameId).reference.dataUrl).toBe('local-reference');
  session.annotate({ frameId: first.frameId, label: 'present' });
  expect(session.list()[0].annotation).toBe('present');
  expect(() => session.annotate({ frameId: 'missing', label: 'present' })).toThrow('introuvable');
  expect(() => session.annotate({ frameId: first.frameId, label: 'made-up' })).toThrow('non reconnue');
  session.start(options);
  expect(session.list()).toHaveLength(0);
  await session.stop();
  session.clear();
  expect(session.state.status).toBe('idle');
});

it('rejects unsupported cadence/duration inputs before capturing', () => {
  for (const input of [null, {}, { durationSeconds: 600, showOverlay: false }, { durationSeconds: 30, showOverlay: 'yes' }]) {
    expect(() => validateObservationOptions(input)).toThrow();
  }
  expect(validateObservationOptions({ durationSeconds: 30, showOverlay: false })).toEqual({ durationSeconds: 30, showOverlay: false });
});
