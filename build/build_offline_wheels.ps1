# Prepare an offline installation bundle on a machine WITH internet.
# It downloads all wheels into vendor\wheels so that another machine can install
# without network access.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File build\build_offline_wheels.ps1
#   powershell -ExecutionPolicy Bypass -File build\build_offline_wheels.ps1 -DownloadPython -Zip
param(
    [string]$PythonVersion = "3.11",
    [string]$Abi = "cp311",
    [switch]$DownloadPython,
    [switch]$Zip
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Wheels = Join-Path $Root "vendor\wheels"
New-Item -ItemType Directory -Force -Path $Wheels | Out-Null

Write-Host "[1/3] Downloading wheels for Python $PythonVersion (win_amd64)..."
python -m pip download -r requirements.txt -d $Wheels `
    --only-binary=:all: `
    --platform win_amd64 `
    --python-version $PythonVersion `
    --implementation cp `
    --abi $Abi

if ($DownloadPython) {
    Write-Host "[2/3] Downloading Python installer..."
    $PyDir = Join-Path $Root "vendor\python"
    New-Item -ItemType Directory -Force -Path $PyDir | Out-Null
    $Name = "python-$PythonVersion.9-amd64.exe"
    $Url = "https://www.python.org/ftp/python/$PythonVersion.9/$Name"
    Invoke-WebRequest -Uri $Url -OutFile (Join-Path $PyDir $Name) -UseBasicParsing
    Write-Host "  Saved: vendor\python\$Name"
}

Write-Host "[3/3] Done."
Write-Host "Copy the whole project folder to the offline machine, then run install_offline.bat."

if ($Zip) {
    $ZipPath = Join-Path $Root "dist\MengXingCapture-offline-installer.zip"
    New-Item -ItemType Directory -Force -Path (Join-Path $Root "dist") | Out-Null
    if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
    $Items = @(
        "app", "main.py", "requirements.txt", "README.md", "vendor",
        "build\run_console.bat", "build\first_run_setup.bat", "build\install_offline.bat"
    )
    foreach ($i in $Items) {
        if (Test-Path (Join-Path $Root $i)) {
            Compress-Archive -Path (Join-Path $Root $i) -DestinationPath $ZipPath -Update -Force
        }
    }
    Write-Host "Zip created: $ZipPath"
}
