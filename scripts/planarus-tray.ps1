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

# A tray has nowhere to print. WinForms also swallows exceptions thrown inside a
# click handler, so without this a failed menu item is indistinguishable from a
# menu item that did nothing - which is exactly how the first version shipped
# broken. Every action is logged and every failure is also shown as a balloon,
# so a user sees something went wrong and a maintainer can read why.
$LogFile = Join-Path $env:LOCALAPPDATA 'Planarus\tray.log'

function Write-TrayLog {
    param([string]$Message)
    try {
        $dir = Split-Path -Parent $LogFile
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        "{0:yyyy-MM-dd HH:mm:ss}  {1}" -f (Get-Date), $Message | Add-Content -Path $LogFile
    } catch {
        # Logging must never be the thing that breaks the tray.
    }
}

# Wraps a menu action so a failure is reported rather than silently discarded.
function Invoke-Action {
    param([string]$Name, [scriptblock]$Body)
    Write-TrayLog "$Name : start"
    try {
        & $Body
        Write-TrayLog "$Name : ok"
    } catch {
        Write-TrayLog "$Name : FAILED - $($_.Exception.Message)"
        try {
            $notify.BalloonTipTitle = "Planarus - $Name failed"
            $notify.BalloonTipText = "$($_.Exception.Message)`nSee $LogFile"
            $notify.ShowBalloonTip(8000)
        } catch { }
    }
}

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
    # Both families, because the two services disagree about which one to use:
    #
    #   TCP    127.0.0.1:8000    LISTENING    <- uvicorn, IPv4 only
    #   TCP    [::1]:5173        LISTENING    <- vite, IPv6 only
    #
    # and TcpClient's parameterless constructor makes an IPv4 socket, so it
    # resolves "localhost" and then only ever tries 127.0.0.1. That probe cannot
    # see vite at all: it returned false while the page was serving 200, which
    # left the tray showing "stopped" with Open greyed out on a running app.
    foreach ($family in [System.Net.Sockets.AddressFamily]::InterNetwork,
                        [System.Net.Sockets.AddressFamily]::InterNetworkV6) {
        if ($family -eq [System.Net.Sockets.AddressFamily]::InterNetwork) {
            $address = '127.0.0.1'
        } else {
            $address = '::1'
        }
        $client = [System.Net.Sockets.TcpClient]::new($family)
        try {
            # 150ms per family, because this now runs up to four times while the
            # user waits for the menu to open (two ports, two families). A live
            # loopback answers in single-digit milliseconds; a closed one on ::1
            # does not always refuse promptly, so this is a timeout in practice
            # and the budget is what bounds the wait.
            if ($client.ConnectAsync($address, $Port).Wait(150)) { return $true }
        } catch {
            # Wrong family or nothing listening; try the other one.
        } finally {
            $client.Dispose()
        }
    }
    return $false
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
    if ((Get-Status).Running) {
        Write-TrayLog 'start : already running, nothing to do'
        return
    }
    if (-not (Test-Path $StartScript)) {
        throw "run-planarus.bat not found at $StartScript"
    }
    # Handed to cmd.exe explicitly rather than given to Start-Process as a .bat.
    # This host is a hidden PowerShell with no console of its own, and asking it
    # to launch a console application is the same arrangement that already broke
    # Get-Status. Naming cmd.exe puts the console creation somewhere that
    # definitely has one.
    #
    # Deliberately not hidden and not -Wait: the launcher can spend minutes
    # creating a virtual environment or prompting to install Node, and its window
    # is where a failed migration is visible. Hiding it would turn a first run
    # into a tray that appears to do nothing for several minutes.
    # No arguments: silent is the launcher's default now, and it also declines to
    # start a second copy if one is already up. Passing "silent" explicitly would
    # only suggest the flag still does something.
    Write-TrayLog "start : launching $StartScript"
    Start-Process -FilePath $env:ComSpec -ArgumentList '/c', "`"$StartScript`"" -WorkingDirectory $Root
}

function Stop-Planarus {
    if (-not (Test-Path $StopScript)) {
        throw "stop-planarus.bat not found at $StopScript"
    }
    Write-TrayLog "stop : launching $StopScript"
    Start-Process -FilePath $env:ComSpec -ArgumentList '/c', "`"$StopScript`"" `
        -WorkingDirectory $Root -WindowStyle Hidden -Wait
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

$itemOpen.Add_Click({ Invoke-Action 'open' { Open-Planarus } })
$itemStart.Add_Click({ Invoke-Action 'start' { Start-Planarus }; Update-Menu })
$itemStop.Add_Click({ Invoke-Action 'stop' { Stop-Planarus }; Update-Menu })
$itemExit.Add_Click({
        # Hide before exiting: an unhidden NotifyIcon leaves a ghost in the
        # notification area until the user hovers over it.
        Write-TrayLog 'tray : exit requested from the menu'
        $notify.Visible = $false
        [System.Windows.Forms.Application]::Exit()
    })

# Double-click opens the UI, which is what a tray icon is expected to do.
$notify.Add_MouseDoubleClick({ Invoke-Action 'open (double-click)' { Open-Planarus } })

# The menu is only read when it opens, so refresh then rather than on a timer --
# no polling, and the state is never stale at the moment it is looked at.
$menu.Add_Opening({ Update-Menu })

# Set the tooltip BEFORE showing the icon. The shell caches the text it is given
# when the icon is registered, so doing this the other way round left the tray
# reading a bare "Planarus" for the whole session while the status text the code
# had carefully computed went nowhere.
Write-TrayLog "tray : starting, root=$Root"
Update-Menu
$notify.Visible = $true
Write-TrayLog 'tray : icon visible, entering message loop'

# A vanished tray icon is the one failure nobody can report usefully: this host
# is a hidden PowerShell, so a crash in the message loop takes the icon away
# without a window, a dialog or a line anywhere. The log is the only place left
# to say what happened, and "the icon is gone and the log ends at startup" was
# indistinguishable from "someone clicked Exit tray".
try {
    [System.Windows.Forms.Application]::Run([System.Windows.Forms.ApplicationContext]::new())
    Write-TrayLog 'tray : message loop ended, exiting'
} catch {
    Write-TrayLog "tray : CRASHED - $($_.Exception.Message)"
    throw
} finally {
    $notify.Visible = $false
    $notify.Dispose()
}
