// Target positions are generated independently of camera samples and crop choice.
// They are a requested fixation, not ground truth for where a person's eyes looked.
export const TARGET_STEP_MS = 3000;
export const TARGET_SETTLE_MS = 800;

/** @typedef {{width:number,height:number}} Size */
/** @typedef {{id:string,index:number,x:number,y:number,radius:number,zone:'edge'|'interior',seed:string}} BenchmarkTarget */
/** @typedef {{x:number,y:number,width:number,height:number}} Rect */

function size(value, label, integer = false) {
  if (!value || !['width', 'height'].every(key => Number.isFinite(value[key]) && value[key] > 0
    && (!integer || Number.isSafeInteger(value[key])))) throw new TypeError(`${label} dimensions are invalid`);
}
function seedText(seed) {
  if ((typeof seed !== 'string' && typeof seed !== 'number') || (typeof seed === 'number' && !Number.isFinite(seed))) {
    throw new TypeError('Benchmark seed must be a finite number or a string');
  }
  const text = String(seed);
  if (!text.length || text.length > 128) throw new RangeError('Benchmark seed must contain 1–128 characters');
  return text;
}
function randomFor(text) {
  let state = 2166136261;
  for (let i = 0; i < text.length; i += 1) state = Math.imul(state ^ text.charCodeAt(i), 16777619) >>> 0;
  // mulberry32, with the seed completely specified above rather than Math.random.
  return () => {
    state = (state + 0x6D2B79F5) >>> 0;
    let n = Math.imul(state ^ (state >>> 15), state | 1);
    n ^= n + Math.imul(n ^ (n >>> 7), n | 61);
    return ((n ^ (n >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * One randomized block visits four corners, four edge centers, and four interior
 * quadrants. Blocks are shuffled and jittered reproducibly. Coordinates are local
 * display DIP (bounds.x/y are intentionally irrelevant), not capture pixels.
 * @param {{seed:string|number,index:number,bounds:Size}} input
 * @returns {BenchmarkTarget}
 */
export function generateTarget({ seed, index, bounds }) {
  size(bounds, 'Display');
  const normalizedSeed = seedText(seed);
  if (!Number.isSafeInteger(index) || index < 0 || index > 1_000_000) throw new RangeError('Target index is invalid');
  const random = randomFor(`${normalizedSeed}:${Math.floor(index / 12)}`);
  const order = Array.from({ length: 12 }, (_, n) => n);
  for (let i = order.length - 1; i > 0; i -= 1) {
    const j = Math.floor(random() * (i + 1));
    [order[i], order[j]] = [order[j], order[i]];
  }
  const cell = order[index % 12];
  // A 24 DIP gap outside the red disc; shrink safely for a synthetic tiny screen.
  const radius = Math.min(12, bounds.width / 10, bounds.height / 10);
  const marginX = Math.min(radius + 24, bounds.width / 4);
  const marginY = Math.min(radius + 24, bounds.height / 4);
  const extentX = bounds.width - 2 * marginX;
  const extentY = bounds.height - 2 * marginY;
  const jitter = randomFor(`${normalizedSeed}:target:${index}`);
  const near = () => jitter() * 0.035;
  const middle = () => 0.42 + jitter() * 0.16;
  let x, y;
  if (cell < 4) {
    x = cell % 2 ? 1 - near() : near();
    y = cell < 2 ? near() : 1 - near();
  } else if (cell < 8) {
    x = cell === 4 ? near() : cell === 5 ? 1 - near() : middle();
    y = cell === 6 ? near() : cell === 7 ? 1 - near() : middle();
  } else {
    x = (cell % 2 ? 0.58 : 0.25) + jitter() * 0.17;
    y = (cell < 10 ? 0.25 : 0.58) + jitter() * 0.17;
  }
  return { id: `${normalizedSeed}:${index}`, index, seed: normalizedSeed,
    x: marginX + x * extentX, y: marginY + y * extentY, radius,
    zone: cell < 8 ? 'edge' : 'interior' };
}

/**
 * Score a frozen target against the REAL crop, with the actual source dimensions.
 * The caller must hold the target across capture and only set stable=true when
 * the acknowledged displayed target is unchanged throughout that interval.
 * All time values share the main-process monotonic clock. No camera exposure
 * timestamp, eye-tracking accuracy, or model inference success is implied.
 * @param {{target:BenchmarkTarget,bounds:Size,source:Size,cropRect:Rect,presentedAt:number|null,
 * selectionAt:number,captureCompletedAt:number,stable:boolean,mode:string,signalUsed?:string,
 * regionDisposition?:string,settleMs?:number}} input
 */
export function evaluateTargetFrame({ target, bounds, source, cropRect, presentedAt, selectionAt,
  captureCompletedAt, stable, mode, signalUsed, regionDisposition, settleMs = TARGET_SETTLE_MS }) {
  size(bounds, 'Display'); size(source, 'Source', true);
  if (!target || !['x', 'y', 'radius'].every(key => Number.isFinite(target[key])) || target.radius <= 0
    || target.x - target.radius < 0 || target.y - target.radius < 0
    || target.x + target.radius > bounds.width || target.y + target.radius > bounds.height
    || !['edge', 'interior'].includes(target.zone)) throw new RangeError('Target is outside this display');
  if (!cropRect || !['x', 'y', 'width', 'height'].every(key => Number.isSafeInteger(cropRect[key]))
    || cropRect.x < 0 || cropRect.y < 0 || cropRect.width <= 0 || cropRect.height <= 0
    || cropRect.x + cropRect.width > source.width || cropRect.y + cropRect.height > source.height) {
    throw new RangeError('Crop is outside the captured source');
  }
  if (!Number.isFinite(settleMs) || settleMs < 0) throw new RangeError('Settling interval is invalid');
  const targetPixels = { x: target.x * source.width / bounds.width, y: target.y * source.height / bounds.height,
    radiusX: target.radius * source.width / bounds.width, radiusY: target.radius * source.height / bounds.height };
  const fullFrame = cropRect.x === 0 && cropRect.y === 0 && cropRect.width === source.width && cropRect.height === source.height;
  const fullFallback = fullFrame && regionDisposition === 'full-fallback';
  const areaFraction = cropRect.width * cropRect.height / (source.width * source.height);
  /** @type {'unpresented'|'transition'|'unstable'|'invalid-timing'|null} */
  let reason = null;
  if (presentedAt === null || presentedAt === undefined) reason = 'unpresented';
  else if (![presentedAt, selectionAt, captureCompletedAt].every(Number.isFinite) || captureCompletedAt < selectionAt) reason = 'invalid-timing';
  else if (!stable) reason = 'unstable';
  else if (selectionAt - presentedAt < settleMs) reason = 'transition';
  const scorable = reason === null;
  const right = cropRect.x + cropRect.width, bottom = cropRect.y + cropRect.height;
  // Centers follow the same half-open pixel rectangle convention as capture.
  // Full-disc containment permits a tangent at the image boundary.
  const centerContained = scorable ? targetPixels.x >= cropRect.x && targetPixels.x < right
    && targetPixels.y >= cropRect.y && targetPixels.y < bottom : null;
  const fullContained = scorable ? targetPixels.x - targetPixels.radiusX >= cropRect.x
    && targetPixels.y - targetPixels.radiusY >= cropRect.y
    && targetPixels.x + targetPixels.radiusX <= right
    && targetPixels.y + targetPixels.radiusY <= bottom : null;
  return { target: { ...target }, targetPixels, mode, signalUsed: signalUsed ?? mode,
    scorable, reason, centerContained, fullContained, areaFraction, fullFrame, fullFallback,
    presentedAt: presentedAt ?? null, selectionAt, captureCompletedAt, settleMs };
}

/** @typedef {ReturnType<typeof evaluateTargetFrame>} TargetScore */
/** @param {TargetScore[]} scores */
function counts(scores) {
  const scored = scores.filter(score => score.scorable);
  const cropped = scored.filter(score => !score.fullFrame);
  const total = scores.length;
  return {
    total, scored: scored.length, unscored: total - scored.length,
    centerHits: scored.filter(score => score.centerContained).length,
    fullHits: scored.filter(score => score.fullContained).length,
    croppedScored: cropped.length, croppedFullHits: cropped.filter(score => score.fullContained).length,
    fullFrames: scores.filter(score => score.fullFrame).length,
    fullFallbacks: scores.filter(score => score.fullFallback).length,
    // Surface is a crop property, not a token-saving estimate. Unknown/empty stays null.
    meanAreaFraction: scored.length ? scored.reduce((sum, score) => sum + score.areaFraction, 0) / scored.length : null,
  };
}

/**
 * Counts rather than a single flattering score: full-screen returns are separated
 * from cropped target hits, and unacknowledged/transition frames are excluded.
 * Modes describe the requested experimental condition; actual signals are also
 * grouped so hybrid fallback cannot silently masquerade as successful fusion.
 * @param {TargetScore[]} scores
 */
export function summarizeTargetScores(scores) {
  const group = key => Object.fromEntries([...new Set(scores.map(score => score[key]))]
    .map(value => [value, counts(scores.filter(score => score[key] === value))]));
  return { ...counts(scores), byMode: group('mode'), bySignal: group('signalUsed'),
    edge: counts(scores.filter(score => score.target.zone === 'edge')),
    interior: counts(scores.filter(score => score.target.zone === 'interior')) };
}
