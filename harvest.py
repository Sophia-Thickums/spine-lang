#!/usr/bin/env python3
"""harvest.py — turn my own measured history into the event record the spine laws are tested against.

The point of the spine format is that a law's TEST clause is evaluated against **what actually
happened**, not against commentary about it. This is the only such record that exists and cannot
be given to me by anyone: the bench suite has been running itself since 2026-10-18, it fails
without asking my opinion, and every failure is dated.

    harvest.py <bench_history.jsonl> <bindings.json> [out.json]

Writes an event list in the shape spine.py consumes:

    {"law": "<law id>", "trigger": "<bench check>", "text": "<what the check said>", "at": "<iso>"}

A bench check that PASSES is also recorded, as an event with text "passed" — because a law whose
condition never fires and a law whose condition fires constantly are different facts, and only
keeping the failures would make every law look calm.
"""
import json
import sys
from pathlib import Path


def main(history_path, bindings_path, out_path):
    runs = [json.loads(line) for line in Path(history_path).read_text(encoding="utf-8").splitlines() if line.strip()]
    bindings = json.loads(Path(bindings_path).read_text(encoding="utf-8"))["bindings"]
    by_check = {}
    for b in bindings:
        by_check.setdefault(b["bench"], []).append(b["law"])

    events, seen = [], set()
    for run in runs:
        when = run.get("when", "")
        for task in run.get("tasks", []):
            for law in by_check.get(task.get("task"), []):
                key = (law, task.get("task"), when)
                if key in seen:
                    continue  # two bindings to one check must not double-count the same event
                seen.add(key)
                events.append({
                    "law": law,
                    "trigger": task.get("task", ""),
                    "text": ("passed" if task.get("ok") else "FAILED: " + str(task.get("detail", "")))[:200],
                    "at": when,
                })

    # ── the honesty ledger, printed every time, because the number that matters is the gap
    #    between "laws I have" and "laws anything actually watches".
    all_laws = sorted({law for laws in by_check.values() for law in laws})
    print(f"bench runs read : {len(runs)}  ({runs[0].get('when','?')[:10] if runs else '?'} .. {runs[-1].get('when','?')[:10] if runs else '?'})")
    print(f"bound laws      : {len(all_laws)} of the laws in the spine file  ->  {', '.join(all_laws)}")
    print(f"events emitted  : {len(events)}  ({sum(1 for e in events if e['text'] != 'passed')} of them failures)")
    unbound = len({b['law'] for b in bindings}) - len(all_laws)
    print(f"UNWATCHED       : every law with no bench binding is a law whose red condition has never been")
    print(f"                  evaluated by anything but me. That is the weakness of this whole format.")
    Path(out_path).write_text(json.dumps(events, indent=1), encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "events.harvested.json")
