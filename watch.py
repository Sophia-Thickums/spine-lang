#!/usr/bin/env python3
"""watch.py — run the perception loop: write claims from live surfaces, re-read them, record everything.

WHY THE HEARTBEAT MATTERS MORE THAN THE READINGS. A stream with holes in it is indistinguishable from a
stream taken while nothing changed — both look like "nothing happened". So every cycle writes a beat
whether or not anything moved, the loop records its own gaps, and it notices a suspend by comparing wall
clock against monotonic clock. Then "no gaps" is a claim the record can test instead of a feeling.

WHY THE SCRIBE WRITES CLAIMS. A hand-stamped claim is a perception for minutes; re-stamping by hand is
narration. The scribe takes a reading and writes the claim from that same instant; the reader — a
different process, a cycle later — compares it against the live surface. Not circular, because the writer
is not the reader and time has passed. A dead writer becomes SOURCE-STALE; a moved world becomes DRIFT.

WHY ROTATION IS NOT OPTIONAL. Measured 2026-10-21: 0.41 MB/hour, ~10 MB/day, ~3.5 GB/year, unbounded. The
first rotation held one append handle for the process lifetime and swapped the inode underneath it, so
every later line — including the "rotated" event itself — went to an unlinked file and the stream looked
frozen at exactly the keep-line count. Hence: every write opens the path.

WHY THE PUSH IS A PUSH. The perceiver cannot report its own absence; a witness on the same box dies with
it. So each record goes over ssh to another machine, and a failed push IS the far side seeing nothing.
Push rather than pull, so the watched box needs no sshd, no inbound rule and no credentials into the thing
being watched.

    python3 watch.py --states states.spine@86400 --states states.auto.spine@300 \
                     --record stream.jsonl --interval 30 \
                     --push-to user@otherhost:/path/beats.jsonl
    python3 watch.py ... --once        # one cycle, for a systemd timer
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
PUSH = {"target": None, "fails": 0}

# A loop that runs forever must cap what it writes. Both ends: this stream and the far side's inbox.
MAX_BYTES = int(os.environ.get("SPINE_MAX_BYTES", 8 * 1024 * 1024))
KEEP_LINES = int(os.environ.get("SPINE_KEEP_LINES", 20000))


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rotate(path):
    """Keep the last KEEP_LINES. Called only when the file is over MAX_BYTES; atomic for readers."""
    p = Path(path)
    try:
        if p.stat().st_size < MAX_BYTES:
            return False
    except OSError:
        return False
    tmp = p.with_name(p.name + ".rot")
    with open(p, "r", encoding="utf-8", errors="replace") as src:
        lines = src.readlines()[-KEEP_LINES:]
    with open(tmp, "w", encoding="utf-8") as out:
        out.writelines(lines)
    tmp.replace(p)
    return True


def emit(rec_path, obj):
    """Write one record, then push it if a witness is configured.

    ★ THE PATH IS OPENED PER WRITE, so a rotation can never leave us holding a corpse.
    """
    line = json.dumps({"at": stamp(), **obj}, ensure_ascii=False)
    with open(rec_path, "a", encoding="utf-8") as h:
        h.write(line + "\n")
        h.flush()
        os.fsync(h.fileno())      # a record still sitting in a buffer is not a record

    if not PUSH["target"]:
        return
    host, _, path = PUSH["target"].partition(":")
    # The far side caps its own inbox in the same breath, so a witness's file cannot grow forever either.
    remote = (f"cat >> {path!r}; "
              f"if [ $(stat -c%s {path!r}) -gt {MAX_BYTES} ]; then "
              f"tail -n {KEEP_LINES} {path!r} > {path!r}.rot && mv {path!r}.rot {path!r}; fi")
    try:
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=6", host, remote],
                           input=line + "\n", text=True, capture_output=True, timeout=20)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or "push failed")[:200])
    except (subprocess.TimeoutExpired, OSError, RuntimeError) as e:
        PUSH["fails"] += 1
        with open(rec_path, "a", encoding="utf-8") as h:
            h.write(json.dumps({"at": stamp(), "kind": "push-failed", "detail": str(e)[:200],
                                "total": PUSH["fails"]}) + "\n")
            h.flush()


def run_scribe():
    """The scribe is a separate program on purpose: it is the only part allowed to run commands."""
    r = subprocess.run([sys.executable, str(HERE / "scribe.py")],
                       capture_output=True, text=True, timeout=90)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def run_claim_writer(interval):
    """The writer takes the reading and writes the claim from that instant; the reader checks it later."""
    cmd = [sys.executable, str(HERE / "scribe.py"), "--fresh", str(max(60, int(interval) * 3))]
    surfaces, auto = HERE / "surfaces.txt", HERE / "states.auto.spine"
    if surfaces.exists():
        cmd += ["--emit-claims", str(auto), "--surfaces", str(surfaces)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def run_observe(states, record, undeclared=()):
    """Observe every state file and merge the verdicts. One unreadable file must not hide another's."""
    merged = {"states": 0, "errors": [], "results": []}
    worst = 0
    for spec in states:
        # A file may declare its own stale window as FILE@SECONDS: an invariant is legitimately true for a
        # day, and a claim taken seconds ago must not share that window.
        path, _, window = str(spec).partition("@")
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
            merged["errors"].append(f"{path}: observe produced no JSON ({r.stdout[:120]} {r.stderr[:120]})")
            worst = max(worst, 1)
            continue
        merged["states"] += payload.get("states", 0)
        merged["results"] += payload.get("results", [])
        merged["errors"] += payload.get("errors", [])
    return worst, merged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", action="append", default=[],
                    help="a state file to observe, optionally FILE@SECONDS (repeatable)")
    ap.add_argument("--record", default=str(HERE / "stream.jsonl"))
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--once", action="store_true", help="one cycle then exit (for a systemd timer)")
    ap.add_argument("--no-scribe", action="store_true", help="skip writing claims this cycle")
    ap.add_argument("--push-to", default=None, metavar="USER@HOST:PATH",
                    help="append every record to a file on another machine over ssh")
    ap.add_argument("--undeclared", action="append", default=[],
                    help="a directory whose every file should have a state line (repeatable)")
    a = ap.parse_args()

    if not a.states:
        a.states = [str(HERE / "states.spine")]
    PUSH["target"] = a.push_to
    Path(a.record).parent.mkdir(parents=True, exist_ok=True)

    emit(a.record, {"kind": "start", "pid": os.getpid(), "interval": a.interval, "states": a.states})
    last_wall = last_mono = None
    try:
        while True:
            now, mono = time.time(), time.monotonic()

            if last_mono is not None:
                wall_gap, mono_gap = now - last_wall, mono - last_mono
                # A suspended process writes nothing and notices nothing on wake; wall and monotonic clocks
                # diverge across a suspend, and that divergence is the only evidence this loop can give.
                if wall_gap - mono_gap > 5:
                    emit(a.record, {"kind": "suspended", "wall_s": round(wall_gap),
                                    "monotonic_s": round(mono_gap),
                                    "unaccounted_s": round(wall_gap - mono_gap)})
                # The gap is measured and written, so "no gaps" is a claim the record can test.
                if not a.once and wall_gap > a.interval + max(5, a.interval * 0.5):
                    emit(a.record, {"kind": "gap", "seconds": round(wall_gap - a.interval)})

            if rotate(a.record):
                emit(a.record, {"kind": "rotated", "keep_lines": KEEP_LINES})

            if not a.no_scribe:
                writer = run_claim_writer if (HERE / "surfaces.txt").exists() else run_scribe
                rc_s, out_s = writer(a.interval) if writer is run_claim_writer else writer()
                if rc_s != 0:
                    emit(a.record, {"kind": "scribe-failed", "detail": out_s.strip()[:400]})

            rc, payload = run_observe(a.states, a.record, a.undeclared)
            counts = {}
            for r in payload.get("results", []):
                counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
            emit(a.record, {"kind": "beat", "states": payload.get("states", 0), "verdicts": counts,
                            "errors": payload.get("errors", []), "ok": rc == 0})

            last_wall, last_mono = time.time(), time.monotonic()
            if a.once:
                emit(a.record, {"kind": "stop", "reason": "once", "exit": rc})
                return rc
            time.sleep(a.interval)
    except KeyboardInterrupt:
        emit(a.record, {"kind": "stop", "reason": "interrupted"})
        return 0


if __name__ == "__main__":
    sys.exit(main())
