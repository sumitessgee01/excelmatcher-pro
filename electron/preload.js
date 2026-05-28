const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electron", {
  openFileDialog: () => ipcRenderer.invoke("open-file-dialog"),
  saveFileDialog: (defaultName) => ipcRenderer.invoke("save-file-dialog", defaultName),
  saveExportFromUrl: (downloadUrl, defaultName, options = {}) =>
    ipcRenderer.invoke("save-export-from-url", { downloadUrl, defaultName, ...options }),
  getUserDataPath: () => ipcRenderer.invoke("get-user-data-path"),
  shellOpen: (targetPath) => ipcRenderer.invoke("shell-open", targetPath)
});
