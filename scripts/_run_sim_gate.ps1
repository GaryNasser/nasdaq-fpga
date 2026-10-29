$ErrorActionPreference = 'Stop'
$rtl = Join-Path $PSScriptRoot '..\rtl'
$log = Join-Path $env:TEMP 'nasdaq_xvlog.log'
Push-Location $rtl
$xvlog = & 'D:\Xilinx\Vivado\2024.1\bin\xvlog.bat' ctrl_regs.v itch\mold64_reasm.v itch\itch_parse.v itch\order_book.v itch\ts_hist.v itch\tb_mold64_reasm.v itch\tb_itch_parse.v itch\tb_order_book.v itch\tb_ts_hist.v 2>&1
$xvlog | Set-Content $log
if ($LASTEXITCODE -ne 0) { Write-Host "xvlog FAILED"; Pop-Location; exit 1 }
Write-Host "xvlog OK"

# elaborate + run mold64 TB
& 'D:\Xilinx\Vivado\2024.1\bin\xelab.bat' -debug typical tb_mold64_reasm -s tb_mold64 2>&1 | Set-Content (Join-Path $env:TEMP 'nasdaq_xelab.log')
if ($LASTEXITCODE -ne 0) { Write-Host "xelab mold64 FAILED"; exit 1 }
& 'D:\Xilinx\Vivado\2024.1\bin\xsim.bat' tb_mold64 -runall 2>&1 | Set-Content (Join-Path $env:TEMP 'nasdaq_xsim_mold64.log')
$sim = Get-Content (Join-Path $env:TEMP 'nasdaq_xsim_mold64.log') -Raw
if ($sim -notmatch 'TB-ALL-PASS') { Write-Host "mold64 TB FAIL"; exit 1 }
Write-Host "mold64 TB-ALL-PASS"

# elaborate + run itch TB
& 'D:\Xilinx\Vivado\2024.1\bin\xelab.bat' -debug typical tb_itch_parse -s tb_itch 2>&1 | Set-Content (Join-Path $env:TEMP 'nasdaq_xelab2.log')
if ($LASTEXITCODE -ne 0) { Write-Host "xelab itch FAILED"; exit 1 }
& 'D:\Xilinx\Vivado\2024.1\bin\xsim.bat' tb_itch -runall 2>&1 | Set-Content (Join-Path $env:TEMP 'nasdaq_xsim_itch.log')
$sim2 = Get-Content (Join-Path $env:TEMP 'nasdaq_xsim_itch.log') -Raw
if ($sim2 -notmatch 'TB-ALL-PASS') { Write-Host "itch TB FAIL"; exit 1 }
Write-Host "itch TB-ALL-PASS"

# elaborate + run order_book TB
& 'D:\Xilinx\Vivado\2024.1\bin\xelab.bat' -debug typical tb_order_book -s tb_order_book 2>&1 | Set-Content (Join-Path $env:TEMP 'nasdaq_xelab3.log')
if ($LASTEXITCODE -ne 0) { Write-Host "xelab order_book FAILED"; exit 1 }
& 'D:\Xilinx\Vivado\2024.1\bin\xsim.bat' tb_order_book -runall 2>&1 | Set-Content (Join-Path $env:TEMP 'nasdaq_xsim_order_book.log')
$sim3 = Get-Content (Join-Path $env:TEMP 'nasdaq_xsim_order_book.log') -Raw
if ($sim3 -notmatch 'TB-ALL-PASS') { Write-Host "order_book TB FAIL"; exit 1 }
Write-Host "order_book TB-ALL-PASS"

# elaborate + run ts_hist TB
& 'D:\Xilinx\Vivado\2024.1\bin\xelab.bat' -debug typical tb_ts_hist -s tb_ts_hist_sim 2>&1 | Set-Content (Join-Path $env:TEMP 'nasdaq_xelab4.log')
if ($LASTEXITCODE -ne 0) { Write-Host "xelab ts_hist FAILED"; exit 1 }
& 'D:\Xilinx\Vivado\2024.1\bin\xsim.bat' tb_ts_hist_sim -runall 2>&1 | Set-Content (Join-Path $env:TEMP 'nasdaq_xsim_ts_hist.log')
$sim4 = Get-Content (Join-Path $env:TEMP 'nasdaq_xsim_ts_hist.log') -Raw
if ($sim4 -notmatch 'TB-ALL-PASS') { Write-Host "ts_hist TB FAIL"; exit 1 }
Write-Host "ts_hist TB-ALL-PASS"

Pop-Location
Write-Host "SIM-GATE-OK"
