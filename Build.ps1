# FileMatcher - Build Windows Setup.exe (PowerShell Version)
# Run this script to build a professional Windows installer

param(
    [switch]$Clean = $false,
    [switch]$Test = $false
)

$ProjectPath = "f:\Data Mather Projects\Data project 2\excelmatcher-pro"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "     FileMatcher Setup.exe Builder" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Check Node.js
try {
    $nodeVersion = & node --version
    Write-Host "✓ Node.js found: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ ERROR: Node.js not found" -ForegroundColor Red
    Write-Host "Download from: https://nodejs.org/" -ForegroundColor Yellow
    exit 1
}

# Check npm
try {
    $npmVersion = & npm --version
    Write-Host "✓ npm found: version $npmVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ ERROR: npm not found" -ForegroundColor Red
    exit 1
}

# Change to project directory
Set-Location $ProjectPath
Write-Host "✓ Changed to project directory" -ForegroundColor Green
Write-Host ""

# Clean if requested
if ($Clean) {
    Write-Host "Cleaning previous builds..." -ForegroundColor Yellow
    Remove-Item -Path "dist" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -Path "release" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "✓ Clean complete" -ForegroundColor Green
    Write-Host ""
}

# Step 1: Install dependencies
Write-Host "Step 1/4: Installing dependencies..." -ForegroundColor Cyan
& npm install
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ npm install failed" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Dependencies installed" -ForegroundColor Green
Write-Host ""

# Step 2: Build frontend
Write-Host "Step 2/4: Building frontend assets..." -ForegroundColor Cyan
& npm run build
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Frontend build failed" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Frontend built successfully" -ForegroundColor Green
Write-Host ""

# Step 3: Build Windows installer
Write-Host "Step 3/4: Building Windows installer..." -ForegroundColor Cyan
Write-Host "This may take 2-5 minutes, please wait..." -ForegroundColor Yellow
& npm run electron:build
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Electron build failed" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Windows installer built" -ForegroundColor Green
Write-Host ""

# Step 4: Verify output
Write-Host "Step 4/4: Verifying installer..." -ForegroundColor Cyan
$InstallerPath = Get-Item -Path "release\FileMatcher-*-win-x64.exe" -ErrorAction SilentlyContinue | Select-Object -First 1

if ($InstallerPath) {
    $FileSizeMB = [math]::Round($InstallerPath.Length / 1MB, 2)
    Write-Host "✓ Installer found: $($InstallerPath.Name)" -ForegroundColor Green
    Write-Host "  File size: $FileSizeMB MB" -ForegroundColor Green
    Write-Host ""
    
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "     BUILD COMPLETED SUCCESSFULLY!" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host ""
    
    Write-Host "📁 Installer location:" -ForegroundColor Yellow
    Write-Host "   $($InstallerPath.FullName)" -ForegroundColor White
    Write-Host ""
    
    Write-Host "🔍 Next steps:" -ForegroundColor Yellow
    Write-Host "   1. Test the installer:" -ForegroundColor White
    Write-Host "      & '$($InstallerPath.FullName)'" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "   2. Or publish to GitHub:" -ForegroundColor White
    Write-Host "      https://github.com/sumitessgee01/excelmatcher-pro/releases" -ForegroundColor Cyan
    Write-Host ""
    
    # Optional: Test installer
    if ($Test) {
        Write-Host "🚀 Launching installer for testing..." -ForegroundColor Yellow
        & $InstallerPath.FullName
    }
} else {
    Write-Host "✗ ERROR: Installer file not found in release folder" -ForegroundColor Red
    Write-Host "Check release\ folder for troubleshooting" -ForegroundColor Yellow
    exit 1
}

Write-Host ""
