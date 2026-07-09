#Requires -Version 5
<#
.SYNOPSIS
  Turn the AgentBoard external API on or off. Sets the persistent Windows *user*
  environment variable AGENTBOARD_EXTERNAL_API_ENABLED, then reminds you to restart.

.EXAMPLE
  .\set-external-api.ps1 on
  .\set-external-api.ps1 off

.NOTES
  The app reads this value once at startup, so a change only takes effect after you
  restart AgentBoard in a FRESH terminal. See docs/guide/connect-agentboard-to-chatgpt.md.
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory, Position = 0)]
  [ValidateSet('on', 'off')]
  [string]$State
)

$enabled = $State -eq 'on'
$value = $enabled.ToString().ToLower()   # 'true' / 'false' (pydantic-friendly)
[Environment]::SetEnvironmentVariable('AGENTBOARD_EXTERNAL_API_ENABLED', $value, 'User')

$allowed = [Environment]::GetEnvironmentVariable('AGENTBOARD_EXTERNAL_API_ALLOWED_HOSTS', 'User')

Write-Host ""
Write-Host "AGENTBOARD_EXTERNAL_API_ENABLED        = $value" -ForegroundColor Cyan
Write-Host "AGENTBOARD_EXTERNAL_API_ALLOWED_HOSTS  = $(if ($allowed) { $allowed } else { '(empty - loopback only)' })"

if ($enabled -and -not $allowed) {
  Write-Host ""
  Write-Host "WARNING: API enabled but no public host is allowlisted." -ForegroundColor Yellow
  Write-Host "         Set it first (guide Step 2) or ChatGPT requests will be rejected." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Restart AgentBoard in a FRESH terminal for this to take effect:" -ForegroundColor Green
Write-Host "  1. Close the AgentBoard API/Web windows."
Write-Host "  2. Open a new terminal, run: run-agentboard.bat"
