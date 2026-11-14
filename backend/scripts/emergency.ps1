# Emergency laptop mode (BE-04.4), Windows PowerShell version of emergency.sh.
#
#   backend\scripts\emergency.ps1            # real Gemini, memory store, port 8000
#   backend\scripts\emergency.ps1 -Fake      # fake AI (rehearsal without a Gemini key)
#   backend\scripts\emergency.ps1 -Port 8001
#
# Storage is always memory (the fixture recipe is seeded at startup). GEMINI_API_KEY and any
# GHOSTCHEF_MODEL_* values come from the environment, else from backend\.env. No key is printed.
# Allow Python through Windows Firewall for private networks when prompted.
param(
    [switch]$Fake,
    [int]$Port = 8000
)
$ErrorActionPreference = "Stop"

$BackendDir = Split-Path -Parent $PSScriptRoot
Set-Location $BackendDir

function Get-DotEnvValue([string]$Name) {
    if (-not (Test-Path ".env")) { return $null }
    $line = Get-Content ".env" | Where-Object { $_ -match "^\s*(export\s+)?$Name=" } | Select-Object -Last 1
    if (-not $line) { return $null }
    $value = ($line -split "=", 2)[1].Trim()
    if ($value -match '^"([^"]*)"' -or $value -match "^'([^']*)'") {
        return $Matches[1]                          # quoted: take what is inside the quotes
    }
    return ($value -replace '\s+#.*$', '').Trim()   # unquoted: drop an inline " # comment"
}

# ghostchef_ai reads these from the process environment, not from backend\.env.
foreach ($var in "GEMINI_API_KEY", "GHOSTCHEF_MODEL_VIDEO", "GHOSTCHEF_MODEL_CHECK",
                 "GHOSTCHEF_MODEL_WATCH", "GHOSTCHEF_MODEL_LIVE") {
    if (-not [Environment]::GetEnvironmentVariable($var)) {
        $val = Get-DotEnvValue $var
        if ($val) { [Environment]::SetEnvironmentVariable($var, $val, "Process") }
    }
}

$env:STORAGE = "memory"
# Derive URLs from the request, i.e. the LAN address phones use. A single space, not "": assigning
# "" deletes the variable in PowerShell, and backend\.env's value would then win. The backend
# treats a blank value as unset.
$env:PUBLIC_BASE_URL = " "
if ($Fake) {
    $env:GHOSTCHEF_AI_FAKE = "1"
} else {
    $env:GHOSTCHEF_AI_FAKE = "0"
    if (-not $env:GEMINI_API_KEY) {
        Write-Error "GEMINI_API_KEY is not set (environment or backend\.env). Use -Fake to rehearse without it."
        exit 1
    }
    # Real Gemini on a shared network: refuse the public default demo key.
    $demoKey = if ($env:DEMO_API_KEY) { $env:DEMO_API_KEY } else { Get-DotEnvValue "DEMO_API_KEY" }
    if (-not $demoKey -or $demoKey -eq "dev-key") {
        Write-Error "DEMO_API_KEY is unset or the public default 'dev-key'. Set a private key in backend\.env (the same one the apps use), or use -Fake."
        exit 1
    }
    Remove-Variable demoKey
}

$Python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }

$mode = if ($Fake) { "fake" } else { "gemini" }
Write-Host "Ghost Chef emergency mode: STORAGE=memory, AI=$mode, port $Port"
Write-Host "Type one of these into the app's settings as the server URL (same Wi-Fi / hotspot as this laptop):"
$addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    Select-Object -ExpandProperty IPAddress -Unique
if ($addresses) {
    foreach ($a in $addresses) { Write-Host "    http://${a}:$Port" }
} else {
    Write-Host "    (no LAN address found: is this laptop connected to the hotspot?)"
}
Write-Host "Demo key: the DEMO_API_KEY in backend\.env (not printed). Check: curl http://<address>:$Port/health"
Write-Host "Plain HTTP: the web simulator's camera works only on this laptop (http://localhost:$Port/app/)."
Write-Host ""

& $Python -m uvicorn app.main:app --host 0.0.0.0 --port $Port --workers 1
exit $LASTEXITCODE
