<#
Polymarkov dev servers — start / stop both with one command.

  .\scripts\dev.ps1            start FastAPI (:8000) + Next.js (:3000), each in its own window
  .\scripts\dev.ps1 -Stop      kill everything listening on :8000 and :3000
  .\scripts\dev.ps1 -Restart   stop, then start

Always kills stale listeners before starting: this machine has had zombie
uvicorn processes hold :8000 with old code (symptom: 404s on routes that
exist on disk), so a clean slate is non-negotiable.
#>

param(
    [switch]$Stop,
    [switch]$Restart
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot   # repo root (this file lives in scripts/)
$Ports = @(8000, 3000)

function Stop-Servers {
    foreach ($port in $Ports) {
        $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        $pids = $conns | Select-Object -ExpandProperty OwningProcess -Unique
        if (-not $pids) {
            Write-Host "  :$port  nothing listening"
            continue
        }
        foreach ($procId in $pids) {
            try {
                $name = (Get-Process -Id $procId -ErrorAction Stop).ProcessName
                Stop-Process -Id $procId -Force -ErrorAction Stop
                Write-Host "  :$port  killed $name (pid $procId)"
            } catch {
                Write-Host "  :$port  pid $procId already gone"
            }
        }
    }
}

function Start-Servers {
    if (-not (Test-Path (Join-Path $Root ".venv\Scripts\python.exe"))) {
        Write-Host "ERROR: .venv missing - run:  python -m venv .venv; .venv\Scripts\pip install -r requirements-dev.txt"
        exit 1
    }
    if (-not (Test-Path (Join-Path $Root "node_modules"))) {
        Write-Host "node_modules missing - running npm install first..."
        Push-Location $Root; npm install; Pop-Location
    }

    Write-Host "starting FastAPI backend on http://localhost:8000 ..."
    Start-Process -WorkingDirectory $Root -FilePath "powershell" -ArgumentList @(
        "-NoExit", "-Command",
        "`$Host.UI.RawUI.WindowTitle = 'polymarkov api :8000'; .venv\Scripts\python -m uvicorn api.index:app --reload --port 8000"
    )

    Write-Host "starting Next.js frontend on http://localhost:3000 ..."
    Start-Process -WorkingDirectory $Root -FilePath "powershell" -ArgumentList @(
        "-NoExit", "-Command",
        "`$Host.UI.RawUI.WindowTitle = 'polymarkov web :3000'; npm run dev"
    )

    Write-Host ""
    Write-Host "up. open http://localhost:3000  (GUI; /api/* proxies to :8000)"
    Write-Host "take it down with:  .\scripts\dev.ps1 -Stop"
}

if ($Stop) {
    Write-Host "stopping dev servers..."
    Stop-Servers
} elseif ($Restart) {
    Write-Host "restarting dev servers..."
    Stop-Servers
    Start-Sleep -Seconds 1
    Start-Servers
} else {
    Write-Host "clearing stale listeners..."
    Stop-Servers
    Start-Servers
}
