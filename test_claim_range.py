#!/usr/bin/env python3
"""CLI regressions for claimed-value admission under declared MIN/MAX limits.

Synthetic temporary sources only. SPINE_CHECKER_UNDER_TEST can target an older
checker to verify the regressions fail before the claim-range guard existed.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CHECKER = Path(os.environ.get('SPINE_CHECKER_UNDER_TEST', Path(__file__).with_name('spine.py')))


class ClaimRangeChecks(unittest.TestCase):
    def check_case(self, claim, raw, tolerance, limits, expected):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            surface = root / 'surface'
            surface.write_text(raw + '\n')
            now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            states = root / 'states.spine'
            states.write_text(
                f'§OBS.range WHEN diagnostic IS temperature_c = {claim} SRC {surface} '
                f'SCALE 0.001 UNC bounded TOL {tolerance} {limits} '
                f'SEEN {now} FRESH 3600\n')
            run = subprocess.run(
                [sys.executable, str(CHECKER), 'observe', str(states), '--json'],
                capture_output=True, text=True, timeout=10)
            self.assertEqual(run.stderr, '', run.stdout + run.stderr)
            response = json.loads(run.stdout)
            self.assertEqual(response['errors'], [], run.stdout)
            self.assertEqual(len(response['results']), 1, run.stdout)
            self.assertEqual(response['results'][0]['verdict'], expected, run.stdout)
            self.assertEqual(run.returncode, int(expected != 'OK'), run.stdout)

    def test_inside_range(self):
        self.check_case('33', '33000', '10', 'MIN 0 MAX 130', 'OK')

    def test_source_sentinel(self):
        self.check_case('-1', '-1000', '10', 'MIN 0 MAX 130', 'UNREADABLE')

    def test_claim_below_range(self):
        self.check_case('-1', '33000', '50', 'MIN 0 MAX 130', 'MALFORMED')

    def test_claim_above_range(self):
        self.check_case('131', '130000', '10', 'MIN 0 MAX 130', 'MALFORMED')

    def test_equal_min(self):
        self.check_case('0', '0', '10', 'MIN 0 MAX 130', 'OK')

    def test_equal_max(self):
        self.check_case('130', '130000', '10', 'MIN 0 MAX 130', 'OK')

    def test_min_only(self):
        self.check_case('-1', '33000', '50', 'MIN 0', 'MALFORMED')

    def test_max_only(self):
        self.check_case('131', '130000', '10', 'MAX 130', 'MALFORMED')

    def test_within_range_tolerance_edge(self):
        self.check_case('33', '32500', '0.5', 'MIN 0 MAX 130', 'OK')

    def test_text_claim_with_range(self):
        self.check_case('offline', 'offline', '10', 'MIN 0 MAX 130', 'MALFORMED')

    def test_text_claim_no_range_legacy(self):
        self.check_case('offline', 'offline', '10', '', 'OK')

    def test_nan_claim_with_range(self):
        self.check_case('nan', '33000', '10', 'MIN 0 MAX 130', 'MALFORMED')

    def test_infinite_claim_with_range(self):
        self.check_case('inf', '33000', '10', 'MIN 0 MAX 130', 'MALFORMED')


if __name__ == '__main__':
    unittest.main()
