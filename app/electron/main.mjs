import { app, BrowserWindow, globalShortcut, ipcMain, protocol, net, screen, session, systemPreferences } from 'electron';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { performance } from 'node:perf_hooks';
import { setTimeout as delay } from 'node:timers/promises';
import { captureObservation } from './capture.mjs';
import { runHolo } from './holo.mjs';
import { boundedRect, screenPointToCapture, captureRectToDisplay, validateSettings } from './geometry.mjs';
import { windowIdsFromMediaSources } from './window-ids.mjs';
import { requestCameraAccess } from './camera-permission.mjs';
import { ObservationSession, validateObservationOptions } from './observation-session.mjs';
import { acceptGazeSample, acceptHeadSample, calibratedForSelection, headDiagnostics, selectAttention } from './attention-selection.mjs';
import { TargetSequence } from './target-sequence.mjs';
import { summarizeTargetScores } from './target-benchmark.mjs';

const root = fileURLToPath(new URL('..', import.meta.url));
if (existsSync(path.join(root, '.env'))) process.loadEnvFile(path.join(root, '.env'));
const devURL = process.env.HCS_DEV_URL;
if (devURL && devURL !== 'http://localhost:5173') throw new Error('Origine de développement non autorisée.');
const origin = devURL || 'hcompanion://localhost';
const binary = path.join(root, 'out/capture');
const model = process.env.HCS_MODEL || 'holo4-27b';
const models = [...new Set([model, 'holo4-27b', 'holo4-35b-a3b', 'holo3-1-35b-a3b'])];
protocol.registerSchemesAsPrivileged([{ scheme: 'hcompanion', privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true, stream: true } }]);

let panel;
let overlay;
let tracker;
let display;
let frame = null;
let gaze = null;
let head = null;
let operation = null;
let shuttingDown = false;
let displayGeneration = 0;
let calibrationInteractive = false;
let observationOverlay = false;
let observationShortcutAvailable = false;
const RECOVERY_SHORTCUT = 'CommandOrControl+Shift+Space';
const cameraRequests = new WeakMap();
const state = {
  tracker: { state: 'off', gazeCalibrated: false, headCalibrated: false },
  head: headDiagnostics(null, performance.now()), candidate: null, sent: null, observed: null, busy: null,
  settings: { selection: 'gaze', roiWidth: 800, roiHeight: 600, includeGlobal: true, overlay: true },
  benchmarkTarget: null,
};
const targets = new TargetSequence({ onTarget: target => { state.benchmarkTarget = target; broadcast(); } });
const observation = new ObservationSession({
  capture: async signal => {
    operation = new AbortController();
    try {
      return await captureFrame(AbortSignal.any([signal, operation.signal]), true);
    } finally { operation = null; }
  },
  onChange: status => { state.observation = { ...status,
    ...(status.benchmark ? { benchmarkSummary: summarizeTargetScores(observation.list().map(sample => sample.benchmark).filter(Boolean)) } : {}) }; broadcast(); },
  onFinish: () => { targets.stop(); setOverlayVisibility(); showPanel(); },
});
state.observation = { ...observation.state };

function showPanel() {
  if (shuttingDown || !panel || panel.isDestroyed()) return;
  if (panel.isMinimized()) panel.restore();
  panel.show(); panel.focus();
}
function recoverPanel() {
  if (observation.active) void observation.stop('user');
  else { if (state.busy === 'capture') operation?.abort(); showPanel(); }
}
async function captureFrame(signal, reference = false) {
  const generation = displayGeneration;
  const settings = { ...state.settings };
  const targetSnapshot = reference ? targets.beforeCapture() : null;
  const calibrationProfile = state.tracker.calibrationProfile;
  const selection = currentSelection(settings);
  state.busy = 'capture'; state.sent = null;
  broadcast();
  try {
    const captured = await captureObservation({
      binary, display, settings, signal, reference,
      excludeWindowIds: windowIdsFromMediaSources(BrowserWindow.getAllWindows().filter(window => !window.isDestroyed() && window.isVisible() && !window.isMinimized()).map(window => window.getMediaSourceId())),
      selection,
    });
    signal.throwIfAborted();
    if (generation !== displayGeneration) throw new Error('Écran modifié pendant la capture. Recommencez.');
    if (calibrationProfile) captured.calibrationProfile = calibrationProfile;
    if (targetSnapshot) captured.benchmark = targets.score(targetSnapshot, captured);
    frame = captured;
    state.observed = { frameId: captured.frameId, rect: captureRectToDisplay(captured.cropRect, { width: captured.sourceWidth, height: captured.sourceHeight }, captured.screenBounds) };
    return captured;
  } finally { state.busy = null; updateCandidate(); }
}

function isOwnURL(url) {
  try { const parsed = new URL(url); return `${parsed.protocol}//${parsed.host}` === origin; } catch { return false; }
}
function authorize(event, target = panel) {
  if (!target || target.isDestroyed() || event.sender !== target.webContents || event.senderFrame !== event.sender.mainFrame || !isOwnURL(event.senderFrame.url)) {
    throw new Error('Appel IPC non autorisé.');
  }
}
function broadcast() {
  for (const window of [panel, overlay, tracker]) {
    if (window && !window.isDestroyed()) window.webContents.send('companion:state-updated', state);
  }
}
function makeWindow(options, hash) {
  const window = new BrowserWindow({
    ...options,
    webPreferences: { preload: path.join(root, 'electron/preload.cjs'), contextIsolation: true, sandbox: true, nodeIntegration: false, backgroundThrottling: false },
  });
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('will-navigate', event => event.preventDefault());
  window.webContents.on('will-attach-webview', event => event.preventDefault());
  void window.loadURL(`${origin}/${hash === '#tracker' ? 'tracker.html' : ''}${hash || ''}`);
  return window;
}
function resetTracker() {
  gaze = null; head = null;
  state.head = headDiagnostics(null, performance.now());
  calibrationInteractive = false;
  state.tracker = { state: 'off', gazeCalibrated: false, headCalibrated: false,
    calibrationErrorPx: state.tracker.calibrationErrorPx, headCalibrationErrorPx: state.tracker.headCalibrationErrorPx };
  if (tracker && !tracker.isDestroyed()) tracker.close();
  tracker = undefined;
  setOverlayVisibility();
  broadcast();
}
function setOverlayVisibility() {
  if (!overlay || overlay.isDestroyed()) return;
  const wanted = observation.active ? observationOverlay || Boolean(state.benchmarkTarget) : state.settings.overlay;
  if (wanted && !calibrationInteractive) overlay.showInactive(); else overlay.hide();
}
function currentSelection(settings = state.settings) {
  return selectAttention({ mode: settings.selection, bounds: display.bounds, tracker: state.tracker,
    gaze, head, cursor: settings.selection === 'cursor' ? screen.getCursorScreenPoint() : null, now: performance.now() });
}
function updateCandidate() {
  if (!display) return;
  const now = performance.now();
  state.head = headDiagnostics(head, now);
  if (['tracking', 'lost'].includes(state.tracker.state)) {
    // The tracker remains alive if either calibrated signal is fresh. Selection
    // still applies the requested mode, with an explicit per-frame fallback.
    const available = Boolean(selectAttention({ mode: 'hybrid', bounds: display.bounds,
      tracker: state.tracker, gaze, head, now }).point);
    const nextState = available ? 'tracking' : 'lost';
    if (nextState !== state.tracker.state) state.tracker = { ...state.tracker, state: nextState,
      message: available ? 'Suivi actif' : 'Signaux indisponibles ; repli plein écran.' };
  }
  const source = frame
    ? { width: frame.sourceWidth, height: frame.sourceHeight }
    : { width: Math.round(display.bounds.width * display.scaleFactor), height: Math.round(display.bounds.height * display.scaleFactor) };
  const selected = currentSelection();
  const rect = !selected.point ? { x: 0, y: 0, ...source } : boundedRect(
    screenPointToCapture(selected.point, display.bounds, source),
    { width: state.settings.roiWidth, height: state.settings.roiHeight }, source,
  );
  state.candidate = captureRectToDisplay(rect, source, display.bounds);
  broadcast();
}

ipcMain.handle('companion:status', event => {
  authorize(event);
  const captureAvailable = process.platform === 'darwin' && existsSync(binary);
  return {
    platform: process.platform, model, models, apiKeyConfigured: Boolean(process.env.HAI_API_KEY?.trim()), captureAvailable, observationShortcutAvailable,
    captureError: captureAvailable ? undefined : 'Capture propre disponible sur macOS 14+, après npm run native (Xcode Command Line Tools).',
    display: { id: display.id, bounds: display.bounds, scaleFactor: display.scaleFactor },
  };
});
ipcMain.handle('companion:state', event => {
  if (event.sender === overlay?.webContents) authorize(event, overlay);
  else if (event.sender === tracker?.webContents) authorize(event, tracker);
  else authorize(event);
  return state;
});
ipcMain.handle('companion:configure', (event, input) => {
  authorize(event);
  if (state.busy || observation.active) throw new Error('Arrêtez l’observation ou attendez la fin de l’opération avant de changer le mode.');
  state.settings = validateSettings(input);
  setOverlayVisibility();
  updateCandidate();
});
ipcMain.handle('companion:start-tracker', event => {
  authorize(event);
  if (state.busy || observation.active) throw new Error('Une opération est en cours.');
  resetTracker();
  calibrationInteractive = true;
  setOverlayVisibility();
  state.tracker = { state: 'calibrating', gazeCalibrated: false, headCalibrated: false,
    message: 'Autorisez la caméra puis calibrez le signal choisi.' };
  tracker = makeWindow({ ...display.bounds, title: 'H-Companion · Calibration', frame: false, transparent: true, resizable: false, movable: false, hasShadow: false, alwaysOnTop: false }, '#tracker');
  const openedTracker = tracker;
  openedTracker.on('closed', () => {
    if (tracker !== openedTracker) return;
    tracker = undefined; gaze = null; head = null; calibrationInteractive = false;
    state.head = headDiagnostics(null, performance.now());
    state.tracker = { state: 'off', gazeCalibrated: false, headCalibrated: false,
      calibrationErrorPx: state.tracker.calibrationErrorPx, headCalibrationErrorPx: state.tracker.headCalibrationErrorPx };
    setOverlayVisibility(); broadcast();
  });
  broadcast();
});
ipcMain.handle('companion:stop-tracker', async event => {
  authorize(event, event.sender === tracker?.webContents ? tracker : panel);
  if (observation.active) await observation.stop('user');
  resetTracker();
});
ipcMain.handle('companion:finish-calibration', event => {
  authorize(event, tracker);
  calibrationInteractive = false;
  tracker.setIgnoreMouseEvents(true);
  tracker.setFocusable(false);
  setOverlayVisibility();
  panel?.focus();
  broadcast();
});
ipcMain.handle('companion:request-camera', event => {
  authorize(event, tracker);
  const requestingWindow = tracker;
  if (cameraRequests.has(requestingWindow)) return cameraRequests.get(requestingWindow);
  const request = requestCameraAccess({
    // Chromium's fake device must never open an OS permission prompt in smoke tests.
    platform: app.commandLine.hasSwitch('use-fake-device-for-media-stream') ? 'synthetic' : process.platform,
    preferences: systemPreferences, trackerWindow: requestingWindow, overlayWindow: overlay,
  }).finally(() => cameraRequests.delete(requestingWindow));
  cameraRequests.set(requestingWindow, request);
  return request;
});
ipcMain.on('companion:gaze', (event, sample) => {
  try { authorize(event, tracker); } catch { return; }
  // Receipt clock, NOT a camera-frame capture timestamp. The upstream callback
  // does not expose a reliable camera timestamp; never call this tracker latency.
  gaze = acceptGazeSample(sample, display.bounds, performance.now());
});
ipcMain.on('companion:head', (event, sample) => {
  try { authorize(event, tracker); } catch { return; }
  head = acceptHeadSample(sample, display.bounds, performance.now());
});
ipcMain.on('companion:target-presented', (event, input) => {
  try { authorize(event, overlay); } catch { return; }
  if (!observation.active || !overlay.isVisible() || calibrationInteractive) return;
  if (!input || typeof input.runId !== 'string' || !Number.isInteger(input.index)) return;
  targets.acknowledge(input);
});
ipcMain.on('companion:tracker-status', (event, status) => {
  try { authorize(event, tracker); } catch { return; }
  if (!status || !['off', 'calibrating', 'tracking', 'lost', 'error'].includes(status.state)) return;
  state.tracker = {
    state: status.state, message: typeof status.message === 'string' ? status.message.slice(0, 400) : undefined,
    calibrationErrorPx: Number.isFinite(status.calibrationErrorPx) && status.calibrationErrorPx >= 0 ? status.calibrationErrorPx : undefined,
    gazeCalibrated: typeof status.gazeCalibrated === 'boolean' ? status.gazeCalibrated : undefined,
    headCalibrated: status.headCalibrated === true,
    headCalibrationErrorPx: Number.isFinite(status.headCalibrationErrorPx) && status.headCalibrationErrorPx >= 0 ? status.headCalibrationErrorPx : undefined,
    headMessage: typeof status.headMessage === 'string' ? status.headMessage.slice(0, 400) : undefined,
    calibrationProfile: ['standard', 'wide'].includes(status.calibrationProfile) ? status.calibrationProfile : undefined,
  };
  broadcast();
});
ipcMain.handle('companion:capture', async event => {
  authorize(event);
  if (state.busy || observation.active) throw new Error('Une opération est déjà en cours.');
  if (process.platform !== 'darwin' || !existsSync(binary)) throw new Error('Capture ScreenCaptureKit indisponible ; lancez npm run native sur Mac.');
  operation = new AbortController();
  const controller = operation;
  state.busy = 'capture';
  state.sent = null;
  state.observed = null;
  frame = null;
  panel.hide();
  broadcast();
  try {
    await delay(3000, undefined, { signal: operation.signal });
    return await captureFrame(controller.signal);
  } finally {
    operation = null; state.busy = null; updateCandidate(); showPanel();
  }
});
ipcMain.handle('companion:observation-start', (event, input) => {
  authorize(event);
  const options = validateObservationOptions(input);
  if (state.busy || observation.active || calibrationInteractive) throw new Error('Terminez l’opération ou la calibration en cours.');
  if (!calibratedForSelection(state.settings.selection, state.tracker)) {
    const label = state.settings.selection === 'head' ? 'la tête' : state.settings.selection === 'hybrid' ? 'le regard et la tête' : 'le regard';
    throw new Error(`Activez et calibrez ${label} avant cette observation, ou choisissez Curseur.`);
  }
  if (process.platform !== 'darwin' || !existsSync(binary)) throw new Error('Capture macOS indisponible.');
  if (!observationShortcutAvailable) throw new Error('Le raccourci ⌘⇧Espace est déjà utilisé. Libérez-le puis relancez l’app pour pouvoir revenir au panneau.');
  observationOverlay = options.showOverlay;
  frame = null; state.sent = null; state.observed = null;
  panel.hide();
  if (options.benchmark) targets.start({ seed: options.seed, bounds: display.bounds }); else targets.stop();
  observation.start(options);
  setOverlayVisibility();
});
ipcMain.handle('companion:observation-stop', async event => { authorize(event); await observation.stop('user'); });
ipcMain.handle('companion:observation-list', event => { authorize(event); return observation.list(); });
ipcMain.handle('companion:observation-select', (event, id) => {
  authorize(event);
  if (state.busy) throw new Error('Une opération est en cours.');
  frame = observation.select(id); state.sent = null; updateCandidate();
  return frame;
});
ipcMain.handle('companion:observation-annotate', (event, input) => { authorize(event); observation.annotate(input); });
ipcMain.handle('companion:observation-clear', event => {
  authorize(event);
  if (state.busy) throw new Error('Une opération est en cours.');
  observation.clear(); frame = null; state.sent = null; state.observed = null; broadcast();
});
ipcMain.handle('companion:analyze', async (event, input) => {
  authorize(event);
  if (state.busy || observation.active) throw new Error('Une opération est déjà en cours.');
  if (!frame || input?.frameId !== frame.frameId) throw new Error('Observation expirée. Préparez une nouvelle capture.');
  if (typeof input.prompt !== 'string' || input.prompt.trim().length === 0 || input.prompt.length > 8000) throw new Error('Saisissez une consigne de 1 à 8 000 caractères.');
  if (!process.env.HAI_API_KEY?.trim()) throw new Error('Renseignez HAI_API_KEY dans app/.env puis relancez l’app.');
  const selectedModel = input.model ?? model;
  if (!models.includes(selectedModel)) throw new Error('Modèle non proposé dans cette session.');
  const capturedFrame = frame;
  operation = new AbortController();
  state.busy = 'inference';
  state.sent = { frameId: capturedFrame.frameId, rect: captureRectToDisplay(capturedFrame.cropRect, { width: capturedFrame.sourceWidth, height: capturedFrame.sourceHeight }, capturedFrame.screenBounds) };
  broadcast();
  try {
    return await runHolo({ frame: capturedFrame, prompt: input.prompt.trim(), model: selectedModel, apiKey: process.env.HAI_API_KEY, signal: AbortSignal.any([operation.signal, AbortSignal.timeout(60_000)]) });
  } finally {
    operation = null; state.busy = null; broadcast();
  }
});
ipcMain.handle('companion:cancel', async event => {
  authorize(event);
  if (observation.active) await observation.stop('user'); else operation?.abort();
});

app.whenReady().then(() => {
  protocol.handle('hcompanion', request => {
    const url = new URL(request.url);
    if (url.host !== 'localhost') return new Response('Forbidden', { status: 403 });
    const base = path.join(root, 'dist');
    let pathname;
    try { pathname = decodeURIComponent(url.pathname); } catch { return new Response('Bad URL', { status: 400 }); }
    const file = path.resolve(base, `.${pathname === '/' ? '/index.html' : pathname}`);
    if (!file.startsWith(`${base}${path.sep}`)) return new Response('Forbidden', { status: 403 });
    return net.fetch(pathToFileURL(file).toString());
  });
  session.defaultSession.setPermissionRequestHandler((contents, permission, callback, details) => {
    const allowed = contents === tracker?.webContents && permission === 'media' && isOwnURL(details.requestingUrl) && details.mediaTypes?.length > 0 && details.mediaTypes.every(type => type === 'video');
    callback(Boolean(allowed));
  });
  session.defaultSession.setPermissionCheckHandler((contents, permission, requestingOrigin, details) =>
    contents === tracker?.webContents && permission === 'media' && isOwnURL(requestingOrigin) && details.mediaType === 'video');
  session.defaultSession.on('will-download', event => event.preventDefault());
  display = screen.getPrimaryDisplay();
  panel = makeWindow({ width: 1180, height: 850, minWidth: 760, minHeight: 650, title: 'H-Companion · Vision Lab', backgroundColor: '#f4f6f1' }, '');
  observationShortcutAvailable = globalShortcut.register(RECOVERY_SHORTCUT, recoverPanel);
  // Returning through the Dock also stops sampling: looking at the lab must not
  // silently keep recording the software behind it.
  panel.on('show', () => { if (observation.active) void observation.stop('panel-returned'); });
  app.on('activate', recoverPanel);
  overlay = makeWindow({ ...display.bounds, title: 'H-Companion · Zone', transparent: true, frame: false, focusable: false, resizable: false, movable: false, hasShadow: false, alwaysOnTop: true, skipTaskbar: true, show: false }, '#overlay');
  overlay.setIgnoreMouseEvents(true);
  overlay.setAlwaysOnTop(true, 'floating');
  overlay.webContents.once('did-finish-load', () => { setOverlayVisibility(); updateCandidate(); });
  panel.on('closed', () => { if (!shuttingDown) app.quit(); });
  const invalidateDisplay = () => {
    displayGeneration += 1;
    if (observation.active) void observation.stop('display-changed');
    operation?.abort(); resetTracker(); frame = null; state.sent = null; state.observed = null;
    display = screen.getPrimaryDisplay(); overlay?.setBounds(display.bounds);
    state.tracker = { state: 'off', message: 'Géométrie écran modifiée : relancez la calibration et capturez à nouveau.' };
    broadcast();
    panel?.webContents.reload();
  };
  screen.on('display-metrics-changed', (_event, _display, metrics) => {
    if (metrics.some(metric => ['bounds', 'scaleFactor', 'rotation'].includes(metric))) invalidateDisplay();
  });
  screen.on('display-removed', invalidateDisplay);
  screen.on('display-added', invalidateDisplay);
  const timer = setInterval(updateCandidate, 100);
  app.on('before-quit', () => { shuttingDown = true; clearInterval(timer); void observation.stop('user'); operation?.abort(); resetTracker(); });
  app.on('will-quit', () => globalShortcut.unregisterAll());
});
app.on('window-all-closed', () => app.quit());
