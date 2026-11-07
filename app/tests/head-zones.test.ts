import { describe, expect, it } from 'vitest';
import { HeadScreenMapper, type HeadPose } from '../src/lib/head-pose';

const extent = { width: 1470, height: 956 };
const targets = [{ x: 735, y: 478 }, { x: 48, y: 48 }, { x: 1422, y: 48 }, { x: 1422, y: 908 }, { x: 48, y: 908 }];
const neutral: HeadPose = { yaw: 0, pitch: 0, roll: 0 };
function fitted(mirror = false) {
  const mapper = new HeadScreenMapper();
  for (const target of targets) for (let i = 0; i < 5; i += 1) mapper.addSample({
    yaw: (target.x - 735) / 343.5 * (mirror ? -1 : 1), pitch: (target.y - 478) / 215, roll: 0,
  }, target);
  expect(mapper.fit(extent).ready).toBe(true);
  return mapper;
}

describe('five head zones, independently of the fine regression', () => {
  it('keeps a direction whose fine point projects offscreen, without changing the baseline', () => {
    const mapper = fitted();
    const pose = { ...neutral, yaw: 2.6, pitch: -2.6 };
    expect(mapper.predictWithDiagnostics(pose).reason).toBe('outside-screen');
    expect(mapper.zones.predict(pose, 0)).toEqual({ zone: null, reason: 'stabilizing' });
    expect(mapper.zones.predict(pose, 250)).toEqual({ zone: 'top-right', reason: 'valid' });
    expect(mapper.predict(pose)).toBeNull();
    expect(mapper.zones.predict({ ...pose, yaw: 3.2 }, 350).zone).toBe('top-right');
  });

  it('learns camera sign from calibration prototypes and snaps all four directions', () => {
    const mapper = fitted(true);
    for (const [yaw, pitch, zone] of [[2, -2, 'top-left'], [-2, -2, 'top-right'], [-2, 2, 'bottom-right'], [2, 2, 'bottom-left']] as const) {
      mapper.zones.resetMotion();
      const pose = { yaw, pitch, roll: 0 };
      mapper.zones.predict(pose, 0);
      expect(mapper.zones.predict(pose, 250).zone).toBe(zone);
    }
  });

  it('uses a neutral region and dwell hysteresis instead of chasing one noisy sample', () => {
    const mapper = fitted();
    mapper.zones.predict(neutral, 0);
    expect(mapper.zones.predict(neutral, 250).zone).toBe('center');
    expect(mapper.zones.predict({ ...neutral, yaw: 0.8 }, 350).zone).toBe('center');
    const corner = { ...neutral, yaw: 2, pitch: -2 };
    expect(mapper.zones.predict(corner, 450).zone).toBe('center');
    expect(mapper.zones.predict(neutral, 500).zone).toBe('center');
    mapper.zones.predict(corner, 600);
    expect(mapper.zones.predict(corner, 849).zone).toBe('center');
    expect(mapper.zones.predict(corner, 850).zone).toBe('top-right');
  });

  it('does not reuse a zone after face loss, long gaps, extreme poses or recalibration', () => {
    const mapper = fitted();
    mapper.zones.predict(neutral, 0); mapper.zones.predict(neutral, 250);
    expect(mapper.zones.predict(null, 300)).toEqual({ zone: null, reason: 'invalid-pose' });
    expect(mapper.zones.predict(neutral, 400).reason).toBe('stabilizing');
    mapper.zones.predict(neutral, 650);
    expect(mapper.zones.predict(neutral, 2200).reason).toBe('stabilizing');
    expect(mapper.zones.predict({ ...neutral, yaw: 20 }, 2300)).toEqual({ zone: null, reason: 'outside-zone-domain' });
    expect(mapper.zones.predict({ ...neutral, roll: 80 }, 2400).reason).toBe('invalid-pose');
    mapper.reset();
    expect(mapper.zones.predict(neutral, 2500).reason).toBe('uncalibrated');
  });
});
