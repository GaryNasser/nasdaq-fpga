param([string]$Cmd = 'uname -a', [int]$Seconds = 12)
$port = New-Object System.IO.Ports.SerialPort('COM3',115200,[System.IO.Ports.Parity]::None,8,[System.IO.Ports.StopBits]::One)
$port.ReadTimeout = 500
$port.DtrEnable = $true
$port.RtsEnable = $true
try { $port.Open() } catch { "OPEN-FAIL: " + $_.Exception.Message; exit 1 }
# drain pending output
try { $null = $port.ReadExisting() } catch {}
Start-Sleep -Milliseconds 300
try { $null = $port.ReadExisting() } catch {}
# unique marker to find end of output
$m1 = "B" + (Get-Random -Maximum 999999)
$port.Write("`r`n echo ${m1}S; ${Cmd}; echo ${m1}E`r`n")
$deadline = (Get-Date).AddSeconds($Seconds)
$buf = New-Object System.Text.StringBuilder
while ((Get-Date) -lt $deadline) {
  try { $s = $port.ReadExisting(); if ($s) { [void]$buf.Append($s) } } catch {}
  if ($buf.ToString() -match "${m1}E") { break }
  Start-Sleep -Milliseconds 200
}
$port.Close()
"=== output of: $Cmd ==="
$buf.ToString()
