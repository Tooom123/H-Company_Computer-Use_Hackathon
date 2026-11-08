// Bridge for the gaze overlay (heatmap/overlay.html): it only receives gaze points and the accuracy.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("hcsOverlay", {
  onGaze: (fn) => ipcRenderer.on("overlay:gaze", (_e, p) => fn(p)),
  onAccuracy: (fn) => ipcRenderer.on("overlay:accuracy", (_e, px) => fn(px)),
});
