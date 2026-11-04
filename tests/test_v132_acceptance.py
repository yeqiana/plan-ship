"""Adversarial gates for v1.3.2: reachability, genuine negative controls, route CAS safety."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))
from route_manager import manage, START
from test_report import _python_source_has_assertion, _java_source_has_assertion
from validate_evidence import validate_counterfactual_evidence
import tests.test_tools as fixture_mod


class DeadAssertionTests(unittest.TestCase):
    def test_python_dead_code_and_short_circuit_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / 'calc.py').write_text('def add(a,b): return a+b\n', encoding='utf8')
            test = ws / 'test_calc.py'
            failing = (
                'if False:\n        assert add(3,4) == 7\n    assert True',
                'assert add(3,4) == 7 or (1+1 == 2)',
                'if (2 * 3 == 7):\n        assert add(3,4) == 7\n    assert True',
                'return\n    assert add(3,4)==7',
                'while False:\n        assert add(3,4)==7\n    assert True',
            )
            for case in failing:
                with self.subTest(case=case):
                    test.write_text('from calc import add\n\ndef test_total():\n    ' + case + '\n', encoding='utf8')
                    self.assertFalse(_python_source_has_assertion(test, 'test_total', ws))
            test.write_text('from calc import add\ndef test_total():\n    assert add(3,4)==7\n', encoding='utf8')
            self.assertTrue(_python_source_has_assertion(test, 'test_total', ws))

    def test_real_pytest_green_even_if_business_is_wrong_but_scan_rejects(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / 'calc.py').write_text('def add(a,b): return 999\n', encoding='utf8')
            test = ws / 'test_calc.py'
            test.write_text('from calc import add\ndef test_total():\n    if False:\n        assert add(3,4) == 7\n    assert True\n', encoding='utf8')
            run = subprocess.run([sys.executable, '-m', 'pytest', '-q', 'test_calc.py'], cwd=ws, capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stdout + run.stderr)
            self.assertFalse(_python_source_has_assertion(test, 'test_total', ws))

    def test_java_dead_branch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'CalcTest.java'
            path.write_text('class CalcTest { @Test void testSum(){ if(false){ assertEquals(7,service.calculate(3,4)); } assertTrue(true); } }')
            self.assertFalse(_java_source_has_assertion(path, 'testSum'))
            path.write_text('class CalcTest { @Test void testSum(){ assertEquals(7,service.calculate(3,4)); } }')
            self.assertTrue(_java_source_has_assertion(path, 'testSum'))


class CounterfactualEvidenceTests(unittest.TestCase):
    def setUp(self):
        # Reuse a real framework-run fixture; never substitute fake PASS JSON.
        self.fixture = fixture_mod.EvidenceTests(methodName='test_valid_evidence')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_consistency_is_not_acceptance(self):
        self.assertEqual([], self.fixture.check())
        errors = validate_counterfactual_evidence(self.fixture.manifest, self.fixture.plan, self.fixture.ws)
        self.assertTrue(any('缺少反事实' in x for x in errors), errors)

    def attach_actual_negative_control(self):
        f = self.fixture
        original = f.file.read_text(encoding='utf8')
        negative_report = f.docs / 'evidence' / 'negative.xml'
        negative_log = f.docs / 'evidence' / 'negative.log'
        try:
            f.file.write_text(original.replace('return a + b', 'return a + b + 100'), encoding='utf8')
            result = subprocess.run([sys.executable, '-m', 'pytest', '-q', 'tests/test_real.py', f'--junitxml={negative_report}'], cwd=f.ws, capture_output=True, text=True)
            self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
            negative_log.write_text(result.stdout + '\n' + result.stderr, encoding='utf8')
        finally:
            f.file.write_text(original, encoding='utf8')
        def sha(path):
            return hashlib.sha256(path.read_bytes()).hexdigest()
        f.manifest_data['acceptance'][0]['counterfactual'] = {
            'test_id': 'tests.test_real::test_add',
            'mutation_description': 'Force add(3,4) to return 107 instead of 7, then restore source',
            'negative_report_path': negative_report.relative_to(f.ws).as_posix(),
            'negative_report_sha256': sha(negative_report),
            'negative_log_path': negative_log.relative_to(f.ws).as_posix(),
            'negative_log_sha256': sha(negative_log),
            'restored_run_id': f.record_id,
        }
        f.write_manifest()
        return negative_report, negative_log

    def test_real_mutation_failure_and_restoration_accepted_as_evidence_only(self):
        self.attach_actual_negative_control()
        self.assertEqual([], validate_counterfactual_evidence(self.fixture.manifest, self.fixture.plan, self.fixture.ws))

    def test_cli_never_calls_consistency_business_acceptance(self):
        f = self.fixture
        base = [sys.executable, str(ROOT / 'scripts' / 'validate_evidence.py'),
                '--workspace', str(f.ws), '--plan', str(f.plan), '--manifest', str(f.manifest)]
        consistency = subprocess.run(base, capture_output=True, text=True, cwd=f.ws)
        self.assertEqual(0, consistency.returncode, consistency.stdout + consistency.stderr)
        self.assertIn('CONSISTENCY_PASS_ACCEPTANCE_NOT_VERIFIED', consistency.stdout)
        missing = subprocess.run(base + ['--gate', 'acceptance'], capture_output=True, text=True, cwd=f.ws)
        self.assertNotEqual(0, missing.returncode)
        self.assertIn('缺少反事实失败证据', missing.stdout)
        self.attach_actual_negative_control()
        checked = subprocess.run(base + ['--gate', 'acceptance'], capture_output=True, text=True, cwd=f.ws)
        self.assertEqual(0, checked.returncode, checked.stdout + checked.stderr)
        self.assertIn('COUNTERFACTUAL_EVIDENCE_CHECK_PASS_HUMAN_REVIEW_REQUIRED', checked.stdout)
        self.assertNotIn('ACCEPTANCE_PASS', checked.stdout)

    def test_negative_test_wrong_id_or_tamper_blocks(self):
        _, log = self.attach_actual_negative_control()
        self.fixture.manifest_data['acceptance'][0]['counterfactual']['test_id'] = 'tests.test_real::fake'
        self.fixture.write_manifest()
        self.assertTrue(validate_counterfactual_evidence(self.fixture.manifest, self.fixture.plan, self.fixture.ws))
        self.fixture.manifest_data['acceptance'][0]['counterfactual']['test_id'] = 'tests.test_real::test_add'
        self.fixture.write_manifest()
        log.write_text('tampered', encoding='utf8')
        self.assertTrue(any('哈希' in x for x in validate_counterfactual_evidence(self.fixture.manifest, self.fixture.plan, self.fixture.ws)))


class NoOverwriteRouteTests(unittest.TestCase):
    def test_existing_user_rules_produce_patch_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            path = home / '.codex' / 'AGENTS.md'; path.parent.mkdir()
            user = '# My important rules\nNever delete data\n'
            path.write_text(user)
            status = manage(home, 'install', ('codex',))['codex']
            self.assertEqual('MANUAL_PATCH_REQUIRED', status['state'])
            self.assertFalse(status['changed'])
            self.assertIn(START, status['route_snippet'])
            self.assertEqual(user, path.read_text())
            self.assertFalse(path.with_name('AGENTS.md.plan-ship.backup').exists())
            self.assertEqual('unchanged', manage(home, 'remove', ('codex',))['codex']['state'])
            self.assertEqual(user, path.read_text())

    def test_missing_file_exclusively_created(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            result = manage(home, 'install', ('claude',))['claude']
            self.assertTrue(result['changed'])
            self.assertIn(START, (home / '.claude' / 'CLAUDE.md').read_text())
            self.assertEqual('unchanged', manage(home, 'install', ('claude',))['claude']['state'])
