# Start the local-preset watcher if it is not already running.
#
# The watcher keeps the `local` preset in oh-my-opencode-slim.json pointed at
# whatever model is currently loaded in Ollama, falling back to the 192k
# Qwen3.8 Distill build. It is safe to call this repeatedly: only one instance
# runs at a time.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File start-local-preset-watch.ps1
#   powershell -ExecutionPolicy Bypass -File start-local-preset-watch.ps1 -Stop

param(
    [switch]$Stop,
    [int]$IntervalMs = 15000
)

$ErrorActionPreference = 'Stop'

$script = Join-Path $PSScriptRoot 'local-preset-watch.mjs'
$lock = Join-Path $env:TEMP 'opencode-local-preset-watch.pid'

function Get-WatcherProcess {
    if (-not (Test-Path $lock)) { return $null }
    $pidText = (Get-Content $lock -Raw).Trim()
    if (-not $pidText) { Remove-Item $lock -Force -ErrorAction SilentlyContinue; return $null }
    $proc = Get-Process -Id ([int]$pidText) -ErrorAction SilentlyContinue
    if (-not $proc) { Remove-Item $lock -Force -ErrorAction SilentlyContinue; return $null }
    return $proc
}

$existing = Get-WatcherProcess
if ($Stop) {
    if ($existing) {
        Stop-Process -Id $existing.Id -Force
        Remove-Item $lock -Force -ErrorAction SilentlyContinue
        Write-Output "Stopped local-preset watcher (pid $($existing.Id))."
    } else {
        Write-Output 'No local-preset watcher was running.'
    }
    exit 0
}

if ($existing) {
    Write-Output "Local-preset watcher already running (pid $($existing.Id))."
    exit 0
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Output 'Node.js is not on PATH; local preset will not track the loaded model.'
    exit 1
}

$env:LOCAL_PRESET_INTERVAL = "$IntervalMs"
$proc = Start-Process -FilePath 'node' -ArgumentList @($script) `
    -WindowStyle Hidden -PassThru
$proc.Id | Set-Content $lock -NoNewline

Write-Output "Started local-preset watcher (pid $($proc.Id), interval ${IntervalMs}ms)."
Write-Output 'The local preset now follows the model loaded in Ollama.'