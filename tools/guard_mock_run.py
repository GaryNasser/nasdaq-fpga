"""Guard mock_run.py's test body so the module can be imported.

mock_run.py runs its 7 cases at module level with no `if __name__` guard, so
importing it - which check_ctrl_sequence.py needs in order to reuse the MMIO/DMA
models - executes the whole suite and then exits.

Wrapping the driver-facing section in a guard makes the models importable while
keeping `python tools/mock_run.py` behaving exactly as before.
"""
import io
import re

PATH = r"D:\agent\nasdaq-fpga\tools\mock_run.py"
src = io.open(PATH, encoding="utf-8").read()

# Find where the case runner begins. It is the first module-level line that
# references CASES after the model definitions.
m = re.search(r"^fails = \[\]", src, re.M)
assert m, "case runner start not found"

head = src[:m.start()]
body = src[m.start():]

# Indent the runner under a guard.
indented = "\n".join(("    " + ln) if ln.strip() else ln
                     for ln in body.split("\n"))

src = head + "if __name__ == '__main__':\n" + indented
io.open(PATH, "w", encoding="utf-8").write(src)
print("case runner wrapped in __name__ guard")
