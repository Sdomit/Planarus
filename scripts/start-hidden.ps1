# =============================================================================
# Planarus - launch one background service with no window
#
# Called by run-planarus.bat in silent mode.
#
# Input arrives in environment variables, not parameters, and that is the whole
# point of this file. The command being launched contains spaces, quotes, && and
# a redirect; sending that through cmd and then through powershell.exe -File
# means two parsers get a turn at it, and both take one. Passing it as a
# parameter failed twice - first the name -Command was swallowed by
# powershell.exe's own switch, then the quoting collapsed and "call pnpm
# dev:web" arrived split across three parameters, which surfaced as
# "A drive with the name 'dev' does not exist". An environment variable is
# inherited by value and never re-parsed.
#
#   PLANARUS_HIDDEN_WORKDIR   directory to run in
#   PLANARUS_HIDDEN_CMD       command line to hand to cmd /c
#   PLANARUS_HIDDEN_LOG       file to append stdout and stderr to
#
# Prints the new process id so the caller can record it.
# =============================================================================
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$workDir = $env:PLANARUS_HIDDEN_WORKDIR
$commandLine = $env:PLANARUS_HIDDEN_CMD
$logFile = $env:PLANARUS_HIDDEN_LOG

foreach ($pair in @(
        @{ Name = 'PLANARUS_HIDDEN_WORKDIR'; Value = $workDir },
        @{ Name = 'PLANARUS_HIDDEN_CMD'; Value = $commandLine },
        @{ Name = 'PLANARUS_HIDDEN_LOG'; Value = $logFile })) {
    if ([string]::IsNullOrWhiteSpace($pair.Value)) {
        throw "$($pair.Name) is not set - this script is called by run-planarus.bat, not directly"
    }
}

if (-not (Test-Path -LiteralPath $workDir)) {
    throw "working directory does not exist: $workDir"
}

$dir = Split-Path -Parent $logFile
if (-not (Test-Path -LiteralPath $dir)) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

# Truncate per run. These logs answer "why did it not come up just now", and an
# ever-growing file makes that answer harder to find, not easier.
"=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') === $commandLine" |
    Set-Content -LiteralPath $logFile -Encoding utf8

# Redirection is written into the command cmd runs rather than passed as
# -RedirectStandardOutput: that parameter cannot be combined with a hidden
# window, and losing the output is the exact failure this file exists to
# prevent. A hidden service that dies still leaves its reason behind.
$full = "$commandLine >> `"$logFile`" 2>&1"

$proc = Start-Process -FilePath $env:ComSpec -ArgumentList '/c', $full `
    -WorkingDirectory $workDir -WindowStyle Hidden -PassThru

$proc.Id
