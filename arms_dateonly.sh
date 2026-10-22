#!/usr/bin/env bash
# arms_dateonly.sh — saturnia's date-only boundary, frozen clock 2026-10-22T12:00:00.
# The defect it pins: a date-only SEEN was expanded to 23:59:59 for the AGE test, and that same
# expanded value went into the future-timestamp guard, so TODAY'S DATE was refused as clock skew.
# The fix: admissibility reads the precision the caller WROTE; aging keeps the end-of-day expansion.
set -u
pass=0; fail=0
check() { # name expected actual
  if [ "$2" = "$3" ]; then printf 'PASS  %-46s %s\n' "$1" "$3"; pass=$((pass+1))
  else printf 'FAIL  %-46s expected %s got %s\n' "$1" "$2" "$3"; fail=$((fail+1)); fi
}
out=$(python3 - <<'PY'
import importlib.util, os, tempfile, datetime
spec=importlib.util.spec_from_file_location("spine","spine.py")
sp=importlib.util.module_from_spec(spec); spec.loader.exec_module(sp)
FROZEN=datetime.datetime(2026,10,22,12,0,0)
_orig=datetime.datetime
class FakeDT(_orig):
    @classmethod
    def now(cls, tz=None): return FROZEN
datetime.datetime=FakeDT
d=tempfile.mkdtemp(); src=os.path.join(d,"surface.txt")
open(src,"w").write("42\n"); os.utime(src,None)   # real mtime: only the CLAIM clock is frozen
st={"id":"T","subject":"s","value_raw":"42","src":src,"unc":"exact","seen":None,
    "fresh":86400,"field":None,"tol":0}
for seen in ("2026-10-22","2026-10-23","2026-10-21","2026-10-22T12:02:00","2026-10-22T12:02:01"):
    st["seen"]=seen
    try: r=sp.observe_one(st,900); v=r["verdict"]
    except Exception as e: v="EXC:"+type(e).__name__
    print(seen, v)
datetime.datetime=_orig
PY
)
check "today's date is admissible (was MALFORMED)" "OK"        "$(echo "$out" | awk '$1=="2026-10-22"{print $2}')"
check "tomorrow's date is still refused"            "MALFORMED" "$(echo "$out" | awk '$1=="2026-10-23"{print $2}')"
check "yesterday's date still ages to STALE"        "STALE"     "$(echo "$out" | awk '$1=="2026-10-21"{print $2}')"
check "timestamp skew +120s allowed (boundary)"     "OK"        "$(echo "$out" | awk '$1=="2026-10-22T12:02:00"{print $2}')"
check "timestamp skew +121s refused (boundary)"     "MALFORMED" "$(echo "$out" | awk '$1=="2026-10-22T12:02:01"{print $2}')"
echo; echo "$pass passed, $fail failed"; [ "$fail" -eq 0 ]
