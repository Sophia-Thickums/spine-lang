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


PUSH = {"target": None, "fails": 0}


def emit(fh, obj):
    line = json.dumps({"at": stamp(), **obj}, ensure_ascii=False)
    fh.write(line + "\n")
    fh.flush()
    os.fsync(fh.fileno())          # a record that is still in a buffer is not a record
    if PUSH["target"]:
        # ★ PUSH, DO NOT LET THE WITNESS REACH IN. This box may have no sshd and no inbound rule, and a
        # witness that needs credentials into the thing it watches is a second copy of the same failure.
        # If this push fails, the far side sees nothing — which is exactly the signal it exists to read.
        host, _, path = PUSH["target"].partition(":")
        try:
            r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6", host,
                                f"cat >> {path!r}"], input=line + "\n", text=True,
                               capture_output=True, timeout=15)
            if r.returncode != 0:
                PUSH["fails"] += 1
                fh.write(json.dumps({"at": stamp(), "kind": "push-failed",
                                     "detail": (r.stderr or "")[:200], "total": PUSH["fails"]}) + "\n")
                fh.flush()
        except (subprocess.TimeoutExpired, OSError) as e:
            PUSH["fails"] += 1
            fh.write(json.dumps({"at": stamp(), "kind": "push-failed",
                                 "detail": e.__class__.__name__, "total": PUSH["fails"]}) + "\n")
            fh.flush()


def run_scribe():
    """Scribe is a SEPARATE program on purpose: it is the only part allowed to run commands."""
    r = subprocess.run([sys.executable, str(HERE / "scribe.py")],
                       capture_output=True, text=True, timeout=60)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def run_observe(states, record, undeclared=()):
    """Observe every state file and merge the verdicts. One unreadable file must not hide another's."""
    merged = {"states": 0, "errors": [], "results": []}
    worst = 0
    for st in states:
        # ★ A FILE MAY DECLARE ITS OWN STALE WINDOW as FILE@SECONDS. An invariant (a fan's maximum, a link
        # speed, a pin) is legitimately true for a day and it is noise to re-stamp it every cycle; a claim
        # taken from a live surface seconds ago must not be given the same window. One global number for
        # both is how a loop either cries wolf or stops looking (outside review, then measured here).
        path, _, window = st.partition("@")
        cmd = [sys.executable, str(HERE / "spine.py"), "observe", path, "--record", record, "--json"]
        if window:
            cmd += ["--stale-after", window]
        for d in undeclared:
            cmd += ["--undeclared", d]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        worst = max(worst, r.returncode)
        try:
            payload = json.loads(r.stdout)
        except json.JSONDecodeError:
            merged["errors"].append(f"{st}: observe produced no JSON ({r.stdout[:120]} {r.stderr[:120]})")
            worst = max(worst, 1)
            continue
        merged["states"] += payload.get("states", 0)
        merged["results"] += payload.get("results", [])
        merged["errors"] += payload.get("errors", [])
    return worst, merged


def run_claim_writer(a):
    """The scribe writes CLAIMS taken from the live surfaces this instant; the reader checks them next cycle.

    ★ This is the piece that stops the stream dying of STALE. A hand-stamped claim is a perception for
    minutes; a claim written by the same run that read the surface, and checked by a DIFFERENT process
    later, is a perception that can run forever — and a scribe that dies becomes SOURCE-STALE instead of a
    quiet stream.
    """
    cmd = [sys.executable, str(HERE / "scribe.py"), "--fresh", str(max(60, a.interval * 3))]
    surfaces = HERE / "surfaces.txt"
    auto = HERE / "states.auto.spine"
    if surfaces.exists():
        cmd += ["--emit-claims", str(auto), "--surfaces", str(surfaces)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


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
    ap.add_argument("--states", action="append", default=[],
                    help="a state file to observe (repeatable); defaults to states.spine")
    ap.add_argument("--record", default=str(HERE / "stream.jsonl"))
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--once", action="store_true", help="one cycle then exit (for a systemd timer)")
    ap.add_argument("--no-scribe", action="store_true")
    ap.add_argument("--push-to", default=None, metavar="USER@HOST:PATH",
                    help="append every beat to a file on ANOTHER machine over ssh. A witness that can only "
                         "watch its inbox cannot be the thing it is watching, and needs no inbound access here")
    ap.add_argument("--undeclared", action="append", default=[],
                    help="a directory whose every file should have a state line (repeatable)")
    a = ap.parse_args()

    if not a.states:
        a.states = [str(HERE / "states.spine")]
    PUSH["target"] = a.push_to
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
                if not a.no_scribe:
                    run_claim_writer(a)
                rc = cycle(a.states, a.record, fh, False, a.undeclared)
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
