"""Adversarial gates for v1.3.2: reachability, genuine negative controls, route CAS safety."""
from __future__ import annotations

import hashlib
import difflib
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
        mutated = original.replace('return a + b', 'return a + b + 100')
        assert mutated != original
        try:
            f.file.write_text(mutated, encoding='utf8')
            result = subprocess.run([sys.executable, '-m', 'pytest', '-q', 'tests/test_real.py', f'--junitxml={negative_report}'], cwd=f.ws, capture_output=True, text=True)
            self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
            negative_log.write_text(result.stdout + '\n' + result.stderr, encoding='utf8')
        finally:
            f.file.write_text(original, encoding='utf8')
        def sha(path):
            return hashlib.sha256(path.read_bytes()).hexdigest()
        evidence_dir = f.docs / 'evidence'
        snapshot = evidence_dir / 'mutated-calc.py.snapshot'
        diff_file = evidence_dir / 'mutation.patch'
        snapshot.write_text(mutated, encoding='utf8')
        patch = ''.join(difflib.unified_diff(original.splitlines(keepends=True), mutated.splitlines(keepends=True),
                             fromfile='a/' + f.file.relative_to(f.ws).as_posix(),
                             tofile='b/' + f.file.relative_to(f.ws).as_posix()))
        diff_file.write_text(patch, encoding='utf8')
        restored_run = self.fixture.runs_data['runs'][-1] if hasattr(self.fixture, 'runs_data') else None
        if restored_run is None:
            restored_run = json.loads(self.fixture.runs.read_text(encoding='utf8'))['runs'][-1]
        actual_test_source = list(restored_run['test_sources'].values())[0]
        f.manifest_data['acceptance'][0]['counterfactual'] = {
            'mutation_source_path': f.file.relative_to(f.ws).as_posix(),
            'baseline_source_sha256': sha(f.file),
            'mutated_snapshot_path': snapshot.relative_to(f.ws).as_posix(),
            'mutated_source_sha256': sha(snapshot),
            'mutation_patch_path': diff_file.relative_to(f.ws).as_posix(),
            'mutation_patch_sha256': sha(diff_file),
            'negative_test_source_sha256': actual_test_source,
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
        self.assertIn('COUNTERFACTUAL_MUTATION_ARTIFACTS_LINKED_HUMAN_REVIEW_REQUIRED', checked.stdout)
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

    def test_forged_negative_via_changed_expectation_with_no_production_mutation_rejected(self):
        """Reproduce the exact v1.3.2 review: red report from bad test only."""
        f=self.fixture
        target=f.ws/'tests'/'test_real.py'
        clean=target.read_text(encoding='utf8')
        report=f.docs/'evidence'/'negative-forged.xml'
        log=f.docs/'evidence'/'negative-forged.log'
        try:
            target.write_text(clean.replace('== 7', '== 107'), encoding='utf8')
            run=subprocess.run([sys.executable,'-m','pytest','-q','tests/test_real.py',f'--junitxml={report}'],cwd=f.ws,capture_output=True,text=True)
            self.assertNotEqual(run.returncode, 0)
            log.write_text(run.stdout+'\n'+run.stderr,encoding='utf8')
        finally:
            target.write_text(clean,encoding='utf8')
        def sha(x):return hashlib.sha256(x.read_bytes()).hexdigest()
        f.manifest_data['acceptance'][0]['counterfactual']={
            'test_id':'tests.test_real::test_add',
            'mutation_description':'Changed only test expectation from 7 to 107 and restored it',
            'negative_report_path':report.relative_to(f.ws).as_posix(),
            'negative_report_sha256':sha(report),
            'negative_log_path':log.relative_to(f.ws).as_posix(),
            'negative_log_sha256':sha(log),
            'restored_run_id':f.record_id,
        }
        f.write_manifest()
        self.assertTrue(any('生产源码变异' in e for e in validate_counterfactual_evidence(f.manifest,f.plan,f.ws)))

    def test_mutated_snapshot_tamper_and_patch_mismatch_rejected(self):
        self.attach_actual_negative_control()
        info=self.fixture.manifest_data['acceptance'][0]['counterfactual']
        patch=self.fixture.ws/info['mutation_patch_path']
        patch.write_text(patch.read_text(encoding='utf8')+'\n# bogus\n', encoding='utf8')
        info['mutation_patch_sha256']=hashlib.sha256(patch.read_bytes()).hexdigest()
        self.fixture.write_manifest()
        self.assertTrue(any('补丁' in x for x in validate_counterfactual_evidence(self.fixture.manifest,self.fixture.plan,self.fixture.ws)))

    def test_mutating_test_file_instead_of_production_rejected(self):
        self.attach_actual_negative_control()
        info=self.fixture.manifest_data['acceptance'][0]['counterfactual']
        info['mutation_source_path']='tests/test_real.py'
        self.fixture.write_manifest()
        self.assertTrue(any('生产源码' in x for x in validate_counterfactual_evidence(self.fixture.manifest,self.fixture.plan,self.fixture.ws)))


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
