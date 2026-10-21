#!/usr/bin/env python3
"""watch.py — run the perception loop: scribe the non-file facts, re-read every state, record the result.

WHY THE HEARTBEAT MATTERS MORE THAN THE READINGS. A stream of observations with holes in it is
indistinguishable from a stream of observations of an unchanged world — both look like "nothing
happened". So every cycle writes a heartbeat whether or not anything changed, and the loop's own
start/stop is recorded as an event. Then a gap is a FACT IN THE RECORD rather than a silence somebody
has to notice. That is the difference between continuity and the appearance of it.

    python3 watch.py --states states.spine --record /path/stream.jsonl --interval 60
    python3 watch.py --states states.spine --once            # a single cycle, for a timer

The record is append-only JSONL: one heartbeat per cycle, one line per state, and gap/start/stop events
with the wall-clock time. Nothing here is allowed to rewrite an earlier line.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def emit(fh, obj):
    fh.write(json.dumps({"at": stamp(), **obj}, ensure_ascii=False) + "\n")
    fh.flush()
    os.fsync(fh.fileno())          # a record that is still in a buffer is not a record


def run_scribe():
    """Scribe is a SEPARATE program on purpose: it is the only part allowed to run commands."""
    r = subprocess.run([sys.executable, str(HERE / "scribe.py")],
                       capture_output=True, text=True, timeout=60)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def run_observe(states, record, undeclared=()):
    cmd = [sys.executable, str(HERE / "spine.py"), "observe", states, "--record", record, "--json"]
    for d in undeclared:
        cmd += ["--undeclared", d]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    try:
        payload = json.loads(r.stdout)
    except json.JSONDecodeError:
        payload = {"states": 0, "errors": [f"observe produced no JSON: {r.stdout[:200]} {r.stderr[:200]}"],
                   "results": []}
    return r.returncode, payload


def cycle(states, record, fh, do_scribe, undeclared=()):
    if do_scribe:
        rc, out = run_scribe()
        if rc != 0:
            emit(fh, {"kind": "scribe-failed", "detail": out.strip()[:400]})
    rc, payload = run_observe(states, record, undeclared)
    counts = {}
    for r in payload.get("results", []):
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    emit(fh, {"kind": "beat", "states": payload.get("states", 0),
              "verdicts": counts, "errors": payload.get("errors", []),
              "ok": rc == 0})
    return rc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", default=str(HERE / "states.spine"))
    ap.add_argument("--record", default=str(HERE / "stream.jsonl"))
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--once", action="store_true", help="one cycle then exit (for a systemd timer)")
    ap.add_argument("--no-scribe", action="store_true")
    ap.add_argument("--undeclared", action="append", default=[],
                    help="a directory whose every file should have a state line (repeatable)")
    a = ap.parse_args()

    Path(a.record).parent.mkdir(parents=True, exist_ok=True)
    with open(a.record, "a", encoding="utf-8") as fh:
        emit(fh, {"kind": "start", "pid": os.getpid(), "interval": a.interval,
                  "states": a.states})
        last = None
        last_mono = None
        try:
            while True:
                now = time.time()
                mono = time.monotonic()
                # ★ A HEARTBEAT IS SELF-ATTESTED (outside review, 2026-10-21): a suspended process writes
                # nothing and notices nothing on wake. Wall clock and monotonic clock diverge across a
                # suspend, so comparing them is the only way this loop can report its own absence.
                if last_mono is not None:
                    wall_gap, mono_gap = now - last, mono - last_mono
                    if wall_gap - mono_gap > 5:
                        emit(fh, {"kind": "suspended", "wall_s": round(wall_gap),
                                  "monotonic_s": round(mono_gap),
                                  "unaccounted_s": round(wall_gap - mono_gap)})
                if last is not None:
                    # The gap is measured and written down, so "no gaps" is a claim the record can test.
                    drift = now - last - (a.interval if not a.once else 0)
                    if drift > max(5, a.interval * 0.5):
                        emit(fh, {"kind": "gap", "seconds": round(drift)})
                rc = cycle(a.states, a.record, fh, not a.no_scribe, a.undeclared)
                last = time.time()
                last_mono = time.monotonic()
                if a.once:
                    emit(fh, {"kind": "stop", "reason": "once", "exit": rc})
                    return rc
                time.sleep(a.interval)
        except KeyboardInterrupt:
            emit(fh, {"kind": "stop", "reason": "interrupted"})
            return 0


if __name__ == "__main__":
    sys.exit(main())
