export type CalibrationProfile = 'standard' | 'wide';
export type CalibrationPhase = 'calibration' | 'validation' | 'head-calibration' | 'head-validation';
export type CalibrationTarget = { x: number; y: number };
type Viewport = { width: number; height: number };

// A 66 px target plus its 9 px outer ring has a 42 px radius. Keep another
// 6 px of visible background, including at a true display corner.
export const CALIBRATION_EDGE_MARGIN_PX = 48;

const STANDARD_EYES = [0.18, 0.5, 0.82].flatMap(y => [0.12, 0.5, 0.88].map(x => ({ x, y })));
const STANDARD_HEAD = [{ x: 0.5, y: 0.5 }, { x: 0.18, y: 0.22 }, { x: 0.82, y: 0.22 }, { x: 0.82, y: 0.78 }, { x: 0.18, y: 0.78 }];
const STANDARD_VALIDATION = [{ x: 0.3, y: 0.32 }, { x: 0.7, y: 0.68 }, { x: 0.7, y: 0.32 }, { x: 0.3, y: 0.68 }];

/** Pixel positions in the actual tracker viewport, never CSS percentages of a card. */
export function calibrationTargets(phase: CalibrationPhase, profile: CalibrationProfile, viewport: Viewport): CalibrationTarget[] {
  const { width, height } = viewport;
  if (![width, height].every(value => Number.isFinite(value) && value >= 192)) {
    throw new Error('La fenêtre de calibration doit mesurer au moins 192 × 192 pixels.');
  }
  const validating = phase === 'validation' || phase === 'head-validation';
  if (profile === 'standard') {
    const relative = validating ? STANDARD_VALIDATION : phase === 'head-calibration' ? STANDARD_HEAD : STANDARD_EYES;
    return relative.map(point => ({ x: point.x * width, y: point.y * height }));
  }
  if (profile !== 'wide') throw new Error('Profil de calibration inconnu.');
  const margin = CALIBRATION_EDGE_MARGIN_PX;
  if (validating) {
    // Four held-out targets near each edge, deliberately away from the
    // calibration grid. Their labels must never enter either fitted model.
    const insetX = Math.max(margin, Math.min(96, width * 0.2));
    const insetY = Math.max(margin, Math.min(96, height * 0.2));
    return [
      { x: insetX, y: height * 0.28 },
      { x: width * 0.72, y: insetY },
      { x: width - insetX, y: height * 0.72 },
      { x: width * 0.28, y: height - insetY },
    ];
  }
  if (phase === 'head-calibration') return [
    { x: width / 2, y: height / 2 },
    { x: margin, y: margin }, { x: width - margin, y: margin },
    { x: width - margin, y: height - margin }, { x: margin, y: height - margin },
  ];
  return [margin, height / 2, height - margin].flatMap(y => [margin, width / 2, width - margin].map(x => ({ x, y })));
}
