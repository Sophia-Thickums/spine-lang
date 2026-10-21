#!/usr/bin/env python3
"""witness_gap.py — check the perception stream for gaps from somewhere the perceiver is not.

WHY THIS EXISTS. Every other verdict in this format is emitted by the reader while it runs. If the reader
is never scheduled, crashes before printing, or the machine is off, the stream simply STOPS — and a
stream that stopped looks exactly like a stream that found nothing. That was the last finding of the
outside review (2026-10-21), and it cannot be fixed from inside: the process that would report its own
absence is the process that is absent.

So this runs ELSEWHERE — on the second box, or from a cron on a different scheduler — reads the tail of
the stream, and fails when the newest beat is older than it should be. Its own runs are appended to a
separate witness log, so a silent witness is itself detectable.

    python3 witness_gap.py --stream /path/stream.jsonl --max-age 180
    python3 witness_gap.py --ssh ryan@192.168.0.44 --stream /home/.../stream.jsonl --max-age 180

Exit codes: 0 the stream is current · 1 the stream has stopped or gone quiet · 2 the witness could not look.

★ EXIT 2 IS NOT EXIT 0. "I could not look" and "I looked and it is fine" are the two states this whole
house keeps confusing; a witness that cannot reach the stream must say so and fail.
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def read_tail(path, ssh=None, n=400):
    if ssh:
        cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", ssh,
               f"tail -n {n} {path}"]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        except (subprocess.TimeoutExpired, OSError) as e:
            return None, f"could not reach {ssh}: {e.__class__.__name__}"
        if r.returncode != 0:
            return None, f"remote read failed (exit {r.returncode}): {r.stderr.strip()[:200]}"
        return r.stdout, None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()[-n:]
    except OSError as e:
        return None, f"cannot read {path}: {e.__class__.__name__}"
    return "".join(lines), None


def last_beat(text):
    """Newest heartbeat-shaped record. Per-state lines carry no 'kind' and are skipped on purpose."""
    newest, newest_beat = None, None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "kind" in rec and "at" in rec:
            newest = rec        # the file is append-ordered; the last one wins
            if rec["kind"] == "beat":
                newest_beat = rec
    # Prefer the newest BEAT: a stream that ends with "stop" would otherwise report its own clean shutdown
    # as the last sign of life, which is the opposite of what a witness is for.
    return newest_beat or newest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stream", required=True)
    ap.add_argument("--ssh", default=None, help="read the stream from another machine")
    ap.add_argument("--max-age", type=int, default=180, help="seconds a beat may be old before it fails")
    ap.add_argument("--witness-log", default=None, help="append this witness's own verdicts here")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    text, err = read_tail(a.stream, a.ssh)
    if err:
        # COULD NOT LOOK — and that is never reported as a pass.
        print(f"CANNOT-LOOK  {err}")
        return 2

    rec = last_beat(text or "")
    if rec is None:
        print("NO-BEAT      the stream holds no heartbeat at all — this is not a quiet stream, it is an "
              "unwritten one")
        return 1

    try:
        at = datetime.fromisoformat(rec["at"].replace("Z", "+00:00"))
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
    except (ValueError, KeyError):
        print(f"NO-BEAT      the newest record has an unparseable timestamp: {rec.get('at')!r}")
        return 1

    age = (datetime.now(timezone.utc) - at).total_seconds()
    verdict = "OK" if age <= a.max_age else "GAP"
    detail = {
        "kind": rec.get("kind"), "at": rec.get("at"), "age_s": round(age),
        "max_age_s": a.max_age, "where": a.ssh or "local", "verdict": verdict,
        "last_verdicts": rec.get("verdicts"),
    }

    if a.witness_log:
        with open(a.witness_log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"witness_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                 **detail}, ensure_ascii=False) + "\n")

    if a.json:
        print(json.dumps(detail, indent=2))
    elif verdict == "OK":
        print(f"OK           newest beat {round(age)}s old (limit {a.max_age}s) · {rec.get('verdicts')}")
    else:
        print(f"GAP          the newest beat is {round(age)}s old (limit {a.max_age}s) — the perceiver has "
              f"stopped, and nothing inside it could have said so")
    return 0 if verdict == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
