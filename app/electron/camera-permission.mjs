const deniedMessage = 'Accès caméra refusé. Ouvrez Réglages Système → Confidentialité et sécurité → Caméra, activez Electron, puis relancez H-Companion.';

// Never leave a fullscreen/always-on-top surface over a native permission prompt.
// The caller remains responsible for the overlay visibility after this completes.
export async function requestCameraAccess({ platform, preferences, trackerWindow, overlayWindow }) {
  if (trackerWindow.isDestroyed()) throw new Error('Calibration fermée.');
  trackerWindow.setAlwaysOnTop(false);
  if (overlayWindow && !overlayWindow.isDestroyed()) overlayWindow.hide();
  trackerWindow.hide();
  try {
    if (platform === 'darwin') {
      const status = preferences.getMediaAccessStatus('camera');
      if (status === 'denied' || status === 'restricted') throw new Error(deniedMessage);
      if (status !== 'granted' && !await preferences.askForMediaAccess('camera')) throw new Error(deniedMessage);
    }
    if (trackerWindow.isDestroyed()) throw new Error('Calibration fermée pendant l’autorisation caméra.');
  } finally {
    if (!trackerWindow.isDestroyed()) {
      trackerWindow.show();
      trackerWindow.focus();
    }
  }
}
