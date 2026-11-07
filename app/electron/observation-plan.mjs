import { boundedRect, screenPointToCapture } from './geometry.mjs';

/** Plan from the selection frozen before native capture; never consult live tracking here. */
export function planObservationRegion({ source, screenBounds, settings, selection }) {
  const requestedRegion = { width: settings.roiWidth, height: settings.roiHeight };
  const fullRect = { x: 0, y: 0, ...source };
  const fullRequested = settings.selection === 'full';
  const fallbackReason = fullRequested ? null : selection.fallbackReason
    ?? (!selection.point ? 'Position indisponible : plein écran' : null);
  const cropRect = fullRequested || fallbackReason ? fullRect : boundedRect(
    screenPointToCapture(selection.point, screenBounds, source), requestedRegion, source,
  );
  const coversSource = cropRect.width === source.width && cropRect.height === source.height;
  const regionDisposition = fullRequested ? 'full-requested'
    : fallbackReason ? 'full-fallback' : coversSource ? 'full-size' : 'crop';
  return {
    cropRect, requestedRegion, regionDisposition, fallbackReason,
    // A second copy of the same full screen adds no context.
    includeGlobal: settings.includeGlobal && !coversSource,
    gazeAgeMs: selection.gazeAgeMs,
  };
}
