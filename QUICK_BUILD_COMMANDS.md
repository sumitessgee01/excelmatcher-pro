# QUICK BUILD COMMANDS - Copy & Paste Ready!

## 🚀 EASIEST WAY - Use Build Script

### Option 1: Batch File (Windows Command Prompt)
```
Double-click: BUILD.bat
```

### Option 2: PowerShell Script
```powershell
powershell -ExecutionPolicy Bypass -File Build.ps1
```

### Option 3: PowerShell with Auto-Test
```powershell
powershell -ExecutionPolicy Bypass -File Build.ps1 -Test
```

---

## ⚡ MANUAL COMMANDS (Copy one-by-one)

### Navigate to Project
```powershell
cd "f:\Data Mather Projects\Data project 2\excelmatcher-pro"
```

### Install Dependencies (First time only)
```powershell
npm install
```

### Build Frontend
```powershell
npm run build
```

### Build Windows Setup.exe
```powershell
npm run electron:build
```

### View Your Installer
```powershell
cd release
explorer .
```

---

## 🎯 COMPLETE BUILD (Copy & Run Once)

```powershell
cd "f:\Data Mather Projects\Data project 2\excelmatcher-pro"; npm install; npm run build; npm run electron:build; explorer release
```

---

## 📋 STEP-BY-STEP WITH VERSIONS

### First Time Setup:
```powershell
# 1. Open PowerShell in project folder
cd "f:\Data Mather Projects\Data project 2\excelmatcher-pro"

# 2. Install all packages
npm install

# 3. Build frontend
npm run build

# 4. Build Windows installer (takes 2-5 mins)
npm run electron:build

# 5. Open release folder to see setup.exe
start release
```

### For Version Updates (1.0.1, 1.0.2, etc):
```powershell
# 1. Update version in package.json
notepad package.json
# Change: "version": "1.0.1"

# 2. Build
npm run build
npm run electron:build

# 3. Your new setup.exe is ready!
```

---

## 🧹 CLEAN BUILD (If Something Goes Wrong)

```powershell
# Remove old builds
rm -r dist
rm -r release
rm -r node_modules

# Fresh install and build
npm install
npm run build
npm run electron:build
```

---

## 📁 WHERE IS MY INSTALLER?

After building, find it here:

```
f:\Data Mather Projects\Data project 2\excelmatcher-pro\release\

FileMatcher-1.0.0-win-x64.exe  ← THIS IS YOUR SETUP.EXE!
```

File size: Usually 150-400 MB

---

## ✅ VERIFY INSTALLER EXISTS

```powershell
# Check if installer was created
Get-Item "release/FileMatcher-*-win-x64.exe"

# Check file size
$file = Get-Item "release/FileMatcher-*-win-x64.exe"
"Size: {0:N0} bytes ({1:N2} MB)" -f $file.Length, ($file.Length / 1MB)
```

---

## 🧪 TEST YOUR INSTALLER LOCALLY

```powershell
# Go to release folder
cd release

# Run installer
.\FileMatcher-1.0.0-win-x64.exe
```

**Installation window will appear:**
1. Read license (if you added one)
2. Choose where to install (C:\Users\YourName\AppData\...)
3. Click "Install"
4. Choose shortcuts (Desktop, Start Menu)
5. Done! App is installed

---

## 🌐 SHARE YOUR INSTALLER

### Option 1: GitHub Release (Best - Enables Auto-Updates!)
```powershell
# 1. Create git tag
git tag v1.0.0
git push origin v1.0.0

# 2. Go here: https://github.com/sumitessgee01/excelmatcher-pro/releases
# 3. Create Release from tag
# 4. Upload: release\FileMatcher-1.0.0-win-x64.exe
# 5. Add release notes
# 6. Publish

# Users now get auto-update notifications!
```

### Option 2: Direct Share
```powershell
# Copy to send elsewhere
copy "release\FileMatcher-1.0.0-win-x64.exe" "D:\Share\"
```

### Option 3: Email/Cloud
```powershell
# Zip it for easy sharing
Compress-Archive -Path "release\FileMatcher-1.0.0-win-x64.exe" `
  -DestinationPath "FileMatcher-Setup.zip"
```

---

## 🔄 BUILD FOR NEW VERSION

```powershell
# 1. Edit package.json
notepad package.json
# Change version from "1.0.0" to "1.0.1"

# 2. Quick build
npm run build; npm run electron:build

# 3. Your new FileMatcher-1.0.1-win-x64.exe is ready!
```

---

## 💾 CREATE SETUP.EXE WITH CUSTOM NAME

To rename installer to just "setup.exe":

Edit `electron-builder.yml`:
```yaml
artifactName: setup-${version}-${os}-${arch}.${ext}
```

Or:
```yaml
artifactName: FileMatcher-Setup.${ext}
```

Then rebuild:
```powershell
npm run build
npm run electron:build
```

---

## ⏱️ TYPICAL BUILD TIME

| Step | Time |
|------|------|
| npm install | 2-3 min (first time), 10s (updates) |
| npm run build | 30-60 sec |
| npm run electron:build | 2-5 min |
| **Total First Time** | **5-10 min** |
| **Total Updates** | **3-6 min** |

---

## 🎨 CUSTOMIZE INSTALLER LOOK

### Change Icon
1. Replace: `build/icon.ico` with your icon
2. Rebuild: `npm run electron:build`

### Change Product Name
Edit `electron-builder.yml`:
```yaml
productName: YourAppName
```

### Change Company Name
Edit `electron-builder.yml`:
```yaml
appId: com.yourcompany.filematcher
```

---

## 🆘 COMMON ERRORS

| Error | Solution |
|-------|----------|
| `npm: command not found` | Install Node.js from nodejs.org |
| `icon.ico not found` | Copy icon to `build/` folder |
| `Build failed` | Run `npm install` again, then rebuild |
| `Disk space error` | Clean with: `rm -r release node_modules` |
| `Installer too large` | OK! Normal for Electron apps (200-400 MB) |

---

## 📞 GETTING HELP

1. Check: `BUILD_WINDOWS_SETUP.md` for detailed guide
2. Check: `SETUP_AUTO_UPDATES.md` for update help
3. Check: `README.md` for general info
4. GitHub: https://www.electron.build/

---

**REMEMBER: Once you build, your setup.exe works just like any Windows software!** ✨
