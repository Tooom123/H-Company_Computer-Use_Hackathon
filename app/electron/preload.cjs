const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('companion', {
  getStatus: () => ipcRenderer.invoke('companion:status'),
  getState: () => ipcRenderer.invoke('companion:state'),
  configure: settings => ipcRenderer.invoke('companion:configure', settings),
  startTracker: () => ipcRenderer.invoke('companion:start-tracker'),
  stopTracker: () => ipcRenderer.invoke('companion:stop-tracker'),
  capture: () => ipcRenderer.invoke('companion:capture'),
  analyze: input => ipcRenderer.invoke('companion:analyze', input),
  cancel: () => ipcRenderer.invoke('companion:cancel'),
  onState: callback => {
    const listener = (_event, state) => callback(state);
    ipcRenderer.on('companion:state-updated', listener);
    return () => ipcRenderer.removeListener('companion:state-updated', listener);
  },
  reportGaze: sample => ipcRenderer.send('companion:gaze', sample),
  reportTracker: status => ipcRenderer.send('companion:tracker-status', status),
  finishCalibration: () => ipcRenderer.invoke('companion:finish-calibration'),
});
