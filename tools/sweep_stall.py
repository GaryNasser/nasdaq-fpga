"""Sweep the stall length to find where mold64_reasm starts losing data.

Established by measurement:

  tb_chain_cmp     stall 1/2/3/8 cycles AFTER tlast  -> PASS (0 mismatches)
  tb_stall_long    stall 200 cycles per message      -> FAIL (1,013,272 mismatches)
  tb_fullchain     real parser                       -> 19139 bytes lost

So there is a threshold between 8 and 200 cycles. Finding it turns "it breaks
under backpressure" into a concrete, testable boundary, and tells us whether the
cause is a counter width, a timeout, or a genuine state-machine dead-end.

Writes a small patch file per stall length and runs each in turn.
"""
import io
import re
import subprocess
import os

TB = r"D:\agent\nasdaq-fpga\tools\tb_stall_long.v"
WORK = os.path.join(os.environ["TEMP"], "nasdaq_realfile")

src = io.open(TB, encoding="utf-8", errors="surrogateescape").read()

results = []
for stall in (8, 16, 32, 48, 64, 96, 128, 160, 200):
    patched = re.sub(r"parameter STALL_CYC\s*=\s*\d+;",
                     "parameter STALL_CYC    = %d;" % stall, src)
    dst = os.path.join(WORK, "tb_sl_%d.v" % stall)
    io.open(dst, "w", encoding="utf-8", errors="surrogateescape",
            newline="\n").write(patched)

    subprocess.run(["xvlog.bat", r"D:\agent\nasdaq-fpga\rtl\itch\mold64_reasm.v",
                    "tb_sl_%d.v" % stall],
                   cwd=WORK, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   shell=True)
    subprocess.run(["xelab.bat", "-debug", "typical", "tb_stall_long",
                    "-s", "tb_stall_long"],
                   cwd=WORK, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   shell=True)
    r = subprocess.run(["xsim.bat", "tb_stall_long", "-runall"],
                       cwd=WORK, capture_output=True, text=True, shell=True)
    line = [l.strip() for l in r.stdout.splitlines() if "STALLLONG before" in l]
    verdict = [l.strip() for l in r.stdout.splitlines() if "STALLLONG-PASS" in l
               or "STALLLONG-FAIL" in l]
    info = line[0] if line else "(no output)"
    v = verdict[0] if verdict else "?"
    # Pull the key numbers out.
    m = re.search(r"out=(\d+) exp=(\d+) mism=(\d+) tlast=(\d+) m64_pkts=(\d+) m64_msgs=(\d+) gap=(\d+) err=(\d+)", info)
    if m:
        out_b, exp_b, mism, tl, pk, ms, gap, err = m.groups()
        results.append((stall, int(out_b), int(mism), int(pk), int(gap), int(err), v))
        print("stall=%-4d out=%-8s mism=%-8s pkts=%-4s gap=%-2s err=%-5s %s"
              % (stall, out_b, mism, pk, gap, err, v))
    else:
        print("stall=%-4d %s %s" % (stall, v, info))

print()
first_fail = next((r for r in results if r[6] == "STALLLONG-FAIL"), None)
last_ok = None
for r in results:
    if r[6] == "STALLLONG-PASS":
        last_ok = r
print("last passing stall : %s cycles" % (last_ok[0] if last_ok else "none"))
print("first failing stall: %s cycles" % (first_fail[0] if first_fail else "none"))
