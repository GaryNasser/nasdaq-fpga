$ErrorActionPreference = 'Stop'
Set-Location D:\agent\nasdaq-fpga\rtl
Remove-Item -Recurse -Force xsim.dir,.Xil -ErrorAction SilentlyContinue
$log = "$env:TEMP\nasdaq_xvlog_monly.log"
& 'D:\Xilinx\Vivado\2024.1\bin\xvlog.bat' ctrl_regs.v itch\mold64_reasm.v itch\tb_mold64_reasm.v *> $log
if ($LASTEXITCODE -ne 0) { Write-Host "XVLOG FAILED"; Get-Content $log | Select-String ERROR | Select-Object -First 10; exit 1 }
Write-Host "XVLOG OK"
$elog = "$env:TEMP\nasdaq_xelab_mold64.log"
& 'D:\Xilinx\Vivado\2024.1\bin\xelab.bat' -debug typical tb_mold64_reasm -s tb_mold64 *> $elog
if ($LASTEXITCODE -ne 0) { Write-Host "XELAB FAILED"; Get-Content $elog | Select-String ERROR | Select-Object -First 10; exit 1 }
Write-Host "XELAB OK"
$slog = "$env:TEMP\nasdaq_xsim_mold64_v3.log"
& 'D:\Xilinx\Vivado\2024.1\bin\xsim.bat' tb_mold64 -runall *> $slog
$sim = Get-Content $slog -Raw
if ($sim -match 'TB-ALL-PASS') { Write-Host "mold64 TB-ALL-PASS" } else { Write-Host "mold64 TB FAIL"; Get-Content $slog | Select-String 'FAIL|PASS|TB-|finish' | Select-Object -First 20; exit 1 }
