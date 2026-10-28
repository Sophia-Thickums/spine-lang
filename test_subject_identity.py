#!/usr/bin/env python3
"""test_subject_identity.py — the two SUBJECT defects found 2026-10-28 by reading §OBS.02.

§OBS.02 (gigawatt, 2026-10-21) exists because hwmon numbers are reassigned at probe time: the same
path string named one GPU yesterday and another today, every other field still green. The line that
answers it is `SUBJECT <namespace>:<identity>`.

Two defects, both of the same shape — the field is admitted, then nothing consumes it:

D1  SUBJECT IS PARSED AND VALIDATED AND NEVER READ. `observe_one` does not look at `subject_id`,
    so a line can carry a well-formed subject, read the WRONG object's surface, and return OK.
    The identity was written down and had no effect on any verdict.

D2  THE SUBJECT IS NOT RESOLVED, SO A MOVED PCI ADDRESS IS UNDETECTABLE. `pci:0000:03:00.0` is a
    NAME. Firmware renumbers PCI addresses (this house measured it: reserving a 64 GB MMIO window
    moved two cards by one bus each). The memory law already says the ladder is index < bus address
    < device id, because the bus address is an assignment and the vendor:device id is the silicon.
    So a subject may also be `pciid:1002:6860`, and a line carrying BOTH asserts they name the same
    device — which is exactly the thing that goes red when the address moves.

Each check below is paired with the arm that proves it is not vacuous.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPINE = HERE / "spine.py"

passed = failed = 0


def arm(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"PASS  {name}")
    else:
        failed += 1
        print(f"FAIL  {name}  {detail}")


def run(states_text, env_extra=None, args=()):
    """Write a state file to a temp dir and run `observe` over it. Returns (rc, out)."""
    env = dict(os.environ)
    env.update(env_extra or {})
    with tempfile.TemporaryDirectory() as td:
        s = Path(td) / "states.spine"
        s.write_text(states_text)
        p = subprocess.run([sys.executable, str(SPINE), "observe", str(s), "--json", *args],
                           capture_output=True, text=True, env=env)
        return p.returncode, p.stdout + p.stderr


# ---------------------------------------------------------------- D1: a well-formed subject is inert
def d1_subject_is_read():
    """A line whose SUBJECT cannot be resolved must NOT report OK on a value that agrees.

    The surface says 42 and the claim says 42 — so the comparison alone would be green. The subject
    names a device that does not exist on this box. If the verdict is still OK, the field was
    decoration; the correct answer is UNREADABLE ('could not look at the thing I claimed').
    """
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "sensor"
        f.write_text("42\n")
        os.utime(f, None)
        st = (f"§OBS.t1 WHEN test IS thing = 42 SRC {f} UNC exact SEEN 2026-10-28 "
              f"FRESH 3600 SUBJECT pci:0000:ff:00.0\n")
        rc, out = run(st)
    arm("D1 a bogus SUBJECT cannot return OK",
        '"verdict": "UNREADABLE"' in out and rc == 1, out.strip()[:220])

    # non-vacuity: the identical line with NO subject keeps its old behaviour (OK), so the arm above
    # is measuring the subject and not the whole run.
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "sensor"
        f.write_text("42\n")
        os.utime(f, None)
        st = (f"§OBS.t2 WHEN test IS thing = 42 SRC {f} UNC exact SEEN 2026-10-28 FRESH 3600\n")
        rc, out = run(st)
    arm("D1 control: the same line with no SUBJECT is still OK",
        '"verdict": "OK"' in out and rc == 0, out.strip()[:220])


# ------------------------------------------------- D2: the identity a moved address cannot survive
PCI_DEV_ROOT = Path("/sys/bus/pci/devices")


def _real_pci_pair():
    """A real (bus address, vendor:device) pair from this box, or None when there is no PCI at all."""
    for d in sorted(PCI_DEV_ROOT.glob("0000:*")):
        try:
            dev = (d / "device").read_text().strip().removeprefix("0x")
            ven = (d / "vendor").read_text().strip().removeprefix("0x")
        except OSError:
            continue
        return d.name, f"{ven}:{dev}".lower()
    return None


def d2_address_and_id_must_agree():
    pair = _real_pci_pair()
    if pair is None:
        arm("D2 (skipped: no PCI bus on this host)", False, "cannot test identity resolution here")
        return
    addr, pciid = pair

    # a subject that carries BOTH, and both are true -> the identity resolves, nothing is claimed
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "sensor"
        f.write_text("42\n")
        os.utime(f, None)
        st = (f"§OBS.t3 WHEN test IS thing = 42 SRC {f} UNC exact SEEN 2026-10-28 FRESH 3600 "
              f"SUBJECT pci:{addr} SUBJECT pciid:{pciid}\n")
        rc, out = run(st)
    arm("D2 an address that carries its own device id resolves",
        '"verdict": "OK"' in out, out.strip()[:240])

    # the same line where the id is a DIFFERENT device -> the address moved, and that is the fault
    # §OBS.02 was written for. The value still agrees; the identity does not.
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "sensor"
        f.write_text("42\n")
        os.utime(f, None)
        st = (f"§OBS.t4 WHEN test IS thing = 42 SRC {f} UNC exact SEEN 2026-10-28 FRESH 3600 "
              f"SUBJECT pci:{addr} SUBJECT pciid:1002:0000\n")
        rc, out = run(st)
    arm("D2 a moved address is refused, not reported OK",
        '"verdict": "UNREADABLE"' in out and rc == 1, out.strip()[:240])


if __name__ == "__main__":
    d1_subject_is_read()
    d2_address_and_id_must_agree()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
