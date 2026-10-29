param(
  [Parameter(Mandatory=$true)][string]$File,
  [Parameter(Mandatory=$true)][string]$RemoteName,
  [int]$Chunk = 200
)
# Upload a deflate+base64 file to the PYNQ board over the serial console.
#
# Tailscale and SSH are both unreachable from this laptop (the board's campus
# VLAN is firewalled), so the serial console is the only channel. The payload
# is compressed first - the .hwh drops from 413 KB to 37 KB, i.e. ~50 KB of
# base64, which is practical to push at 115200 baud.
#
# The file is appended chunk by chunk with `echo >> 'base64', so an interrupted
# transfer can be resumed by looking at how many lines already arrived.

$b64 = Get-Content $File -Raw
$b64 = $b64 -replace '\s',''
$total = $b64.Length
$nchunks = [math]::Ceiling($total / $Chunk)
Write-Output "uploading $total base64 chars in $nchunks chunks of $Chunk"

$port = New-Object System.IO.Ports.SerialPort('COM3',115200,[System.IO.Ports.Parity]::None,8,[System.IO.Ports.StopBits]::One)
$port.ReadTimeout = 300
$port.WriteTimeout = 3000
$port.DtrEnable = $true
$port.RtsEnable = $true
try { $port.Open() } catch { "OPEN-FAIL: " + $_.Exception.Message; exit 1 }
try { $null = $port.ReadExisting() } catch {}

function Send-Line([string]$s) {
  $port.Write($s + "`r")
  Start-Sleep -Milliseconds 25
}

# Wait until the shell echoes a marker we send, so we never type into a
# half-consumed line.
function Sync-Shell {
  $m = "Z" + (Get-Random -Maximum 999999)
  $port.Write("`r echo ${m}K`r")
  $deadline = (Get-Date).AddSeconds(8)
  $acc = ""
  while ((Get-Date) -lt $deadline) {
    try { $acc += $port.ReadExisting() } catch {}
    if ($acc -match "${m}K") { return $true }
    Start-Sleep -Milliseconds 60
  }
  return $false
}

if (-not (Sync-Shell)) { Write-Output "SYNC-FAIL"; $port.Close(); exit 1 }

Send-Line "rm -f /home/xilinx/$RemoteName.b64"
Send-Line "touch /home/xilinx/$RemoteName.b64"

$sent = 0
for ($i = 0; $i -lt $total; $i += $Chunk) {
  $len = [math]::Min($Chunk, $total - $i)
  $part = $b64.Substring($i, $len)
  Send-Line "printf '%s' '$part' >> /home/xilinx/$RemoteName.b64"
  $sent += $len
  if (($i / $Chunk) % 50 -eq 0) {
    Write-Output "  $sent / $total"
    try { $null = $port.ReadExisting() } catch {}
  }
}
Send-Line "echo UPLOAD-DONE"
Start-Sleep -Milliseconds 800
try { $out = $port.ReadExisting() } catch { $out = "" }
$port.Close()
Write-Output "sent $sent of $total chars"
if ($out -match "UPLOAD-DONE") { Write-Output "MARKER-SEEN" }
