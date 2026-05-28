# FileMatcher

A powerful desktop application for matching and comparing Excel spreadsheets with an integrated Python backend and automatic updates.

## Features

- **File Matching**: Compare and match data across multiple spreadsheet files
- **Auto-Update**: Automatic updates delivered directly from GitHub releases
- **Desktop App**: Built with Electron for Windows
- **Python Backend**: Powerful data processing engine
- **Modern UI**: Built with React and Tailwind CSS

## Installation

### Prerequisites

- Node.js 18+ and npm
- Python 3.8+ (included in the packaged application)
- Windows 10 or later

### Development Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/excelmatcher-pro.git
cd excelmatcher-pro
```

2. Install dependencies:
```bash
npm install
```

3. Start development environment:
```bash
npm run electron:dev
```

This will start both the Vite dev server and the Electron app.

## Building

### Build for Production

```bash
npm run electron:build
```

The installer will be created in the `release/` directory.

### Building Without Publishing

```bash
npm run electron:pack
```

## Auto-Update Feature

FileMatcher includes automatic update functionality powered by `electron-updater`:

- **Automatic Checks**: The app checks for updates on startup
- **GitHub Releases**: Updates are published via GitHub releases
- **Background Updates**: Updates download in the background
- **User Notifications**: Users are prompted when updates are available
- **One-Click Installation**: Users can install updates with a single click

### Publishing Updates

Updates are automatically published to GitHub releases when you:

1. Increment the version in `package.json`
2. Build the app with `npm run electron:build`
3. Create a GitHub release with the same version tag

The auto-updater will detect the new release and notify users.

## Project Structure

```
excelmatcher-pro/
├── electron/           # Electron main process
│   ├── main.js        # App entry point with auto-updater
│   ├── preload.js     # Preload script for security
│   └── python-runner.js # Python backend launcher
├── src/               # React frontend source
├── public/            # Static assets
├── backend/           # Python backend
├── build/             # Build resources (icons, etc.)
└── dist/              # Built frontend (generated)
```

## Scripts

- `npm run dev` - Start Vite dev server
- `npm run build` - Build frontend
- `npm run preview` - Preview production build
- `npm run backend:dev` - Start Python backend
- `npm run electron:dev` - Start dev environment (frontend + backend + Electron)
- `npm run electron:build` - Build and create installer
- `npm run electron:pack` - Build without publishing

## Configuration

### Update Configuration

Edit `electron-builder.yml` to configure GitHub release publishing:

```yaml
publish:
  provider: github
  owner: "your-github-username"
  repo: "excelmatcher-pro"
  releaseType: release
```

Set environment variables before building:

```bash
set GITHUB_OWNER=your-username
set GITHUB_REPO=excelmatcher-pro
npm run electron:build
```

## License

[Your License]

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Support

For issues, questions, or suggestions, please open an issue on GitHub.
