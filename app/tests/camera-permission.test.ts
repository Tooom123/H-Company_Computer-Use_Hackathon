import { expect, it, vi } from 'vitest';
import { requestCameraAccess } from '../electron/camera-permission.mjs';

function fixture(status = 'not-determined') {
  const events: string[] = [];
  let destroyed = false;
  const trackerWindow = {
    isDestroyed: () => destroyed,
    setAlwaysOnTop: (value: boolean) => events.push(`top:${value}`),
    hide: () => events.push('tracker:hide'), show: () => events.push('tracker:show'), focus: () => events.push('tracker:focus'),
  };
  const overlayWindow = { isDestroyed: () => false, hide: () => events.push('overlay:hide') };
  const preferences = { getMediaAccessStatus: () => status, askForMediaAccess: vi.fn(async () => { events.push('os:prompt'); return true; }) };
  return { events, trackerWindow, overlayWindow, preferences, destroy: () => { destroyed = true; } };
}

it('hides both surfaces and drops always-on-top before asking macOS', async () => {
  const f = fixture();
  await requestCameraAccess({ platform: 'darwin', ...f });
  expect(f.events).toEqual(['top:false', 'overlay:hide', 'tracker:hide', 'os:prompt', 'tracker:show', 'tracker:focus']);
  expect(f.preferences.askForMediaAccess).toHaveBeenCalledWith('camera');
});

it('does not prompt again for an already granted camera permission', async () => {
  const f = fixture('granted');
  await requestCameraAccess({ platform: 'darwin', ...f });
  expect(f.preferences.askForMediaAccess).not.toHaveBeenCalled();
});

it('restores an accessible error surface after refusal instead of trapping the user', async () => {
  const f = fixture('denied');
  await expect(requestCameraAccess({ platform: 'darwin', ...f })).rejects.toThrow('Réglages Système');
  expect(f.preferences.askForMediaAccess).not.toHaveBeenCalled();
  expect(f.events.slice(-2)).toEqual(['tracker:show', 'tracker:focus']);
});

it('does not resurrect a calibration closed while permission was pending', async () => {
  const f = fixture();
  f.preferences.askForMediaAccess.mockImplementation(async () => { f.destroy(); return true; });
  await expect(requestCameraAccess({ platform: 'darwin', ...f })).rejects.toThrow('fermée');
  expect(f.events).not.toContain('tracker:show');
});

it('leaves the physical-camera OS permission untouched in synthetic-camera smoke tests', async () => {
  const f = fixture();
  await requestCameraAccess({ platform: 'synthetic', ...f });
  expect(f.preferences.askForMediaAccess).not.toHaveBeenCalled();
});
