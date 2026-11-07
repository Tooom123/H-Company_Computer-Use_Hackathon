// Electron BrowserWindow.getMediaSourceId() exposes the CGWindowID on macOS:
// window:<native-id>:<web-contents-id>. Do not confuse it with an NSView pointer.
export function windowIdsFromMediaSources(sources) {
  if (!Array.isArray(sources)) throw new Error('Liste des fenêtres H-Companion invalide.');
  // The panel and both overlays can legitimately all be hidden during observation.
  // An empty visible-window list needs no explicit native exclusion.
  return [...new Set(sources.map(source => {
    const match = typeof source === 'string' && /^window:(\d+):\d+$/.exec(source);
    const id = match ? Number(match[1]) : NaN;
    if (!Number.isSafeInteger(id) || id <= 0 || id > 0xffff_ffff) {
      throw new Error('Identifiant natif de fenêtre invalide ; capture annulée.');
    }
    return id;
  }))];
}
