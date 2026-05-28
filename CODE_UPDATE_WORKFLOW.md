# 📝 CODE UPDATE WORKFLOW - Step-by-Step Guide

When you update/modify any code, follow these steps to rebuild and distribute:

---

## 🔄 COMPLETE UPDATE WORKFLOW

### Step 1: Make Your Code Changes
```
Edit any file:
├─ src/*.jsx          (Frontend/React code)
├─ backend/*.py       (Backend/Python code)
├─ electron/*.js      (Electron code)
└─ Any other files
```

### Step 2: Test Locally (Before Building)
```powershell
# Start development environment
npm run electron:dev

# This runs:
# - Frontend dev server (hot reload)
# - Python backend
# - Electron app
# All with live updates as you make changes
```

### Step 3: Update Version Number
Edit `package.json`:

**Change this:**
```json
{
  "version": "1.0.0"
}
```

**To this:**
```json
{
  "version": "1.0.1"
}
```

**Version Rules:**
- `1.0.0` → `1.0.1` = Bug fix (patch)
- `1.0.0` → `1.1.0` = New feature (minor)
- `1.0.0` → `2.0.0` = Major changes (major)

### Step 4: Build New Installer
```powershell
# Option A - Easy way (recommended)
cd "f:\Data Mather Projects\Data project 2\excelmatcher-pro"
Double-click: BUILD.bat

# Option B - Manual commands
cd "f:\Data Mather Projects\Data project 2\excelmatcher-pro"
npm run build
npm run electron:build
```

**What this creates:**
```
release/FileMatcher-1.0.1-win-x64.exe  ← New installer!
```

### Step 5: Test New Build Locally
```powershell
# Double-click the new installer
.\release\FileMatcher-1.0.1-win-x64.exe

# Test that app works with your changes
```

### Step 6: Commit Code Changes to Git
```powershell
cd "f:\Data Mather Projects\Data project 2\excelmatcher-pro"

# Add all changes
git add .

# Commit with message
git commit -m "feat: Add new feature" 
# or
git commit -m "fix: Fix bug in backend"

# Push to GitHub
git push
```

**Commit Message Examples:**
```
git commit -m "feat: Add user authentication"
git commit -m "fix: Fix data matching algorithm"
git commit -m "docs: Update README"
git commit -m "perf: Optimize backend processing"
git commit -m "style: Update UI colors"
```

### Step 7: Create GitHub Release (For Users)
```
1. Go to: https://github.com/sumitessgee01/excelmatcher-pro/releases

2. Click: "Create a new release"

3. Fill in:
   Tag version: v1.0.1
   Release title: FileMatcher v1.0.1
   
   Description (examples):
   ✓ Bug fixes in data matching
   ✓ Improved performance
   ✓ New features added
   
4. Upload file:
   Attach: release/FileMatcher-1.0.1-win-x64.exe

5. Click: "Publish release"
```

### Step 8: ✨ Users Get Auto-Update Notification! ✨
```
When users open the app:
1. App checks for updates
2. Finds v1.0.1 available
3. Shows notification: "Update available"
4. User clicks "Restart Now"
5. App downloads and installs
6. App restarts with new version
```

---

## ⚡ QUICK REFERENCE - UPDATE CHECKLIST

```
☑ Make code changes (edit files)
☑ Test locally (npm run electron:dev)
☑ Update version in package.json
☑ Build new installer (BUILD.bat or npm commands)
☑ Test new build
☑ Commit to Git (git add . && git commit -m "message" && git push)
☑ Create GitHub Release
☑ Upload installer file
☑ Publish release
→ Users get auto-update! ✨
```

---

## 📊 DIFFERENT UPDATE SCENARIOS

### Scenario 1: Quick Bug Fix
```
1. Fix bug in code
2. Change version: 1.0.0 → 1.0.1
3. Build: npm run electron:build
4. git add . && git commit -m "fix: bug description"
5. git push
6. Create GitHub Release v1.0.1
7. Upload installer
8. Done! Users get notified automatically
```

### Scenario 2: New Feature
```
1. Add feature to code
2. Test thoroughly
3. Change version: 1.0.0 → 1.1.0
4. Build: npm run electron:build
5. git add . && git commit -m "feat: feature description"
6. git push
7. Create GitHub Release v1.1.0
8. Upload installer
9. Write release notes about feature
10. Done!
```

### Scenario 3: Major Update
```
1. Multiple changes/improvements
2. Change version: 1.0.0 → 2.0.0
3. Test extensively
4. Build: npm run electron:build
5. git add . && git commit -m "chore: major update"
6. git push
7. Create GitHub Release v2.0.0
8. Upload installer
9. Write detailed release notes
10. Users get major update notification
```

### Scenario 4: Urgent Hotfix
```
1. Critical bug found
2. Change version: 1.0.1 → 1.0.2
3. Apply quick fix
4. Build: npm run electron:build
5. git add . && git commit -m "hotfix: critical bug"
6. git push
7. Create GitHub Release v1.0.2 (mark as URGENT in notes)
8. Upload installer
9. Users get immediate update
```

---

## 🗂️ COMMON FILE LOCATIONS FOR EDITS

### Frontend Changes (React)
```
src/
├─ App.jsx                    Main app component
├─ components/               UI components
│  ├─ shared/              Shared components
│  └─ tabs/                Tab components
├─ store/appStore.js        App state
└─ utils/api.js             API calls
```

**After editing:** Rebuild and test with `npm run electron:dev`

### Backend Changes (Python)
```
backend/
├─ server.py                Main server
├─ core/
│  ├─ matcher.py           Matching logic
│  ├─ loader.py            File loading
│  └─ exporter.py          Export functionality
└─ requirements.txt         Dependencies
```

**After editing:** Rebuild with `npm run electron:build`

### Electron/Desktop Changes
```
electron/
├─ main.js                 Main process (auto-updater here)
├─ preload.js              Security context
└─ python-runner.js        Backend launcher
```

**After editing:** Rebuild with `npm run electron:build`

---

## ⚙️ COMPLETE COMMAND SEQUENCE (Copy & Paste)

### For Bug Fixes:
```powershell
# 1. Navigate
cd "f:\Data Mather Projects\Data project 2\excelmatcher-pro"

# 2. Update version in package.json
notepad package.json
# Change version: "1.0.0" → "1.0.1"

# 3. Build
npm run build
npm run electron:build

# 4. Commit
git add .
git commit -m "fix: description of fix"
git push

# 5. Create GitHub Release with new installer
# Go to: https://github.com/sumitessgee01/excelmatcher-pro/releases
# Upload: release/FileMatcher-1.0.1-win-x64.exe
```

### For New Features:
```powershell
cd "f:\Data Mather Projects\Data project 2\excelmatcher-pro"

# Update version
notepad package.json
# Change: "1.0.0" → "1.1.0"

# Build
npm run build
npm run electron:build

# Commit
git add .
git commit -m "feat: new feature description"
git push

# GitHub Release v1.1.0
```

---

## 🧪 TESTING BEFORE RELEASE

```powershell
# 1. Test in development mode
npm run electron:dev
# Test your changes here

# 2. Build production version
npm run build
npm run electron:build

# 3. Test the installer
.\release\FileMatcher-1.0.1-win-x64.exe
# Install and test thoroughly

# 4. Only after testing = publish release
```

---

## 📝 GIT COMMIT MESSAGE EXAMPLES

```
# Bug fix
git commit -m "fix: resolved data matching issue in backend"

# New feature
git commit -m "feat: add user authentication system"

# Documentation
git commit -m "docs: update README with setup instructions"

# Performance improvement
git commit -m "perf: optimize data processing speed"

# Style/UI change
git commit -m "style: update colors and layout"

# Configuration
git commit -m "config: update build settings"

# Dependency update
git commit -m "chore: update electron-updater package"
```

---

## 🚨 IMPORTANT NOTES

### ✅ DO:
- ✓ Always update version before building
- ✓ Test locally with npm run electron:dev
- ✓ Test new build before publishing
- ✓ Write clear commit messages
- ✓ Write release notes describing changes
- ✓ Publish GitHub release to enable auto-updates

### ❌ DON'T:
- ✗ Build without updating version
- ✗ Publish without testing
- ✗ Use vague commit messages
- ✗ Leave release as "draft"
- ✗ Skip git push (users won't see code)
- ✗ Forget to upload installer to release

---

## 🔄 AUTOMATED WORKFLOW SUMMARY

```
Code Change
    ↓
Update version in package.json
    ↓
Build: npm run build && npm run electron:build
    ↓
Test installer locally
    ↓
git add . && git commit && git push
    ↓
Create GitHub Release
    ↓
Upload installer file
    ↓
Publish release
    ↓
✨ Users get auto-update notification!
```

---

## 📞 QUICK HELP

**Q: What if build fails?**
A: Run `npm install` again, then rebuild

**Q: Do I need to push to GitHub?**
A: Yes! Git push updates your code, release upload gives users the installer

**Q: Can users update automatically?**
A: Yes! Only if you create a GitHub Release with version tag

**Q: What version should I use?**
A: Patch (1.0.1), Minor (1.1.0), or Major (2.0.0) depending on changes

**Q: How long does rebuild take?**
A: 3-6 minutes for updates (first time 5-10 min)

---

## 📚 FILES YOU NEED

```
To make updates:
├─ Any file in src/           (Frontend code)
├─ Any file in backend/       (Backend code)
├─ electron/main.js          (Desktop features)
└─ package.json              (Version number)

To rebuild:
├─ BUILD.bat                 (Just double-click!)
├─ npm commands              (npm run electron:build)

To publish:
└─ GitHub Releases           (Upload installer)
```

---

That's it! Follow these steps for ANY code update! 🚀
