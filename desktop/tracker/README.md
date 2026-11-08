# Background gaze tracker

Always-on webcam gaze tracking for the desktop app, whatever app is in front (desktop, browser, game): a plain
Python process reads the camera, finds the irises and the head pose with MediaPipe Face Landmarker, and maps them to
a screen point with a ridge regression fitted during calibration (9 dots clicked while looked at, 4 more looked at
to measure the accuracy). The desktop app drives it and draws the red honeycomb over the screen; the agent gets the
gaze to crop its screenshots (Vision tab, opt-in).

```bash
uv venv desktop/tracker/.venv
uv pip install --python desktop/tracker/.venv/bin/python -r desktop/tracker/requirements.txt
```

Then Vision → Recalibrate in the app. The face model (3.6 MB) is downloaded once to `~/.cache/hcs-companion/`.
On macOS, camera permission is requested before calibration opens. Recalibrate first opens a **local camera
preview inside the Vision panel**, with a Camera 1 / Camera 2 selector (for example, Mac vs Continuity Camera).
No dots appear yet. Once the camera sees a face, click **I can see myself — start calibration**. The main process
checks the face again before opening the targets. The preview is never forwarded to the agent or saved to disk.
The calibration stays below system dialogs and leaves the menu bar and Dock accessible. **Esc**, **Cmd/Ctrl+W**
or **Cancel calibration** returns to Vision and stops the camera. During startup, **Stop tracking** also cancels
the pending request; granting permission afterwards will not reopen calibration. If camera access is denied,
allow H Companion / Electron in System Settings → Privacy & Security → Camera, then retry.
The tracker serves the preview locally on 127.0.0.1:8769; only screen points go to the agent. Close any other app that holds the camera.
`HCS_TRACKER_PYTHON` points to another interpreter; `HCS_VISION_WINDOW=browser|electron` forces the older modes.
