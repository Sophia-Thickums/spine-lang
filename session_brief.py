#!/usr/bin/env python3
"""session_brief.py — what the loop saw while I was not here.

This is the USE of the perception stream: at the start of a session I read this instead of reconstructing
the last hours from memory. It reports the shape of the gap, not a narrative — how long the loop ran, when
it last spoke, whether it ever went quiet, and what changed and stayed changed.

    python3 session_brief.py [--stream PATH] [--since-hours 24]

Exit codes: 0 the loop is current and nothing is red · 1 the loop is behind or something is red ·
            2 the stream could not be read (which is not "quiet").
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(path):
    out = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stream", default=str(HERE / "stream.jsonl"))
    ap.add_argument("--since-hours", type=float, default=24.0)
    ap.add_argument("--stale-after", type=int, default=180, help="seconds before the loop counts as behind")
    a = ap.parse_args()

    try:
        recs = load(a.stream)
    except OSError as e:
        print(f"CANNOT-LOOK  {a.stream}: {e.__class__.__name__} — this is not a quiet stream")
        return 2
    if not recs:
        print("NO RECORD    the stream is empty — the loop has written nothing, which is not the same as nothing happening")
        return 1

    beats = [r for r in recs if r.get("kind") == "beat"]
    gaps = [r for r in recs if r.get("kind") == "gap"]
    susp = [r for r in recs if r.get("kind") == "suspended"]
    stops = [r for r in recs if r.get("kind") == "stop"]
    starts = [r for r in recs if r.get("kind") == "start"]
    rots = [r for r in recs if r.get("kind") == "rotated"]
    pushes = [r for r in recs if r.get("kind") == "push-failed"]

    now = datetime.now(timezone.utc)
    last = beats[-1] if beats else None
    age = None
    if last:
        at = datetime.fromisoformat(last["at"].replace("Z", "+00:00"))
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        age = (now - at).total_seconds()

    span = ""
    if len(beats) > 1:
        first = datetime.fromisoformat(beats[0]["at"].replace("Z", "+00:00"))
        span = f" over {(now - first).total_seconds() / 3600:.1f} h"

    print(f"loop: {len(beats)} beats{span} · started {len(starts)}x · stopped {len(stops)}x · rotations {len(rots)}")
    if age is None:
        print("no beat has ever been written")
    elif age > a.stale_after:
        print(f"BEHIND: last beat {age:.0f}s ago (limit {a.stale_after}s) — the loop is not running")
    else:
        print(f"current: last beat {age:.0f}s ago · {last.get('states')} states · {last.get('verdicts')}")

    if gaps:
        biggest = max(gaps, key=lambda g: g.get("seconds", 0))
        print(f"gaps: {len(gaps)} recorded, largest {biggest.get('seconds')}s")
    if susp:
        print(f"suspends: {len(susp)} (wall clock ran ahead of monotonic — the machine was asleep)")
    if pushes:
        print(f"push failures: {len(pushes)} — the witness on the other box saw silence for those")

    # What changed and STAYED changed: the newest verdict per subject inside the window.
    cutoff = now.timestamp() - a.since_hours * 3600
    newest = {}
    for r in recs:
        if "kind" in r or "subject" not in r:
            continue
        try:
            at = datetime.fromisoformat(r["at"].replace("Z", "+00:00")).timestamp()
        except (ValueError, KeyError):
            continue
        if at < cutoff:
            continue
        newest[r["subject"]] = r
    red = {k: v for k, v in newest.items() if v.get("verdict") != "OK"}
    print(f"subjects seen in the last {a.since_hours:g} h: {len(newest)} · not OK now: {len(red)}")
    for subj, v in sorted(red.items())[:12]:
        why = v.get("why") or ""
        print(f"  {v['verdict']:<11} {subj:<28} {why[:70]}")

    bad = (age is None or age > a.stale_after) or bool(red)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
