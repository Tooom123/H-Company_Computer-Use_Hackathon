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
  startObservation: options => ipcRenderer.invoke('companion:observation-start', options),
  stopObservation: () => ipcRenderer.invoke('companion:observation-stop'),
  listObservations: () => ipcRenderer.invoke('companion:observation-list'),
  selectObservation: frameId => ipcRenderer.invoke('companion:observation-select', frameId),
  annotateObservation: input => ipcRenderer.invoke('companion:observation-annotate', input),
  clearObservations: () => ipcRenderer.invoke('companion:observation-clear'),
  onState: callback => {
    const listener = (_event, state) => callback(state);
    ipcRenderer.on('companion:state-updated', listener);
    return () => ipcRenderer.removeListener('companion:state-updated', listener);
  },
  reportGaze: sample => ipcRenderer.send('companion:gaze', sample),
  reportHead: sample => ipcRenderer.send('companion:head', sample),
  reportTracker: status => ipcRenderer.send('companion:tracker-status', status),
  finishCalibration: () => ipcRenderer.invoke('companion:finish-calibration'),
  requestCamera: () => ipcRenderer.invoke('companion:request-camera'),
});
