<#
.SYNOPSIS
    One command to set up and run the whole app (backend + frontend).

.DESCRIPTION
    Run from the project folder:   .\dev.ps1
    To open it on your phone too:  .\dev.ps1 -Lan
    Public https link (any phone):  .\dev.ps1 -Https

    The frontend is served by the same FastAPI process as the backend, so this single
    script gives you both. First run creates .venv, installs requirements.txt and seeds
    the SQLite database (~1 minute). Later runs skip whatever is already done.
    Stop the server with Ctrl+C.

    If PowerShell says "running scripts is disabled on this system", run this ONCE:
        Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
    or run it without changing any setting:
        powershell -ExecutionPolicy Bypass -File .\dev.ps1

.PARAMETER Port
    First port to try (default 9999). If it is busy the next free one is used.

.PARAMETER NoBrowser
    Do not open the browser automatically.

.PARAMETER Lan
    Also accept connections from other devices on the same Wi-Fi (e.g. your phone).
    Prints the phone URL and a QR code to scan. Anyone on that network can then reach
    the app, so use it on a network you trust.

.PARAMETER Https
    Also publish the app on a temporary https://....trycloudflare.com address through a
    Cloudflare quick tunnel (cloudflared.exe is downloaded to .tools\ on first use).
    https is what phones need for "install app", GPS and the qibla compass. The address
    changes every run and ANYONE who has it can open the app while the script is running.
#>
param(
    [int]$Port = 9999,
    [switch]$NoBrowser,
    [switch]$Lan,
    [switch]$Https
)

# 'Continue', not 'Stop': in Windows PowerShell 5.1 any stderr line from a native command
# (e.g. pip's "new release available" notice) becomes a terminating error under 'Stop' and
# kills the script even though the command succeeded. Native calls below are judged by
# $LASTEXITCODE instead; the few cmdlets that must fail fast use -ErrorAction Stop.
$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath $PSScriptRoot

# Thai text from the seed step must not garble/crash on a legacy console codepage.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

function Say($msg)  { Write-Host "[dev] $msg" -ForegroundColor Green }
function Fail($msg) { Write-Host "[dev] ERROR: $msg" -ForegroundColor Red; exit 1 }

# ---- 1. find a usable Python (3.10+; the code uses `str | None` annotations) ----
function Find-Python {
    $candidates = @(@('py', '-3'), @('python'), @('python3'))
    foreach ($c in $candidates) {
        $exe = $c[0]
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $extra = @()
        if ($c.Count -gt 1) { $extra = $c[1..($c.Count - 1)] }
        try {
            # The Microsoft Store "python" stub exits non-zero / prints nothing useful, so verify by running it.
            $ok = & $exe @extra -c "import sys; print('OK' if sys.version_info >= (3, 10) else 'OLD')" 2>$null
            if ($LASTEXITCODE -eq 0 -and $ok -eq 'OK') { return ,(@($exe) + $extra) }
        } catch { }
    }
    return $null
}

$py = Find-Python
if (-not $py) {
    Fail "Python 3.10+ not found. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run .\dev.ps1 again."
}
$pyExe = $py[0]
$pyArgs = @()
if ($py.Count -gt 1) { $pyArgs = $py[1..($py.Count - 1)] }

$venvDir = Join-Path $PSScriptRoot '.venv'
$venvPy  = Join-Path $venvDir 'Scripts\python.exe'
$reqFile = Join-Path $PSScriptRoot 'requirements.txt'
$stamp   = Join-Path $venvDir '.requirements.sha256'

if (-not (Test-Path $reqFile)) { Fail "requirements.txt not found - run this from the project folder." }

# ---- 2. virtual environment ----
function Test-VenvUsable {
    if (-not (Test-Path $venvPy)) { return $false }
    & $venvPy -c "import sys" 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

if (-not (Test-VenvUsable)) {
    if (Test-Path $venvDir) {
        Say ".venv is broken (probably copied from another machine) - recreating it"
        Remove-Item -LiteralPath $venvDir -Recurse -Force -ErrorAction Stop
    }
    Say "creating virtual environment in .venv ..."
    & $pyExe @pyArgs -m venv $venvDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-VenvUsable)) { Fail "could not create a working .venv" }
}

# ---- 3. dependencies (only when requirements.txt changed) ----
$wanted = (Get-FileHash -LiteralPath $reqFile -Algorithm SHA256).Hash
$have = ''
if (Test-Path $stamp) { $have = (Get-Content -LiteralPath $stamp -Raw).Trim() }
if ($have -ne $wanted) {
    Say "installing requirements (first run takes a minute or two) ..."
    & $venvPy -m pip install --disable-pip-version-check -r $reqFile
    if ($LASTEXITCODE -ne 0) { Fail "pip install failed - read the messages above. Check your internet connection and try again." }
    Set-Content -LiteralPath $stamp -Value $wanted -Encoding ascii -ErrorAction Stop
}

# ---- 4. private SECRET_KEY (signs login cookies) ----
# The placeholder from .env.example is public on GitHub; with it anyone could forge a login
# cookie for any account, including admins. Replace it with a random key once.
$envFile = Join-Path $PSScriptRoot '.env'
$placeholderKeys = @('change-me-to-a-long-random-string', 'dev-secret-key-change-me')
$envLines = @()
if (Test-Path $envFile) { $envLines = @(Get-Content -LiteralPath $envFile -Encoding UTF8) }
$keyIdx = -1
for ($i = 0; $i -lt $envLines.Count; $i++) { if ($envLines[$i] -match '^\s*SECRET_KEY\s*=') { $keyIdx = $i } }
$currentKey = ''
if ($keyIdx -ge 0) { $currentKey = ($envLines[$keyIdx] -split '=', 2)[1].Trim().Trim('"', "'") }
if (-not $currentKey -or $placeholderKeys -contains $currentKey) {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $newLine = 'SECRET_KEY=' + (-join ($bytes | ForEach-Object { $_.ToString('x2') }))
    if ($keyIdx -ge 0) { $envLines[$keyIdx] = $newLine } else { $envLines += $newLine }
    [System.IO.File]::WriteAllLines($envFile, [string[]]$envLines, (New-Object System.Text.UTF8Encoding $false))
    Say "generated a private SECRET_KEY in .env (anyone logged in must log in again, once)"
}

# ---- 5. database: tables + sample data (idempotent, safe to repeat) ----
Say "preparing database (creates tables + sample data; safe to repeat) ..."
& $venvPy -m app.seed
if ($LASTEXITCODE -ne 0) { Fail "seeding the database failed - read the messages above." }

# ---- 6. pick a free port ----
$bindHost = '127.0.0.1'
$bindAddr = [System.Net.IPAddress]::Loopback
if ($Lan) { $bindHost = '0.0.0.0'; $bindAddr = [System.Net.IPAddress]::Any }

function Test-PortFree([int]$p) {
    try {
        $l = New-Object System.Net.Sockets.TcpListener($bindAddr, $p)
        $l.Start(); $l.Stop()
        return $true
    } catch { return $false }
}

$chosen = $null
foreach ($p in $Port..($Port + 19)) {
    if (Test-PortFree $p) { $chosen = $p; break }
}
if ($null -eq $chosen) { Fail "no free port between $Port and $($Port + 19)." }
if ($chosen -ne $Port) {
    Write-Host "[dev] port $Port is busy (another server still running?) - using $chosen instead" -ForegroundColor Yellow
}

$url = "http://127.0.0.1:$chosen"

# ---- 7. open the browser once the server answers, then run the server in the foreground ----
if (-not $NoBrowser) {
    Start-Job -ArgumentList $url, $chosen -ScriptBlock {
        param($u, $p)
        for ($i = 0; $i -lt 60; $i++) {
            try {
                $c = New-Object System.Net.Sockets.TcpClient
                $c.Connect('127.0.0.1', $p); $c.Close()
                Start-Process $u
                return
            } catch { Start-Sleep -Milliseconds 500 }
        }
    } | Out-Null
}

if ($Lan) {
    # Wi-Fi/Ethernet addresses only; skip loopback, link-local and virtual adapters (WSL, Hyper-V, VPN).
    $ips = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and
                       $_.InterfaceAlias -notmatch 'vEthernet|WSL|Loopback|VirtualBox|VMware' } |
        Select-Object -ExpandProperty IPAddress)
    if ($ips.Count -eq 0) {
        Say "no Wi-Fi/LAN address found - is this computer connected to a network?"
    } else {
        $phoneUrl = "http://$($ips[0]):$chosen"
        Say "on your phone (same Wi-Fi), open:  $phoneUrl"
        foreach ($ip in $ips | Select-Object -Skip 1) { Say "   or:  http://${ip}:$chosen" }
        & $venvPy -c "import qrcode, sys; q = qrcode.QRCode(border=1); q.add_data(sys.argv[1]); q.print_ascii(invert=True)" $phoneUrl
    }

    # Windows blocks inbound connections to this port until a firewall rule allows it.
    # (A per-port rule is used because .venv\python.exe is only a launcher for the real interpreter.)
    $ruleName = "Unlock with Unloh (port $chosen)"
    $allowed = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue |
        Where-Object { $_.Enabled -eq 'True' -and $_.Action -eq 'Allow' }
    if (-not $allowed) {
        Write-Host ""
        Write-Host "[dev] The Windows firewall will block your phone. Fix it once: open PowerShell as" -ForegroundColor Yellow
        Write-Host "      Administrator and run:" -ForegroundColor Yellow
        Write-Host "      New-NetFirewallRule -DisplayName '$ruleName' -Direction Inbound -Protocol TCP -LocalPort $chosen -Action Allow" -ForegroundColor Cyan
        Write-Host "      (remove it later with: Remove-NetFirewallRule -DisplayName '$ruleName')" -ForegroundColor Yellow
        Write-Host ""
    }
}

$tunnel = $null
if ($Https) {
    $toolsDir = Join-Path $PSScriptRoot '.tools'
    $cloudflared = Join-Path $toolsDir 'cloudflared.exe'
    if (-not (Test-Path $cloudflared)) {
        Say "downloading cloudflared (one time, ~60 MB) ..."
        New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        $ProgressPreference = 'SilentlyContinue'   # the progress bar makes downloads ~10x slower in PS 5.1
        try {
            Invoke-WebRequest -UseBasicParsing -ErrorAction Stop -OutFile "$cloudflared.part" `
                -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe'
            Move-Item -LiteralPath "$cloudflared.part" -Destination $cloudflared -Force -ErrorAction Stop
        } catch {
            Fail "could not download cloudflared: $($_.Exception.Message)"
        }
    }

    $tunnelOut = Join-Path $toolsDir 'cloudflared.out.log'
    $tunnelErr = Join-Path $toolsDir 'cloudflared.log'
    Remove-Item -LiteralPath $tunnelOut, $tunnelErr -ErrorAction SilentlyContinue
    Say "opening https tunnel ..."
    $tunnel = Start-Process -FilePath $cloudflared -NoNewWindow -PassThru `
        -ArgumentList 'tunnel', '--no-autoupdate', '--url', "http://127.0.0.1:$chosen" `
        -RedirectStandardOutput $tunnelOut -RedirectStandardError $tunnelErr

    # cloudflared prints the random address it was given; wait for it.
    $publicUrl = $null
    for ($i = 0; $i -lt 60 -and -not $publicUrl -and -not $tunnel.HasExited; $i++) {
        Start-Sleep -Milliseconds 500
        $m = Select-String -LiteralPath $tunnelErr -Pattern 'https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com' -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($m) { $publicUrl = $m.Matches[0].Value }
    }
    if ($publicUrl) {
        Write-Host ""
        Say "https link (works on any phone, any network):  $publicUrl"
        & $venvPy -c "import qrcode, sys; q = qrcode.QRCode(border=1); q.add_data(sys.argv[1]); q.print_ascii(invert=True)" $publicUrl
        Write-Host "[dev] Anyone with this link can open the app until you press Ctrl+C. The link changes every run." -ForegroundColor Yellow
        Write-Host "[dev] (It can take ~30 seconds after this before the link starts answering.)" -ForegroundColor Yellow
        Write-Host ""
    } else {
        Write-Host "[dev] the https tunnel did not start - see $tunnelErr. Continuing without it." -ForegroundColor Yellow
    }
}

Say "starting server at $url   (Ctrl+C to stop)"
try {
    & $venvPy -m uvicorn app.main:app --host $bindHost --port $chosen
} finally {
    Get-Job -ErrorAction SilentlyContinue | Remove-Job -Force -ErrorAction SilentlyContinue
    if ($tunnel -and -not $tunnel.HasExited) { Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue }
    Say "server stopped"
}
