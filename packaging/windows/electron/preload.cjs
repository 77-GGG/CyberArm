const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('cyberarmDesktop', {
  checkForUpdates: () => ipcRenderer.invoke('update:check'),
  downloadUpdate: () => ipcRenderer.invoke('update:download'),
  installUpdate: () => ipcRenderer.invoke('update:install'),
  onUpdateDownloaded: callback => ipcRenderer.on('update:downloaded', callback),
  onUpdateProgress: callback => ipcRenderer.on('update:progress', (_event, percent) => callback(percent))
});
