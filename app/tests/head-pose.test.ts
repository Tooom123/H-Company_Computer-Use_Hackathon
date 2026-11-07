import { describe, expect, it } from 'vitest';
import { extractHeadPose, HeadScreenMapper, type HeadPose } from '../src/lib/head-pose';

const neutral: HeadPose = { yaw: 0, pitch: 0, roll: 0 };
type V = [number, number, number];
function mesh(transform: (point: V) => V = point => point) {
  const points: V[] = Array.from({ length: 468 }, () => [0, 0, 0]);
  points[33] = [-50, -25, 0]; points[263] = [50, -25, 0];
  points[10] = [0, -80, 0]; points[152] = [0, 100, 0];
  return points.map(point => transform(point));
}
const rotation = (axis: 'x' | 'y' | 'z', degrees: number) => ([x, y, z]: V): V => {
  const c = Math.cos(degrees * Math.PI / 180), s = Math.sin(degrees * Math.PI / 180);
  if (axis === 'x') return [x, c * y - s * z, s * y + c * z];
  if (axis === 'y') return [c * x + s * z, y, -s * x + c * z];
  return [c * x - s * y, s * x + c * y, z];
};

describe('approximate FaceMesh orientation (synthetic geometry)', () => {
  it('extracts independent yaw, pitch and roll changes without a second model', () => {
    expect(extractHeadPose(mesh())).toEqual(neutral);
    const yaw = extractHeadPose(mesh(rotation('y', 20)))!;
    expect(yaw.yaw).toBeCloseTo(20); expect(yaw.pitch).toBeCloseTo(0);
    const pitch = extractHeadPose(mesh(rotation('x', 12)))!;
    expect(pitch.pitch).toBeCloseTo(-12); expect(pitch.yaw).toBeCloseTo(0);
    const roll = extractHeadPose(mesh(rotation('z', 18)))!;
    expect(roll.roll).toBeCloseTo(18); expect(roll.yaw).toBeCloseTo(0);
  });

  it('is invariant to translation and uniform image scale', () => {
    const turn = rotation('y', -16);
    const actual = extractHeadPose(mesh(point => {
      const [x, y, z] = turn(point); return [3 * x + 320, 3 * y + 240, 3 * z - 20];
    }))!;
    expect(actual.yaw).toBeCloseTo(-16); expect(actual.pitch).toBeCloseTo(0);
  });

  it('rejects missing, collapsed, non-finite or extreme landmarks', () => {
    expect(extractHeadPose(null)).toBeNull();
    expect(extractHeadPose([[1, 2, 3]])).toBeNull();
    expect(extractHeadPose(mesh(() => [0, 0, 0]))).toBeNull();
    const corrupt = mesh(); corrupt[10][2] = NaN;
    expect(extractHeadPose(corrupt)).toBeNull();
    const crossed = mesh(); crossed[152] = [50, -25, 0]; crossed[10] = [-50, -25, 0];
    expect(extractHeadPose(crossed)).toBeNull();
    expect(extractHeadPose(mesh(rotation('y', 80)))).toBeNull();
  });
});

const screen = { width: 1000, height: 700 };
const targets = [{ x: 500, y: 350 }, { x: 150, y: 105 }, { x: 850, y: 105 }, { x: 850, y: 595 }, { x: 150, y: 595 }];
const poseFor = ({ x, y }: { x: number; y: number }): HeadPose => ({ yaw: (x - 500) / 30, pitch: (y - 350) / 20, roll: 0 });
function train(mapper: HeadScreenMapper, pose = poseFor) {
  for (const target of targets) for (let i = 0; i < 5; i += 1) mapper.addSample(pose(target), target);
}

describe('separate head-to-screen calibration', () => {
  it('requires deliberate labels, learns affine coordinates and never trains on prediction', () => {
    const mapper = new HeadScreenMapper();
    expect(mapper.predict(neutral)).toBeNull();
    expect(mapper.fit(screen).ready).toBe(false);
    train(mapper);
    expect(mapper.fit(screen)).toEqual({ ready: true, sampleCount: 25 });
    const validationTarget = { x: 650, y: 230 };
    const predicted = mapper.predict(poseFor(validationTarget))!;
    expect(predicted.x).toBeCloseTo(validationTarget.x, 0);
    expect(predicted.y).toBeCloseTo(validationTarget.y, 0);
    for (let i = 0; i < 10; i += 1) mapper.predict({ yaw: 8, pitch: -9, roll: 15 });
    expect(mapper.predict(poseFor(validationTarget))).toEqual(predicted);
    expect(mapper.fit(screen).sampleCount).toBe(25);
    mapper.reset();
    expect(mapper.predict(neutral)).toBeNull();
    expect(mapper.fit(screen).sampleCount).toBe(0);
  });

  it('learns mirrored camera signs and cross-axis coupling', () => {
    const mapper = new HeadScreenMapper();
    const coupled = (target: { x: number; y: number }): HeadPose => {
      const p = poseFor(target);
      return { yaw: -p.yaw + 0.2 * p.pitch + 8, pitch: p.pitch + 0.1 * p.yaw - 6, roll: 3 };
    };
    train(mapper, coupled);
    expect(mapper.fit(screen).ready).toBe(true);
    const predicted = mapper.predict(coupled({ x: 650, y: 230 }))!;
    expect(predicted.x).toBeCloseTo(650, 0); expect(predicted.y).toBeCloseTo(230, 0);
  });

  it('uses robust per-fixation medians rather than letting one motion spike distort the fit', () => {
    const mapper = new HeadScreenMapper();
    for (const target of targets) {
      const pose = poseFor(target);
      for (const jitter of [-0.3, -0.1, 0.1, 0.3]) mapper.addSample({ ...pose, yaw: pose.yaw + jitter, pitch: pose.pitch + jitter }, target);
      mapper.addSample({ yaw: 50, pitch: -40, roll: 0 }, target);
    }
    expect(mapper.fit(screen).ready).toBe(true);
    const point = mapper.predict(neutral)!;
    expect(Math.abs(point.x - 500)).toBeLessThan(6);
    expect(Math.abs(point.y - 350)).toBeLessThan(6);
  });

  it('refuses head-still and one-axis-only calibration instead of producing invented screen points', () => {
    const still = new HeadScreenMapper(); train(still, () => neutral);
    expect(still.fit(screen)).toMatchObject({ ready: false, reason: expect.stringContaining('insuffisant') });
    expect(still.predict(neutral)).toBeNull();
    const diagonal = new HeadScreenMapper();
    train(diagonal, target => ({ yaw: target.x / 50, pitch: target.x / 100, roll: 0 }));
    expect(diagonal.fit(screen)).toMatchObject({ ready: false, reason: expect.stringContaining('gauche/droite') });
  });

  it('rejects invalid labels, incomplete coverage and excessive extrapolation', () => {
    const mapper = new HeadScreenMapper();
    expect(mapper.addSample({ ...neutral, yaw: NaN }, { x: 100, y: 100 })).toBe(false);
    expect(mapper.addSample(neutral, { x: -1, y: 20 })).toBe(false);
    train(mapper);
    expect(mapper.fit({ width: NaN, height: 100 }).ready).toBe(false);
    expect(mapper.fit(screen).ready).toBe(true);
    expect(mapper.predict({ yaw: 40, pitch: 0, roll: 0 })).toBeNull();
    expect(mapper.predict({ yaw: 0, pitch: 30, roll: 0 })).toBeNull();
    expect(mapper.predict({ ...neutral, roll: Infinity })).toBeNull();
    const narrow = new HeadScreenMapper();
    for (const target of targets) for (let i = 0; i < 5; i += 1) narrow.addSample(poseFor(target), { x: 400 + target.x / 10, y: 300 + target.y / 10 });
    expect(narrow.fit(screen)).toMatchObject({ ready: false, reason: expect.stringContaining('couvrir') });
  });

  it('distinguishes an uncalibrated model, invalid pose and departure from the learned domain', () => {
    const mapper = new HeadScreenMapper();
    expect(mapper.predictWithDiagnostics(neutral)).toEqual({ point: null, reason: 'uncalibrated' });
    train(mapper);
    expect(mapper.fit(screen).ready).toBe(true);
    expect(mapper.predictWithDiagnostics({ ...neutral, yaw: NaN })).toEqual({ point: null, reason: 'invalid-pose' });
    expect(mapper.predictWithDiagnostics({ ...neutral, yaw: 80 })).toEqual({ point: null, reason: 'invalid-pose' });
    const outside = mapper.predictWithDiagnostics({ ...neutral, yaw: 40 });
    expect(outside).toMatchObject({ point: null, reason: 'outside-calibration-domain' });
    expect(outside.rawPoint?.x).toBeGreaterThan(screen.width);
    expect(outside.rawPoint?.y).toBeCloseTo(screen.height / 2);
    expect(mapper.predict({ ...neutral, yaw: 40 })).toBeNull();
  });

  it('reports a fresh valid pose projecting offscreen separately from domain rejection, without relaxing thresholds', () => {
    const mapper = new HeadScreenMapper();
    const extent = { width: 1470, height: 956 };
    const wideTargets = [{ x: 735, y: 478 }, { x: 48, y: 48 }, { x: 1422, y: 48 }, { x: 1422, y: 908 }, { x: 48, y: 908 }];
    // A valid but high-gain fit: four degrees span almost the entire screen.
    for (const target of wideTargets) for (let i = 0; i < 5; i += 1) {
      mapper.addSample({ yaw: (target.x - 735) / 343.5, pitch: (target.y - 478) / 215, roll: 0 }, target);
    }
    expect(mapper.fit(extent).ready).toBe(true);
    const offscreen = mapper.predictWithDiagnostics({ ...neutral, yaw: 2.6 });
    expect(offscreen).toMatchObject({ point: null, reason: 'outside-screen' });
    expect(offscreen.rawPoint?.x).toBeGreaterThan(extent.width * 1.1);
    expect(mapper.predict({ ...neutral, yaw: 2.6 })).toBeNull();

    const clamped = mapper.predictWithDiagnostics({ ...neutral, yaw: 2.2 });
    expect(clamped).toMatchObject({ point: { x: extent.width - 1 }, reason: 'valid' });
    expect(clamped.rawPoint?.x).toBeGreaterThan(extent.width);
    expect(mapper.predict({ ...neutral, yaw: 2.2 })).toEqual(clamped.point);
    expect(mapper.predictWithDiagnostics(neutral)).toMatchObject({ point: { x: 735, y: 478 }, reason: 'valid', rawPoint: { x: 735, y: 478 } });
  });
});
