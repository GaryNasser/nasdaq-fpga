param([int]$Seconds = 20)
# Open COM3 at 115200 8N1, capture output for N seconds, send a newline to prompt a login banner
$port = New-Object System.IO.Ports.SerialPort('COM3',115200,[System.IO.Ports.Parity]::None,8,[System.IO.Ports.StopBits]::One)
$port.ReadTimeout = 500
$port.DtrEnable = $true
$port.RtsEnable = $true
try { $port.Open() } catch { "OPEN-FAIL: " + $_.Exception.Message; exit 1 }
"opened COM3, capturing for $Seconds s ..."
$deadline = (Get-Date).AddSeconds($Seconds)
$buf = New-Object System.Text.StringBuilder
while ((Get-Date) -lt $deadline) {
  try { $s = $port.ReadExisting(); if ($s) { [void]$buf.Append($s) } } catch {}
  Start-Sleep -Milliseconds 200
  if (((Get-Date).Second % 10) -eq 0 -and -not $script:sent) { $port.Write("`r`n"); $script:sent = $true }
}
$port.Close()
"=== captured ==="
$buf.ToString()
