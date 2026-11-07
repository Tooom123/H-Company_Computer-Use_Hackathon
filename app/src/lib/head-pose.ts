/**
 * Approximate face orientation from the FaceMesh already run by WebGazer.
 * This is NOT a calibrated camera pose, a gaze measurement, or MediaPipe Tasks'
 * facial transformation matrix. x/y/z here share FaceMesh's image-space scale.
 * See https://github.com/brownhci/WebGazer/blob/master/src/facemesh.mjs and
 * https://github.com/tensorflow/tfjs-models/tree/master/face-landmarks-detection.
 * Camera mirroring/sign conventions are learned by the separate calibration.
 */
export type HeadPose = { yaw: number; pitch: number; roll: number };
export type ScreenPoint = { x: number; y: number };
export type HeadCalibrationResult = { ready: boolean; reason?: string; sampleCount: number };
type Vector = [number, number, number];
type Label = { pose: HeadPose; target: ScreenPoint };
type Model = {
  x: number[]; y: number[]; center: [number, number]; scale: [number, number];
  min: [number, number]; max: [number, number]; width: number; height: number;
};
const radiansToDegrees = 180 / Math.PI;
const dot = (a: Vector, b: Vector) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const subtract = (a: Vector, b: Vector): Vector => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const length = (a: Vector) => Math.hypot(...a);
const cross = (a: Vector, b: Vector): Vector => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const median = (values: number[]) => {
  const ordered = [...values].sort((a, b) => a - b);
  const mid = Math.floor(ordered.length / 2);
  return ordered.length % 2 ? ordered[mid] : (ordered[mid - 1] + ordered[mid]) / 2;
};
const validPose = (pose: HeadPose) => pose && [pose.yaw, pose.pitch, pose.roll].every(Number.isFinite)
  && Math.abs(pose.yaw) <= 70 && Math.abs(pose.pitch) <= 60 && Math.abs(pose.roll) <= 60;

/** Caller must reject stale arrays: WebGazer keeps the last landmarks on face loss. */
export function extractHeadPose(positions: unknown): HeadPose | null {
  if (!Array.isArray(positions) || positions.length < 468) return null;
  const read = (index: number): Vector | null => {
    const point = positions[index];
    return Array.isArray(point) && point.length >= 3 && point.slice(0, 3).every(Number.isFinite)
      ? [point[0], point[1], point[2]] : null;
  };
  // Outer eye corners define the horizontal axis; forehead/chin define vertical.
  const left = read(33), right = read(263), top = read(10), bottom = read(152);
  if (!left || !right || !top || !bottom) return null;
  const horizontal = subtract(right, left);
  const vertical = subtract(bottom, top);
  const h = length(horizontal), v = length(vertical);
  if (h < 5 || v < 10 || v / h < 0.6 || v / h > 5) return null;
  // Collapsed or crossed landmarks must not create extreme screen predictions.
  const normal = cross(horizontal, vertical);
  const n = length(normal);
  if (n / (h * v) < 0.5 || horizontal[0] <= 0 || vertical[1] <= 0 || normal[2] <= 0) return null;
  const pose = {
    yaw: Math.atan2(normal[0], normal[2]) * radiansToDegrees,
    pitch: Math.atan2(normal[1], Math.hypot(normal[0], normal[2])) * radiansToDegrees,
    roll: Math.atan2(horizontal[1], horizontal[0]) * radiansToDegrees,
  };
  return validPose(pose) ? pose : null;
}

/** Solve the tiny regularized normal system with partial pivoting. */
function solve(matrix: number[][], rhs: number[]): number[] | null {
  const rows = matrix.map((row, i) => [...row, rhs[i]]);
  for (let column = 0; column < 3; column += 1) {
    let pivot = column;
    for (let row = column + 1; row < 3; row += 1) if (Math.abs(rows[row][column]) > Math.abs(rows[pivot][column])) pivot = row;
    [rows[column], rows[pivot]] = [rows[pivot], rows[column]];
    const divisor = rows[column][column];
    if (!Number.isFinite(divisor) || Math.abs(divisor) < 1e-10) return null;
    for (let cell = column; cell < 4; cell += 1) rows[column][cell] /= divisor;
    for (let row = 0; row < 3; row += 1) {
      if (row === column) continue;
      const factor = rows[row][column];
      for (let cell = column; cell < 4; cell += 1) rows[row][cell] -= factor * rows[column][cell];
    }
  }
  const result = rows.map(row => row[3]);
  return result.every(Number.isFinite) ? result : null;
}

/** Explicit training only. predict() never adds a label or changes the fit. */
export class HeadScreenMapper {
  private labels: Label[] = [];
  private model: Model | null = null;

  addSample(pose: HeadPose, target: ScreenPoint): boolean {
    if (!validPose(pose) || !target || !Number.isFinite(target.x) || !Number.isFinite(target.y)
      || target.x < 0 || target.y < 0 || this.labels.length >= 500) return false;
    this.labels.push({ pose: { ...pose }, target: { ...target } });
    // Adding training data invalidates an earlier model; callers explicitly refit.
    this.model = null;
    return true;
  }

  fit({ width, height }: { width: number; height: number }): HeadCalibrationResult {
    this.model = null;
    const fail = (reason: string): HeadCalibrationResult => ({ ready: false, reason, sampleCount: this.labels.length });
    if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return fail('Dimensions d’écran invalides.');
    if (this.labels.some(label => label.target.x >= width || label.target.y >= height)) return fail('Une cible de calibration est hors de l’écran.');

    // Equal weight per fixation, with coordinate medians rejecting isolated
    // motion spikes among the five samples collected on each target.
    const groups = new Map<string, Label[]>();
    for (const label of this.labels) {
      const key = `${label.target.x.toFixed(3)}:${label.target.y.toFixed(3)}`;
      groups.set(key, [...(groups.get(key) ?? []), label]);
    }
    if (groups.size < 5 || [...groups.values()].some(group => group.length < 3)) {
      return fail('Mesures insuffisantes : calibrez les cinq cibles avec la tête.');
    }
    const samples = [...groups.values()].map(group => ({
      pose: { yaw: median(group.map(s => s.pose.yaw)), pitch: median(group.map(s => s.pose.pitch)) },
      target: group[0].target,
    }));
    const targetsX = samples.map(s => s.target.x), targetsY = samples.map(s => s.target.y);
    if (Math.max(...targetsX) - Math.min(...targetsX) < width * 0.4 || Math.max(...targetsY) - Math.min(...targetsY) < height * 0.4) {
      return fail('Les cibles doivent couvrir la largeur et la hauteur de l’écran.');
    }
    const values = [samples.map(s => s.pose.yaw), samples.map(s => s.pose.pitch)];
    const min = values.map(v => Math.min(...v)) as [number, number];
    const max = values.map(v => Math.max(...v)) as [number, number];
    if (max[0] - min[0] < 3 || max[1] - min[1] < 3) {
      return fail('Mouvement de tête insuffisant : tournez légèrement la tête vers chaque cible, horizontalement et verticalement.');
    }
    const center = values.map(v => v.reduce((a, b) => a + b, 0) / v.length) as [number, number];
    const scale = values.map((v, axis) => Math.sqrt(v.reduce((sum, n) => sum + (n - center[axis]) ** 2, 0) / v.length)) as [number, number];
    const correlation = samples.reduce((sum, s) => sum + (s.pose.yaw - center[0]) * (s.pose.pitch - center[1]), 0) / (samples.length * scale[0] * scale[1]);
    if (!Number.isFinite(correlation) || Math.abs(correlation) > 0.98) return fail('Les mouvements de tête ne distinguent pas gauche/droite et haut/bas. Recalibrez les cinq cibles.');

    const rows = samples.map(s => [1, (s.pose.yaw - center[0]) / scale[0], (s.pose.pitch - center[1]) / scale[1]] as Vector);
    const matrix = Array.from({ length: 3 }, (_, i) => Array.from({ length: 3 }, (_, j) => rows.reduce((sum, row) => sum + row[i] * row[j], 0) + (i === j && i !== 0 ? 0.001 : 0)));
    const fitAxis = (axis: 'x' | 'y', extent: number) => solve(matrix, [0, 1, 2].map(i => rows.reduce((sum, row, index) => sum + row[i] * samples[index].target[axis] / extent, 0)));
    const x = fitAxis('x', width), y = fitAxis('y', height);
    if (!x || !y) return fail('La calibration de la tête n’est pas exploitable.');
    const trainingError = Math.sqrt(rows.reduce((sum, row, i) => sum + (dot(x as Vector, row) - samples[i].target.x / width) ** 2 + (dot(y as Vector, row) - samples[i].target.y / height) ** 2, 0) / rows.length);
    if (trainingError > 0.3) return fail('Les mouvements de tête ne correspondent pas assez aux cibles. Recalibrez.');
    this.model = { x, y, center, scale, min, max, width, height };
    return { ready: true, sampleCount: this.labels.length };
  }

  predict(pose: HeadPose): ScreenPoint | null {
    const model = this.model;
    if (!model || !validPose(pose)) return null;
    const values = [pose.yaw, pose.pitch];
    // Do not extrapolate arbitrary pointing from a head turn never calibrated.
    if (values.some((value, axis) => {
      const margin = Math.max(1, (model.max[axis] - model.min[axis]) * 0.2);
      return value < model.min[axis] - margin || value > model.max[axis] + margin;
    })) return null;
    const features: Vector = [1, (pose.yaw - model.center[0]) / model.scale[0], (pose.pitch - model.center[1]) / model.scale[1]];
    const x = dot(model.x as Vector, features) * model.width;
    const y = dot(model.y as Vector, features) * model.height;
    // A modest edge margin is allowed, then clamped. Larger departures are lost.
    if (!Number.isFinite(x) || !Number.isFinite(y) || x < -0.1 * model.width || x > 1.1 * model.width || y < -0.1 * model.height || y > 1.1 * model.height) return null;
    return { x: Math.max(0, Math.min(model.width - 1, x)), y: Math.max(0, Math.min(model.height - 1, y)) };
  }

  reset(): void { this.labels = []; this.model = null; }
}
