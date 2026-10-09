<#
.SYNOPSIS
  Surface Book 3 health check for CloudHUB. Posts to a Discord webhook only
  when something changes: a drive gets low on space, or the TrueNAS VM stops.

.DESCRIPTION
  Run it from a scheduled task every 30 minutes (see README). It keeps the
  last state in C:\ProgramData\CloudHUB\surface-health.json so it doesn't
  repeat the same alert every run, and posts a "recovered" message when a
  problem clears.

  The webhook URL is read from C:\ProgramData\CloudHUB\webhook.txt so it
  never lives in this script. Anyone with that URL can post to the channel,
  so keep the file private.

.PARAMETER Test
  Post a one-off test message and exit.
#>
[CmdletBinding()]
param(
    [int]$DiskWarnPct = 85,
    [string]$VmName = 'TrueNAS',
    [switch]$Test
)

$ErrorActionPreference = 'Stop'
$dir      = Join-Path $env:ProgramData 'CloudHUB'
$hookFile = Join-Path $dir 'webhook.txt'
$stateFile = Join-Path $dir 'surface-health.json'

if (-not (Test-Path $hookFile)) {
    Write-Error "Webhook file not found: $hookFile. Create it first (see README)."
}
$webhook = (Get-Content $hookFile -Raw).Trim()
if ($webhook -notmatch '^https://(discord|discordapp)\.com/api/webhooks/') {
    Write-Error "webhook.txt doesn't look like a Discord webhook URL."
}

# Emoji are built from code points so this file stays plain ASCII
# (Windows PowerShell 5.1 misreads non-ASCII characters in .ps1 files without a BOM).
$EmojiTest = [char]::ConvertFromUtf32(0x1F9EA)
$EmojiWarn = [char]::ConvertFromUtf32(0x26A0) + [char]0xFE0F
$EmojiOk   = [char]::ConvertFromUtf32(0x2705)

function Send-Discord([string]$Text) {
    $json  = @{ content = $Text.Substring(0, [Math]::Min($Text.Length, 1900)) } | ConvertTo-Json
    # Send the JSON as UTF-8 bytes; a plain string body is not sent as UTF-8 by PowerShell 5.1.
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    Invoke-RestMethod -Uri $webhook -Method Post -ContentType 'application/json; charset=utf-8' -Body $bytes | Out-Null
}

if ($Test) {
    Send-Discord "$EmojiTest Surface health check is connected ($env:COMPUTERNAME)."
    Write-Host "Test message sent."
    return
}

# ---- Run the checks: key -> @{ ok = bool; detail = string } ----
$checks = [ordered]@{}

Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object {
    if ($_.Size -gt 0) {
        $usedPct = [Math]::Round(100 * ($_.Size - $_.FreeSpace) / $_.Size)
        $freeGB  = [Math]::Round($_.FreeSpace / 1GB, 1)
        $checks["disk-$($_.DeviceID)"] = @{
            ok     = ($usedPct -lt $DiskWarnPct)
            detail = "Surface drive $($_.DeviceID) $usedPct% used ($freeGB GB free)"
        }
    }
}

$vm = Get-VM -Name $VmName -ErrorAction SilentlyContinue
if ($vm) {
    $checks['vm-truenas'] = @{
        ok     = ($vm.State -eq 'Running')
        detail = "TrueNAS VM is $($vm.State)"
    }
}

# ---- Compare with the last run and post only the changes ----
$previous = @{}
if (Test-Path $stateFile) {
    (Get-Content $stateFile -Raw | ConvertFrom-Json).PSObject.Properties |
        ForEach-Object { $previous[$_.Name] = [bool]$_.Value }
}

$messages = @()
foreach ($key in $checks.Keys) {
    $now = $checks[$key]
    $was = if ($previous.ContainsKey($key)) { $previous[$key] } else { $null }
    if (-not $now.ok -and $was -ne $false) { $messages += "$EmojiWarn $($now.detail)" }
    elseif ($now.ok -and $was -eq $false)  { $messages += "$EmojiOk Recovered: $($now.detail)" }
    $previous[$key] = $now.ok
}

if ($messages.Count -gt 0) { Send-Discord ($messages -join "`n") }

New-Item -ItemType Directory -Path $dir -Force | Out-Null
$previous | ConvertTo-Json | Set-Content -Path $stateFile -Encoding UTF8
Write-Host ("Checked {0} items, posted {1} change(s)." -f $checks.Count, $messages.Count)
