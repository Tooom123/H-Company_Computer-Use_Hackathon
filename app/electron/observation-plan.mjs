import { boundedRect, screenPointToCapture, screenRectToCapture } from './geometry.mjs';

function contains(bounds, point) {
  return bounds && ['x', 'y', 'width', 'height'].every(key => Number.isFinite(bounds[key]))
    && bounds.width > 0 && bounds.height > 0
    && point.x >= bounds.x && point.x < bounds.x + bounds.width
    && point.y >= bounds.y && point.y < bounds.y + bounds.height;
}

/** Plan from the selection frozen before native capture; never consult live tracking here. */
export function planObservationRegion({ source, screenBounds, settings, selection, windows = [] }) {
  const requestedRegion = { width: settings.roiWidth, height: settings.roiHeight };
  const fullRect = { x: 0, y: 0, ...source };
  const fullRequested = settings.selection === 'full';
  const fallbackReason = fullRequested ? null : selection.fallbackReason
    ?? (!selection.point ? 'Position indisponible : plein écran' : null);
  let cropRect = fullRequested || fallbackReason ? fullRect : boundedRect(
    screenPointToCapture(selection.point, screenBounds, source), requestedRegion, source,
  );
  let selectedWindow;
  let windowFallbackReason;
  if (!fullRequested && !fallbackReason && settings.regionScope === 'window') {
    // Native metadata is ordered front-to-back. Pick the first eligible window
    // at the fixation, not the focused application or the largest overlapping one.
    const candidate = Array.isArray(windows) ? windows.find(window =>
      Number.isSafeInteger(window?.id) && window.id > 0 && contains(window.bounds, selection.point)) : undefined;
    const windowRect = candidate && screenRectToCapture(candidate.bounds, screenBounds, source);
    if (windowRect) {
      const point = screenPointToCapture(selection.point, screenBounds, source);
      const within = boundedRect({ x: point.x - windowRect.x, y: point.y - windowRect.y }, requestedRegion, windowRect);
      cropRect = selection.headRegionPolicy === 'zones' && selection.headZone === 'center'
        ? windowRect : { ...within, x: within.x + windowRect.x, y: within.y + windowRect.y };
      selectedWindow = {
        id: candidate.id, appName: typeof candidate.appName === 'string' ? candidate.appName : 'Application',
        bounds: { ...candidate.bounds },
      };
    } else {
      windowFallbackReason = 'Aucune fenêtre visible sous la position : région limitée à l’écran.';
    }
  }
  const coversSource = cropRect.width === source.width && cropRect.height === source.height;
  const regionDisposition = fullRequested ? 'full-requested'
    : fallbackReason ? 'full-fallback' : coversSource ? 'full-size' : 'crop';
  return {
    cropRect, requestedRegion, regionDisposition, fallbackReason,
    // A second copy of the same full screen adds no context.
    includeGlobal: settings.includeGlobal && !coversSource,
    gazeAgeMs: selection.gazeAgeMs,
    ...(selectedWindow ? { selectedWindow } : {}),
    ...(windowFallbackReason ? { windowFallbackReason } : {}),
  };
}
