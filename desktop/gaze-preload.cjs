// Bridge for the built-in gaze window (heatmap/vision.html?embedded=1): the page can only report gaze points,
// its measured accuracy, and ask to start tracking or to close. Nothing else of Electron is exposed.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("hcsGaze", {
  sample: (x, y) => ipcRenderer.send("gaze:sample", { x, y }),
  accuracy: (px) => ipcRenderer.send("gaze:accuracy", px),
  track: () => ipcRenderer.send("gaze:track"),
  close: () => ipcRenderer.send("gaze:close"),
});
