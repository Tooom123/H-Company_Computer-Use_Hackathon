// Bridge for the gaze overlay (heatmap/overlay.html): it receives gaze points, the accuracy and the mode, and
// during calibration asks the app to record a dot, fit, and check a dot. Nothing else of Electron is exposed.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("hcsOverlay", {
  onGaze: (fn) => ipcRenderer.on("overlay:gaze", (_e, p) => fn(p)),
  onAccuracy: (fn) => ipcRenderer.on("overlay:accuracy", (_e, px) => fn(px)),
  onHoneycomb: (fn) => ipcRenderer.on("overlay:honeycomb", (_e, on) => fn(on)),
  onMode: (fn) => ipcRenderer.on("overlay:mode", (_e, m) => fn(m)),
  calibPoint: (x, y) => ipcRenderer.invoke("overlay:calib-point", { x, y }),
  fit: () => ipcRenderer.invoke("overlay:fit"),
  validate: (x, y) => ipcRenderer.invoke("overlay:validate", { x, y }),
  done: (errorPx) => ipcRenderer.send("overlay:done", errorPx),
  close: () => ipcRenderer.send("overlay:close"),
});
