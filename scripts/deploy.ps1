# deploy.ps1 — one-command deploy + load + test on board.
#
# Usage:
#   pwsh scripts/deploy.ps1                                    # default: load only
#   pwsh scripts/deploy.ps1 -Mode loopback -Input <packed_file>  # DMA loopback test
#
# Exit:   0 = PASS on board; 1 = local artifact missing;
#         2 = board unreachable; 3 = transfer failed;
#         4 = board-side check failed (detail forwarded)
param(
  [ValidateSet('load', 'loopback')]
  [string]$Mode = 'load',
  [string]$Input = ''
)

$ErrorActionPreference = 'Stop'
$Repo  = Split-Path -Parent $PSScriptRoot
$Out   = Join-Path $Repo 'vivado/out'
$Board = 'pynq-z2-codex'
$BDIR  = '/home/xilinx/overlays/nasdaq'

$Bit = Join-Path $Out 'nasdaq.bit'
$Hwh = Join-Path $Out 'nasdaq.hwh'
$Ldr = Join-Path $Repo 'board\load_overlay.py'
$BoardLoadCmd = "sudo -n env XILINX_XRT=/usr /usr/local/share/pynq-venv/bin/python $BDIR/load_overlay.py"

function Fail([int]$code, [string]$msg) {
  Write-Host "DEPLOY-FAIL: $msg" -ForegroundColor Red
  exit $code
}

# ---- mode-specific validation --------------------------------------------
if ($Mode -eq 'loopback') {
  if (-not $Input) { Fail 1 "-Input required for -Mode loopback" }
  if (-not (Test-Path $Input)) { Fail 1 "input file not found: $Input" }
}

# ---- local pair check ----------------------------------------------------
Write-Host "[1/4] checking local artifact pair"
foreach ($f in @($Bit, $Hwh)) {
  if (-not (Test-Path $f)) { Fail 1 "missing local artifact: $f (run build.ps1 first)" }
  if ((Get-Item $f).Length -eq 0) { Fail 1 "empty local artifact: $f (run build.ps1 again)" }
}

# ---- board reachable -----------------------------------------------------
Write-Host "[2/4] checking board $Board"
ssh -o ConnectTimeout=10 -o BatchMode=yes $Board "true"
if ($LASTEXITCODE -ne 0) { Fail 2 "board unreachable; see docs/overlay-toolchain.md troubleshooting" }

# ---- transfer ------------------------------------------------------------
Write-Host "[3/4] deploying to ${Board}:$BDIR"
ssh $Board "mkdir -p $BDIR"
if ($LASTEXITCODE -ne 0) { Fail 3 "mkdir on board failed" }
scp -q $Bit $Hwh $Ldr "${Board}:$BDIR/"
if ($LASTEXITCODE -ne 0) { Fail 3 "scp failed" }

# For loopback mode, also transfer the input file
if ($Mode -eq 'loopback') {
  $InputName = Split-Path $Input -Leaf
  $InputBDIR = "$BDIR/$InputName"
  Write-Host "[3b/4] deploying input file to board"
  scp -q $Input "${Board}:$InputBDIR"
  if ($LASTEXITCODE -ne 0) { Fail 3 "scp input file failed" }
}

# ---- board-side load + test ----------------------------------------------
Write-Host "[4/4] board-side load + $Mode test"
if ($Mode -eq 'loopback') {
  $InputName = Split-Path $Input -Leaf
  $BoardCmd = "$BoardLoadCmd --loopback --input $BDIR/$InputName"
} else {
  $BoardCmd = $BoardLoadCmd
}
ssh $Board $BoardCmd
$rc = $LASTEXITCODE
if ($rc -eq 0) {
  if ($Mode -eq 'loopback') {
    Write-Host "DEPLOY-OK: DMA loopback verified on board" -ForegroundColor Green
  } else {
    Write-Host "DEPLOY-OK: overlay verified on board" -ForegroundColor Green
  }
  exit 0
} elseif ($rc -eq 2) {
  Fail 4 "board reports missing files"
} elseif ($rc -eq 3) {
  Fail 4 "board reports overlay load failure (check XILINX_XRT/sudo invocation)"
} elseif ($rc -eq 4) {
  if ($Mode -eq 'loopback') {
    Fail 4 "board reports loopback assertion failure (mismatch/drop/throughput)"
  } else {
    Fail 4 "board reports assertion failure"
  }
} else {
  Fail 4 "board-side script exited $rc"
}
