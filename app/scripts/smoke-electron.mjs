// Launches the built app with Chromium's synthetic camera. No physical webcam,
// screenshot or Holo request is used. Keep this separate from the pure tests.
import { _electron as electron } from 'playwright';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';

const root = fileURLToPath(new URL('..', import.meta.url));
const profile = await mkdtemp(path.join(tmpdir(), 'hcompanion-smoke-'));
const instance = await electron.launch({
  args: [`--user-data-dir=${profile}`, '--use-fake-device-for-media-stream', root],
  env: { ...process.env, HAI_API_KEY: '', HCS_DEV_URL: '' },
  timeout: 30_000,
});
const errors = [];
instance.on('window', page => page.on('pageerror', error => errors.push(error.message)));
try {
  const panel = await instance.firstWindow();
  await panel.getByRole('heading', { name: 'Voir ce que voit Holo.' }).waitFor();
  const status = await panel.evaluate(() => window.companion.getStatus());
  assert.equal(status.apiKeyConfigured, false);
  assert.equal((await panel.evaluate(() => window.companion.getState())).tracker.state, 'off');
  // The window event can fire before navigation populates page.url().
  const opened = instance.waitForEvent('window', { timeout: 15_000 });
  await panel.getByRole('button', { name: 'Activer la caméra et calibrer' }).click();
  const tracker = await opened;
  await tracker.waitForURL('**/tracker.html#tracker', { timeout: 15_000 });
  const windowLevels = await instance.evaluate(({ BrowserWindow }) => {
    const windows = BrowserWindow.getAllWindows();
    return { trackerOnTop: windows.find(w => w.webContents.getURL().includes('#tracker'))?.isAlwaysOnTop(), overlayVisible: windows.find(w => w.webContents.getURL().includes('#overlay'))?.isVisible() };
  });
  assert.deepEqual(windowLevels, { trackerOnTop: false, overlayVisible: false });
  await tracker.getByRole('button', { name: /Activer la caméra et calibrer/ }).click();
  await tracker.getByRole('heading', { name: 'Fixez la cible, puis cliquez dessus.' }).waitFor({ timeout: 30_000 });
  await tracker.waitForFunction(() => {
    const video = document.getElementById('webgazerVideoFeed');
    return video?.readyState >= 2 && video.srcObject?.active;
  }, undefined, { timeout: 20_000 });
  // Wait for one inference to exercise MediaPipe/WASM under the production CSP.
  await tracker.waitForTimeout(2000);
  assert.equal(await tracker.evaluate(() => window.webgazer.params.faceMeshSolutionPath.startsWith('hcompanion://localhost/')), true);
  await assert.rejects(tracker.evaluate(() => window.companion.capture()), /non autorisé/);
  await tracker.getByRole('button', { name: 'Fermer la calibration' }).click();
  await panel.waitForFunction(async () => (await window.companion.getState()).tracker.state === 'off');
  // Exercise the hidden-panel lifecycle, stopping inside the 3-second lead-in
  // so this synthetic-camera test never captures the physical desktop.
  await assert.rejects(panel.evaluate(() => window.companion.startObservation({ durationSeconds: 15, showOverlay: false })), /calibrez/);
  await panel.getByRole('radio', { name: 'Curseur', exact: true }).check();
  await panel.getByRole('button', { name: 'Observer et masquer le panneau' }).click();
  const hidden = await instance.evaluate(({ BrowserWindow, globalShortcut }) => ({
    panelVisible: BrowserWindow.getAllWindows().find(w => w.webContents.getURL() === 'hcompanion://localhost/')?.isVisible(),
    shortcutRegistered: globalShortcut.isRegistered('CommandOrControl+Shift+Space'),
  }));
  assert.deepEqual(hidden, { panelVisible: false, shortcutRegistered: true });
  await panel.evaluate(() => window.companion.stopObservation());
  assert.equal(await panel.evaluate(() => window.companion.listObservations()).then(frames => frames.length), 0);
  assert.equal(await instance.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().find(w => w.webContents.getURL() === 'hcompanion://localhost/')?.isVisible()), true);
  assert.deepEqual(errors, []);
  console.log('Electron smoke passed: isolated IPC, local WebGazer/WASM, synthetic camera, hidden-panel observation start/stop. No physical webcam, capture or Holo call.');
} finally {
  await instance.close();
  await rm(profile, { recursive: true, force: true });
}
