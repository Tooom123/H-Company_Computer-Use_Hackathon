// Electron BrowserWindow.getMediaSourceId() exposes the CGWindowID on macOS:
// window:<native-id>:<web-contents-id>. Do not confuse it with an NSView pointer.
export function windowIdsFromMediaSources(sources) {
  if (!Array.isArray(sources) || sources.length === 0) throw new Error('Aucune fenêtre H-Companion à exclure.');
  return [...new Set(sources.map(source => {
    const match = typeof source === 'string' && /^window:(\d+):\d+$/.exec(source);
    const id = match ? Number(match[1]) : NaN;
    if (!Number.isSafeInteger(id) || id <= 0 || id > 0xffff_ffff) {
      throw new Error('Identifiant natif de fenêtre invalide ; capture annulée.');
    }
    return id;
  }))];
}
