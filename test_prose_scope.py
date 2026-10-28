#!/usr/bin/env python3
"""CLI regressions for scoped prove examples and the lint group-unpack repair."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CHECKER = Path(os.environ.get('SPINE_CHECKER_UNDER_TEST', Path(__file__).with_name('spine.py')))


class ProseScopeChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name, value):
        path = self.root / name
        path.write_text(value)
        return path

    def law(self, pattern='^ALARM$', when='drafting', control='trigger=drafting text=quiet', extra=''):
        scope = '' if when is None else f', when="{when}"'
        clause = f'violation("SCOPE.01","{pattern}"{scope})' + extra
        text = '§SCOPE.01 WHEN drafting DO review NOT miss COST 1027:synthetic TEST ' + clause
        if control is not None:
            text += ' CONTROL ' + control
        return self.write('law.spine', text + '\n')

    def run_cli(self, command, law, path):
        result = subprocess.run([sys.executable, str(CHECKER), command, str(law), str(path)],
                                capture_output=True, text=True, timeout=10)
        self.assertNotIn('Traceback', result.stderr, result.stdout + result.stderr)
        return result.returncode, result.stdout

    def prove(self, law, plant):
        path = self.write('plants.json', json.dumps({'plants': [{'law': 'SCOPE.01', 'text': plant}]}))
        return self.run_cli('prove', law, path)

    def test_scoped_pair_proves(self):
        code, text = self.prove(self.law(), 'trigger=drafting text=ALARM')
        self.assertEqual(code, 0, text)
        self.assertIn('1/1 laws proved', text)

    def test_scoped_matching_control_is_refused(self):
        code, text = self.prove(self.law(control='trigger=drafting text=ALARM'), 'trigger=drafting text=ALARM')
        self.assertEqual(code, 1)
        self.assertIn('matches its DECLARED control', text)

    def test_scoped_match_all_pattern_is_refused(self):
        code, text = self.prove(self.law(pattern='.', control='trigger=plant text=ordinary compliant prose', when='plant'),
                                'trigger=plant text=ALARM')
        self.assertEqual(code, 1)
        self.assertIn('matches its DECLARED control', text)

    def test_out_of_scope_matching_control_cannot_prove(self):
        code, text = self.prove(self.law(pattern='.', control='trigger=control text=ordinary compliant prose', when='plant'),
                                'trigger=plant text=ALARM')
        self.assertEqual(code, 1)
        self.assertIn('outside the predicate', text)

    def test_unlabelled_scoped_plant_is_refused(self):
        code, text = self.prove(self.law(), 'ALARM')
        self.assertEqual(code, 1)
        self.assertIn('plant names no trigger', text)

    def test_unlabelled_scoped_control_is_refused(self):
        code, text = self.prove(self.law(control='quiet'), 'trigger=drafting text=ALARM')
        self.assertEqual(code, 1)
        self.assertIn('CONTROL names no trigger', text)

    def test_out_of_scope_positive_is_blind(self):
        code, text = self.prove(self.law(), 'trigger=unrelated text=ALARM')
        self.assertEqual(code, 1)
        self.assertIn('BLIND', text)

    def test_missing_control_stays_uncontrolled(self):
        code, text = self.prove(self.law(control=None), 'trigger=drafting text=ALARM')
        self.assertEqual(code, 1)
        self.assertIn('UNCONTROLLED', text)

    def test_existing_substring_scope_is_preserved(self):
        code, text = self.prove(self.law(control='trigger=after-drafting text=quiet'),
                                'trigger=before-drafting text=ALARM')
        self.assertEqual(code, 0, text)

    def test_case_insensitive_text_matching_is_preserved(self):
        code, text = self.prove(self.law(), 'trigger=drafting text=alarm')
        self.assertEqual(code, 0, text)

    def test_unscoped_literal_examples_are_preserved(self):
        code, text = self.prove(self.law(pattern='^trigger=', when=None, control='quiet'),
                                'trigger=drafting text=ALARM')
        self.assertEqual(code, 0, text)

    def test_unscoped_matching_control_is_refused(self):
        code, text = self.prove(self.law(when=None, control='ALARM'), 'ALARM')
        self.assertEqual(code, 1)
        self.assertIn('matches its DECLARED control', text)

    def test_invalid_later_clause_prevents_any_ratio(self):
        code, text = self.prove(self.law(extra='; unsupported("x")'), 'trigger=drafting text=ALARM')
        self.assertEqual(code, 1)
        self.assertIn('MALFORMED', text)
        self.assertNotIn('laws proved', text)

    def test_lint_positive_and_negative_do_not_crash(self):
        for when in [None, 'drafting']:
            law = self.law(when=when)
            for value, expected, message in [('ALARM', 1, 'RED'), ('quiet', 0, 'no law fires')]:
                with self.subTest(when=when, value=value):
                    code, text = self.run_cli('lint', law, self.write('draft.txt', value))
                    self.assertEqual(code, expected, text)
                    self.assertIn(message, text)

    def test_check_agrees_on_in_scope_positive_and_negative(self):
        law = self.law()
        for trigger, value, expected in [('drafting', 'ALARM', 1), ('drafting', 'quiet', 0), ('unrelated', 'ALARM', 0)]:
            with self.subTest(trigger=trigger, value=value):
                path = self.write('events.json', json.dumps([{'law': 'SCOPE.01', 'trigger': trigger, 'text': value}]))
                code, text = self.run_cli('check', law, path)
                self.assertEqual(code, expected, text)


if __name__ == '__main__':
    unittest.main()
