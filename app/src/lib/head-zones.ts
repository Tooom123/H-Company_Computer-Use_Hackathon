import type { HeadPose, ScreenPoint } from './head-pose';

export type HeadZone = 'center' | 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right';
export type HeadZonePrediction = { zone: HeadZone | null; reason: 'valid' | 'uncalibrated' | 'invalid-pose' | 'outside-zone-domain' | 'stabilizing' };
type Prototype = { zone: HeadZone; yaw: number; pitch: number };
type Fixation = { pose: { yaw: number; pitch: number }; target: ScreenPoint };

/** Five learned directions, independent of the affine screen-point regression.
 * Only explicit calibration fixations enter configure(); benchmark targets never do.
 * Thresholds are an experimental policy, not a confidence estimate or gaze accuracy.
 */
export class HeadZoneClassifier {
  private prototypes: Prototype[] = [];
  private center = { yaw: 0, pitch: 0 };
  private scale = { yaw: 1, pitch: 1 };
  private limits = { yaw: [0, 0], pitch: [0, 0] };
  private selected: HeadZone | null = null;
  private pending: HeadZone | null = null;
  private pendingSince = 0;
  private lastAt: number | null = null;

  configure(fixations: Fixation[], extent: { width: number; height: number }): void {
    this.reset();
    const classified = fixations.map(({ pose, target }): Prototype => ({ ...pose,
      zone: Math.abs(target.x / extent.width - 0.5) < 0.15 && Math.abs(target.y / extent.height - 0.5) < 0.15
        ? 'center' : `${target.y < extent.height / 2 ? 'top' : 'bottom'}-${target.x < extent.width / 2 ? 'left' : 'right'}`,
    }));
    if (classified.length !== 5 || new Set(classified.map(p => p.zone)).size !== 5) return;
    const center = classified.find(p => p.zone === 'center')!;
    this.center = { yaw: center.yaw, pitch: center.pitch };
    for (const axis of ['yaw', 'pitch'] as const) {
      const values = classified.map(p => p[axis]);
      const min = Math.min(...values), max = Math.max(...values);
      if (!Number.isFinite(min) || !Number.isFinite(max) || max - min < 3) return;
      this.scale[axis] = (max - min) / 2;
      // Permit coarse direction beyond training extremes, but not an arbitrary
      // extrapolation after turning away. This is distinct from the point policy.
      const margin = Math.min(12, (max - min) * 0.5);
      this.limits[axis] = [min - margin, max + margin];
    }
    this.prototypes = classified;
  }

  resetMotion(): void { this.selected = null; this.pending = null; this.pendingSince = 0; this.lastAt = null; }
  reset(): void { this.prototypes = []; this.resetMotion(); }

  predict(pose: HeadPose | null, now: number): HeadZonePrediction {
    const reject = (reason: HeadZonePrediction['reason']): HeadZonePrediction => {
      this.resetMotion(); return { zone: null, reason };
    };
    if (!this.prototypes.length) return reject('uncalibrated');
    if (!pose || !Number.isFinite(now) || ![pose.yaw, pose.pitch, pose.roll].every(Number.isFinite)
      || Math.abs(pose.yaw) > 70 || Math.abs(pose.pitch) > 60 || Math.abs(pose.roll) > 60) return reject('invalid-pose');
    if (this.lastAt !== null && (now < this.lastAt || now - this.lastAt > 1500)) this.resetMotion();
    this.lastAt = now;
    if ((['yaw', 'pitch'] as const).some(axis => pose[axis] < this.limits[axis][0] || pose[axis] > this.limits[axis][1])) return reject('outside-zone-domain');
    const distance = (prototype: { yaw: number; pitch: number }) => Math.hypot(
      (pose.yaw - prototype.yaw) / this.scale.yaw, (pose.pitch - prototype.pitch) / this.scale.pitch,
    );
    // A smaller center-entry radius than exit radius prevents center-edge chatter.
    const centerRadius = this.selected === 'center' ? 0.55 : 0.35;
    const corners = this.prototypes.filter(p => p.zone !== 'center').sort((a, b) => {
      const delta = distance(a) - distance(b);
      return Math.abs(delta) > 1e-9 ? delta : a.zone === this.selected ? -1 : b.zone === this.selected ? 1 : 0;
    });
    const candidate = distance(this.center) <= centerRadius ? 'center' : corners[0].zone;
    if (candidate === this.selected) { this.pending = null; return { zone: this.selected, reason: 'valid' }; }
    if (candidate !== this.pending) { this.pending = candidate; this.pendingSince = now; }
    if (now - this.pendingSince >= 250) { this.selected = candidate; this.pending = null; }
    return { zone: this.selected, reason: this.selected ? 'valid' : 'stabilizing' };
  }
}
