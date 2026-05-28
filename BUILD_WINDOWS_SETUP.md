# FileMatcher - Windows Setup.exe Builder Guide

Complete step-by-step guide to build a professional Windows installer (setup.exe) just like other Windows software.

## 📋 Prerequisites

Before starting, ensure you have:

- ✅ Node.js 18+ installed
- ✅ Git installed
- ✅ Python 3.8+ installed
- ✅ Visual C++ Build Tools (required for electron-builder on Windows)
- ✅ Windows 10 or later

### Install Visual C++ Build Tools (if needed)

Open PowerShell as Administrator and run:

```powershell
# Download and install Visual C++ Build Tools
winget install Microsoft.VisualStudio.2022.BuildTools
```

Or download from: https://visualstudio.microsoft.com/visual-cpp-build-tools/

---

## 🔧 Step-by-Step Build Commands

### Step 1: Navigate to Project Directory

```powershell
cd "f:\Data Mather Projects\Data project 2\excelmatcher-pro"
```

### Step 2: Install All Dependencies

```powershell
npm install
```

**Output should show:** ✓ All packages installed successfully

### Step 3: Update Version (Optional)

Edit `package.json` to set version:

```powershell
# Using Notepad (or your editor)
notepad package.json
```

Change:
```json
"version": "1.0.0"
```

To:
```json
"version": "1.0.1"
```

### Step 4: Clean Previous Builds

```powershell
# Remove old build artifacts
Remove-Item -Path "dist" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -Path "release" -Recurse -Force -ErrorAction SilentlyContinue
```

### Step 5: Build Frontend Assets

```powershell
npm run build
```

**What it does:**
- Compiles React code
- Optimizes for production
- Creates `dist/` folder with compiled files

**Output shows:** ✓ dist/index.html and other assets

### Step 6: Build Windows Installer

```powershell
npm run electron:build
```

**What it does:**
- Packages Electron app
- Bundles Python backend
- Creates setup.exe installer
- Creates portable app (.exe)
- Generates .nsis installer scripts

**Output shows:** Creating installer...

---

## 📦 Output Files Location

After building, check the `release/` folder:

```powershell
# List all release files
Get-ChildItem -Path "release" -Recurse
```

You'll see files like:

```
release/
├── FileMatcher-1.0.1-win-x64.exe         ← MAIN INSTALLER (setup.exe equivalent)
├── FileMatcher-1.0.1-win-x64-unpacked/   ← Unpacked files
├── builder-effective-config.yaml
└── FileMatcher-1.0.1-nsis-web-x64.exe    ← Web installer (optional)
```

---

## 🚀 Complete Build Command (All-in-One)

Run this single command to build everything:

```powershell
cd "f:\Data Mather Projects\Data project 2\excelmatcher-pro"; npm run build; npm run electron:build
```

Or create a batch file for easy rebuilding:

**Create file:** `build.bat`

```batch
@echo off
echo Building FileMatcher Setup...
cd /d "f:\Data Mather Projects\Data project 2\excelmatcher-pro"
echo.
echo Step 1: Installing dependencies...
call npm install
echo.
echo Step 2: Building frontend...
call npm run build
echo.
echo Step 3: Building Windows installer...
call npm run electron:build
echo.
echo Build complete! Check release/ folder for installer.
echo.
pause
```

Save this file in the project directory and double-click to build!

---

## 🎯 Installer Customization

The installer is configured in `electron-builder.yml`. Key settings:

### Current Configuration:

```yaml
appId: com.essgee.filematcher
productName: FileMatcher
artifactName: FileMatcher-${version}-${os}-${arch}.${ext}

win:
  icon: build/icon.ico              # Installer icon
  target:
    - target: nsis
      arch:
        - x64                        # 64-bit only

nsis:
  oneClick: false                    # Show installation path choice
  perMachine: false                  # Install per user, not system-wide
  allowToChangeInstallationDirectory: true
  createDesktopShortcut: true
  createStartMenuShortcut: true
  shortcutName: FileMatcher
```

### Customize the Installer

Edit `electron-builder.yml`:

```powershell
notepad electron-builder.yml
```

**Change installer appearance:**

```yaml
nsis:
  oneClick: false                    # false = professional installer
  perMachine: false                  # true = install for all users
  allowToChangeInstallationDirectory: true
  createDesktopShortcut: true        # Add desktop shortcut
  createStartMenuShortcut: true      # Add start menu
  installerIcon: build/icon.ico      # Installer icon
  uninstallerIcon: build/icon.ico    # Uninstaller icon
  installerHeader: build/header.bmp  # 150x57 header image (optional)
  installerSidebar: build/side.bmp   # 164x314 sidebar image (optional)
```

---

## 🖼️ Customizing Icons and Images

### Update App Icon

Replace `build/icon.ico` with your custom icon.

**Create icon from PNG:**

```powershell
# Using Python
python -m pip install Pillow
```

Then create a Python script to convert PNG to ICO:

```python
# convert_to_ico.py
from PIL import Image

img = Image.open("your_icon.png")
img.save("build/icon.ico")
```

### Add Installer Header (Optional)

Create `build/header.bmp` (150x57 pixels)  
Create `build/side.bmp` (164x314 pixels)

---

## ✅ Verification Checklist

After building, verify everything:

```powershell
# Check if installer exists
Test-Path "release/FileMatcher-1.0.1-win-x64.exe"

# Check file size (should be 150-500 MB)
Get-Item "release/FileMatcher-1.0.1-win-x64.exe" | Select-Object -Property Length

# Verify it's a valid Windows executable
file "release/FileMatcher-1.0.1-win-x64.exe"
```

---

## 📥 Installing Your Setup.exe Locally

### Test the Installer

```powershell
# Navigate to release folder
cd "release"

# Run installer
.\FileMatcher-1.0.1-win-x64.exe
```

**Installer Steps:**
1. License agreement (if added)
2. Choose installation directory
3. Create desktop shortcut? (Yes/No)
4. Create start menu shortcuts? (Yes/No)
5. Install files
6. Complete installation
7. Launch app

### Verify Installation

After installation, check:

```powershell
# Find install location (usually)
cd "$env:APPDATA\FileMatcher"
Get-ChildItem

# Or find in Program Files
Get-ChildItem "C:\Program Files\FileMatcher" -ErrorAction SilentlyContinue
Get-ChildItem "C:\Users\$env:USERNAME\AppData\Local\FileMatcher" -ErrorAction SilentlyContinue
```

---

## 🌐 Distributing Your Installer

### Option 1: GitHub Releases (Recommended)

```powershell
cd "f:\Data Mather Projects\Data project 2\excelmatcher-pro"

# Create git tag
git tag v1.0.1
git push origin v1.0.1

# Go to GitHub: https://github.com/sumitessgee01/excelmatcher-pro/releases
# - Click "Create a new release"
# - Select tag v1.0.1
# - Upload: release/FileMatcher-1.0.1-win-x64.exe
# - Add release notes
# - Publish
```

Users will now be notified automatically when they open FileMatcher!

### Option 2: Direct Download Link

```powershell
# Copy installer to web server or cloud storage
Copy-Item "release/FileMatcher-1.0.1-win-x64.exe" "D:\Uploads\"
```

Share the download link with users.

### Option 3: Create Setup Folder for Distribution

```powershell
# Create setup package
mkdir "FileMatcher-Setup-Package"
cd "FileMatcher-Setup-Package"

# Copy installer and readme
Copy-Item "..\release\FileMatcher-1.0.1-win-x64.exe" .
Copy-Item "..\README.md" .
Copy-Item "..\SETUP_AUTO_UPDATES.md" .

# Create ZIP for distribution
Compress-Archive -Path "." -DestinationPath "FileMatcher-1.0.1-Setup.zip"
```

---

## 🔄 Update Build Process (Next Version)

When you release version 1.0.2:

```powershell
# 1. Update version in package.json
notepad package.json
# Change "version": "1.0.1" → "1.0.2"

# 2. Commit version change
git add package.json
git commit -m "chore: bump version to 1.0.2"
git push

# 3. Build setup.exe
npm run build
npm run electron:build

# 4. Create release on GitHub with new installer
# Users get auto-update notification!
```

---

## 🐛 Troubleshooting

### Build Fails - "icon.ico not found"

```powershell
# Create basic icon from scratch or download one
# Ensure build/icon.ico exists
Test-Path "build/icon.ico"
```

### Build Fails - "Cannot find Python"

```powershell
# Ensure Python is in PATH
python --version

# Or specify Python path in environment
$env:PYTHON = "C:\Python312\python.exe"
npm run electron:build
```

### Build Fails - "Out of disk space"

```powershell
# Clean up old builds
Remove-Item "dist" -Recurse -Force
Remove-Item "node_modules" -Recurse -Force
npm cache clean --force

# Reinstall
npm install
npm run build
npm run electron:build
```

### Installer too large (>500MB)

```powershell
# Check what's being included
Get-ChildItem -Path "electron" -Recurse | Measure-Object -Property Length -Sum

# Remove unnecessary files from electron/ and backend/ folders
# Rebuild
```

### Auto-update not working after build

```powershell
# Verify GitHub token is set (if doing automated releases)
$env:GH_TOKEN = "your_github_token"

# Ensure version in package.json matches release tag
# Verify release is "published" not "draft" on GitHub
```

---

## 📊 Build Output Summary

When successful, you'll see:

```
✓ 50 files changed
✓ Frontend compiled: dist/
✓ Electron app packaged
✓ Python backend included
✓ NSIS installer created: release/FileMatcher-1.0.1-win-x64.exe
✓ Setup ready for distribution!
```

---

## 🎁 Final Installer Features

Your setup.exe includes:

✅ Professional Windows installer UI  
✅ Installation directory selection  
✅ Start Menu shortcuts  
✅ Desktop shortcut option  
✅ Uninstaller support  
✅ Auto-update capability  
✅ Python runtime included  
✅ All dependencies bundled  

---

## 📋 Quick Reference Card

```bash
# One-time setup
npm install

# Build release version
npm run build

# Create Windows installer
npm run electron:build

# Install locally for testing
.\release\FileMatcher-1.0.1-win-x64.exe

# Publish to GitHub
git tag v1.0.1
git push origin v1.0.1
# Then upload release on GitHub
```

---

## ✨ That's It!

You now have a professional Windows setup.exe installer that:
- Looks like other Windows software
- Installs like Windows software  
- Updates automatically via GitHub
- Works on all Windows 10+ systems

Happy building! 🚀
