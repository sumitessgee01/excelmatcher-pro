# FileMatcher Auto-Update Setup Guide

This guide explains how the auto-update feature works and how to publish updates.

## How Auto-Updates Work

FileMatcher uses `electron-updater` to check for and install updates automatically:

1. **Startup Check**: When the app starts, it checks GitHub releases for a newer version
2. **Background Download**: If a new version is found, it downloads in the background
3. **User Notification**: Users are notified when an update is ready
4. **One-Click Install**: Users can click to install the update and restart the app

## Publishing Updates to GitHub

### Step 1: Update Version

Edit `package.json` and increment the version:

```json
{
  "version": "1.0.1"
}
```

### Step 2: Build the Application

Build the application with the updated version:

```bash
set GITHUB_OWNER=sumitessgee01
set GITHUB_REPO=excelmatcher-pro
npm run electron:build
```

This will create an installer in the `release/` directory with the new version.

### Step 3: Create a GitHub Release

On GitHub, create a new release:

1. Go to https://github.com/sumitessgee01/excelmatcher-pro/releases
2. Click "Create a new release"
3. Set the tag version to match `package.json` (e.g., `1.0.1`)
4. Upload the installer from `release/FileMatcher-1.0.1-win-x64.exe`
5. Add release notes describing the changes
6. Publish the release

### Step 4: Users Get Notified

When users run FileMatcher:
- If a new version is available, they'll see a notification
- They can click "Restart Now" to install the update immediately
- The app will download and install the update, then restart

## Auto-Updater Configuration

The auto-updater is configured in `electron-builder.yml`:

```yaml
publish:
  provider: github
  owner: "sumitessgee01"
  repo: "excelmatcher-pro"
  releaseType: release
```

### GitHub Authentication

For automated publishing (optional), set GitHub token:

```bash
set GH_TOKEN=your_github_token
npm run electron:build
```

## Troubleshooting

### Update not detected

1. Check that the version in `package.json` is higher than the installed version
2. Ensure the GitHub release is published (not in draft)
3. Verify the installer file is uploaded to the release
4. Restart the app to trigger a new update check

### Update download failed

1. Check internet connection
2. Verify the release is public
3. Check that the installer filename matches the expected pattern
4. See `Preferences/Logs` in the app for error details

### Manual Update Check

Add this code to trigger a manual update check:

```javascript
const { autoUpdater } = require("electron-updater");
autoUpdater.checkForUpdatesAndNotify();
```

## Architecture

The auto-update system consists of:

- **`electron-updater`**: Core library handling update logic
- **`electron/main.js`**: Setup and event handlers
- **`electron-builder.yml`**: Publishing configuration
- **GitHub Releases**: Release storage and delivery

## Best Practices

1. **Semantic Versioning**: Use semver (1.0.0, 1.0.1, 1.1.0, 2.0.0)
2. **Release Notes**: Always document changes in release notes
3. **Testing**: Test locally before publishing
4. **Gradual Rollout**: Consider publishing to a subset of users first
5. **Monitoring**: Track update adoption through app usage analytics

## Additional Resources

- [electron-updater Documentation](https://www.electron.build/auto-update)
- [GitHub Releases API](https://docs.github.com/en/rest/reference/releases)
- [Semantic Versioning](https://semver.org/)
