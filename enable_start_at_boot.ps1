<#
.SYNOPSIS
    Run the profile switcher automatically at login.

.DESCRIPTION
    Creates a shortcut in the current user's Startup folder that launches
    switcher.py with pythonw.exe (no console window). The Startup folder is used
    rather than Task Scheduler because it needs no administrator rights.

.PARAMETER PythonPath
    The interpreter to launch it with. Defaults to whatever `python` resolves to
    on PATH. install.ps1 passes the interpreter it just validated, which matters
    when Python was installed as part of that run and isn't on PATH yet.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File enable_start_at_boot.ps1
    powershell -ExecutionPolicy Bypass -File enable_start_at_boot.ps1 -Uninstall
#>

param(
    [switch]$Uninstall,
    [string]$PythonPath
)

$ErrorActionPreference = 'Stop'

$here = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$script = Join-Path $here 'switcher.py'
$startup = [Environment]::GetFolderPath('Startup')
$linkPath = Join-Path $startup 'Attack Shark Profile Switcher.lnk'

# Windows keeps a per-shortcut on/off switch here, written when a Startup item
# is toggled in Task Manager > Startup (or Settings > Startup Apps). It is keyed
# by file name and outlives the .lnk, so a shortcut switched off there stays
# suppressed even after being deleted and recreated - which means creating the
# shortcut is not on its own enough to make anything run at login.
$approvedKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder'
$linkName = Split-Path -Leaf $linkPath

function Test-StartupBlocked {
    <# Bit 0 of the first byte set means Windows has this item switched off. #>
    $entry = Get-ItemProperty -Path $approvedKey -Name $linkName -ErrorAction SilentlyContinue
    if (-not $entry) { return $false }
    $value = $entry.$linkName
    if ($null -eq $value -or $value.Count -lt 1) { return $false }
    return (($value[0] -band 1) -ne 0)
}

function Clear-StartupBlock {
    <# Delete the switch rather than set it to "on": no value at all is Windows'
       own never-toggled state, so this leaves nothing of ours in the registry.
       Returns whether there was actually something to clear. #>
    if (-not (Test-Path $approvedKey)) { return $false }
    $existing = Get-ItemProperty -Path $approvedKey -Name $linkName -ErrorAction SilentlyContinue
    if (-not $existing) { return $false }
    Remove-ItemProperty -Path $approvedKey -Name $linkName -Force
    return $true
}

if ($Uninstall) {
    $cleared = Clear-StartupBlock
    if (Test-Path $linkPath) {
        Remove-Item $linkPath -Force
        Write-Output "Removed $linkPath"
    } else {
        Write-Output 'Not installed - nothing to remove.'
    }
    if ($cleared) { Write-Output "Cleared Windows' startup-apps entry for it." }
    return
}

if (-not (Test-Path $script)) {
    throw "switcher.py not found next to this script ($script)"
}

$python = if ($PythonPath) { $PythonPath }
          else { (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $python -or -not (Test-Path $python)) {
    throw 'No Python found. Run install.bat first, or pass -PythonPath.'
}

# pythonw.exe runs without a console window; fall back to python.exe if absent.
$pythonw = Join-Path (Split-Path -Parent $python) 'pythonw.exe'
if (-not (Test-Path $pythonw)) {
    Write-Warning 'pythonw.exe not found; using python.exe (a console window will appear).'
    $pythonw = $python
}

$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($linkPath)
$link.TargetPath = $pythonw
$link.Arguments = '"{0}"' -f $script
$link.WorkingDirectory = $here
$link.WindowStyle = 7            # minimized
$link.Description = 'Switches the Attack Shark V8 mouse profile when a game runs'
$link.Save()

if (Clear-StartupBlock) {
    Write-Output 'Cleared the Windows startup-apps switch that was suppressing it.'
}

# Verify instead of assuming. switcher.py's tray checkbox reads a zero exit as
# "it will start at login", so anything short of that has to be an error here.
if (-not (Test-Path $linkPath)) {
    throw "The shortcut was not created at $linkPath"
}
if (Test-StartupBlocked) {
    throw "Windows still has this shortcut switched off in Task Manager > Startup."
}

Write-Output "Installed: $linkPath"
Write-Output "  target : $pythonw"
Write-Output "  script : $script"
Write-Output ''
Write-Output 'It will start at your next login. To start it now:'
Write-Output ('  Start-Process "{0}" -ArgumentList "{1}"' -f $pythonw, $script)
