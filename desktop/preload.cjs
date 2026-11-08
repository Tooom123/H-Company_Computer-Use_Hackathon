// Narrow bridge: the renderer can only ask for these actions; the main process validates each one.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("hcs", {
  agent: (method, path, body) => ipcRenderer.invoke("agent", method, path, body),
  vision: {
    status: () => ipcRenderer.invoke("vision:status"),
    start: () => ipcRenderer.invoke("vision:start"),
    stop: () => ipcRenderer.invoke("vision:stop"),
  },
  platform: process.platform,
});
