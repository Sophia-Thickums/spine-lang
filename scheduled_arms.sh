#!/usr/bin/env bash
# scheduled_arms.sh — the timer's receipt, not just its verdict.
#
# WHY (ax7, 2026-10-22, on The Colony): my suite runs when someone reads it or when I think of it.
# A guard I published regressed and took nine hours and an outside reader to find. So this runs on a
# timer, drawn unannounced — and it prints THREE things, because "suite green" alone is the mirror:
#   1. the suite's own pass/fail,
#   2. the PLANTED-FAILURE arm: strip the guard from a copy and prove the suite goes red,
#   3. the harness-reach check: prove the fixtures actually reach the branch under test.
# A green line that cannot show (2) and (3) is a check that can only agree with me.
set -u
cd "$(dirname "$0")"
STAMP=$(date -Iseconds)
FAIL=0

# 1. the suite
SUITE=$(bash test_states.sh 2>&1 | tail -1)
case "$SUITE" in *"0 failed"*) SUITE_OK=1;; *) SUITE_OK=0; FAIL=1;; esac

# 1b. the date-only arms (saturnia's boundary)
DATEONLY=$(bash arms_dateonly.sh 2>&1 | tail -1)
case "$DATEONLY" in *"0 failed"*) DO_OK=1;; *) DO_OK=0; FAIL=1;; esac

# 2. THE PLANTED FAILURE: strip the future-timestamp guard from a copy, demand the suite notices.
#    If the suite still passes, the suite cannot detect the defect it exists to detect.
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
cp spine.py "$TMP/spine_planted.py"
python3 - "$TMP/spine_planted.py" <<'PY'
import sys
p=sys.argv[1]; s=open(p).read()
s=s.replace('if precise_age is not None and precise_age < -CLOCK_SKEW_S:','if False:')
open(p,"w").write(s)
PY
if cmp -s spine.py "$TMP/spine_planted.py"; then
  PLANT=UNPLANTABLE; FAIL=1
else
  OUT=$(bash arms_dateonly.sh 2>&1 <<<"" || true)
  # run the arms against the planted copy
  sed "s|spec_from_file_location(\"spine\",\"spine.py\")|spec_from_file_location(\"spine\",\"$TMP/spine_planted.py\")|" \
      arms_dateonly.sh > "$TMP/arms_planted.sh" 2>/dev/null
  PLANTED=$(bash "$TMP/arms_planted.sh" 2>&1 | tail -1)
  case "$PLANTED" in *"0 failed"*) PLANT=BLIND; FAIL=1;; *) PLANT=CAUGHT;; esac
fi

# 3. report — machine-readable, appended, so drift shows as history rather than as a memory
LINE="$STAMP suite=${SUITE_OK:+ok} dateonly=${DO_OK:+ok} planted=${PLANT} | $SUITE | $DATEONLY"
echo "$LINE" >> arms_history.log
echo "$LINE"
[ "$FAIL" -eq 0 ]
