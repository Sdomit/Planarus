# =============================================================================
# Planarus - system tray launcher
#
# Start, stop and open the local app from the notification area instead of
# keeping a console in the way. It drives the same run-planarus.bat and
# stop-planarus.bat as everything else, so there is one start path and one stop
# path, not three.
#
# WinForms NotifyIcon rather than a Python tray library: it ships with Windows,
# so the tray costs no dependency. pystray would have pulled Pillow into the
# API's virtual environment, which is a runtime tree, for a developer
# convenience that never runs in production.
# =============================================================================
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$Root = Split-Path -Parent $PSScriptRoot
$StartScript = Join-Path $PSScriptRoot 'run-planarus.bat'
$StopScript = Join-Path $PSScriptRoot 'stop-planarus.bat'

# --- state -------------------------------------------------------------------

# Where run-planarus.bat records the ports it settled on. It moves off 5173/8000
# when they are busy, so the tray cannot assume the defaults.
$PortsFile = Join-Path $env:LOCALAPPDATA 'Planarus\local.ports'

# Nothing in here starts a child process, and that is deliberate rather than
# tidiness. An earlier version read the ports out of the launcher's window titles
# via tasklist, which meant Get-Status shelled out on every call - including from
# the ContextMenuStrip Opening handler. A tray runs as a hidden, console-less
# PowerShell, spawning a console child from one is not dependable, and when it
# stalled it took the whole tray with it: the menu never opened and the icon
# never appeared, because the call that hung was the one before Visible = true.
# File read plus a socket connect, both in-process, cannot do that.
function Test-Port {
    param([int]$Port)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        # Short timeout: this runs while the user is waiting for a menu to open,
        # and both ports are probed, so the budget is half of what feels instant.
        # Loopback either answers immediately or is not there.
        return $client.ConnectAsync('127.0.0.1', $Port).Wait(250)
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Get-Status {
    $webPort = $null
    $apiPort = $null

    if (Test-Path $PortsFile) {
        foreach ($line in (Get-Content -Path $PortsFile -ErrorAction SilentlyContinue)) {
            if ($line -match '^\s*API\s*=\s*(\d+)') { $apiPort = [int]$Matches[1] }
            elseif ($line -match '^\s*WEB\s*=\s*(\d+)') { $webPort = [int]$Matches[1] }
        }
    }

    # The file says where it would be, not that it is there. A crash or a hard
    # window close leaves the file behind, and reporting "running" off a stale
    # file would offer an Open that goes nowhere.
    $webUp = ($null -ne $webPort) -and (Test-Port $webPort)
    $apiUp = ($null -ne $apiPort) -and (Test-Port $apiPort)

    [PSCustomObject]@{
        Running = $webUp -or $apiUp
        WebPort = if ($webUp) { $webPort } else { $null }
        ApiPort = if ($apiUp) { $apiPort } else { $null }
    }
}

# --- icon --------------------------------------------------------------------

function Get-TrayIcon {
    $png = Join-Path $Root 'apps\web\public\planarus-icon.png'
    if (Test-Path $png) {
        try {
            $bitmap = [System.Drawing.Bitmap]::new($png)
            try {
                # 16x16 is the notification area's own size; letting it downscale
                # a 256px bitmap itself produces a noticeably muddier result.
                $small = [System.Drawing.Bitmap]::new($bitmap, 16, 16)
                try {
                    return [System.Drawing.Icon]::FromHandle($small.GetHicon())
                } finally { $small.Dispose() }
            } finally { $bitmap.Dispose() }
        } catch {
            # Fall through to the stock icon rather than refuse to start.
        }
    }
    return [System.Drawing.SystemIcons]::Application
}

# --- actions -----------------------------------------------------------------

function Start-Planarus {
    if ((Get-Status).Running) { return }
    # The launcher opens its own API and Web windows and then exits, so this is
    # deliberately not hidden: its output is where a failed migration shows up.
    Start-Process -FilePath $StartScript -WorkingDirectory $Root
}

function Stop-Planarus {
    Start-Process -FilePath $StopScript -WorkingDirectory $Root `
        -WindowStyle Hidden -Wait
}

function Open-Planarus {
    $status = Get-Status
    if ($null -eq $status.WebPort) { return }
    Start-Process "http://localhost:$($status.WebPort)"
}

# --- tray --------------------------------------------------------------------

$menu = [System.Windows.Forms.ContextMenuStrip]::new()
$itemOpen = $menu.Items.Add('Open Planarus')
$itemStart = $menu.Items.Add('Start Planarus')
$itemStop = $menu.Items.Add('Stop Planarus')
$menu.Items.Add('-') | Out-Null
$itemExit = $menu.Items.Add('Exit tray')

$notify = [System.Windows.Forms.NotifyIcon]::new()
$notify.Icon = Get-TrayIcon
$notify.ContextMenuStrip = $menu
$notify.Text = 'Planarus'

function Update-Menu {
    $status = Get-Status
    $itemOpen.Enabled = $null -ne $status.WebPort
    $itemStart.Enabled = -not $status.Running
    $itemStop.Enabled = $status.Running

    # NotifyIcon.Text throws above 63 characters, so this stays short.
    $notify.Text = if ($status.Running) {
        if ($null -ne $status.WebPort) { "Planarus - running on :$($status.WebPort)" }
        else { 'Planarus - starting...' }
    } else { 'Planarus - stopped' }
}

$itemOpen.Add_Click({ Open-Planarus })
$itemStart.Add_Click({ Start-Planarus; Update-Menu })
$itemStop.Add_Click({ Stop-Planarus; Update-Menu })
$itemExit.Add_Click({
        # Hide before exiting: an unhidden NotifyIcon leaves a ghost in the
        # notification area until the user hovers over it.
        $notify.Visible = $false
        [System.Windows.Forms.Application]::Exit()
    })

# Double-click opens the UI, which is what a tray icon is expected to do.
$notify.Add_MouseDoubleClick({ Open-Planarus })

# The menu is only read when it opens, so refresh then rather than on a timer --
# no polling, and the state is never stale at the moment it is looked at.
$menu.Add_Opening({ Update-Menu })

# Set the tooltip BEFORE showing the icon. The shell caches the text it is given
# when the icon is registered, so doing this the other way round left the tray
# reading a bare "Planarus" for the whole session while the status text the code
# had carefully computed went nowhere.
Update-Menu
$notify.Visible = $true

[System.Windows.Forms.Application]::Run([System.Windows.Forms.ApplicationContext]::new())

$notify.Dispose()
