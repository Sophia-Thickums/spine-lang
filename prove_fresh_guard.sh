#!/usr/bin/env bash
# Prove the nan/inf FRESH arms can go RED: remove the guard, the same input must stop being refused.
set -u
cd "$(dirname "$0")"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT

cp spine.py "$T/noguard.py"
python3 - "$T/noguard.py" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read()
a = s.find('        if d.get("fresh") is not None and (d["fresh"] != d["fresh"]')
b = s.find('        if d.get("fresh") is not None and d["fresh"] < 0:')
assert a > 0 and b > a, "guard block not located"
open(p, "w").write(s[:a] + s[b:])
print("removed %d chars of the nan/inf guard" % (b - a))
PY

printf '42' > "$T/w"
touch -d '-10 minutes' "$T/w"
NOW=$(date +%Y-%m-%dT%H:%M:%S)

cat > "$T/nan.spine" <<EOF
§OBS.F5 WHEN test IS t.v = 42 SRC $T/w UNC exact SEEN $NOW FRESH nan
EOF

echo "--- guard REMOVED, expect the frozen source to be wrongly called OK ---"
python3 "$T/noguard.py" observe "$T/nan.spine"
echo "exit=$?"

echo "--- guard PRESENT, expect MALFORMED and exit 1 ---"
python3 spine.py observe "$T/nan.spine"
echo "exit=$?"
