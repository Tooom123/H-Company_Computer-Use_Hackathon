import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cameraErrorMessage, WebGazerTracker } from '../src/lib/webgazer';

class FakeWebGazer {
  params = { faceMeshSolutionPath: '' };
  labels: unknown[] = [];
  eyesVisible = true;
  persistent = true;
  dotVisible = true;
  previewVisible = true;
  positions: number[][] | null = null;
  listener: ((sample: { x: number; y: number } | null, elapsed: number) => void) | undefined;
  begin = vi.fn(async () => this);
  pause = vi.fn(() => this);
  removeMouseEventListeners = vi.fn(() => this);
  clearGazeListener = vi.fn(() => { this.listener = undefined; return this; });
  async clearData() { this.labels = []; }
  setGazeListener(callback: NonNullable<FakeWebGazer['listener']>) { this.listener = callback; return this; }
  setRegression() { return this; }
  saveDataAcrossSessions(value: boolean) { this.persistent = value; return this; }
  showPredictionPoints(value: boolean) { this.dotVisible = value; return this; }
  showVideoPreview(value: boolean) { this.previewVisible = value; return this; }
  recordScreenPosition(x: number, y: number) {
    if (this.eyesVisible) {
      this.labels.push({ x, y });
      // Exercise acceptance when the regression buffer has reached its capacity.
      if (this.labels.length > 2) this.labels.shift();
    }
    return this;
  }
  getRegression() { return [{ getData: () => this.labels }]; }
  getTracker() { return { getPositions: () => this.positions }; }
  emit(sample: { x: number; y: number } | null) { this.listener?.(sample, 123); }
}

class FakeStream {
  tracks = [{ stop: vi.fn() }, { stop: vi.fn() }];
  getTracks() { return this.tracks; }
}

let engine: FakeWebGazer;
let stream: FakeStream;

beforeEach(() => {
  engine = new FakeWebGazer();
  stream = new FakeStream();
  vi.stubGlobal('MediaStream', FakeStream);
  vi.stubGlobal('document', {
    getElementById: (id: string) => id === 'webgazerVideoFeed' ? { srcObject: stream } : { style: {} },
  });
  vi.stubGlobal('window', { webgazer: engine, location: { href: 'http://localhost:5173/tracker.html#tracker' } });
});
afterEach(() => vi.unstubAllGlobals());

describe('WebGazer adapter (simulated camera and engine)', () => {
  it('waits for explicit start and uses only the local assets with no persistent calibration', async () => {
    const tracker = new WebGazerTracker(vi.fn());
    expect(engine.begin).not.toHaveBeenCalled();
    await tracker.start();
    expect(engine.params.faceMeshSolutionPath).toBe('http://localhost:5173/vendor/mediapipe/face_mesh');
    expect(engine.persistent).toBe(false);
    expect(engine.dotVisible).toBe(false);
    expect(engine.previewVisible).toBe(false);
    expect(engine.removeMouseEventListeners).toHaveBeenCalledOnce();
    tracker.dispose();
  });

  it('accepts one deliberate calibration label per inference, including a full regression buffer', async () => {
    const tracker = new WebGazerTracker(vi.fn());
    await tracker.start();
    for (let i = 0; i < 4; i++) {
      engine.emit({ x: 25, y: 45 });
      expect(tracker.recordCalibrationPoint(25, 45)).toBe(true);
      expect(tracker.recordCalibrationPoint(25, 45)).toBe(false);
    }
    engine.eyesVisible = false;
    engine.emit(null);
    expect(tracker.recordCalibrationPoint(25, 45)).toBe(false);
    tracker.dispose();
  });

  it('reports absent or non-finite predictions as missing without inventing a capture timestamp', async () => {
    const onSample = vi.fn();
    const tracker = new WebGazerTracker(onSample);
    await tracker.start();
    engine.emit({ x: 10, y: 30 });
    expect(onSample).toHaveBeenLastCalledWith({ x: 10, y: 30, emittedAt: expect.any(Number) }, null);
    engine.emit({ x: NaN, y: 30 });
    expect(onSample).toHaveBeenLastCalledWith(null, null);
    engine.emit(null);
    expect(onSample).toHaveBeenLastCalledWith(null, null);
    tracker.dispose();
  });

  it('uses fresh face landmarks even before gaze calibration and rejects the retained mesh after face loss', async () => {
    const onSample = vi.fn();
    const tracker = new WebGazerTracker(onSample);
    await tracker.start();
    const points = Array.from({ length: 468 }, () => [0, 0, 0]);
    points[33] = [100, 100, 0]; points[263] = [200, 100, 0];
    points[10] = [150, 50, 0]; points[152] = [150, 250, 0];
    engine.positions = points;
    engine.emit(null); // No learned eyes yet, but this is a fresh real mesh shape.
    expect(onSample).toHaveBeenLastCalledWith(null, { yaw: 0, pitch: 0, roll: 0 });
    engine.emit(null); // Upstream keeps the very same array when no face is found.
    expect(onSample).toHaveBeenLastCalledWith(null, null);
    engine.positions = points.map(p => [...p]);
    engine.emit(null);
    expect(onSample).toHaveBeenLastCalledWith(null, { yaw: 0, pitch: 0, roll: 0 });
    tracker.dispose();
  });

  it('stops every camera track and callbacks on dispose', async () => {
    const onSample = vi.fn();
    const tracker = new WebGazerTracker(onSample);
    await tracker.start();
    tracker.dispose();
    for (const track of stream.tracks) expect(track.stop).toHaveBeenCalledOnce();
    expect(engine.pause).toHaveBeenCalled();
    expect(engine.clearGazeListener).toHaveBeenCalled();
    engine.emit({ x: 10, y: 30 });
    expect(onSample).not.toHaveBeenCalled();
    expect(tracker.recordCalibrationPoint(10, 30)).toBe(false);
  });

  it('releases a camera granted after the user has already stopped', async () => {
    let grant!: (value: FakeWebGazer) => void;
    engine.begin.mockImplementation(() => new Promise(resolve => { grant = resolve; }));
    const tracker = new WebGazerTracker(vi.fn());
    const starting = tracker.start();
    await vi.waitFor(() => expect(engine.begin).toHaveBeenCalledOnce());
    tracker.dispose();
    grant(engine);
    await starting;
    for (const track of stream.tracks) expect(track.stop).toHaveBeenCalledTimes(2);
    expect(tracker.recordCalibrationPoint(10, 30)).toBe(false);
  });

  it('releases camera resources if startup fails and provides a useful permission message', async () => {
    const failure = new DOMException('Permission denied', 'NotAllowedError');
    engine.begin.mockRejectedValue(failure);
    const tracker = new WebGazerTracker(vi.fn());
    await expect(tracker.start()).rejects.toBe(failure);
    for (const track of stream.tracks) expect(track.stop).toHaveBeenCalledOnce();
    expect(cameraErrorMessage(failure)).toContain('Accès caméra refusé');
  });
});
