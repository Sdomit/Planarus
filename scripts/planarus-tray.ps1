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

# The launcher moves off 5173/8000 when they are busy and records whichever port
# it settled on in the window title ("Planarus Web (:5174)"). Reading it back
# from there keeps the tray correct without a state file to write, and without
# the launcher having to know the tray exists.
function Get-PlanarusPort {
    param([string]$TitlePrefix)

    # tasklist rather than Get-Process: MainWindowTitle comes back empty for
    # these console windows in some sessions, and the /V column does not.
    $rows = & tasklist /FI "WINDOWTITLE eq $TitlePrefix*" /FO CSV /V 2>$null
    if (-not $rows -or $rows.Count -lt 2) { return $null }

    foreach ($row in $rows | Select-Object -Skip 1) {
        if ($row -match '\(:(\d+)\)') { return [int]$Matches[1] }
    }
    return $null
}

function Get-Status {
    $webPort = Get-PlanarusPort -TitlePrefix 'Planarus Web'
    $apiPort = Get-PlanarusPort -TitlePrefix 'Planarus API'
    [PSCustomObject]@{
        Running = ($null -ne $webPort) -or ($null -ne $apiPort)
        WebPort = $webPort
        ApiPort = $apiPort
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
$notify.Visible = $true

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

Update-Menu
[System.Windows.Forms.Application]::Run([System.Windows.Forms.ApplicationContext]::new())

$notify.Dispose()
