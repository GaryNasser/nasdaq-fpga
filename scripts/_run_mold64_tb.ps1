$ErrorActionPreference = 'Stop'
$rtl = Join-Path $PSScriptRoot '..\rtl'
$log = Join-Path $env:TEMP 'nasdaq_xvlog.log'
Push-Location $rtl
Remove-Item -Recurse -Force xsim.dir,.Xil -ErrorAction SilentlyContinue
$xvlog = & 'D:\Xilinx\Vivado\2024.1\bin\xvlog.bat' ctrl_regs.v itch\mold64_reasm.v itch\itch_parse.v itch\order_book.v itch\ts_hist.v itch\tb_mold64_reasm.v itch\tb_itch_parse.v itch\tb_order_book.v itch\tb_ts_hist.v 2>&1
$xvlog | Set-Content $log
if ($LASTEXITCODE -ne 0) { Write-Host "xvlog FAILED"; Pop-Location; exit 1 }
Write-Host "xvlog OK"

# elaborate + run mold64 TB
& 'D:\Xilinx\Vivado\2024.1\bin\xelab.bat' -debug typical tb_mold64_reasm -s tb_mold64 2>&1 | Set-Content (Join-Path $env:TEMP 'nasdaq_xelab.log')
if ($LASTEXITCODE -ne 0) { Write-Host "xelab mold64 FAILED"; Pop-Location; exit 1 }
& 'D:\Xilinx\Vivado\2024.1\bin\xsim.bat' tb_mold64 -runall 2>&1 | Set-Content (Join-Path $env:TEMP 'nasdaq_xsim_mold64.log')
$sim = Get-Content (Join-Path $env:TEMP 'nasdaq_xsim_mold64.log') -Raw
if ($sim -notmatch 'TB-ALL-PASS') { Write-Host "mold64 TB FAIL"; Pop-Location; exit 1 }
Write-Host "mold64 TB-ALL-PASS"
Pop-Location
