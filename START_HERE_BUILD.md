# 🚀 COPY-PASTE COMMANDS TO BUILD setup.exe

## FASTEST WAY (5 Seconds to Build!)

### Just Double-Click This File:
```
BUILD.bat
```

That's it! The script handles everything.

---

## OR USE THESE EXACT COMMANDS

### In PowerShell - Copy & Paste This:

```powershell
cd "f:\Data Mather Projects\Data project 2\excelmatcher-pro"
npm install
npm run build
npm run electron:build
start release
```

### Or All in One Line:
```powershell
cd "f:\Data Mather Projects\Data project 2\excelmatcher-pro"; npm install; npm run build; npm run electron:build; start release
```

---

## WHAT HAPPENS AFTER RUNNING COMMANDS

✅ **npm install** - Installs all packages  
✅ **npm run build** - Compiles your React app  
✅ **npm run electron:build** - Creates setup.exe  
✅ **start release** - Opens folder with your installer

---

## YOUR INSTALLER LOCATION

After running commands, your installer is here:

```
f:\Data Mather Projects\Data project 2\excelmatcher-pro\release\

FileMatcher-1.0.0-win-x64.exe  ← YOUR SETUP.EXE!
```

Size: ~200-300 MB (Normal for Electron apps)

---

## NEXT STEPS AFTER BUILDING

### 1️⃣ Test Locally
Double-click installer and follow installation steps.

### 2️⃣ Publish to GitHub (Enables Auto-Updates!)

```powershell
cd "f:\Data Mather Projects\Data project 2\excelmatcher-pro"
git tag v1.0.0
git push origin v1.0.0
```

Then go to: **https://github.com/sumitessgee01/excelmatcher-pro/releases**
- Click "Create a new release"
- Select tag v1.0.0
- Upload: `release/FileMatcher-1.0.0-win-x64.exe`
- Add release notes
- Click "Publish"

### 3️⃣ Share with Users
Users download and install. They automatically get update notifications!

---

## UPDATE FOR NEXT VERSION

For version 1.0.1:

```powershell
# 1. Edit package.json - change version to 1.0.1
notepad package.json

# 2. Rebuild
npm run build
npm run electron:build

# 3. Your new installer is ready in release/ folder!

# 4. Publish to GitHub
git tag v1.0.1
git push origin v1.0.1
# Then create release on GitHub
```

---

## TROUBLESHOOTING

### Error: "npm: command not found"
→ Download Node.js from https://nodejs.org/

### Error: "icon.ico not found"
→ Icon already exists in `build/` folder, should be fine

### Build takes forever
→ Normal! First build is slower. Wait 5-10 minutes.

### Installer size is 300 MB
→ Normal for Electron apps with Python backend included

### Auto-update not working
→ Make sure GitHub release is published (not draft)

---

## WANT TO CHANGE INSTALLER APPEARANCE?

### Edit `electron-builder.yml`:

```yaml
appId: com.essgee.filematcher           # Change to your company
productName: FileMatcher                 # App name
artifactName: FileMatcher-${version}.${ext}  # Installer name

win:
  icon: build/icon.ico                  # Icon file

nsis:
  oneClick: false                        # Professional installer
  allowToChangeInstallationDirectory: true
  createDesktopShortcut: true
  createStartMenuShortcut: true
```

Then rebuild to see changes.

---

## ALL YOUR BUILD RESOURCES

In your project folder:

```
📄 BUILD.bat                    ← Double-click to build
📄 Build.ps1                    ← PowerShell version
📄 QUICK_BUILD_COMMANDS.md      ← Copy-paste commands
📄 BUILD_WINDOWS_SETUP.md       ← Detailed guide
📄 SETUP_AUTO_UPDATES.md        ← How to publish updates
📄 README.md                    ← General info
📄 PROJECT_SETUP_COMPLETE.md    ← Setup summary

build/
└── icon.ico                    ← Installer icon

electron-builder.yml            ← Build configuration

release/
└── FileMatcher-1.0.0-win-x64.exe  ← YOUR INSTALLER!
```

---

## ⚡ SUPER QUICK REFERENCE

| Action | Command |
|--------|---------|
| Build everything | `npm run build; npm run electron:build` |
| Find installer | `start release` |
| Test installer | Double-click in release folder |
| Update version | Edit `package.json` version field |
| Publish to GitHub | `git tag v1.0.0; git push origin v1.0.0` |
| Change icon | Replace `build/icon.ico` |
| Clean and rebuild | `rm -r release; npm run build; npm run electron:build` |

---

## 🎯 FINAL CHECKLIST

Before building:
- ✅ Node.js installed (check: `node --version`)
- ✅ Project folder: `f:\Data Mather Projects\Data project 2\excelmatcher-pro`
- ✅ In PowerShell or Command Prompt
- ✅ At least 5GB free disk space

Build:
- ✅ Run `npm install`
- ✅ Run `npm run build`
- ✅ Run `npm run electron:build`
- ✅ Wait 5-10 minutes

Result:
- ✅ Check `release/` folder
- ✅ See `FileMatcher-1.0.0-win-x64.exe`
- ✅ File size: 150-400 MB
- ✅ Ready to share!

---

## 🎉 THAT'S ALL!

Your professional Windows setup.exe is ready to be shared and distributed!

**It will:**
- ✨ Install like any Windows software
- ✨ Create Start Menu shortcuts
- ✨ Create Desktop shortcut
- ✨ Have uninstaller
- ✨ Support auto-updates via GitHub

**Next: Publish to GitHub for auto-updates!** 🚀
