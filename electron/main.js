const { app, BrowserWindow, ipcMain, dialog, shell, Menu, nativeTheme } = require("electron");
const { autoUpdater } = require("electron-updater");
const path = require("path");
const fs = require("fs");
const { Readable } = require("stream");
const { pipeline } = require("stream/promises");
const { startPythonBackend, stopPythonBackend } = require("./python-runner");

let mainWindow = null;
let backendStarted = false;
const APP_NAME = "FileMatcher";

function setupAutoUpdater() {
  autoUpdater.checkForUpdatesAndNotify();
  
  autoUpdater.on("update-available", () => {
    dialog.showMessageBox(mainWindow, {
      type: "info",
      title: "Update Available",
      message: "A new version of FileMatcher is available.",
      detail: "The update will be downloaded and installed automatically.",
      buttons: ["OK"]
    });
  });

  autoUpdater.on("update-downloaded", () => {
    dialog.showMessageBox(mainWindow, {
      type: "info",
      title: "Update Ready",
      message: "FileMatcher update is ready to install.",
      detail: "The app will restart to apply the update.",
      buttons: ["Restart Now", "Later"]
    }).then((result) => {
      if (result.response === 0) {
        autoUpdater.quitAndInstall();
      }
    });
  });

  autoUpdater.on("error", (error) => {
    dialog.showErrorBox("Update Error", "Failed to update FileMatcher: " + error.message);
  });
}

function appIconPath() {
  if (app.isPackaged) {
    return path.join(__dirname, "..", "dist", "icon.png");
  }
  return path.join(__dirname, "..", "build", "icon.png");
}

async function waitForBackend(baseUrl, timeoutMs = 60000, intervalMs = 500) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const res = await fetch(`${baseUrl}/health`);
      if (res.ok) {
        return true;
      }
    } catch {
      // backend not ready
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  return false;
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    title: APP_NAME,
    width: 1280,
    height: 800,
    show: false,
    backgroundColor: "#0F172A",
    icon: appIconPath(),
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, "preload.js")
    }
  });
  // Remove default menu bar items like File/Edit/View.
  mainWindow.removeMenu();
  mainWindow.setMenuBarVisibility(false);

  const isDev = !app.isPackaged;
  if (isDev) {
    await mainWindow.loadURL("http://localhost:5173");
  } else {
    await mainWindow.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }

  const backendReady = await waitForBackend("http://127.0.0.1:8787");
  if (backendReady) {
    mainWindow.show();
  } else {
    dialog.showErrorBox(
      "Backend Startup Failed",
      "Local Python backend did not become healthy in time."
    );
    mainWindow.show();
  }
}

function setupIpc() {
  ipcMain.handle("open-file-dialog", async () => {
    const result = await dialog.showOpenDialog({
      properties: ["openFile"],
      filters: [
        { name: "Spreadsheet Files", extensions: ["xlsx", "xls", "csv"] },
        { name: "All Files", extensions: ["*"] }
      ]
    });
    return result.canceled ? [] : result.filePaths;
  });

  ipcMain.handle("save-file-dialog", async (_event, defaultName) => {
    const result = await dialog.showSaveDialog({
      defaultPath: defaultName || "FileMatcher_Report.xlsx",
      filters: [{ name: "Excel", extensions: ["xlsx"] }]
    });
    return result.canceled ? "" : result.filePath || "";
  });

  ipcMain.handle("get-user-data-path", () => app.getPath("userData"));
  ipcMain.handle("shell-open", async (_event, targetPath) => shell.openPath(targetPath));

  ipcMain.handle("save-export-from-url", async (_event, payload) => {
    const downloadUrl = String(payload?.downloadUrl || "").trim();
    const rawName = String(payload?.defaultName || "FileMatcher_Report.xlsx").trim();
    const defaultName = path.basename(rawName).toLowerCase().endsWith(".xlsx")
      ? path.basename(rawName)
      : `${path.basename(rawName)}.xlsx`;
    const mode = String(payload?.mode || "dialog");
    const preferredDir = String(payload?.directory || "").trim();

    if (!downloadUrl) {
      throw new Error("Missing download URL");
    }

    let filePath = "";
    let usedDialog = false;

    if (mode === "auto" && preferredDir) {
      filePath = path.join(preferredDir, defaultName);
    } else {
      usedDialog = true;
      const saveResult = await dialog.showSaveDialog({
        defaultPath: preferredDir ? path.join(preferredDir, defaultName) : defaultName,
        filters: [{ name: "Excel", extensions: ["xlsx"] }]
      });
      if (saveResult.canceled || !saveResult.filePath) {
        return { canceled: true, filePath: "", directory: "", usedDialog };
      }
      filePath = saveResult.filePath;
    }

    const res = await fetch(downloadUrl);
    if (!res.ok || !res.body) {
      throw new Error(`Download failed: ${res.status}`);
    }

    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    const out = fs.createWriteStream(filePath);
    await pipeline(Readable.fromWeb(res.body), out);
    return {
      canceled: false,
      filePath,
      directory: path.dirname(filePath),
      usedDialog
    };
  });
}

app.whenReady().then(async () => {
  app.setName(APP_NAME);
  app.setAppUserModelId("com.essgee.filematcher");
  // Keep native chrome dark to avoid white top/title area.
  nativeTheme.themeSource = "dark";
  Menu.setApplicationMenu(null);

  if (!backendStarted) {
    startPythonBackend({
      isPackaged: app.isPackaged,
      userDataPath: app.getPath("userData"),
      port: 8787
    });
    backendStarted = true;
  }

  setupIpc();
  await createWindow();
  
  // Setup auto-updater after window is created
  setupAutoUpdater();

  app.on("activate", async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      await createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  stopPythonBackend();
});
