$ErrorActionPreference = "Continue"

Write-Host "[Prereqs] Checking OBS..."
$obs = Get-Command obs64.exe -ErrorAction SilentlyContinue
if (-not $obs) {
  Write-Host "[Prereqs] OBS not found. TODO: Run OBS installer silently here."
  # Example:
  # Start-Process -FilePath "$PSScriptRoot\..\assets\OBS-Studio.exe" -ArgumentList "/S" -Wait
}

Write-Host "[Prereqs] Checking VB-CABLE..."
$vbPresent = Get-ChildItem "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall" -ErrorAction SilentlyContinue |
  ForEach-Object { Get-ItemProperty $_.PsPath -ErrorAction SilentlyContinue } |
  Where-Object { $_.DisplayName -like "*VB-Audio*" -or $_.DisplayName -like "*VB-CABLE*" }

if (-not $vbPresent) {
  Write-Host "[Prereqs] VB-CABLE not found. TODO: Run VB-CABLE installer silently here."
  # Example:
  # Start-Process -FilePath "$PSScriptRoot\..\assets\VBCABLE_Setup_x64.exe" -ArgumentList "/S" -Verb RunAs -Wait
}

Write-Host "[Prereqs] Done."
