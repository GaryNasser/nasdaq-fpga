# build.ps1 — one-command overlay build (specs/001-overlay-bootstrap, FR-001..003).
#
# Usage:  pwsh scripts/build.ps1 [-SkipSim] [-PackItch <raw_file>]
# Exit:   0 = bit+hwh pair emitted to vivado/out/
#         2 = Vivado not found        3 = simulation gate failed
#         4 = Vivado build failed     5 = artifact pair check failed
param(
  [switch]$SkipSim,
  [string]$PackItch = ''
)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $PSScriptRoot
$Rtl  = Join-Path $Repo 'rtl'
$Ws   = Join-Path $Repo 'vivado\workspace'
$Out  = Join-Path $Repo 'vivado\out'
$Vivado = 'D:\Xilinx\Vivado\2024.1\bin\vivado.bat'

function Fail([int]$code, [string]$msg) {
  Write-Host "BUILD-FAIL: $msg" -ForegroundColor Red
  exit $code
}

# ---- prerequisites ------------------------------------------------------
if (-not (Test-Path $Vivado)) { Fail 2 "Vivado 2024.1 not found at $Vivado" }

Write-Host "[1/4] cleaning workspace $Ws (repeatable builds)"
if (Test-Path $Ws)  { Remove-Item -Recurse -Force $Ws }
New-Item -ItemType Directory -Force -Path $Out | Out-Null

# ---- simulation gate (constitution III: no bitstream without sim) -------
if ($SkipSim) {
  Write-Warning "SKIP-SIM requested (constitution III deviation - dev only)"
} else {
  Write-Host "[2/4] simulation gate (tools/run_sims.py)"
  # Round 203: this gate used to hand-list four benches from rtl/itch/. One of them
  # (tb_mold64_reasm) now hangs mid-run, so the gate could never complete - and it
  # overlapped run_sims.py only by name, so the suite was green while the gate was not.
  # There is now ONE set of benches: the suite.
  $py = Join-Path $Repo "tools\run_sims.py"
  & python $py 2>&1 | Tee-Object -Variable simOut | Select-Object -Last 3
  $simText = ($simOut | Out-String)
  if ($LASTEXITCODE -ne 0 -or $simText -notmatch "SIMSUITE-PASS") {
    Fail 3 "simulation suite failed (tools/run_sims.py); no bitstream without sim"
  }
  Write-Host "      SIMSUITE-PASS ($(($simText | Select-String "passed \d+, failed \d+").Matches[0].Value))"
}

# ---- Vivado batch build --------------------------------------------------
# Retries on transient file-read failures (AV/indexer briefly locks
# random install-dir TCL files; observed ~1-in-3 clean builds locally).
Write-Host "[3/4] Vivado batch build (BD + synth + impl + bitstream)"
$buildLogBase = Join-Path $env:TEMP 'nasdaq_vivado'
$Driver = Join-Path $Repo 'vivado\build_driver.tcl'
$maxAttempts = 5
$attempt = 0
$done = $false
$materialize = Join-Path $Repo 'scripts\materialize_vivado_tcl.ps1'
$finalBuildLog = Join-Path $env:TEMP 'nasdaq_vivado.log'
while (-not $done -and $attempt -lt $maxAttempts) {
  $attempt++
  # Use a unique log file per attempt to avoid file-lock contention
  # when a prior Vivado process still holds the log handle.
  $buildLog = "${buildLogBase}_${attempt}.log"
  # Pre-hydrate OneDrive-backed Tcl files so Vivado's Tcl open() does not
  # hit the cloud. Without this, ~1-in-3 builds fail with "No error" /
  # "invalid argument" on random install-dir .tcl files.
  if (Test-Path $materialize) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $materialize *> $null
  }
  # Invoke via a fresh child PowerShell with the exact command form that
  # is verified to work reliably on this machine (direct invocation from
  # within this script intermittently fails to even start Vivado)
  & powershell -NoProfile -Command "& '$Vivado' -mode batch -nojournal -nolog -notrace -source '$Driver' *> '$buildLog'; exit `$LASTEXITCODE"
  $errLines = @()
  if (Test-Path $buildLog) {
    $errLines = @(Get-Content $buildLog | Select-String '^ERROR:' | Select-Object -First 8)
  }
  if (Test-Path "$buildLog.err") {
    $errLines += @(Get-Content "$buildLog.err" | Select-String 'ERROR|Error' | Select-Object -First 4)
  }
  if ($LASTEXITCODE -eq 0 -and $errLines.Count -eq 0) {
    $done = $true
    # Copy the successful attempt's log to the canonical name for the
    # WNS extraction below.
    Copy-Item $buildLog $finalBuildLog -Force
  } elseif ($attempt -lt $maxAttempts) {
    # Vivado startup is intermittently flaky on this machine (observed:
    # transient TCL file-read errors, or startup failing without touching
    # the log). Retry any failure - real errors fail consistently.
    Write-Warning "Vivado attempt $attempt/$maxAttempts failed, retrying..."
    Start-Sleep -Seconds 10
  } else {
    $errLines | ForEach-Object { Write-Host "      $_" }
    Copy-Item $buildLog $finalBuildLog -ErrorAction SilentlyContinue
    Fail 4 "Vivado build failed (first errors above; full log: $buildLog)"
  }
}


# ---- artifact pair check (FR-001) ----------------------------------------
Write-Host "[4/4] artifact pair check"
$bit = Join-Path $Out 'nasdaq.bit'
$hwh = Join-Path $Out 'nasdaq.hwh'
foreach ($f in @($bit, $hwh)) {
  if (-not (Test-Path $f)) { Fail 5 "missing artifact: $f" }
  if ((Get-Item $f).Length -eq 0) { Fail 5 "empty artifact: $f" }
}
$bitSize = '{0:N0}' -f (Get-Item $bit).Length
$hwhSize = '{0:N0}' -f (Get-Item $hwh).Length
# Read the canonical copy, not the per-attempt name: $finalBuildLog is written only on success,
# so the WNS printed always comes from the build that produced the bitstream.
$m = Get-Content $finalBuildLog | Select-String '^WNS:'
$wns = if ($m) { $m.ToString() } else { 'WNS-UNKNOWN' }
Write-Host "BUILD-OK  nasdaq.bit ($bitSize B) + nasdaq.hwh ($hwhSize B)  $wns" -ForegroundColor Green

# ---- optional ITCH packer (US2 integration) -------------------------------
if ($PackItch) {
  Write-Host "[5/4] packing ITCH sample"
  if (-not (Test-Path $PackItch)) { Fail 1 "PackItch file not found: $PackItch" }
  $packedOut = Join-Path $Repo 'data\itch_dev.mold64'
  New-Item -ItemType Directory -Force -Path (Split-Path $packedOut) | Out-Null
  & python (Join-Path $Repo 'scripts\pack_itch.py') --input $PackItch --output $packedOut --session NASDAQ01
  if ($LASTEXITCODE -ne 0) { Fail 1 "pack_itch.py failed (exit $LASTEXITCODE)" }
  Write-Host "      packed output: $packedOut"
}

exit 0
