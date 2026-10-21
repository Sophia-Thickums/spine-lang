#!/usr/bin/env python3
"""spine.py — a tiny compiler for law files written as tests instead of sentences.

A law is five fields on one logical line:

    §ID  WHEN <trigger>  DO <obligation>  NOT <prohibition>  COST <date:scar>  TEST <predicate> ; <predicate>

`TEST` clauses are the point. Each is a predicate over a RECORD of events:

    violation("<id>", "<pattern>", when="<substring of trigger>")

which is TRUE when an event's text matches <pattern> and that event must therefore
be counted as this law firing. The law PASSES only if, for every recorded event,
the expectation and the observation agree.

Usage:
    spine.py check   <laws.spine> <record.json>     # run every TEST, exit 1 if any go red
    spine.py lint    <laws.spine> <record.json>     # would this draft break a law?
    spine.py prove   <laws.spine> <plants.json>     # can each law fire at all?
    spine.py observe <states.spine> [--record f] [--stale-after s] [--json]
                                                    # re-read every SRC and compare to IS
    spine.py list    <laws.spine>                   # ids, sizes, and whether each has a TEST
    spine.py stats   <laws.spine> <prose.md>        # chars-per-law, before and after

THE DESCRIPTIVE HALF (§OBS, added 2026-10-21) — a law file says what to DO; a state file says what IS:

    §OBS.<id>  WHEN <scope>  IS <subject> = <value>  SRC <file>  UNC <exact|bounded|inferred>  SEEN <date> [TOL <n>]

An §OBS line is a PERCEPTION, and it earns that word by holding four things at once:
  · it names the SURFACE that owns the fact (SRC), not my memory of the fact;
  · it states how sure it is (UNC), so `inferred` can never pass silently as `exact`;
  · it says when it was true (SEEN), because a reading with no time is a memory wearing a sight's clothes;
  · re-reading the source either AGREES or the line goes red. DRIFT, STALE and UNREADABLE all fail —
    the last one especially: a source that cannot be read is not a source that agrees.

SRC is a FILE PATH, never a command. A state file that can execute code is a liability the moment
someone else can write one, and a shared format is only shared if a stranger may write one.

Exit codes: 0 all green · 1 something went red · 2 the file itself is malformed.
"""
import json
import os
import re
import sys
from pathlib import Path

FIELD_RE = re.compile(
    r"^§(?P<id>\S+)\s+"
    r"WHEN\s+(?P<when>.+?)\s+"
    r"DO\s+(?P<do>.+?)\s+"
    r"NOT\s+(?P<not>.+?)\s+"
    r"COST\s+(?P<cost>\S+)\s+"
    r"TEST\s+(?P<test>.+)$"
)

# §OBS.<id>  WHEN <scope>  IS <subject> = <value>  SRC <file>  UNC <...>  SEEN <date> [TOL <n>]
OBS_RE = re.compile(
    r"^§OBS\.(?P<id>\S+)\s+"
    r"WHEN\s+(?P<when>.+?)\s+"
    r"IS\s+(?P<claim>.+?)\s+"
    r"SRC\s+(?P<src>\S+)\s+"
    r"UNC\s+(?P<unc>\S+)"
    r"(?:\s+SEEN\s+(?P<seen>\S+))?"
    r"(?:\s+SCALE\s+(?P<scale>-?[0-9.eE+]+))?"
    r"(?:\s+TOL\s+(?P<tol>-?[0-9.]+))?\s*$"
)
CLAIM_RE = re.compile(r"^(?P<subject>.+?)\s*=\s*(?P<value>.+)$")
UNC_VALUES = {"exact", "bounded", "inferred"}


def parse_obs(text):
    """Parse §OBS lines. A state without SRC, UNC or SEEN is malformed, never soft.

    The three refusals here are the format's whole character:
      · no SRC   -> the claim rests on my memory, which is what the format exists to stop;
      · no UNC   -> `inferred` would pass as `exact` the first time nobody looked;
      · no SEEN  -> a reading with no time can be re-read as though it were current forever.

    Fields after IS are parsed BY NAME, in any order, because a rigid order turns a typo into a
    mysterious "not a state" and a rigid order is not a property of the meaning. §OBS.<id> and WHEN
    stay positional: they are what makes the line a state at all.
    """
    states, errors = [], []
    head = re.compile(r"^§OBS\.(?P<id>\S+)\s+WHEN\s+(?P<when>.+?)\s+IS\s+(?P<rest>.+)$")
    marker = re.compile(r"\s+(?=(?:SRC|UNC|SEEN|SCALE|TOL)\s)")
    fields = {"SRC", "UNC", "SEEN", "SCALE", "TOL"}

    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = head.match(line)
        if not m:
            errors.append(f"line {n}: not a state (needs §OBS.<id> WHEN <scope> IS <subject> = <value> ...): {line[:90]}")
            continue
        d = m.groupdict()
        parts = marker.split(d.pop("rest"))
        claim = parts[0].strip()
        got = {}
        for part in parts[1:]:
            k, _, v = part.strip().partition(" ")
            k = k.upper()
            if k not in fields:
                errors.append(f"line {n}: §OBS.{d['id']} has unknown field {k!r}")
                continue
            got[k] = v.strip()
        c = CLAIM_RE.match(claim)
        if not c:
            errors.append(f"line {n}: §OBS.{d['id']} has an IS field that is not 'subject = value'")
            continue
        d["subject"] = c.group("subject").strip()
        d["value_raw"] = c.group("value").strip()
        d["src"] = got.get("SRC", "")
        d["unc"] = got.get("UNC", "")
        d["seen"] = got.get("SEEN", "")
        try:
            d["scale"] = float(got["SCALE"]) if "SCALE" in got else 1.0
            d["tol"] = float(got["TOL"]) if "TOL" in got else 0.0
        except ValueError:
            errors.append(f"line {n}: §OBS.{d['id']} SCALE/TOL must be numbers")
            continue
        if d["unc"] not in UNC_VALUES:
            errors.append(f"line {n}: §OBS.{d['id']} UNC must be one of {sorted('exact','bounded')}, got {d['unc']!r}")
            continue
        # ★ UNC WAS A LABEL THAT CHANGED NO VERDICT (outside review, 2026-10-21). Three refusals make it mean
        # something, and the third one is honest rather than clever: derivation is not implemented, so a
        # claim that says it was derived has no surface to be checked against and is refused outright.
        if d["unc"] == "inferred":
            errors.append(f"line {n}: §OBS.{d['id']} UNC inferred is NOT IMPLEMENTED — name the surface the "
                          f"value came from, or do not claim it")
            continue
        if d["unc"] == "exact" and "TOL" in got:
            errors.append(f"line {n}: §OBS.{d['id']} is UNC exact and carries TOL — exact means a point, "
                          f"bounded means a band; pick one")
            continue
        if d["unc"] == "bounded" and "TOL" not in got:
            errors.append(f"line {n}: §OBS.{d['id']} is UNC bounded with no TOL — a band with no width is a point "
                          f"claim wearing a band's word")
            continue
        if not d["seen"]:
            errors.append(f"line {n}: §OBS.{d['id']} has no SEEN — an undated reading is a memory")
            continue
        if not d["src"].startswith("/"):
            errors.append(f"line {n}: §OBS.{d['id']} SRC must be an absolute file path, got {d['src']!r}")
            continue
        d["chars"] = len(raw.rstrip())
        states.append(d)
    return states, errors


def _norm(v):
    return re.sub(r"\s+", " ", str(v)).strip()


def _as_num(v):
    try:
        return float(_norm(v).rstrip("C%").strip())
    except ValueError:
        return None


def _read_source(path):
    """Read the surface that owns the fact. Returns (value, None) or (None, why-not)."""
    try:
        with open(path, "r", encoding="utf-8", errors="strict") as fh:
            raw = fh.read(4096)
    except FileNotFoundError:
        return None, "missing"
    except PermissionError:
        return None, "unreadable (permission)"
    except OSError as e:
        return None, f"unreadable ({e.__class__.__name__})"
    val = _norm(raw)
    if val == "":
        return None, "empty (a source that returns nothing has not agreed with anything)"
    return val, None


def _age_seconds(seen):
    """SEEN is a date (YYYY-MM-DD) or an ISO timestamp. Unknown shapes are an error, not a guess."""
    from datetime import datetime, timezone
    s = seen.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            if fmt == "%Y-%m-%d":
                dt = dt.replace(hour=23, minute=59, second=59)  # a date is true through its last second
            return (datetime.now() - dt).total_seconds(), None
        except ValueError:
            continue
    return None, f"SEEN {seen!r} is not a date or ISO timestamp"


def _source_is_live(path):
    """Live surfaces are regenerated by the kernel on every read; written ones are a scribe's output.

    ★ THE DISTINCTION IS THE POINT (outside review, 2026-10-21): a claim's age was checked but the
    SOURCE's age was not, so a scribe that dies leaves its last file behind and `observe` reads a frozen
    value, agrees with it, and returns OK — a dead sense reporting health forever.
    """
    return path.startswith("/sys/") or path.startswith("/proc/")


def _source_age(path):
    try:
        import time as _t
        return _t.time() - os.stat(path).st_mtime
    except OSError:
        return None


def observe_one(st, stale_after):
    """One state line, re-checked against its own source. Returns a dict; 'verdict' is the answer."""
    age, age_err = _age_seconds(st["seen"])
    observed, why = _read_source(st["src"])
    rec = {
        "id": st["id"], "subject": st["subject"], "claimed": st["value_raw"],
        "observed": observed, "src": st["src"], "unc": st["unc"], "seen": st["seen"],
        "age_s": None if age is None else round(age),
    }
    if age_err:
        rec["verdict"], rec["why"] = "MALFORMED", age_err
        return rec
    rec["age_s"] = round(age)
    if age > stale_after:
        rec["verdict"] = "STALE"
        rec["why"] = f"last seen {rec['age_s']}s ago, threshold {stale_after}s — a memory, not a sight"
        return rec
    if why:
        # UNREADABLE is a FAILURE, never a pass. This is the bug class this whole house keeps paying for:
        # a source that cannot be read looks identical to a source that agrees, unless you refuse it.
        rec["verdict"], rec["why"] = "UNREADABLE", why
        return rec
    # A WRITTEN surface must prove it was rewritten recently. Otherwise a frozen file agrees with anything.
    if not _source_is_live(st["src"]):
        src_age = _source_age(st["src"])
        rec["src_age_s"] = None if src_age is None else round(src_age)
        if src_age is None:
            rec["verdict"], rec["why"] = "UNREADABLE", "cannot stat the source to prove it is current"
            return rec
        if src_age > stale_after:
            rec["verdict"] = "SOURCE-STALE"
            rec["why"] = (f"the surface has not been rewritten in {round(src_age)}s (limit {stale_after}s) — "
                          f"a frozen file agrees with anything")
            return rec

    def agrees(obs):
        av, bv = _as_num(st["value_raw"]), _as_num(obs)
        if av is not None and bv is not None:
            return abs(av - bv * st.get("scale", 1.0)) <= st["tol"], bv * st.get("scale", 1.0)
        return _norm(st["value_raw"]).casefold() == _norm(obs).casefold(), None

    agree, scaled = agrees(observed)
    if scaled is not None:
        rec["observed_scaled"] = round(scaled, 6)
    if not agree:
        # ★ A READ IS NOT ATOMIC (outside review, 2026-10-21): a sysfs read or a scribe write can be caught
        # mid-write, and a truncated value then reads as a real drift. Confirm before calling it.
        again, _ = _read_source(st["src"])
        if again is not None and again != observed:
            rec["verdict"] = "FLAKY"
            rec["why"] = f"two reads of the same surface disagreed ({observed!r} then {again!r}) — not a drift"
            return rec
    if agree:
        rec["verdict"], rec["why"] = "OK", ""
    else:
        # Show the value in the CLAIM's units, not the surface's. Reporting "39.0 -> 38000" for a
        # temperature is a true statement that reads as nonsense, and nonsense is how a real drift
        # gets dismissed as a format bug.
        shown = rec.get("observed_scaled", observed)
        rec["verdict"], rec["why"] = "DRIFT", f"{st['value_raw']} -> {shown}"
    return rec


def cmd_observe(argv):
    """Re-read every SRC and compare against IS. This is the verb that makes a state file a perception."""
    path, stale_after, record_path, as_json = None, 900, None, False
    undeclared_dirs = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--json":
            as_json = True
        elif a == "--record":
            i += 1
            if i >= len(argv):
                print("--record needs a path")
                return 2
            record_path = argv[i]
        elif a.startswith("--record="):
            record_path = a.split("=", 1)[1]
        elif a == "--stale-after":
            i += 1
            if i >= len(argv):
                print("--stale-after needs a number of seconds")
                return 2
            stale_after = int(argv[i])
        elif a.startswith("--stale-after="):
            stale_after = int(a.split("=", 1)[1])
        elif a == "--undeclared":
            i += 1
            if i >= len(argv):
                print("--undeclared needs a directory")
                return 2
            undeclared_dirs.append(argv[i])
        elif a.startswith("--"):
            print(f"unknown option {a}")
            return 2
        else:
            path = a
        i += 1
    if path is None:
        print(__doc__)
        return 2

    states, errors = parse_obs(Path(path).read_text(encoding="utf-8"))
    results = [observe_one(s, stale_after) for s in states]

    if record_path:
        from datetime import datetime, timezone
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with open(record_path, "a", encoding="utf-8") as fh:
            for r in results:
                fh.write(json.dumps({"at": stamp, **r}, ensure_ascii=False) + "\n")

    # ★ THE BLIND SPOT THE TWELVE TESTS COULD NOT SEE (outside review, 2026-10-21): a state file perceives
    # only the subjects somebody already wrote a line for. A surface nobody named produces no red line, and
    # silence about the unnamed is indistinguishable from health. `--undeclared DIR` closes it for any
    # directory whose every file ought to have a line — a scribe output directory, for instance.
    undeclared = []
    declared = {st["src"] for st in states}
    for d in undeclared_dirs:
        try:
            entries = sorted(os.listdir(d))
        except OSError as e:
            errors.append(f"--undeclared {d}: {e.__class__.__name__} — a directory that cannot be listed is not an empty one")
            continue
        for name in entries:
            full = os.path.join(d, name)
            if os.path.isfile(full) and full not in declared:
                undeclared.append(full)

    if as_json:
        print(json.dumps({"states": len(states), "errors": errors, "results": results,
                          "undeclared": undeclared}, indent=2))
    else:
        for e in errors:
            print(f"MALFORMED  {e}")
        for r in results:
            line = f"{r['verdict']:<11} §OBS.{r['id']:<10} {r['subject'][:38]:<38} {r['why']}"
            print(line.rstrip())
        for u in undeclared:
            print(f"{'UNDECLARED':<11} {'-':<15} {'a surface with no state line':<38} {u}")
        counts = {}
        for r in results:
            counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
        summary = ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "no states"
        if undeclared:
            summary += f", UNDECLARED {len(undeclared)}"
        print(f"\n{len(states)} states · {summary}")

    bad = len(errors) + len(undeclared) + sum(1 for r in results if r["verdict"] != "OK")
    return 1 if bad else 0



def parse(text):
    """Return (laws, errors). A law without COST or TEST is a malformed law, never a soft one."""
    laws, errors = [], []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = FIELD_RE.match(line)
        if not m:
            errors.append(f"line {n}: not a law (needs WHEN/DO/NOT/COST/TEST): {line[:90]}")
            continue
        d = m.groupdict()
        d["test"] = [t.strip() for t in d["test"].split(";") if t.strip()]
        if not d["test"]:
            errors.append(f"line {n}: §{d['id']} has no TEST — a law that cannot go red is a preference")
            continue
        d["chars"] = len(raw.rstrip())
        laws.append(d)
    return laws, errors


def evaluate(clause, events):
    """Two predicate kinds, and nothing else. Deliberately NOT eval(): a law file is data, and
    a law file that can execute code is a liability the moment someone else can write one.

        violation("<id>", "<regex>"[, when="<trigger>"])   a shape in my own words
        fails("<check>")                                  a mechanical check that did not pass

    The second kind exists because a law bound to a bench check is not tested by matching prose —
    it is tested by the check's own verdict, which no one argued it into.
    """
    m = re.match(r'violation\(\s*"([^"]*)"\s*,\s*"([^"]*)"\s*(?:,\s*when\s*=\s*"([^"]*)")?\s*\)$', clause)
    if m:
        law_id, pattern, when = m.groups()
        hits = [
            e for e in events
            if e.get("law") == law_id
            and re.search(pattern, e.get("text", ""))
            and (not when or when in e.get("trigger", ""))
        ]
        return len(hits), None
    m = re.match(r'fails\(\s*"([^"]*)"\s*\)$', clause)
    if m:
        check = m.group(1)
        hits = [
            e for e in events
            if e.get("trigger") == check and str(e.get("text", "")).startswith("FAILED")
        ]
        return len(hits), None
    return None, f"unsupported predicate: {clause[:60]}"


def cmd_check(laws_path, record_path):
    laws, errors = parse(Path(laws_path).read_text(encoding="utf-8"))
    events = json.loads(Path(record_path).read_text(encoding="utf-8"))
    red = 0
    for e in errors:
        print(f"MALFORMED  {e}")
        red += 1
    for law in laws:
        for clause in law["test"]:
            hits, err = evaluate(clause, events)
            if err:
                print(f"UNKNOWN    §{law['id']}  {err}")
                red += 1
                continue
            # A clause names the shape that COUNTS AS THE LAW FIRING — i.e. being broken.
            # So a hit is a RED result, not a curiosity. The first version of this checker
            # printed FIRING and still exited 0, which is the exact bug this whole format
            # exists to catch: a check that reports success while the violating condition
            # is sitting in its own output.
            expected = law.get("expect")
            if hits:
                red += 1
                print(f"RED        §{law['id']:<12} {hits:>3} violating event(s)  <- {clause}")
                firing = [x for x in events
                          if x.get("law") == law["id"] and str(x.get("text", "")).startswith("FAILED")]
                for e in firing[:2]:
                    print(f"              at {e.get('at','?')}: {e.get('text','')[:70]}")
            else:
                print(f"green      §{law['id']:<12}   no violating event  <- {clause}")
    print()
    if red:
        print(f"{red} red — the spine does not hold.")
        return 1
    print(f"{len(laws)} laws, {sum(len(l['test']) for l in laws)} tests, all parseable, none firing.")
    return 0


def cmd_list(laws_path):
    laws, errors = parse(Path(laws_path).read_text(encoding="utf-8"))
    for law in laws:
        print(f"§{law['id']:<14} {law['chars']:>4} chars  {len(law['test'])} test(s)  COST {law['cost']}")
    for e in errors:
        print("MALFORMED", e)
    print(f"\n{len(laws)} laws, mean {sum(l['chars'] for l in laws)//max(len(laws),1)} chars per law")
    return 1 if errors else 0


def cmd_stats(laws_path, prose_path):
    laws, _ = parse(Path(laws_path).read_text(encoding="utf-8"))
    prose = Path(prose_path).read_text(encoding="utf-8")
    rules = len(re.findall(r"^\s*[-*]\s", prose, re.M))
    per_rule = len(prose) // max(rules, 1)
    per_law = sum(l["chars"] for l in laws) // max(len(laws), 1)
    print(f"prose: {len(prose)} chars, {rules} rules, {per_rule} chars/rule")
    print(f"spine: {sum(l['chars'] for l in laws)} chars, {len(laws)} laws, {per_law} chars/law")
    if per_law:
        print(f"ratio: {per_rule / per_law:.1f}x smaller per law")
    return 0


def cmd_lint(laws_path, text_path):
    """Run every prose clause of every law against a text I am ABOUT TO SEND.

    This is the half the history-checker cannot do. `check` asks whether a law was broken in the
    past; `lint` asks whether the draft in front of me breaks one now — which is the only moment
    the answer can still change anything. A law whose pattern matches the draft is reported by
    the law's own name, so the correction is `§GATE.02 says this asks permission`, not "the
    linter didn't like it".
    """
    laws, errors = parse(Path(laws_path).read_text(encoding="utf-8"))
    text = Path(text_path).read_text(encoding="utf-8")
    red = 0
    for e in errors:
        print(f"MALFORMED  {e}")
        red += 1
    for law in laws:
        for clause in law["test"]:
            m = re.match(r'violation\(\s*"([^"]*)"\s*,\s*"([^"]*)"', clause)
            if not m:
                continue  # a fails() clause is about a bench check, not about a draft
            _, pattern = m.groups()
            hit = re.search(pattern, text, re.I)
            if hit:
                red += 1
                line_start = text.rfind("\n", 0, hit.start()) + 1
                line_end = text.find("\n", hit.end())
                line = text[line_start: line_end if line_end != -1 else len(text)].strip()
                print(f"RED   §{law['id']:<12} {law['do']}")
                print(f"      matched \"{hit.group(0)}\" in: {line[:90]}")
    print()
    if red:
        print(f"{red} law(s) this draft would break.")
        return 1
    print("no law fires on this draft.")
    return 0


def cmd_prove(laws_path, plants_path):
    """Every law must catch a planted positive before its silence means anything.

    A law that has never fired may be a law nobody breaks, or a rule whose pattern cannot match
    the way the breach actually looks. Those two are indistinguishable from the green output — and
    the second one is worse, because it reads as virtue. This is the law-file version of the rule
    that has cost the most elsewhere: a check that cannot fail is not a check.
    """
    laws, _ = parse(Path(laws_path).read_text(encoding="utf-8"))
    plants = {p["law"]: p["text"] for p in json.loads(Path(plants_path).read_text(encoding="utf-8"))["plants"]}
    red, proved = 0, 0
    for law in laws:
        plant = plants.get(law["id"])
        if plant is None:
            print(f"NO PLANT   §{law['id']:<12} — its silence is not evidence, and nobody has said so")
            red += 1
            continue
        caught = False
        for clause in law["test"]:
            m = re.match(r'violation\(\s*"([^"]*)"\s*,\s*"([^"]*)"', clause)
            if not m:
                continue
            if re.search(m.group(2), plant, re.I):
                caught = True
                break
        if caught:
            proved += 1
            print(f"proved     §{law['id']:<12} catches: \"{plant[:60]}\"")
        else:
            red += 1
            print(f"BLIND      §{law['id']:<12} did NOT catch its own plant: \"{plant[:60]}\"")
            print(f"                                  the pattern is narrower than the behaviour it names")
    print()
    print(f"{proved}/{len(laws)} laws proved able to fire.")
    return 1 if red else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "check" and len(args) == 2:
        sys.exit(cmd_check(*args))
    if cmd == "lint" and len(args) == 2:
        sys.exit(cmd_lint(*args))
    if cmd == "prove" and len(args) == 2:
        sys.exit(cmd_prove(*args))
    if cmd == "observe":
        sys.exit(cmd_observe(args))
    if cmd == "list" and len(args) == 1:
        sys.exit(cmd_list(*args))
    if cmd == "stats" and len(args) == 2:
        sys.exit(cmd_stats(*args))
    print(__doc__)
    sys.exit(2)
