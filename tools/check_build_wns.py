"""The WNS line in build.ps1 must read the log of the build that succeeded.

`build.ps1` step 4 reads WNS from `$buildLog`, but the loop may have moved on.

    $finalBuildLog = Join-Path $env:TEMP 'nasdaq_vivado.log'
    while (...) {
        $buildLog = "${buildLogBase}_${attempt}.log"     reassigned each attempt
        ...
        if (success) { Copy-Item $buildLog $finalBuildLog -Force; $done = $true }
    }
    ...
    $m = Get-Content $buildLog | Select-String '^WNS:'    <- which log is this?

On success `$buildLog` still names the successful attempt, so this happens to work. **But the copy to
`$finalBuildLog` says the intent is to use the canonical name**, and the WNS line reads the attempt-specific one.
Two names for one file, used inconsistently - a latent bug, not a live one.

### Also checked

Step 4 asserts only that the bit and hwh exist and are non-empty. **It does not check that they are a matched pair** -
that is `check_bit_repro` and `check_deploy_triple`'s job, and those do run in the suite.

So this audit's question is narrow: **is the WNS the script prints read from the log of the build that produced the
bitstream?**
"""
import io
import os
import re
import sys

REPO = r"D:\agent\nasdaq-fpga"
SCRIPT = os.path.join(REPO, "scripts", "build.ps1")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

src = io.open(SCRIPT, encoding="utf-8", errors="replace").read()
lines = src.split("\n")

print("build.ps1: %d lines" % len(lines))
print()

# Where is $buildLog assigned vs read?
assigned = [(i + 1, l.strip()) for i, l in enumerate(lines)
            if re.search(r"\$buildLog\s*=", l)]
read = [(i + 1, l.strip()) for i, l in enumerate(lines)
        if re.search(r"\$buildLog\b", l) and not re.search(r"\$buildLog\s*=", l)]

print("$buildLog assigned at: %s" % [n for n, _ in assigned])
print("$buildLog read at    : %s" % [n for n, _ in read])
print("$finalBuildLog used at: %s"
      % [i + 1 for i, l in enumerate(lines) if "finalBuildLog" in l])
print()

# Is $buildLog assigned inside the while loop?
loop_start = next((i + 1 for i, l in enumerate(lines) if re.search(r"^\s*while\b", l)), None)
print("while loop starts at L%s" % loop_start)
inside = [n for n, _ in assigned if loop_start and n > loop_start]
outside_reads = [n for n, _ in read if loop_start and n > loop_start]
print("assignments inside the loop: %s" % inside)
print()

# The WNS read after the loop.
wns_line = next(((i + 1, l.strip()) for i, l in enumerate(lines) if "WNS:" in l and "Select-String" in l),
                None)
print("WNS extraction at L%s:" % (wns_line[0] if wns_line else "?"))
print("   " + (wns_line[1][:88] if wns_line else "not found"))

print()
issues = []
if wns_line and "$buildLog" in wns_line[1] and "$finalBuildLog" in src:
    issues.append("the WNS line reads $buildLog (attempt-specific) while the script also maintains "
                  "$finalBuildLog (canonical) - two names, one file, used inconsistently")

# The WNS must come from the canonical log. That is the property; nothing else about the names matters.
if wns_line and "$finalBuildLog" not in wns_line[1]:
    issues.append("the WNS line does not read $finalBuildLog")

print("issues: %d" % len(issues))
for i in issues:
    print("   " + i)

print()
if issues:
    print("BUILD-WNS-FAIL (%d)" % len(issues))
    sys.exit(1)
print("BUILD-WNS-PASS (the WNS line reads the log of the build that succeeded)")
