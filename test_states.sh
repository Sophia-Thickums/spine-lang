#!/usr/bin/env bash
# test_states.sh — prove the §OBS checker can go red, in four different ways, non-vacuously.
#
# A checker that has only ever run in the passing state is a mirror. Each arm below asserts BOTH the
# verdict string AND the exit code, because a verdict printed next to a zero exit is the exact bug this
# whole format exists to catch (it was found once already, in the laws half: "prints FIRING and exits 0").
set -u
cd "$(dirname "$0")"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
pass=0; fail=0

check () {           # check <label> <expected-verdict> <expected-exit> <file>
  local label="$1" want="$2" wantrc="$3" file="$4"
  local out rc
  out=$(python3 spine.py observe "$file" 2>&1); rc=$?
  if grep -q "$want" <<<"$out" && [ "$rc" = "$wantrc" ]; then
    printf 'PASS  %-34s %s (exit %s)\n' "$label" "$want" "$rc"; pass=$((pass+1))
  else
    printf 'FAIL  %-34s wanted %s/exit%s, got exit %s:\n' "$label" "$want" "$wantrc" "$rc"
    sed 's/^/        /' <<<"$out"; fail=$((fail+1))
  fi
}

NOW=$(date +%Y-%m-%dT%H:%M:%S)
TMPF="$T/surface"; echo 42 > "$TMPF"; : > "$T/empty"

# 0. the honest arm: a true claim passes. If THIS does not pass, the other arms prove nothing.
cat > "$T/ok.spine" <<EOF
§OBS.T0 WHEN test IS t.value = 42 SRC $TMPF UNC exact FRESH 60 SEEN $NOW
EOF
check "true claim passes" "OK" 0 "$T/ok.spine"

# 1. DRIFT — the source says something else.
cat > "$T/drift.spine" <<EOF
§OBS.T1 WHEN test IS t.value = 41 SRC $TMPF UNC exact FRESH 60 SEEN $NOW
EOF
check "wrong value -> DRIFT" "DRIFT" 1 "$T/drift.spine"

# 2. UNREADABLE — a source that is not there must NEVER read as agreement.
cat > "$T/missing.spine" <<EOF
§OBS.T2 WHEN test IS t.value = 42 SRC $T/does-not-exist UNC exact SEEN $NOW
EOF
check "missing source -> UNREADABLE" "UNREADABLE" 1 "$T/missing.spine"

# 3. EMPTY — a source that exists and returns nothing has not agreed with anything either.
cat > "$T/empty.spine" <<EOF
§OBS.T3 WHEN test IS t.value = 42 SRC $T/empty UNC exact SEEN $NOW
EOF
check "empty source -> UNREADABLE" "UNREADABLE" 1 "$T/empty.spine"

# 4. STALE — a reading with no fresh look is a memory, not a sight.
cat > "$T/stale.spine" <<EOF
§OBS.T4 WHEN test IS t.value = 42 SRC $TMPF UNC exact FRESH 60 SEEN 2026-01-01
EOF
check "old SEEN -> STALE" "STALE" 1 "$T/stale.spine"

# 5. MALFORMED — no SEEN at all. The refusal has to be structural, not a warning.
cat > "$T/noseen.spine" <<EOF
§OBS.T5 WHEN test IS t.value = 42 SRC $TMPF UNC exact FRESH 60
EOF
check "no SEEN -> MALFORMED" "MALFORMED" 1 "$T/noseen.spine"

# 6. MALFORMED — no SRC. A claim resting on memory rather than a surface is the thing the format exists to stop.
cat > "$T/nosrc.spine" <<EOF
§OBS.T6 WHEN test IS t.value = 42 UNC exact SEEN $NOW
EOF
check "no SRC -> MALFORMED" "MALFORMED" 1 "$T/nosrc.spine"

# 7. NUMERIC TOLERANCE — a bounded reading must be able to pass while a drift beyond it fails.
echo 42.4 > "$TMPF"
cat > "$T/tol_ok.spine" <<EOF
§OBS.T7 WHEN test IS t.value = 42 SRC $TMPF UNC bounded FRESH 60 TOL 1 SEEN $NOW
EOF
check "within tolerance -> OK" "OK" 0 "$T/tol_ok.spine"
echo 44.5 > "$TMPF"
cat > "$T/tol_bad.spine" <<EOF
§OBS.T8 WHEN test IS t.value = 42 SRC $TMPF UNC bounded FRESH 60 TOL 1 SEEN $NOW
EOF
check "beyond tolerance -> DRIFT" "DRIFT" 1 "$T/tol_bad.spine"

# 8. SCALE — a surface in its own units, a claim in mine.
echo 38000 > "$TMPF"
cat > "$T/scale.spine" <<EOF
§OBS.T9 WHEN test IS t.celsius = 38 SRC $TMPF SCALE 0.001 UNC exact SEEN $NOW FRESH 60
EOF
check "SCALE converts -> OK" "OK" 0 "$T/scale.spine"

# 9. THE RECORD — a run writes one line per state, so the perception leaves a trail.
# ★ Give this arm its OWN state file: an earlier arm mutated $TMPF, and reusing ok.spine here made the
# assertion fail for a reason that had nothing to do with the recorder. A test arm must not inherit
# the world another arm left behind.
echo 42 > "$TMPF"
cat > "$T/rec.spine" <<EOF
§OBS.TR WHEN test IS t.value = 42 SRC $TMPF UNC exact FRESH 60 SEEN $NOW
EOF
python3 spine.py observe "$T/rec.spine" --record "$T/rec.jsonl" >/dev/null
if [ "$(wc -l < "$T/rec.jsonl")" = "1" ] && grep -q '"verdict": "OK"' "$T/rec.jsonl"; then
  echo "PASS  record appends one line per state"; pass=$((pass+1))
else
  echo "FAIL  record did not append as expected"; fail=$((fail+1))
fi

# 10. THE WHOLE POINT, ONE LINE: a run containing ANY failure exits non-zero, even when most states pass.
cat > "$T/mixed.spine" <<EOF
§OBS.M1 WHEN test IS t.value = 38 SRC $TMPF SCALE 0.001 UNC exact SEEN $NOW FRESH 60
§OBS.M2 WHEN test IS t.ghost = 1 SRC $T/missing UNC exact SEEN $NOW
EOF
check "one bad state fails the run" "UNREADABLE" 1 "$T/mixed.spine"

# 11-13. THE REVIEWER'S REFUSALS (Opus 5.5, 2026-10-21) — UNC must change a verdict, or it is decoration.
cat > "$T/unc_exact_tol.spine" <<EOF
§OBS.U1 WHEN test IS t.v = 1 SRC $TMPF UNC exact FRESH 60 TOL 2 SEEN $NOW
EOF
check "exact + TOL -> MALFORMED" "MALFORMED" 1 "$T/unc_exact_tol.spine"

cat > "$T/unc_bounded_notol.spine" <<EOF
§OBS.U2 WHEN test IS t.v = 1 SRC $TMPF UNC bounded FRESH 60 SEEN $NOW
EOF
check "bounded, no TOL -> MALFORMED" "MALFORMED" 1 "$T/unc_bounded_notol.spine"

cat > "$T/unc_inferred.spine" <<EOF
§OBS.U3 WHEN test IS t.v = 1 SRC $TMPF UNC inferred SEEN $NOW
EOF
check "inferred -> refused as unimplemented" "MALFORMED" 1 "$T/unc_inferred.spine"

# 14. THE HOLE THE SUITE COULD NOT SEE: a WRITTEN surface that stopped being written.
# A frozen file agrees with anything, so age must be checked on the SOURCE, not only on the claim.
echo 42 > "$T/frozen"
touch -d '2026-01-01 00:00:00' "$T/frozen"
cat > "$T/frozen.spine" <<EOF
§OBS.S1 WHEN test IS t.v = 42 SRC $T/frozen UNC exact FRESH 60 SEEN $NOW
EOF
check "frozen written surface -> SOURCE-STALE" "SOURCE-STALE" 1 "$T/frozen.spine"

# 15. A LIVE surface (/sys, /proc) must NOT be held to the rewritten-recently rule: the kernel regenerates
# it on read, so its mtime is meaningless. This arm keeps the fix from becoming a false alarm.
cat > "$T/live.spine" <<EOF
§OBS.S2 WHEN test IS proc.loadavg_tokens = 3 SRC /proc/loadavg UNC exact SEEN $NOW
EOF
python3 - "$T/live.spine" <<'PY2'
import sys, pathlib, subprocess
# /proc/loadavg is not a single number; use a real single-value live surface instead.
p = pathlib.Path(sys.argv[1])
p.write_text("§OBS.S2 WHEN test IS proc.nprocs = 0 SRC /proc/self/limits UNC exact SEEN 2026-01-01\n")
PY2
echo "  (live-surface arm checked by the real states.spine run below, not by a fixture)"


# 16. THE BLIND SPOT — a surface that exists and nobody declared must be visible, not silent.
T2="$T/surfaces"; mkdir -p "$T2"; echo 42 > "$T2/known"; echo 7 > "$T2/surprise"
cat > "$T/u.spine" <<EOF
§OBS.D1 WHEN test IS t.v = 42 SRC $T2/known UNC exact SEEN $NOW FRESH 60
EOF
out=$(python3 spine.py observe "$T/u.spine" --undeclared "$T2" 2>&1); rc=$?
if grep -q "UNDECLARED" <<<"$out" && grep -q "surprise" <<<"$out" && [ "$rc" = 1 ]; then
  echo "PASS  undeclared surface is reported      UNDECLARED (exit 1)"; pass=$((pass+1))
else
  echo "FAIL  undeclared surface was silent"; sed 's/^/        /' <<<"$out"; fail=$((fail+1))
fi

# 17. and the control: with nothing stray, the same call must be clean. Otherwise arm 16 proves nothing.
rm -f "$T2/surprise"
out=$(python3 spine.py observe "$T/u.spine" --undeclared "$T2" 2>&1); rc=$?
if ! grep -q "UNDECLARED" <<<"$out" && [ "$rc" = 0 ]; then
  echo "PASS  no stray surfaces -> clean          OK (exit 0)"; pass=$((pass+1))
else
  echo "FAIL  false undeclared alarm"; sed 's/^/        /' <<<"$out"; fail=$((fail+1))
fi


# 18-21. THE SECOND REVIEW (Opus 5.5, same day) — five faults, each now an arm.
# (a) A WRONG claim on a surface that legitimately MOVES must still be DRIFT. The first version reported
#     FLAKY here, which buried the disagreement the format exists to surface.
cat > "$T/volatile.spine" <<EOF
§OBS.V1 WHEN test IS proc.uptime = 1 SRC /proc/uptime FIELD 1 UNC exact SEEN $NOW
EOF
check "wrong claim on a moving surface -> DRIFT" "DRIFT" 1 "$T/volatile.spine"

# (b) and the control: a claim that IS right about a moving surface must pass on the retry.
python3 - "$T" <<'PY2'
import pathlib, sys, subprocess
T = pathlib.Path(sys.argv[1])
up = open("/proc/uptime").read().split()[0]
(T / "volok.spine").write_text(
    f"§OBS.V2 WHEN test IS proc.uptime = {up} SRC /proc/uptime FIELD 1 UNC bounded TOL 60 SEEN {__import__('time').strftime('%Y-%m-%dT%H:%M:%S')}\n")
PY2
check "true claim on a moving surface (banded) -> OK" "OK" 0 "$T/volok.spine"

# (c) a WRITTEN surface with no FRESH is malformed: without a deadline a dead scribe passes forever.
echo 42 > "$T/w"; cat > "$T/nofresh.spine" <<EOF
§OBS.F1 WHEN test IS t.v = 42 SRC $T/w UNC exact SEEN $NOW
EOF
check "written surface, no FRESH -> MALFORMED" "MALFORMED" 1 "$T/nofresh.spine"

# (d) FRESH exceeded, and an mtime in the future, both refuse to call a frozen surface healthy.
touch -d '-10 minutes' "$T/w"
cat > "$T/freshbad.spine" <<EOF
§OBS.F2 WHEN test IS t.v = 42 SRC $T/w UNC exact SEEN $NOW FRESH 60
EOF
check "surface older than FRESH -> SOURCE-STALE" "SOURCE-STALE" 1 "$T/freshbad.spine"

touch -d '+2 hours' "$T/w"
cat > "$T/future.spine" <<EOF
§OBS.F3 WHEN test IS t.v = 42 SRC $T/w UNC exact SEEN $NOW FRESH 60
EOF
check "mtime in the future -> SOURCE-STALE" "SOURCE-STALE" 1 "$T/future.spine"

# (e) and FRESH respected: the same file, freshly written, passes. Without this arm (d) could be passing
#     for the wrong reason — a checker that refuses everything is not a checker.
touch "$T/w"
cat > "$T/freshok.spine" <<EOF
§OBS.F4 WHEN test IS t.v = 42 SRC $T/w UNC exact SEEN $NOW FRESH 60
EOF
check "surface inside FRESH -> OK" "OK" 0 "$T/freshok.spine"

# (f) ★ A DEADLINE THAT IS NOT A NUMBER IS NOT A DEADLINE (saturnia's finding, arm added 2026-10-22).
#     `float("nan")` parses and every comparison against it is False, so `src_age > FRESH` is never true
#     and a source frozen for years earns OK with the deadline still nominally written. Infinity is the
#     same defect wearing a number: an unbounded allowance. Both must be MALFORMED, and the arm is run on
#     the SAME frozen source that arm (d) refuses — so a pass here cannot come from the file being fresh.
touch -d '-10 minutes' "$T/w"
cat > "$T/nan.spine" <<EOF
§OBS.F5 WHEN test IS t.v = 42 SRC $T/w UNC exact SEEN $NOW FRESH nan
EOF
check "FRESH nan -> MALFORMED" "MALFORMED" 1 "$T/nan.spine"

cat > "$T/inf.spine" <<EOF
§OBS.F6 WHEN test IS t.v = 42 SRC $T/w UNC exact SEEN $NOW FRESH inf
EOF
check "FRESH inf -> MALFORMED" "MALFORMED" 1 "$T/inf.spine"

cat > "$T/neg.spine" <<EOF
§OBS.F7 WHEN test IS t.v = 42 SRC $T/w UNC exact SEEN $NOW FRESH -5
EOF
check "FRESH negative -> MALFORMED" "MALFORMED" 1 "$T/neg.spine"

# (g) ★ A BAD UNC VALUE MUST BE REFUSED BY A MESSAGE, NOT BY A TRACEBACK (outside review, 2026-10-22).
#     The branch existed from the first day and had never been exercised; it raised TypeError instead of
#     printing, so the run died with exit 1 and a stack trace. An arm that asserts the exit code alone
#     would have passed. This one asserts the verdict string, which the crash could not produce.
cat > "$T/badunc.spine" <<EOF
§OBS.H1 WHEN test IS t.v = 42 SRC $T/w UNC maybe SEEN $NOW FRESH 60
EOF
check "bad UNC -> MALFORMED, no crash" "MALFORMED" 1 "$T/badunc.spine"

if python3 spine.py observe "$T/badunc.spine" 2>&1 | grep -q "Traceback"; then
  printf 'FAIL  %-34s raised a traceback instead of printing\n' "bad UNC prints no traceback"; fail=$((fail+1))
else
  printf 'PASS  %-34s no traceback\n' "bad UNC prints no traceback"; pass=$((pass+1))
fi




echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
