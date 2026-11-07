// Receipt timestamps use the main-process monotonic clock. These are not camera
// exposure times and must never be presented as end-to-end webcam latency.
export const MAX_SIGNAL_AGE_MS = 1500;
const HEAD_MAPPING_REASONS = ['uncalibrated', 'invalid-pose', 'outside-calibration-domain', 'outside-screen', 'valid'];
const HEAD_ZONES = ['center', 'top-left', 'top-right', 'bottom-left', 'bottom-right'];
const ZONE_REASONS = ['uncalibrated', 'invalid-pose', 'outside-zone-domain', 'stabilizing', 'valid'];
const HEAD_REASON_LABELS = {
  'tracker-inactive': 'Suivi tête arrêté', uncalibrated: 'Tête non calibrée',
  'no-pose': 'Visage ou orientation non détectés', stale: 'Mesure tête trop ancienne',
  'invalid-timing': 'Horodatage tête invalide', 'invalid-pose': 'Orientation tête invalide',
  'outside-calibration-domain': 'Orientation hors des mouvements appris pendant la calibration',
  'outside-screen': 'Position tête prédite trop loin hors de l’écran',
  'point-rejected': 'Orientation reçue, mais aucune position écran exploitable',
  valid: 'Position tête disponible',
  'zone-valid': 'Zone tête disponible',
  'zone-unavailable': 'Classification tête indisponible',
  'outside-zone-domain': 'Orientation au-delà de la plage élargie des zones',
  stabilizing: 'Direction tête en cours de stabilisation (250 ms)',
};

function localPoint(point, bounds) {
  return Boolean(point && Number.isFinite(point.x) && Number.isFinite(point.y)
    && point.x >= 0 && point.y >= 0 && point.x < bounds.width && point.y < bounds.height);
}

export function acceptGazeSample(sample, bounds, receivedAt) {
  return localPoint(sample, bounds) && Number.isFinite(receivedAt)
    ? { x: sample.x, y: sample.y, receivedAt } : null;
}

export function acceptHeadSample(sample, bounds, receivedAt) {
  if (!sample || !Number.isFinite(receivedAt) || !sample.pose
    || !['yaw', 'pitch', 'roll'].every(key => Number.isFinite(sample.pose[key]) && Math.abs(sample.pose[key]) <= 180)
    || (sample.point !== null && !localPoint(sample.point, bounds))) return null;
  return {
    point: sample.point ? { x: sample.point.x, y: sample.point.y } : null,
    pose: { yaw: sample.pose.yaw, pitch: sample.pose.pitch, roll: sample.pose.roll },
    receivedAt,
    ...(HEAD_MAPPING_REASONS.includes(sample.reason) ? { reason: sample.reason } : {}),
    ...(sample.rawPoint && ['x', 'y'].every(key => Number.isFinite(sample.rawPoint[key]))
      ? { rawPoint: { x: sample.rawPoint.x, y: sample.rawPoint.y } } : {}),
    ...(sample.zonePrediction && ZONE_REASONS.includes(sample.zonePrediction.reason)
      && (sample.zonePrediction.zone === null || HEAD_ZONES.includes(sample.zonePrediction.zone))
      ? { zonePrediction: { zone: sample.zonePrediction.zone, reason: sample.zonePrediction.reason } } : {}),
  };
}

function ageOf(sample, now) {
  if (!sample || !Number.isFinite(sample.receivedAt) || !Number.isFinite(now)) return null;
  const age = now - sample.receivedAt;
  return age >= 0 ? age : null;
}

export function headDiagnostics(head, now) {
  const ageMs = ageOf(head, now);
  const available = ageMs !== null && ageMs <= MAX_SIGNAL_AGE_MS;
  return {
    available, ageMs,
    yaw: available ? head.pose.yaw : null,
    pitch: available ? head.pose.pitch : null,
    roll: available ? head.pose.roll : null,
    ...(head?.reason ? { mappingReason: head.reason, mappingMessage: HEAD_REASON_LABELS[head.reason] } : {}),
    ...(available && head?.zonePrediction ? { zoneMessage: head.zonePrediction.zone && head.zonePrediction.reason === 'valid'
      ? `Zone tête : ${head.zonePrediction.zone}` : HEAD_REASON_LABELS[head.zonePrediction.reason] } : {}),
  };
}

export function calibratedForSelection(mode, tracker) {
  if (mode === 'cursor' || mode === 'full') return true;
  if (!['tracking', 'lost'].includes(tracker.state)) return false;
  // The original gaze-only tracker did not expose a calibration flag. Explicit
  // false is authoritative; a missing flag only preserves that legacy case.
  const gazeCalibrated = tracker.gazeCalibrated !== false;
  const headCalibrated = tracker.headCalibrated === true;
  if (mode === 'gaze') return gazeCalibrated;
  if (mode === 'head') return headCalibrated;
  return mode === 'hybrid' && gazeCalibrated && headCalibrated;
}

/** Select only from the frozen samples supplied by the caller. No live reads. */
export function selectAttention({ mode, bounds, tracker, gaze, head, cursor, now, headRegionPolicy = 'point' }) {
  const gazeAgeMs = ageOf(gaze, now);
  const headAgeMs = ageOf(head, now);
  const active = ['tracking', 'lost'].includes(tracker.state);
  const gazeValid = active && tracker.gazeCalibrated !== false && localPoint(gaze, bounds)
    && gazeAgeMs !== null && gazeAgeMs <= MAX_SIGNAL_AGE_MS;
  const coarse = mode === 'head' && headRegionPolicy === 'zones';
  const zone = head?.zonePrediction?.reason === 'valid' && HEAD_ZONES.includes(head.zonePrediction.zone)
    ? head.zonePrediction.zone : null;
  const headPoint = coarse ? (!zone ? null : zone === 'center' ? { x: bounds.width / 2, y: bounds.height / 2 }
    : { x: zone.endsWith('left') ? 0 : bounds.width - 1, y: zone.startsWith('top') ? 0 : bounds.height - 1 }) : head?.point;
  const headValid = active && tracker.headCalibrated === true && localPoint(headPoint, bounds)
    && headAgeMs !== null && headAgeMs <= MAX_SIGNAL_AGE_MS;
  const globalPoint = point => ({ x: bounds.x + point.x, y: bounds.y + point.y });
  const headReason = !active ? 'tracker-inactive' : tracker.headCalibrated !== true ? 'uncalibrated'
    : !head ? 'no-pose' : headAgeMs === null ? 'invalid-timing'
      : headAgeMs > MAX_SIGNAL_AGE_MS ? 'stale' : headValid ? (coarse ? 'zone-valid' : 'valid')
        : coarse ? (ZONE_REASONS.includes(head.zonePrediction?.reason) && head.zonePrediction.reason !== 'valid'
          ? head.zonePrediction.reason : 'zone-unavailable')
        : HEAD_MAPPING_REASONS.includes(head.reason) && head.reason !== 'valid' ? head.reason : 'point-rejected';
  const headDiagnostic = { reason: headReason, message: HEAD_REASON_LABELS[headReason],
    ...(head?.rawPoint ? { rawPoint: { ...head.rawPoint } } : {}) };
  const use = (point, signalUsed, signalReason) => ({
    point: globalPoint(point), signalUsed, signalReason, fallbackReason: null, gazeAgeMs, headAgeMs, headDiagnostic,
    ...(coarse ? { headZone: zone, headRegionPolicy: 'zones' } : {}),
  });
  const fallback = reason => ({ point: null, signalUsed: 'full', signalReason: reason,
    fallbackReason: reason, gazeAgeMs, headAgeMs, headDiagnostic,
    ...(coarse ? { headRegionPolicy: 'zones' } : {}) });

  if (mode === 'full') return { point: null, signalUsed: 'full', fallbackReason: null, gazeAgeMs: null, headAgeMs: null };
  if (mode === 'cursor') {
    const valid = cursor && Number.isFinite(cursor.x) && Number.isFinite(cursor.y)
      && cursor.x >= bounds.x && cursor.y >= bounds.y
      && cursor.x < bounds.x + bounds.width && cursor.y < bounds.y + bounds.height;
    return { point: valid ? { ...cursor } : null, signalUsed: valid ? 'cursor' : 'full',
      fallbackReason: valid ? null : 'Curseur hors de l’écran principal', gazeAgeMs: null, headAgeMs: null };
  }
  if (mode === 'gaze') return gazeValid ? use(gaze, 'gaze')
    : fallback('Regard indisponible, non calibré ou trop ancien : plein écran');
  if (mode === 'head') return headValid ? use(headPoint, 'head', coarse ? `Zones tête · ${zone} · décision stabilisée` : undefined)
    : fallback(`Tête : ${headDiagnostic.message} ; plein écran`);
  if (mode === 'hybrid') {
    if (gazeValid && headValid) return use({ x: gaze.x * 0.7 + head.point.x * 0.3, y: gaze.y * 0.7 + head.point.y * 0.3 },
      'hybrid', 'Fusion expérimentale : 70 % regard + 30 % tête.');
    if (gazeValid) return use(gaze, 'gaze', `Tête : ${headDiagnostic.message} ; regard seul.`);
    if (headValid) return use(head.point, 'head', 'Regard indisponible, non calibré ou trop ancien : tête seule.');
    return fallback(`Regard indisponible ; tête : ${headDiagnostic.message} ; plein écran`);
  }
  return fallback('Mode de sélection inconnu : plein écran');
}
