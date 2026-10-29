#!/bin/bash
# Replay each session-byte variant and print what the reassembler reports.
#
# err counts rescan retries, a direct function of which session comparison failed. A variant whose
# err differs from the others identifies the broken term.
cd /home/xilinx/overlays/nasdaq || exit 1
PY="sudo -n env XILINX_XRT=/usr /usr/local/share/pynq-venv/bin/python"
for v in correct flip0 flip1 flip2 flip3 flip4 flip5 flip6 flip7; do
  printf "%-9s " "$v"
  $PY load_overlay.py --book --input "/home/xilinx/_sess_$v.mold64" --repeat 1 --no-golden 2>&1 \
      | grep -o 'M64-STATS:.*' | head -1
done
