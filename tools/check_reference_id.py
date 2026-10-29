"""Verify the reference-capture test distinguishes the two skip cases.

The fix added _is_reference_capture(path, total_bytes). It must:

  * return True for the real capture, so a wrong message count from it becomes a
    FAILURE rather than a skip;
  * return False for any other file, so a deliberately different input still skips.

Testing the predicate directly is cheap and needs no board or mock overlay. It also
checks the boundary case: a file of the SAME SIZE but different content must not be
mistaken for the reference.
"""
import hashlib
import importlib.util
import io
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tempfile

DRV = r"D:\agent\nasdaq-fpga\board\load_overlay.py"
REF = r"D:\agent\nasdaq-fpga\data\itch_loc6836.mold64"

# --- stub the driver's imports, so the REAL function can be loaded -----------------
# The driver imports numpy, pynq and xrt. None exist on a development host, so a plain
# import fails and the check falls back to its own copy of the predicate - which tests
# nothing about the driver. mock_run.py already builds stand-ins for the same reason; its
# numpy source is reused here so there is ONE definition of the stub, not two.
import tempfile as _tf

def _install_stubs():
    import sys as _sys
    d = _tf.mkdtemp(prefix="refid_stubs_")
    try:
        import mock_run as _mr
        numpy_src = _mr.NUMPY_SRC
    except Exception:
        numpy_src = "uint8 = 'B'\nclass _A:\n    def __init__(self, n):\n        pass\n"
    io.open(os.path.join(d, "numpy.py"), "w", encoding="utf-8").write(numpy_src)
    io.open(os.path.join(d, "pynq.py"), "w", encoding="utf-8").write(
        "class Overlay:\n"
        "    def __init__(self, *a, **k):\n        pass\n"
        "class _D:\n"
        "    def __getattr__(self, n):\n        return lambda *a, **k: None\n"
        "def __getattr__(n):\n    return _D()\n"
        "Device = _D()\n")
    io.open(os.path.join(d, "xrt.py"), "w", encoding="utf-8").write(
        "class _X:\n"
        "    def __getattr__(self, n):\n        return lambda *a, **k: None\n"
        "def __getattr__(n):\n    return _X()\n")
    _sys.path.insert(0, d)
    return d


MOCKPATH = _install_stubs()

spec = importlib.util.spec_from_file_location("drv", DRV)
drv = importlib.util.module_from_spec(spec)
ON_FALLBACK = False
try:
    spec.loader.exec_module(drv)
except Exception as e:
    print("could not import the driver directly (%s)" % type(e).__name__)
    print("REFERENCE-ID-FALLBACK: the driver could not be imported, so the three "
          "cases below test this check's own copy of the predicate, NOT the "
          "driver's function. A PASS here does not certify the driver.")
    ON_FALLBACK = True
    src = io.open(DRV, encoding="utf-8").read()
    import re
    size = int(re.search(r"REFERENCE_CAPTURE_SIZE = (\d+)", src).group(1))
    dig = re.search(r'REFERENCE_HEAD_SHA256_16 = "(\w+)"', src).group(1)

    def _is_reference_capture(path, total_bytes):
        if total_bytes != size:
            return False
        with open(path, "rb") as f:
            head = f.read(1024)
        return hashlib.sha256(head).hexdigest()[:16] == dig
else:
    _is_reference_capture = drv._is_reference_capture

fails = []

# 1. the real capture
size = os.path.getsize(REF)
ok = _is_reference_capture(REF, size)
print("reference capture        : %s" % ("True (correct)" if ok else "False (WRONG)"))
if not ok:
    fails.append("real capture not recognised")

# 2. a smaller file
small = tempfile.NamedTemporaryFile(delete=False, suffix=".mold64")
small.write(b"NASDAQ01" + bytes(100))
small.close()
ok = _is_reference_capture(small.name, os.path.getsize(small.name))
print("a 108-byte file          : %s" % ("False (correct)" if not ok else "True (WRONG)"))
if ok:
    fails.append("small file mistaken for the reference")

# 3. same size, different content - the dangerous case
fake = tempfile.NamedTemporaryFile(delete=False, suffix=".mold64")
fake.write(bytes(size))
fake.close()
ok = _is_reference_capture(fake.name, size)
print("same size, zeroed content: %s" % ("False (correct)" if not ok else "True (WRONG)"))
if ok:
    fails.append("same-size different-content file mistaken for the reference")

for p in (small.name, fake.name):
    os.unlink(p)

print()
if fails:
    print("REFERENCE-ID-FAIL (%d)" % len(fails))
    for f in fails:
        print("  " + f)
    sys.exit(1)
if ON_FALLBACK:
    print("REFERENCE-ID-PASS-UNVERIFIED (copy passed; driver not exercised)")
else:
    print("REFERENCE-ID-PASS")
