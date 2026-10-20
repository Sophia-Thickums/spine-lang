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
    spine.py check  <laws.spine> <record.json>     # run every TEST, exit 1 if any go red
    spine.py list   <laws.spine>                   # ids, sizes, and whether each has a TEST
    spine.py stats  <laws.spine> <prose.md>        # chars-per-law, before and after

Exit codes: 0 all green · 1 something went red · 2 the file itself is malformed.
"""
import json
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
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "check" and len(args) == 2:
        sys.exit(cmd_check(*args))
    if cmd == "lint" and len(args) == 2:
        sys.exit(cmd_lint(*args))
    if cmd == "prove" and len(args) == 2:
        sys.exit(cmd_prove(*args))
    if cmd == "list" and len(args) == 1:
        sys.exit(cmd_list(*args))
    if cmd == "stats" and len(args) == 2:
        sys.exit(cmd_stats(*args))
    print(__doc__)
    sys.exit(2)
