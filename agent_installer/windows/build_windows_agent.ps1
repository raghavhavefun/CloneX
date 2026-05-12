Param(
  [string]$PythonExe = "python",
  [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path "$PSScriptRoot\..\.."
$WinRoot = Resolve-Path "$PSScriptRoot\.."

Write-Host "[Build] Root: $Root"

& $PythonExe -m pip install --upgrade pip
& $PythonExe -m pip install pyinstaller
& $PythonExe -m pip install -r "$Root\requirements.txt"

& $PythonExe -m PyInstaller --noconfirm --clean "$Root\agent_installer\pyinstaller\AriaAgent.spec"

$distSrc = "$Root\dist\AriaAgent"
$distDst = "$WinRoot\dist\AriaAgent"
New-Item -ItemType Directory -Force "$WinRoot\dist" | Out-Null
if (Test-Path $distDst) { Remove-Item $distDst -Recurse -Force }
Copy-Item $distSrc $distDst -Recurse -Force

Write-Host "[Build] Running prerequisite installer hook..."
& powershell -ExecutionPolicy Bypass -File "$PSScriptRoot\scripts\install_prereqs.ps1"

$inno = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (!(Test-Path $inno)) {
  throw "Inno Setup ISCC.exe not found. Install Inno Setup 6."
}

New-Item -ItemType Directory -Force "$WinRoot\output" | Out-Null
& $inno "$PSScriptRoot\inno\AriaAgentSetup.iss" /DAppVersion=$Version /DSourceRoot="$Root"

Write-Host "[Build] Done. Installer at $WinRoot\output\AriaAgentSetup.exe"
