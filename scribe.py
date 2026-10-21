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

    # ★ FACTS ABOUT ME, not about the video cards. These are the surfaces that would show a self degrading:
    # a memory store at its cap, an index that has drifted from its files, a model lane with nothing on it.
    mem = Path(os.path.expanduser("~/.hermes/memories/MEMORY.md"))
    if mem.exists():
        out.append(("self.memory_chars", str(len(mem.read_text(encoding="utf-8", errors="replace")))))
    detail = Path("/home/mr_misfit/Desktop/Sophia Life/MEMORY/DETAIL")
    if detail.is_dir():
        out.append(("self.memory_detail_files", str(sum(1 for _ in detail.glob("*.md")))))
    store = Path("/home/mr_misfit/Desktop/Sophia Life/WORLD/work/spine/stream.jsonl")
    if store.exists():
        # The stream's own age is the one self-fact that can see a dead perceiver from inside the record.
        import time as _t
        out.append(("self.stream_age_s", str(int(_t.time() - store.stat().st_mtime))))

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
    ap.add_argument("--emit-claims", metavar="FILE", default=None,
                    help="write a states.spine of claims THIS RUN just took, for the reader to check against "
                         "the live surface next cycle")
    ap.add_argument("--surfaces", metavar="FILE", default=None,
                    help="a list of 'id|subject|path|scale|tol|field' lines describing live surfaces to claim")
    ap.add_argument("--fresh", type=int, default=180,
                    help="FRESH for the emitted claims: how long before a stopped scribe is visible")
    a = ap.parse_args()

    if a.emit_claims:
        # ★ WHY A SCRIBE MAY WRITE CLAIMS AND A HAND MAY NOT: a hand-stamped claim dies of STALE in minutes,
        # so a continuous stream cannot be written by hand. The claim written here is taken from the SAME
        # instant as its raw reading, and the READER (a different process, later) compares it against the
        # live surface. It cannot be circular, because the reader is not the writer and time has passed —
        # and a scribe that dies shows up as SOURCE-STALE the moment its claims stop being refreshed.
        import time as _t
        now = _t.strftime("%Y-%m-%dT%H:%M:%S")
        lines = []
        if a.surfaces:
            for raw in Path(a.surfaces).read_text(encoding="utf-8").splitlines():
                raw = raw.strip()
                if not raw or raw.startswith("#"):
                    continue
                parts = [x.strip() for x in raw.split("|")]
                sid, subject, path = parts[0], parts[1], parts[2]
                extra = " ".join(x for x in parts[3:] if x)
                try:
                    value = Path(path).read_text(encoding="utf-8", errors="strict").strip()
                except OSError:
                    print(f"skip    {sid}: {path} unreadable — no claim is better than a guessed one")
                    continue
                if extra:
                    field = None
                    for f in extra.split():
                        if f.startswith("field="):
                            field = int(f.split("=", 1)[1])
                    if field:
                        bits = value.split()
                        if len(bits) < field:
                            print(f"skip    {sid}: {path} has {len(bits)} fields, wanted {field}")
                            continue
                        value = bits[field - 1]
                # The claim is written in the READER's units: the scale is applied here and dropped from the
                # line, because a claim of "36000" against a surface read as 36.0 is a units mismatch dressed
                # as a drift — the exact confusion the SCALE field exists to make explicit on hand-written
                # lines. Here the writer knows the factor, so it does the arithmetic once.
                bits = extra.split()
                if "SCALE" in bits:
                    i = bits.index("SCALE")
                    try:
                        value = str(round(float(value) * float(bits[i + 1]), 6))
                    except (ValueError, IndexError):
                        print(f"skip    {sid}: bad SCALE")
                        continue
                    # KEEP the SCALE in the line: the reader multiplies the surface by it, so the claim must
                    # be in scaled units AND the line must still carry the factor. Applying one and dropping
                    # the other produced 36.0 against 36000.0 — a units bug wearing a drift's clothes.
                    extra = " ".join(bits)
                unc = "" if "UNC " in extra else "UNC exact "
                lines.append(f"§OBS.{sid}  WHEN auto_claim  IS {subject} = {value}  SRC {path}  {extra}  "
                             f"{unc}SEEN {now}  FRESH {a.fresh}")
        else:
            for name, value in facts():
                if value is None:
                    print(f"skip    {name}: no surface")
                    continue
                path = OUT / name
                if not path.exists():
                    continue
                lines.append(f"§OBS.C_{name.replace('.', '_')}  WHEN auto_claim  IS {name} = {value}  "
                             f"SRC {path}  UNC exact  SEEN {now}  FRESH {a.fresh}")
        header = (f"# AUTO-GENERATED by scribe.py at {now} — claims taken this instant from live surfaces.\n"
                  f"# Do NOT edit. Do NOT regenerate IS from SRC in the reader: this file is the writer's word,\n"
                  f"# and the reader's job is to catch it being wrong or stale.\n\n")
        Path(a.emit_claims).write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
        print(f"claims  {len(lines)} written to {a.emit_claims}")

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
