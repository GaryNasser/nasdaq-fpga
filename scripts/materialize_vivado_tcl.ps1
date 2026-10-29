# Force OneDrive to materialize every .tcl under the Vivado install.
# Vivado's Tcl open()/source() intermittently fails on reparse-point (P)
# cloud placeholders; reading content here forces the OS to hydrate them so
# the subsequent Vivado run sees plain local files. No files are modified.
$root = 'D:\Xilinx\Vivado\2024.1'
$total = 0
$errs  = 0
Get-ChildItem $root -Recurse -Filter '*.tcl' -File -ErrorAction SilentlyContinue | ForEach-Object {
    $total++
    try {
        $null = [System.IO.File]::ReadAllText($_.FullName)
    } catch {
        $errs++
    }
}
Write-Host "scanned $total .tcl files under $root, $errs read errors"
