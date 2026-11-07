/**
 * Geometry shared by capture, the overlay and (later) the action executor.
 * Source dimensions always describe the actual captured image, not an assumed
 * devicePixelRatio. Rectangles are half-open: [x, x + width) × [y, y + height).
 */

/** @typedef {{ x: number, y: number }} Point */
/** @typedef {{ width: number, height: number }} Size */
/** @typedef {Point & Size} Rect */

function finite(value, name) {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new TypeError(`${name} must be a finite number`);
  }
  return value;
}

function point(value, name) {
  if (!value || typeof value !== 'object') throw new TypeError(`${name} is required`);
  finite(value.x, `${name}.x`);
  finite(value.y, `${name}.y`);
}

function imageSize(source) {
  if (!source || typeof source !== 'object') throw new TypeError('source is required');
  for (const dimension of ['width', 'height']) {
    const value = finite(source[dimension], `source.${dimension}`);
    if (!Number.isSafeInteger(value) || value < 1) {
      throw new RangeError(`source.${dimension} must be a positive pixel integer`);
    }
  }
}

function screenRect(bounds) {
  point(bounds, 'screenBounds');
  for (const dimension of ['width', 'height']) {
    if (finite(bounds[dimension], `screenBounds.${dimension}`) <= 0) {
      throw new RangeError(`screenBounds.${dimension} must be positive`);
    }
  }
}

function imageRect(rect, source) {
  imageSize(source);
  point(rect, 'rect');
  for (const dimension of ['x', 'y', 'width', 'height']) {
    if (!Number.isSafeInteger(finite(rect[dimension], `rect.${dimension}`))) {
      throw new RangeError(`rect.${dimension} must be a pixel integer`);
    }
  }
  if (rect.x < 0 || rect.y < 0 || rect.width < 1 || rect.height < 1
      || rect.x + rect.width > source.width || rect.y + rect.height > source.height) {
    throw new RangeError('rect must be contained in the captured image');
  }
}

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

/**
 * Center a crop and translate it at edges, preserving its area where possible.
 * Oversized requests become the full source extent; tiny requests become 1 px.
 * @param {Point} center
 * @param {Size} requested
 * @param {Size} source
 * @returns {Rect}
 */
export function boundedRect(center, requested, source) {
  point(center, 'center');
  imageSize(source);
  if (!requested || typeof requested !== 'object') throw new TypeError('requested is required');
  const width = clamp(Math.round(finite(requested.width, 'requested.width')), 1, source.width);
  const height = clamp(Math.round(finite(requested.height, 'requested.height')), 1, source.height);
  return {
    x: clamp(Math.round(center.x - width / 2), 0, source.width - width),
    y: clamp(Math.round(center.y - height / 2), 0, source.height - height),
    width,
    height,
  };
}

/**
 * Map a global desktop point in DIP to the actual captured image pixels.
 * Keep points outside the screen outside; the caller decides whether to reject
 * the gaze sample, fall back or translate a candidate rectangle at the boundary.
 * @param {Point} position
 * @param {Rect} screenBounds
 * @param {Size} source
 * @returns {Point}
 */
export function screenPointToCapture(position, screenBounds, source) {
  point(position, 'position');
  screenRect(screenBounds);
  imageSize(source);
  return {
    x: (position.x - screenBounds.x) * source.width / screenBounds.width,
    y: (position.y - screenBounds.y) * source.height / screenBounds.height,
  };
}

/**
 * Clip a desktop DIP rectangle to this display, then map inward to image pixels.
 * Returns null when the visible intersection contains no complete source pixel.
 * @param {Rect} rect
 * @param {Rect} screenBounds
 * @param {Size} source
 * @returns {Rect | null}
 */
export function screenRectToCapture(rect, screenBounds, source) {
  screenRect(rect);
  screenRect(screenBounds);
  imageSize(source);
  const left = Math.max(rect.x, screenBounds.x);
  const top = Math.max(rect.y, screenBounds.y);
  const right = Math.min(rect.x + rect.width, screenBounds.x + screenBounds.width);
  const bottom = Math.min(rect.y + rect.height, screenBounds.y + screenBounds.height);
  if (right <= left || bottom <= top) return null;
  const start = screenPointToCapture({ x: left, y: top }, screenBounds, source);
  const end = screenPointToCapture({ x: right, y: bottom }, screenBounds, source);
  const x = Math.max(0, Math.ceil(start.x));
  const y = Math.max(0, Math.ceil(start.y));
  const width = Math.min(source.width, Math.floor(end.x)) - x;
  const height = Math.min(source.height, Math.floor(end.y)) - y;
  return width > 0 && height > 0 ? { x, y, width, height } : null;
}

/**
 * Map a source-pixel rectangle into an overlay covering this display.
 * The output origin is local to the display, intentionally excluding bounds.x/y.
 * @param {Rect} rect
 * @param {Size} source
 * @param {Rect} screenBounds
 * @returns {Rect}
 */
export function captureRectToDisplay(rect, source, screenBounds) {
  imageRect(rect, source);
  screenRect(screenBounds);
  return {
    x: rect.x * screenBounds.width / source.width,
    y: rect.y * screenBounds.height / source.height,
    width: rect.width * screenBounds.width / source.width,
    height: rect.height * screenBounds.height / source.height,
  };
}

/**
 * Map Holo [0, 1000] coordinates relative to a crop into global desktop DIP.
 * Supports a plain resized crop, not padding/letterboxing. Quantization happens
 * in source pixels. 1000 maps to the last pixel inside the half-open rectangle.
 * Invalid model coordinates must be rejected, not coerced into a valid click.
 * @param {Point} normalized
 * @param {Rect} cropRect
 * @param {Size} source
 * @param {Rect} screenBounds
 * @returns {Point}
 */
export function normalizedPointToScreen(normalized, cropRect, source, screenBounds) {
  point(normalized, 'normalized');
  imageRect(cropRect, source);
  screenRect(screenBounds);
  if (normalized.x < 0 || normalized.x > 1000 || normalized.y < 0 || normalized.y > 1000) {
    throw new RangeError('Model coordinates must be in [0, 1000]');
  }
  const pixelX = cropRect.x + Math.min(cropRect.width - 1, Math.round(normalized.x * cropRect.width / 1000));
  const pixelY = cropRect.y + Math.min(cropRect.height - 1, Math.round(normalized.y * cropRect.height / 1000));
  return {
    x: screenBounds.x + pixelX * screenBounds.width / source.width,
    y: screenBounds.y + pixelY * screenBounds.height / source.height,
  };
}

/** Validate untrusted renderer settings and return only the supported fields. */
export function validateSettings(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) {
    throw new TypeError('Settings must be an object');
  }
  if (!['gaze', 'head', 'hybrid', 'cursor', 'full'].includes(input.selection)) {
    throw new RangeError('Unknown selection mode');
  }
  for (const key of ['roiWidth', 'roiHeight']) {
    if (!Number.isInteger(input[key]) || input[key] < 64 || input[key] > 8192) {
      throw new RangeError(`${key} must be an integer between 64 and 8192`);
    }
  }
  for (const key of ['includeGlobal', 'overlay']) {
    if (typeof input[key] !== 'boolean') throw new TypeError(`${key} must be boolean`);
  }
  if (input.regionScope !== undefined && !['screen', 'window'].includes(input.regionScope)) {
    throw new RangeError('Unknown region scope');
  }
  return {
    selection: input.selection,
    roiWidth: input.roiWidth,
    roiHeight: input.roiHeight,
    includeGlobal: input.includeGlobal,
    overlay: input.overlay,
    ...(input.regionScope === undefined ? {} : { regionScope: input.regionScope }),
  };
}
