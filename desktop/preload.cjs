// Narrow bridge: the renderer can only ask for these actions; the main process validates each one.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("hcs", {
  agent: (method, path, body) => ipcRenderer.invoke("agent", method, path, body),
  plans: () => ipcRenderer.invoke("plans"),
  checkout: (plan) => ipcRenderer.invoke("checkout", plan),
  openCase: (caseId) => ipcRenderer.invoke("open-case", caseId),
  openDashboard: () => ipcRenderer.invoke("open-dashboard"),
  vision: {
    status: () => ipcRenderer.invoke("vision:status"),
    start: () => ipcRenderer.invoke("vision:start"),
    stop: () => ipcRenderer.invoke("vision:stop"),
  },
  window: {
    minimize: () => ipcRenderer.send("win", "minimize"),
    maximize: () => ipcRenderer.send("win", "maximize"),
    close: () => ipcRenderer.send("win", "close"),
    onState: (fn) => ipcRenderer.on("win:state", (_e, state) => fn(state)),
  },
  platform: process.platform,
});
