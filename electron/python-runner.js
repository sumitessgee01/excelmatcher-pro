const { spawn } = require("child_process");
const path = require("path");

let pythonProcess = null;

function startPythonBackend({ isPackaged, userDataPath, port = 8787 }) {
  if (pythonProcess) {
    return pythonProcess;
  }

  // Prefer a project-local data folder in dev mode so users can inspect learning.db/exports.
  // In packaged mode we fall back to userDataPath to avoid permission issues.
  const projectDataDir = path.join(__dirname, "..", "data");
  const dataDir = isPackaged ? path.join(userDataPath, "excelmatcher-data") : projectDataDir;
  const args = ["--port", String(port), "--data-dir", dataDir];
  let command = "py";
  let commandArgs = [];

  if (isPackaged) {
    const exePath = path.join(process.resourcesPath, "backend", "server.exe");
    command = exePath;
    commandArgs = args;
  } else {
    const scriptPath = path.join(__dirname, "..", "backend", "server.py");
    command = "py";
    commandArgs = ["-3", scriptPath, ...args];
  }

  pythonProcess = spawn(command, commandArgs, {
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"]
  });

  pythonProcess.stdout.on("data", (buf) => {
    const text = buf.toString().trim();
    if (text) {
      console.log(`[python] ${text}`);
    }
  });

  pythonProcess.stderr.on("data", (buf) => {
    const text = buf.toString().trim();
    if (text) {
      console.error(`[python:error] ${text}`);
    }
  });

  pythonProcess.on("exit", (code, signal) => {
    console.log(`[python] exited code=${code} signal=${signal}`);
    pythonProcess = null;
  });

  return pythonProcess;
}

function stopPythonBackend() {
  if (!pythonProcess) {
    return;
  }
  try {
    pythonProcess.kill();
  } catch (error) {
    console.error(`Failed to stop python backend: ${error.message}`);
  }
}

module.exports = {
  startPythonBackend,
  stopPythonBackend
};
