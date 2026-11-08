import { readFileSync } from 'node:fs';
import { setTimeout as delay } from 'node:timers/promises';

const ID = /^[A-Za-z0-9_-]{1,96}$/;
const TERMINAL = new Set(['resolved', 'workaround', 'escalated', 'stopped', 'preflight_failed', 'abandoned', 'failed']);
export const VOICE_STOP_SHORTCUT = 'CommandOrControl+Shift+.';

export function allowedPilotRequest(method, path) {
  if (method === 'GET') return ['/pilot/status', '/pilot/scenarios'].includes(path)
    || /^\/pilot\/episodes\/[A-Za-z0-9_-]{1,96}$/.test(path);
  return method === 'POST' && (path === '/pilot/episodes'
    || /^\/pilot\/episodes\/[A-Za-z0-9_-]{1,96}\/feedback$/.test(path));
}

export function installVoicePilot({ app, ipcMain, globalShortcut, systemPreferences, panel, authorize }) {
  const base = process.env.HCS_PILOT_URL || 'http://127.0.0.1:8767';
  if (base !== 'http://127.0.0.1:8767') throw new Error('Le pilote doit utiliser le serveur local configuré.');
  const tokenPath = process.env.HCS_PILOT_TOKEN_FILE;
  if (!tokenPath) throw new Error('Démarrez le serveur vocal avant cette fenêtre.');
  const token = readFileSync(tokenPath, 'utf8').trim();
  if (token.length < 16) throw new Error('Configuration locale du pilote invalide.');
  let active = null;
  let approving = false;
  let closing = false;
  let polling = false;
  let failures = 0;

  const show = () => { if (!panel.isDestroyed()) { if (panel.isMinimized()) panel.restore(); panel.show(); panel.focus(); } };
  async function call(method, route, body, mime) {
    const response = await fetch(base + route, {
      method, headers: { Authorization: `Bearer ${token}`, ...(body === undefined ? {} : { 'Content-Type': mime || 'application/json' }) },
      ...(body === undefined ? {} : { body: mime ? body : JSON.stringify(body) }),
      signal: AbortSignal.timeout(route.startsWith('/pilot/audio') ? 120_000 : 20_000),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Le serveur a refusé la demande (${response.status}).`);
    return data;
  }
  function checkId(value) { if (typeof value !== 'string' || !ID.test(value)) throw new Error('Session invalide.'); return value; }

  // Do not expose approval IPC unless this instance owns the emergency shortcut.
  // A second window may otherwise approve a run before installation fails.
  const registered = globalShortcut.register(VOICE_STOP_SHORTCUT, () => { void stop().catch(() => show()); });
  if (!registered) throw new Error('Le raccourci d’arrêt ⌘⇧. est indisponible. Fermez les autres pilotes avant de démarrer.');

  ipcMain.handle('voice:request', (event, method, route, body) => {
    authorize(event);
    if (!allowedPilotRequest(method, route) || (body && JSON.stringify(body).length > 40_000)) throw new Error('Demande non autorisée.');
    return call(method, route, body);
  });
  ipcMain.handle('voice:microphone', async event => {
    authorize(event);
    if (process.platform !== 'darwin') return { granted: true };
    const status = systemPreferences.getMediaAccessStatus('microphone');
    return { granted: status === 'granted' || (status === 'not-determined' && await systemPreferences.askForMediaAccess('microphone')) };
  });
  ipcMain.handle('voice:audio', async (event, input) => {
    authorize(event);
    if (!input || !['request', 'feedback'].includes(input.purpose)
      || !['audio/webm', 'audio/webm;codecs=opus', 'audio/wav', 'audio/x-wav'].includes(input.mimeType)
      || !(input.data instanceof ArrayBuffer) || input.data.byteLength > 12 * 1024 * 1024 || !input.data.byteLength) {
      throw new Error('Enregistrement audio invalide ou trop volumineux.');
    }
    return call('POST', `/pilot/audio?purpose=${input.purpose}`, Buffer.from(input.data), input.mimeType);
  });
  ipcMain.handle('voice:approve', async (event, id) => {
    authorize(event); checkId(id);
    if (active || approving) throw new Error('Un passage est déjà en cours.');
    const before = await call('GET', `/pilot/episodes/${id}`);
    if (before.state !== 'awaiting_approval') throw new Error('Ce plan ne peut plus être approuvé.');
    active = id; approving = true; failures = 0;
    panel.hide();
    try {
      await delay(3000);
      if (active !== id) throw new Error('Lancement annulé.');
      return await call('POST', `/interventions/${id}/approve`, {
        approved: true,
        scope_note: 'Scénario choisi et plan approuvés dans H-Companion. Société Odoo de démonstration uniquement. Aucun message externe ni identifiant.',
      });
    } catch (error) { active = null; show(); throw error; }
    finally { approving = false; }
  });
  async function stop(id = active) {
    if (!id) { show(); return null; }
    checkId(id);
    const result = await call('POST', `/interventions/${id}/stop`, { reason: 'Arrêt demandé depuis H-Companion' });
    if (approving) active = null;
    show();
    return result;
  }
  ipcMain.handle('voice:stop', (event, id) => { authorize(event); return stop(id); });

  const timer = setInterval(async () => {
    if (!active || approving || polling) return;
    polling = true;
    try {
      const state = await call('GET', `/pilot/episodes/${active}`);
      failures = 0;
      if (TERMINAL.has(state.state)) { active = null; show(); }
    } catch { if (++failures === 3) show(); }
    finally { polling = false; }
  }, 1000);
  app.on('activate', show);
  app.on('before-quit', event => {
    if (!active || closing) return;
    event.preventDefault(); closing = true;
    void stop().finally(() => { clearInterval(timer); active = null; app.quit(); });
  });
  app.on('will-quit', () => { clearInterval(timer); globalShortcut.unregister(VOICE_STOP_SHORTCUT); });
}
