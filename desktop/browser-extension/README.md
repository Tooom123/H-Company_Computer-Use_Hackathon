# Gaze magnet (browser extension)

While H Companion tracks your gaze, the red honeycomb snaps to the buttons and links you look at. On web pages
the app cannot see the controls by itself (the screen is just pixels), so this small Chrome / Chromium / Edge /
Brave extension tells it where they are.

- What leaves the page: the boxes of the visible clickable controls (screen pixels) and a 40-character label,
  only to `http://127.0.0.1:8770`, only while the browser window has focus. No URL, no text, no screenshot.
- Cost: one DOM query when the page scrolls, resizes or changes (throttled to 150 ms), plus one heartbeat a
  second. Nothing runs if the app is closed (the request just fails).

## Install

1. Open `chrome://extensions`, turn on **Developer mode**.
2. **Load unpacked** and pick this folder (`desktop/browser-extension`).
3. Start H Companion, turn Vision on, calibrate: the honeycomb now clings to the controls of the page.

## Limits

- Browsers do not tell a page where its window is on screen. The extension assumes toolbars on top and even
  borders; on Linux Wayland the window position is unknown, so it is exact for a **maximized** window only.
- Page zoom other than the zoom at load time is approximated.
- Desktop apps (outside the browser) need the OS accessibility tree (AX on macOS, AT-SPI on Linux): not done here.
