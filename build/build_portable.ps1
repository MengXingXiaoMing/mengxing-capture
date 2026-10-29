# Build a fully self-contained portable folder (no installation, no registry writes).
# Usage:
#   powershell -ExecutionPolicy Bypass -File build\build_portable.ps1
#   powershell -ExecutionPolicy Bypass -File build\build_portable.ps1 -WithModels -Zip
param(
    [switch]$Clean,
    [switch]$WithModels,
    [switch]$WithOllama,
    [switch]$Zip,
    [switch]$SkipDeps
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Venv = Join-Path $Root ".venv"
$Py = Join-Path $Venv "Scripts\python.exe"

if (-not (Test-Path $Py)) {
    Write-Host "[1/5] Creating isolated virtual environment..."
    python -m venv $Venv
    & $Py -m pip install --upgrade pip
    & $Py -m pip install -r requirements.txt
} elseif (-not $SkipDeps) {
    Write-Host "[1/5] Ensuring dependencies..."
    & $Py -m pip install -r requirements.txt -q
}

Write-Host "[2/5] Installing PyInstaller..."
& $Py -m pip install pyinstaller -q

Write-Host "[3/5] Rendering application icon..."
& $Py (Join-Path $Root "build\make_icon.py")

if ($Clean) {
    Remove-Item -Recurse -Force (Join-Path $Root "dist") -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force (Join-Path $Root "build\MengXingCapture") -ErrorAction SilentlyContinue
}

Write-Host "[4/5] Packaging with PyInstaller (onedir)..."
& $Py -m PyInstaller main.py `
    --noconfirm --clean --onedir --windowed `
    --name MengXingCapture `
    --icon "build\app.ico" `
    --collect-all rapidocr `
    --collect-all ctranslate2 `
    --collect-all onnxruntime `
    --collect-all imageio_ffmpeg `
    --collect-all pyaudiowpatch `
    --collect-data sentencepiece `
    --exclude-module tkinter `
    --exclude-module matplotlib `
    --exclude-module torch `
    --exclude-module pandas

$Out = Join-Path $Root "dist\MengXingCapture"
if (-not (Test-Path $Out)) {
    throw "PyInstaller output not found: $Out"
}

Write-Host "[5/5] Post-processing portable folder..."

$Ffmpeg = (& $Py -c "import imageio_ffmpeg,sys; sys.stdout.write(imageio_ffmpeg.get_ffmpeg_exe())")
if ($Ffmpeg -and (Test-Path $Ffmpeg)) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Out "tools\ffmpeg") | Out-Null
    Copy-Item $Ffmpeg (Join-Path $Out "tools\ffmpeg\ffmpeg.exe") -Force
    Write-Host "  ffmpeg bundled."
}

if ($WithModels) {
    $Pkg = Join-Path $Root "userdata\models\argos\packages"
    if (Test-Path $Pkg) {
        $Dest = Join-Path $Out "userdata\models\argos"
        New-Item -ItemType Directory -Force -Path $Dest | Out-Null
        Copy-Item $Pkg $Dest -Recurse -Force
        Write-Host "  Argos language packs bundled."
    } else {
        Write-Host "  No Argos language packs found, skipped."
    }
}

if ($WithOllama) {
    $VendorOllama = Join-Path $Root "vendor\ollama"
    if (Test-Path $VendorOllama) {
        $VendorDest = Join-Path $Out "vendor"
        New-Item -ItemType Directory -Force -Path $VendorDest | Out-Null
        Copy-Item $VendorOllama $VendorDest -Recurse -Force
        Write-Host "  Ollama offline bundle copied."
    } else {
        Write-Host "  vendor\ollama not found. Run build\make_ollama_bundle.py first."
    }
}

$Launcher = @"
@echo off
cd /d "%~dp0"
start "" "MengXingCapture.exe"
"@
Set-Content -Path (Join-Path $Out "Start.bat") -Value $Launcher -Encoding ASCII

$Readme = @"
MengXing Capture - Portable

1. Double-click MengXingCapture.exe (or Start.bat).
2. All data (config, captures, recordings, models) is stored in the userdata folder
   next to the exe. Nothing is written to the system.
3. To use offline translation, put .argosmodel packs into
   userdata\models\argos\packages\<from>_<to>\ or install them from the Translation page.
"@
Set-Content -Path (Join-Path $Out "README.txt") -Value $Readme -Encoding UTF8

if ($Zip) {
    $ZipPath = Join-Path $Root "dist\MengXingCapture-portable.zip"
    if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
    Compress-Archive -Path (Join-Path $Out "*") -DestinationPath $ZipPath -Force
    Write-Host "  Zip created: $ZipPath"
}

Write-Host ""
Write-Host "Done. Portable folder: $Out"
Write-Host "Size: " ([math]::Round((Get-ChildItem $Out -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB, 1)) "MB"
