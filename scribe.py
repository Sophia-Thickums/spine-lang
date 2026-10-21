#!/usr/bin/env python3
"""scribe.py — write the facts that are not files, so a state line can read them.

WHY THIS EXISTS. §OBS reads a FILE and nothing else, on purpose: a state file that can execute code is
a liability the moment somebody else may write one. But some of the things that are true about this
machine are not exposed as files at all — Ollama's GPU pin lives in a service unit's environment and in
the running process, not in sysfs. Those facts still need a surface, so this writer creates one:

    /run/user/1000/spine/ollama.pin        GGML_VK_VISIBLE_DEVICES, as the running process actually has it
    /run/user/1000/spine/ollama.resident   the models currently held in memory, or "none"

The split matters: the SCRIBE may run commands; the STATE FILE may only read. A stranger can review
this file once and know every command the perception layer is capable of running. Put the other way
round — commands inside the data file — and nobody can audit it at all.

Run it on a timer (or from the watch loop). When it stops running, the facts it owns go UNREADABLE,
which is the honest verdict and not a stale pass.

    python3 scribe.py            # write the current facts
    python3 scribe.py --print    # show what would be written, write nothing
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

OUT = Path(os.environ.get("SPINE_SCRIBE_DIR", "/run/user/1000/spine"))


def sh(cmd, timeout=10):
    """Run a command and return stdout, or None when it fails. None is never laundered into ''."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout


def facts():
    """Every fact this writer owns, as (name, value-or-None)."""
    out = []

    # The pin as the RUNNING process has it, falling back to the unit's declared environment.
    # The process's own environ is the surface that owns the claim; the unit only says what was intended.
    pin = None
    pid = sh("systemctl show ollama -p MainPID --value")
    if pid and pid.strip().isdigit() and pid.strip() != "0":
        env = sh(f"cat /proc/{pid.strip()}/environ")
        if env:
            for kv in env.split("\0"):
                if kv.startswith("GGML_VK_VISIBLE_DEVICES="):
                    pin = kv.split("=", 1)[1]
    if pin is None:
        unit = sh("systemctl show ollama -p Environment --value")
        if unit:
            for tok in unit.split():
                if tok.startswith("GGML_VK_VISIBLE_DEVICES="):
                    pin = tok.split("=", 1)[1]
    out.append(("ollama.pin", pin))

    # What is resident right now. "none" is a real answer; empty output is not.
    ps = sh("ollama ps")
    if ps is None:
        out.append(("ollama.resident", None))
    else:
        rows = [l.split()[0] for l in ps.strip().splitlines()[1:] if l.strip()]
        out.append(("ollama.resident", ",".join(rows) if rows else "none"))

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", dest="show", action="store_true", help="print, do not write")
    a = ap.parse_args()

    ok = True
    for name, value in facts():
        if value is None:
            # Do NOT write a placeholder. An unwritten fact stays missing, and the state line that
            # reads it says UNREADABLE — which is true. A written "unknown" would read as a value.
            print(f"skip    {name}: no surface available (state line will read UNREADABLE)")
            ok = False
            continue
        target = OUT / name
        if a.show:
            print(f"would   {name} = {value}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value + "\n", encoding="utf-8")
        print(f"wrote   {name} = {value}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
