import sys
import traceback
import faulthandler
import signal

def dump_stacks(signum, frame):
    print("=== STACK DUMP (signal %d) ===" % signum, flush=True)
    traceback.print_stack(frame, file=sys.stdout)
    sys.stdout.flush()
    raise SystemExit(9)

signal.signal(signal.SIGUSR1, dump_stacks)
faulthandler.register(signal.SIGUSR1, all_threads=True)

sys.argv = ['load_overlay.py'] + sys.argv[1:]
import runpy
runpy.run_path('/home/xilinx/overlays/nasdaq/load_overlay.py', run_name='__main__')
