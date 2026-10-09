#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Creates a Hyper-V VM for TrueNAS SCALE / Community Edition (CloudHUB hybrid storage, Phase 0d).

.DESCRIPTION
    Pre-flight checks run before anything is created, and the script stops on the first failure:
      1. A TrueNAS*.iso exists in the ISO folder (newest one is used)
      2. No VM with the same name already exists (nothing is overwritten)
      3. The virtual switch exists (Hyper-V's built-in "Default Switch" by default)
      4. The drive holding the VM folder has room for both disks plus a 20 GB margin

    Then it creates a Generation 2 VM with:
      - fixed memory (TrueNAS does not support dynamic memory; ZFS uses RAM for caching)
      - a boot disk for the TrueNAS OS and a separate dynamic data disk for the ZFS pool
      - Hyper-V checkpoints disabled (use ZFS snapshots instead)
      - Secure Boot off and the ISO as the first boot device

    After it finishes: start the VM in Hyper-V Manager, press a key at
    "Press any key to boot from CD or DVD", and install TrueNAS to the BOOT disk.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\New-TrueNASVM.ps1

.EXAMPLE
    # Smaller data disk if the host is short on space
    powershell -ExecutionPolicy Bypass -File .\New-TrueNASVM.ps1 -DataGB 32
#>

[CmdletBinding()]
param(
    [string]$VMName     = "TrueNAS",
    [string]$VMRoot     = "C:\HyperV",
    [ValidateRange(8, 1024)][int]$MemGB  = 16,   # 8 GB is the practical minimum for TrueNAS
    [ValidateRange(2, 64)]  [int]$CPUs   = 4,
    [ValidateRange(16, 512)][int]$BootGB = 32,   # TrueNAS OS disk
    [ValidateRange(8, 8192)][int]$DataGB = 64,   # ZFS pool disk (dynamic: only grows as it fills)
    [string]$IsoDir     = (Join-Path $env:USERPROFILE "Downloads"),
    [string]$SwitchName = "Default Switch"
)

$VMPath = Join-Path $VMRoot $VMName

# --- 1. ISO -----------------------------------------------------------------
$iso = Get-ChildItem -Path $IsoDir -Filter "TrueNAS*.iso" -ErrorAction SilentlyContinue |
       Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $iso) {
    Write-Host "No TrueNAS*.iso found in '$IsoDir'. Download it from truenas.com, then rerun." -ForegroundColor Red
    exit 1
}
Write-Host "Using ISO: $($iso.Name)"

# --- 2. Name clash ------------------------------------------------------------
if (Get-VM -Name $VMName -ErrorAction SilentlyContinue) {
    Write-Host "A VM named '$VMName' already exists. Stopping so nothing gets overwritten." -ForegroundColor Yellow
    exit 1
}

# --- 3. Virtual switch ---------------------------------------------------------
if (-not (Get-VMSwitch -Name $SwitchName -ErrorAction SilentlyContinue)) {
    Write-Host "Virtual switch '$SwitchName' not found. Did you restart after enabling Hyper-V?" -ForegroundColor Red
    exit 1
}

# --- 4. Free space ---------------------------------------------------------------
$driveLetter = (Split-Path -Qualifier $VMRoot).TrimEnd(':')
$drive = Get-PSDrive -Name $driveLetter -ErrorAction SilentlyContinue
if (-not $drive) {
    Write-Host "Could not read free space for drive '$driveLetter'. Check -VMRoot." -ForegroundColor Red
    exit 1
}
$freeGB   = [math]::Round($drive.Free / 1GB)
$neededGB = $BootGB + $DataGB + 20
if ($freeGB -lt $neededGB) {
    Write-Host "Only $freeGB GB free on ${driveLetter}: but $neededGB GB is needed. Rerun with a smaller -DataGB." -ForegroundColor Red
    exit 1
}

# --- Create ----------------------------------------------------------------
New-Item -ItemType Directory -Path $VMPath -Force | Out-Null

New-VM -Name $VMName -Generation 2 -MemoryStartupBytes ($MemGB * 1GB) -Path $VMRoot `
       -NewVHDPath (Join-Path $VMPath "boot.vhdx") -NewVHDSizeBytes ($BootGB * 1GB) `
       -SwitchName $SwitchName | Out-Null

Set-VMMemory    -VMName $VMName -DynamicMemoryEnabled $false
Set-VMProcessor -VMName $VMName -Count $CPUs
Set-VM          -Name   $VMName -CheckpointType Disabled

$dataPath = Join-Path $VMPath "data.vhdx"
New-VHD -Path $dataPath -SizeBytes ($DataGB * 1GB) -Dynamic | Out-Null
Add-VMHardDiskDrive -VMName $VMName -Path $dataPath

$dvd = Add-VMDvdDrive -VMName $VMName -Path $iso.FullName -Passthru
Set-VMFirmware -VMName $VMName -EnableSecureBoot Off -FirstBootDevice $dvd

Write-Host "VM '$VMName' created: $MemGB GB RAM, $CPUs CPUs, $BootGB GB boot disk, $DataGB GB data disk." -ForegroundColor Green
Write-Host "Next: start it in Hyper-V Manager and press a key at 'Press any key to boot from CD or DVD'."
exit 0
