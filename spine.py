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
    r"TEST\s+(?P<test>.+?)"
    r"(?:\s+CONTROL\s+(?P<control>.+))?$"
)

# ★ ONE COMPLETE PREDICATE GRAMMAR FOR EVERY VERB (saturnia, 2026-10-25, adopted 2026-10-26).
# Recognising two arguments is not the same as recognising a clause. A truncated call, or a valid
# prefix followed by junk, is not a clause — and because each verb had its OWN matcher, the three
# verbs disagreed about whether such a line was a clause at all: `prove` reported 1/1 exit 0 over
# `violation(...); unsupported("x")` while `lint` and `check` both refused it. Three matchers meant
# three opinions, and the one that ran unattended decided what "verified" meant.
VIOLATION_RE = re.compile(
    r'violation\(\s*"([^"]*)"\s*,\s*"([^"]*)"\s*(?:,\s*when\s*=\s*"([^"]*)")?\s*\)'
)
FAILS_RE = re.compile(r'fails\(\s*"([^"]*)"\s*\)')


def clause_kind(clause):
    """'prose' | 'bench' | None for one TEST clause. THE single admission rule."""
    c = clause.strip()
    if VIOLATION_RE.fullmatch(c):
        return "prose"
    if FAILS_RE.fullmatch(c):
        return "bench"
    return None


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
    marker = re.compile(r"\s+(?=(?:SRC|UNC|SEEN|SCALE|TOL|FRESH|FIELD|SUBJECT|AS-OF)\s)")
    fields = {"SRC", "UNC", "SEEN", "SCALE", "TOL", "FRESH", "FIELD", "SUBJECT", "AS-OF"}

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
        d["subject_id"] = got.get("SUBJECT", "")
        d["as_of"] = got.get("AS-OF", "")
        try:
            d["scale"] = float(got["SCALE"]) if "SCALE" in got else 1.0
            d["tol"] = float(got["TOL"]) if "TOL" in got else 0.0
            d["fresh"] = float(got["FRESH"]) if "FRESH" in got else None
            # ★ EXTRACTION WAS UNSPECIFIED (outside review, 2026-10-21) and it bites on the very first real
            # surface: /proc/uptime holds two numbers, /proc/loadavg holds five. FIELD selects a
            # whitespace-separated field by number — no pattern language, nothing to smuggle a regex into,
            # and a file with fewer fields than asked for is an error rather than a guess.
            d["field"] = int(got["FIELD"]) if "FIELD" in got else None
            if d["field"] is not None and d["field"] < 1:
                raise ValueError("FIELD is 1-based")
        except ValueError:
            errors.append(f"line {n}: §OBS.{d['id']} SCALE/TOL must be numbers")
            continue
        # ★ A DEADLINE OF nan OR inf IS NOT A DEADLINE (found by saturnia, 2026-10-21, verified here).
        # `float("nan")` parses, and every comparison against it is false — so `src_age > FRESH` is False
        # and a source frozen since 2020 earns OK, with the check still nominally in place. Infinity is
        # the same defect wearing a number: an unbounded allowance. A duration must be finite and >= 0,
        # or the line is malformed rather than fresh.
        # ★ AN ADMISSION RULE BELONGS TO THE KIND OF VALUE, NOT TO THE FIELD THAT REPORTED IT
        # (deep-seeker, 2026-10-26). The FRESH nan/inf guard below was correct and FIELD-SHAPED: it
        # validated FRESH because that is where nan bit. Meanwhile SCALE and TOL come through the
        # same try block and were never checked at all — `SCALE 0` multiplies the source value to
        # zero, so "claim 0 against a source reading 1000" returned OK; `TOL 0` is a band with no
        # width on a row that claims `bounded`; `TOL 1e400` floats to inf and is the same unbounded
        # allowance the FRESH guard exists to refuse. So: one validator per KIND, applied to every
        # field of that kind at parse time, and a new field of an existing kind cannot reintroduce
        # the class.
        def _finite(v):
            return v == v and v not in (float("inf"), float("-inf"))

        if not _finite(d["scale"]) or d["scale"] == 0:
            errors.append(f"line {n}: §OBS.{d['id']} SCALE {got.get('SCALE')!r} is not a usable factor — "
                          f"it must be finite and non-zero, or the claim is multiplied out of existence "
                          f"and every comparison against it silently passes")
            continue
        if not _finite(d["tol"]) or d["tol"] < 0:
            errors.append(f"line {n}: §OBS.{d['id']} TOL {got.get('TOL')!r} is not a usable tolerance — "
                          f"it must be finite and >= 0, or the band is unbounded and nothing can drift")
            continue
        if d["fresh"] is not None and (not _finite(d["fresh"]) or d["fresh"] < 0):
            errors.append(f"line {n}: §OBS.{d['id']} FRESH {got.get('FRESH')!r} is not a finite duration — "
                          f"nan/inf disables the source-age check while looking like a deadline")
            continue
        if d["tol"] == 0 and d["unc"] == "bounded":
            errors.append(f"line {n}: §OBS.{d['id']} UNC bounded with TOL 0 is a band with no width — "
                          f"that is a point; say UNC exact")
            continue
        if d["unc"] not in UNC_VALUES:
            # ★ THE REFUSAL ITSELF CRASHED (outside review, 2026-10-22). `sorted('exact','bounded')` takes
            # ONE iterable — the branch that exists to name a bad UNC raised TypeError instead of writing
            # its message, so the run died with a traceback and exit 1. It looked green because no arm ever
            # sent a bad UNC value; the arm below is the fix's other half.
            errors.append(f"line {n}: §OBS.{d['id']} UNC must be one of {sorted(UNC_VALUES)}, got {d['unc']!r}")
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
        # ★ SUBJECT: THE IDENTITY OF THE THING, NOT ITS NAME (gigawatt, 2026-10-21). SRC names where the
        # value is read and SEEN/FRESH name when, and nothing named WHAT the value is about — so a surface
        # can keep answering under a retired identity and every other field passes. Names are not
        # identities either: `gpu.xt.*` re-pointed at the MI25 the night hwmon numbers swapped, and the
        # format had nowhere to say "this line is about the card at 0000:03:00.0".
        if d["subject_id"]:
            if not re.match(r"^[a-z0-9][a-z0-9._-]*:\S+$", d["subject_id"]):
                errors.append(f"line {n}: §OBS.{d['id']} SUBJECT must be '<namespace>:<identity>' "
                              f"(e.g. pci:0000:03:00.0), got {d['subject_id']!r}")
                continue
        if d["as_of"] and not re.match(r"^\d{4}-\d{2}-\d{2}$", d["as_of"]):
            errors.append(f"line {n}: §OBS.{d['id']} AS-OF must be a date (YYYY-MM-DD), got {d['as_of']!r}")
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


def _expand(path):
    """Turn a SRC that names a NODE BY PATTERN into one real path. Returns (path, why-not).

    ★ WHY THIS EXISTS (2026-10-21, found the hard way). hwmon indices are assigned at probe time and
    MOVE between boots: card1 was `hwmon1` yesterday and `hwmon2` today, so five sensor lines went
    blind while both cards were perfectly healthy and answering. A state file that hardcodes an index
    does not measure the hardware, it measures the kernel's enumeration order — and it fails by
    reporting the sensor MISSING, which reads exactly like a dead device.

    That is the law this house already carries for the GPUs themselves: PIN BY NAME, NEVER BY INDEX.
    So a SRC may name its node with a wildcard, and the two ways a wildcard can lie are both refused
    rather than guessed: ZERO matches is a blind sense, and more than one is ambiguous — taking the
    first match would be a choice wearing a reading's clothes.
    """
    if not any(ch in path for ch in "*?["):
        return path, None
    import glob
    hits = sorted(glob.glob(path))
    if not hits:
        return None, "missing (the pattern matches no node — a renamed or absent surface is a blind sense)"
    if len(hits) > 1:
        names = ", ".join(os.path.basename(h) for h in hits)
        return None, f"ambiguous ({len(hits)} nodes match: {names}) — name the one that owns the fact"
    return hits[0], None


def _read_source(path):
    """Read the surface that owns the fact. Returns (value, None) or (None, why-not)."""
    path, why = _expand(path)
    if why:
        return None, why
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


def _select(val, field):
    """Pick a whitespace-separated field. Returns (value, None) or (None, why-not)."""
    if field is None:
        return val, None
    parts = val.split()
    if len(parts) < field:
        return None, f"the surface has {len(parts)} field(s); FIELD {field} asks for one that is not there"
    return parts[field - 1], None


def _age_seconds(seen):
    """SEEN is a date (YYYY-MM-DD) or an ISO timestamp. Unknown shapes are an error, not a guess.

    ★ RETURNS THREE THINGS, and the third is the fix for a defect the second caused (saturnia, 2026-10-22):
    a date-only SEEN was expanded to 23:59:59 so that "true through its last second" would hold for the AGE
    test — but the same expanded value then went into the future-timestamp guard, so TODAY'S DATE reported
    -43,199 s (a day and a bit in the future) and was refused as clock skew. The two tests want different
    clocks: admissibility wants the ACTUAL precision the caller wrote, aging wants the end of the day.
    So `precise_age` is computed from the value AS WRITTEN, never from the expansion.
    """
    from datetime import datetime, timezone
    s = seen.strip()
    # ★ THE MOST STANDARD TIMESTAMP AN AGENT EMITS WAS THE ONE THIS PARSER REFUSED (deep-seeker,
    # 2026-10-26). An RFC 3339 UTC stamp — 2026-10-26T00:00:00Z — failed all three formats and came
    # back as "not a date or ISO timestamp". It failed CLOSED, so it was safe rather than silent,
    # but a format nobody can write without knowing my parser is a format with a hidden dialect.
    # A trailing Z (or +00:00) means UTC, which is the assumption the rest of this function already
    # makes, so accepting it changes no arithmetic.
    if s.endswith("Z") or s.endswith("z"):
        s = s[:-1]
    elif s.endswith("+00:00"):
        s = s[:-6]
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
        except ValueError:
            continue
        # ★ "NOW" IS UTC AND THE INHERITED TZ IS NOT IT (found 2026-10-26 while testing deep-seeker's
        # SCALE finding). `datetime.now()` is NAIVE — it reads the system clock in whatever TZ the
        # process inherited. Under a shell with TZ=America/Chicago every SEEN read 17,999 s in the
        # FUTURE and was refused as clock skew, which looks exactly like a bad claim and is a bad
        # instrument. A timestamp written without a zone is UTC by this format's own convention, so
        # "now" must be UTC too. Every reading taken in a non-UTC shell was wrong by the offset.
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        precise_age = (now - dt).total_seconds()   # the instant the caller actually wrote
        if fmt == "%Y-%m-%d":
            dt = dt.replace(hour=23, minute=59, second=59)  # a date is true through its last second
        return (now - dt).total_seconds(), None, precise_age
    return None, f"SEEN {seen!r} is not a date or ISO timestamp", None


def _resolve(path):
    """Resolve symlinks and bind-mount lookalikes BEFORE deciding what kind of surface this is."""
    try:
        return os.path.realpath(path)
    except OSError:
        return path


def _source_is_live(path):
    """Live surfaces are regenerated by the kernel on every read; written ones are a scribe's output.

    ★ THE DISTINCTION IS THE POINT (outside review, 2026-10-21): a claim's age was checked but the
    SOURCE's age was not, so a scribe that dies leaves its last file behind and `observe` reads a frozen
    value, agrees with it, and returns OK — a dead sense reporting health forever.
    """
    real = _resolve(_expand(path)[0] or path)
    return real.startswith("/sys/") or real.startswith("/proc/")


def _source_age(path):
    real, why = _expand(path)
    if why:
        return None
    try:
        import time as _t
        return _t.time() - os.stat(real).st_mtime
    except OSError:
        return None


def observe_one(st, stale_after):
    """One state line, re-checked against its own source. Returns a dict; 'verdict' is the answer."""
    age, age_err, precise_age = _age_seconds(st["seen"])
    observed, why = _read_source(st["src"])
    if observed is not None:
        observed, why = _select(observed, st.get("field"))
    rec = {
        "id": st["id"], "subject": st["subject"], "claimed": st["value_raw"],
        "observed": observed, "src": st["src"], "unc": st["unc"], "seen": st["seen"],
        "age_s": None if age is None else round(age),
    }
    if age_err:
        rec["verdict"], rec["why"] = "MALFORMED", age_err
        return rec
    # ★ A SEEN THAT HAS NOT HAPPENED YET IS NOT FRESH, IT IS UNREADABLE (found by saturnia, 2026-10-21,
    # verified here). `_age_seconds` returns a NEGATIVE age for a future timestamp, and `age > stale_after`
    # is false for any negative number — so `SEEN 2099-01-01` passed every freshness test and reported OK.
    # The surface's own mtime already has this guard; the claim's timestamp did not. A small skew is real
    # (two clocks, one read), so the allowance is declared rather than silently zero.
    CLOCK_SKEW_S = 120
    # ★ ADMISSIBILITY USES THE PRECISION THE CALLER WROTE, NOT THE END-OF-DAY EXPANSION (saturnia, 2026-10-22).
    # `age` has had a date-only SEEN expanded to 23:59:59 so the age test is fair; feeding THAT into the
    # future guard made today's date read as -43,199 s and refused it. `precise_age` is the unexpanded value.
    # A date-only SEEN is never "in the future" unless the date itself is after today.
    if precise_age is not None and precise_age < -CLOCK_SKEW_S:
        rec["verdict"] = "MALFORMED"
        rec["why"] = (f"SEEN is {-round(precise_age)}s in the FUTURE (allowance {CLOCK_SKEW_S}s) — a claim cannot be "
                      f"read before it was made, and a future timestamp makes every freshness test pass")
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
        # ★ ONE GLOBAL FRESHNESS NUMBER CANNOT FIT BOTH A TEN-SECOND SCRIBE AND /etc/machine-id, and a
        # write-on-change scribe leaves an OLD mtime on a CURRENT value (outside review, 2026-10-21). So each
        # written surface declares its own deadline in the line — FRESH <seconds> — and the global threshold
        # applies only to SEEN. FRESH is REQUIRED for a written surface: without it, a dead scribe passes.
        if st.get("fresh") is None:
            rec["verdict"], rec["why"] = "MALFORMED", "written surface with no FRESH — how long may it sit unrewritten?"
            return rec
        if src_age < -60:
            rec["verdict"] = "SOURCE-STALE"
            rec["why"] = f"the surface's mtime is {-round(src_age)}s in the FUTURE — a clock with no trust in it"
            return rec
        if src_age > st["fresh"]:
            rec["verdict"] = "SOURCE-STALE"
            rec["why"] = (f"the surface has not been rewritten in {round(src_age)}s (FRESH {st['fresh']}s) — "
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

    # ★ RETRY, DO NOT INVENT A "FLAKY" VERDICT (outside review, 2026-10-21). The first version reported
    # FLAKY whenever two reads disagreed — which is wrong twice over: a legitimately moving surface
    # (/proc/uptime, a byte counter) would fail every run, and a WRONG claim on a moving surface would be
    # reported as FLAKY instead of DRIFT, hiding the very disagreement the format exists to surface.
    # So: on disagreement, read again (a truncated read will differ); if any read agrees, the claim was true
    # at some instant and is OK. If none agree, it is DRIFT, and the spread is printed as evidence.
    readings = [observed]
    if not agree:
        for _ in range(2):
            again, why2 = _read_source(st["src"])
            if again is not None:
                again, why2 = _select(again, st.get("field"))
            if again is None:
                continue
            readings.append(again)
            agree2, scaled2 = agrees(again)
            if agree2:
                agree, scaled = agree2, scaled2
                rec["observed"] = again
                rec["note"] = f"agreed on re-read {len(readings)}"
                if scaled is not None:
                    rec["observed_scaled"] = round(scaled, 6)
                break
        if not agree and len(set(readings)) > 1:
            rec["spread"] = readings
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
    path, stale_after, record_path, as_json, require_subject = None, 900, None, False, False
    undeclared_dirs = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--json":
            as_json = True
        elif a == "--require-subject":
            require_subject = True
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

    # ★ A LINE WITH NO SUBJECT IS A CLAIM ABOUT NO PARTICULAR THING, and the default stays permissive only
    # until the scribe can emit one. `--require-subject` is the strict arm, and it must be runnable red.
    no_subject = [st["id"] for st in states if not st.get("subject_id")]
    if require_subject and no_subject:
        errors.append(f"{len(no_subject)} state(s) name no SUBJECT — the value's identity is unchecked: "
                      f"{', '.join(no_subject[:6])}")

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
            # Editor swaps, backups and half-written temporaries are not surfaces with no line; they are
            # not surfaces at all (outside review, 2026-10-21). Filter them by name, not by hope.
            if name.startswith(".") or name.endswith(("~", ".swp", ".swo", ".tmp", ".part", ".bak")):
                continue
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



def _plant_event(plant):
    """Split an explicitly labelled example into (trigger, text).

    Bench plants and scoped prose positives/controls must name their actual trigger.
    Returns (None, plant) when the example does not label itself; the caller decides
    whether an unlabelled example is meaningful for its predicate kind.
    """
    m = re.match(r'^\s*trigger=(\S+)\s+text=(.*)$', plant, re.S)
    if m:
        return m.group(1), m.group(2)
    return None, plant


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
    m = VIOLATION_RE.fullmatch(clause.strip())
    if m:
        law_id, pattern, when = m.groups()
        # ★ ONE MATCHER, ONE CASE RULE (saturnia, 2026-10-21; reintroduced by me 2026-10-26).
        # `lint` and `prove` have always matched case-insensitively at the DRAFT level, because a
        # draft sentence may start a clause with a capital. This function did not, so the same
        # pattern was red in `lint` and quiet in `check` for any sentence beginning with the word
        # the pattern was about — and when `prove` was changed to call this function it silently
        # lost the flag and the public example fell from 4/4 to 2/4. The rule now lives in one
        # place: prose is matched case-insensitively everywhere, and `prove`/`check`/`lint` cannot
        # disagree about a sentence again.
        hits = [
            e for e in events
            if e.get("law") == law_id
            and re.search(pattern, e.get("text", ""), re.I)
            and (not when or when in e.get("trigger", ""))
        ]
        return len(hits), None
    m = FAILS_RE.fullmatch(clause.strip())
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
            m = VIOLATION_RE.fullmatch(clause.strip())
            if not m:
                # ★ A fails() clause is about a bench check, not about a draft — that is a
                # legitimate skip. But ANYTHING ELSE is a clause nobody implemented, and the
                # first version of this verb `continue`d on it silently, so a law carrying
                # `TEST unsupported("x")` linted clean and exited 0 while `check` refused the
                # same clause loudly. An unimplemented predicate is not a passing one
                # (found by an outside reviewer, 2026-10-21). Say so and go red.
                if FAILS_RE.fullmatch(clause.strip()) is None:
                    red += 1
                    print(f"UNKNOWN   §{law['id']:<12} lint cannot evaluate: {clause[:70]}")
                    print(f"          a clause lint does not understand is not a clause this draft passed")
                continue
            _, pattern, _ = m.groups()
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

    ★ A MALFORMED LAW MUST NOT DISAPPEAR FROM THE DENOMINATOR (found by an outside reviewer,
    2026-10-21). This verb used to discard parse()'s error list, so an invalid rule was simply
    removed before counting: a file of four good laws plus one unparseable one reported `4/4` and
    exited 0, and a file containing ONLY the bad law reported `0/0` and exited 0. Both readings
    are indistinguishable from a clean file, which is the exact defect prove exists to catch,
    one layer up. Refusing the parse is the only honest answer: a rule that is not in the
    denominator has not been proved, it has been dropped.

    ★ A LAW THAT CAN ONLY FIRE IS ALSO BLIND, AND THE MIRROR HOLE WAS OPEN (found 2026-10-25).
    The check above asks whether a pattern CAN fire. It never asked whether it can STOP. A law
    written as `violation("A.01",".")` matched its own plant, reported `1/1 laws proved able to
    fire`, exited 0 — and then fired on every sentence ever written, including fully compliant
    ones. That is the same defect as a check that can only agree with you, seen from the other
    side: a check that can only disagree carries no information either, and it trains its reader
    to ignore the output. So a pattern must match its plant AND must not match a plain control
    sentence. The control is not a plant; it is the silence the plant has to be distinguishable
    from.

    ★ AND A fails() LAW COULD NEVER BE PROVED AT ALL (found 2026-10-25). evaluate() has two
    predicate kinds, but this verb only recognised `violation(...)` and `continue`d on anything
    else, so EVERY bench-bound law reported BLIND and dragged the file red however well its check
    worked — the exact law the evaluate() docstring says exists because a bench check is not
    tested by matching prose. A fails() law is proved by its plant carrying the shape evaluate()
    looks for: the check's own name on an event whose text starts with FAILED. Credit is given for
    the clause being able to see that, with no control arm, because a failing bench check is
    already the control — it is a verdict arrived at by something other than prose.

    ★ AND THE FIRST fixes FOR BOTH WERE THEMSELVES THE DEFECT THEY CURED (saturnia, 2026-10-26).
    Two findings, both reproduced on the tree before a line was changed:

    (1) THE CONTROL WAS ONE FIXED SENTENCE AND NOBODY HAD JUSTIFIED THAT IT WAS COMPLIANT.
    The control read "...saying nothing that any standing law forbids." A law written against
    exactly that claim (a rule forbidding blanket compliance assertions) matched its own plant
    AND the control, so the prover called it BLIND and printed "matches EVERY sentence" — a
    false accusation, because `lint` showed the pattern is narrow and quiet on neutral prose.
    A control is not evidence that a pattern is universal; it is evidence that the pattern
    matched ONE sentence. So the control is now PER LAW, declared in the law file itself
    (`control "..."`), and a law with neither a declared control nor a bench plant is reported
    UNCONTROLLED rather than silently credited. A universal pattern is caught by the DECLARED
    control matching, not by a sentence the prover happened to own.

    (2) A SUBSTRING IN ANOTHER CHECK'S FAILURE PROVED THE WRONG LAW. `fails("gpu_check")` was
    credited whenever the plant started with FAILED and merely CONTAINED "gpu_check" — so
    "FAILED disk_check: gpu_check passed" proved a law that `check` (which requires the
    trigger to BE gpu_check) correctly leaves green. The prover agreed for a reason other than
    the one it named, which is the whole subject of this file. So the prover now runs the SAME
    evaluator `check` runs, over an event built from the plant and its declared trigger, and
    demands a hit from that — one implementation, one verdict, no second opinion.
    """
    laws, errors = parse(Path(laws_path).read_text(encoding="utf-8"))
    # ★ VALIDATE EVERY CLAUSE BEFORE ANY PLANT IS TESTED (saturnia, 2026-10-25). A first clause
    # that matches its plant used to short-circuit the loop, hiding an unsupported LATER clause —
    # so `violation(...); unsupported("x")` proved 1/1 exit 0 while lint and check both refused
    # it. Admission is now decided for the whole law file, before a single ratio can be printed.
    for law in laws:
        for clause in law["test"]:
            if clause_kind(clause) is None:
                errors.append(f"§{law['id']}: unsupported predicate: {clause[:60]}")
    if errors:
        print(f"MALFORMED  {laws_path} — {len(errors)} parse/predicate error(s), so this file's")
        print("           denominator is not the file you wrote. Refusing to report a ratio.")
        for e in errors:
            print(f"           · {e}")
        return 1
    plants = {p["law"]: p["text"] for p in json.loads(Path(plants_path).read_text(encoding="utf-8"))["plants"]}
    # ★ THE CONTROL IS PER LAW AND MUST BE DECLARED (saturnia, 2026-10-26). There is no default
    # sentence: a prover that supplies its own compliant control has decided, silently, what
    # compliance looks like — and the first version's choice contained the exact phrase a
    # legitimate narrow law was written against, so the prover accused a correct pattern of being
    # universal. A law declares what must NOT fire, or it says it has no such case.
    red, proved = 0, 0
    for law in laws:
        plant = plants.get(law["id"])
        if plant is None:
            print(f"NO PLANT   §{law['id']:<12} — its silence is not evidence, and nobody has said so")
            red += 1
            continue
        caught = False
        blind_reason = ""
        kind = "prose"          # what the credit actually rests on, printed with the receipt
        for clause in law["test"]:
            m = VIOLATION_RE.fullmatch(clause.strip())
            if m:
                when = m.group(3)
                control = (law.get("control") or "").strip()
                # Scope is part of the example, not something prove may invent from
                # the predicate. Keep legacy unscoped text literal; scoped examples
                # use the existing trigger=... text=... event notation.
                plant_trigger, plant_text = "plant", plant
                if when:
                    plant_trigger, plant_text = _plant_event(plant)
                    if plant_trigger is None:
                        blind_reason = ("scoped prose plant names no trigger — declare "
                                        "'trigger=<actual-context> text=<violating text>'")
                        continue
                # One event, one law id, exactly as check() would see it.
                plant_events = [{"law": law["id"], "trigger": plant_trigger, "text": plant_text}]
                hits, _ = evaluate(clause, plant_events)
                hit_plant = bool(hits)
                if not hit_plant:
                    blind_reason = "the pattern is narrower than the behaviour it names"
                    continue
                if not control:
                    print(f"UNCONTROLLED §{law['id']:<11} caught its plant, but no CONTROL is declared —")
                    print(f"                                  a pattern that fires on everything would also pass this")
                    red += 1
                    caught = "uncontrolled"
                    break
                control_trigger, control_text = "control", control
                if when:
                    control_trigger, control_text = _plant_event(control)
                    if control_trigger is None:
                        blind_reason = ("scoped prose CONTROL names no trigger — declare "
                                        "'trigger=<actual-context> text=<compliant text>'")
                        continue
                    if when not in control_trigger:
                        blind_reason = ("the DECLARED control is outside the predicate's scope — "
                                        "silence there does not test in-scope text discrimination")
                        continue
                control_events = [{"law": law["id"], "trigger": control_trigger, "text": control_text}]
                chits, _ = evaluate(clause, control_events)
                if chits:
                    blind_reason = ("the pattern matches its DECLARED control — it can fire but cannot "
                                    "tell a breach from prose")
                    continue
                caught = True
                kind = "prose+control"
                break
            mb = FAILS_RE.fullmatch(clause.strip())
            if mb:
                check = mb.group(1)
                # ★ THE PLANT'S OWN TRIGGER IS THE THING THAT DECIDES — NOT THE CHECK'S NAME
                # (saturnia, 2026-10-26, and my first fix got this wrong in the same way).
                # The first version credited a plant on "starts with FAILED and contains the
                # check name", so "FAILED disk_check: gpu_check passed" proved a fails("gpu_check")
                # law that check() correctly leaves green. My first repair hard-wired the trigger
                # to the check name, which made that plant pass anyway — I had moved the
                # assumption rather than removed it. Now the plant declares the trigger it arrived
                # on ("trigger=disk_check") and the SAME evaluator check() uses is asked whether
                # that event fires this law. An unlabelled plant is refused, not guessed.
                trigger, ptext = _plant_event(plant)
                if trigger is None:
                    blind_reason = (f"fails(\"{check}\") — the plant names no trigger, so which check "
                                    f"failed is unstated; write 'trigger={check} text=FAILED {check}: ...'")
                    continue
                hits, _ = evaluate(clause, [{"law": law["id"], "trigger": trigger, "text": ptext}])
                if hits:
                    caught = True
                    kind = f"bench/evaluate trig={trigger}"
                    break
                blind_reason = (f"fails(\"{check}\") is not exercised by its plant — the plant fired on "
                                f"trigger {trigger!r}, which is not that check")
                continue
            blind_reason = f"unimplemented predicate, cannot be proved: {clause[:50]}"
        if caught is True:
            proved += 1
            print(f"proved     §{law['id']:<12} catches: \"{plant[:52]}\"  [{kind}]")
        elif caught == "uncontrolled":
            pass
        else:
            red += 1
            print(f"BLIND      §{law['id']:<12} did NOT catch its own plant: \"{plant[:60]}\"")
            print(f"                                  {blind_reason or 'the pattern is narrower than the behaviour it names'}")
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
