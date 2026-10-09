#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Checks that this Windows host can run the TrueNAS VM (CloudHUB hybrid storage, Phase 0b).

.DESCRIPTION
    - Stops if the Windows edition is Home (Hyper-V is not available there).
    - Reports whether Hyper-V is already enabled.
    - If it is not, enables it and tells you to restart. Nothing else is changed.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\Test-HyperVReady.ps1
#>

[CmdletBinding()]
param()

$os = (Get-CimInstance Win32_OperatingSystem).Caption
Write-Host "Windows edition: $os"

if ($os -match "Home") {
    Write-Host "Home edition: Hyper-V is not available. Upgrade to Pro/Enterprise/Education or install TrueNAS on bare metal." -ForegroundColor Red
    exit 1
}

$hv = Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All
if ($hv.State -eq "Enabled") {
    Write-Host "Hyper-V is already enabled. No restart needed - run New-TrueNASVM.ps1 next." -ForegroundColor Green
    exit 0
}

Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All -All -NoRestart | Out-Null
Write-Host "Hyper-V enabled. Restart Windows, then run New-TrueNASVM.ps1." -ForegroundColor Yellow
exit 0
