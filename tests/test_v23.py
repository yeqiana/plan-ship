"""Independent regression/adversarial gates added after the v2.2 review."""
from __future__ import annotations
import json
import sys
import tempfile
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import doc_registry as reg
from test_report import validate_test_artifacts
from preflight import check
from tests.test_v22 import tech, plain


class DirectoryAndTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ws = Path(self.temp.name) / 'workspace'
        self.ws.mkdir()
        self.name = '拆分改造'

    def prepare(self):
        folder = reg.init(self.ws, self.name)
        a, b = folder / '.drafts' / 'plan.md', folder / '.drafts' / 'explain.md'
        a.write_text(tech('方案初稿'), encoding='utf-8')
        b.write_text(plain('方案初稿'), encoding='utf-8')
        return folder, a, b

    def publish(self, a, b):
        return reg.publish(self.ws, self.name, 'plan', '正式方案', a, b)

    def test_docs_symlink_external_blocks_all(self):
        external = Path(self.temp.name) / 'outside'
        external.mkdir()
        (self.ws / '.idea').mkdir()
        (self.ws / '.idea' / 'docs').symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(reg.DocumentError, '链接|junction'):
            reg.init(self.ws, self.name)
        self.assertTrue(reg.verify_all(self.ws, self.name))
        self.assertEqual([], list(external.iterdir()))

    def test_idea_and_plan_symlink_blocks(self):
        ext = Path(self.temp.name) / 'external'; ext.mkdir()
        (self.ws / '.idea').symlink_to(ext, target_is_directory=True)
        with self.assertRaises(reg.DocumentError):
            reg.init(self.ws, self.name)
        (self.ws / '.idea').unlink()
        folder = reg.init(self.ws, self.name)
        folder.rmdir() if not list(folder.iterdir()) else None
        # A new plan name alias is forbidden even when it points inside docs.
        (self.ws / '.idea' / 'docs' / '别名').symlink_to(folder, target_is_directory=True)
        with self.assertRaises(reg.DocumentError):
            reg.init(self.ws, '别名')

    def test_windows_control_char_rejected(self):
        for name in ('含\tTab', '控制\x1f字符', 'DEL\x7f字符'):
            with self.subTest(name=repr(name)), self.assertRaises(reg.DocumentError):
                reg.init(self.ws, name)

    def test_each_write_failure_restores_old_docs_and_idempotency(self):
        for fail_index in (0, 1, 2):
            with self.subTest(fail_index=fail_index):
                folder, a, b = self.prepare() if fail_index == 0 else (folder, a, b)
                original = self.publish(a, b)
                base_bytes = [f.read_bytes() for f in (*original, folder / reg.INDEX)]
                a.write_text(tech('方案新版本') + '\n新一轮分析包含旧版本兼容验证。\n', encoding='utf-8')
                b.write_text(plain('方案新版本') + '\n新增故障排查与清理步骤。\n', encoding='utf-8')
                atomic = reg.atomic
                def broken(path, data):
                    target_names = {original[0], original[1], folder / reg.INDEX}
                    idx = [original[0], original[1], folder / reg.INDEX].index(path) if path in target_names else -1
                    if idx == fail_index:
                        raise OSError('injected failure')
                    return atomic(path, data)
                with patch.object(reg, 'atomic', side_effect=broken):
                    with self.assertRaises(OSError):
                        self.publish(a, b)
                self.assertEqual(base_bytes, [f.read_bytes() for f in (*original, folder / reg.INDEX)])
                self.assertEqual([], reg.verify_all(self.ws, self.name))
                updated = self.publish(a, b)
                self.assertEqual(original, updated)
                self.assertEqual([], reg.verify_all(self.ws, self.name))

    def test_partial_failure_on_new_doc_rolls_back_and_keeps_number(self):
        folder, a, b = self.prepare()
        orig = reg.atomic
        with patch.object(reg, 'atomic', side_effect=lambda p, data: (_ for _ in ()).throw(OSError('injected')) if p.parent.name == '大白话解释' else orig(p, data)):
            with self.assertRaises(OSError):
                self.publish(a, b)
        self.assertEqual([], reg.verify_all(self.ws, self.name))
        published, explanation = self.publish(a, b)
        self.assertTrue(published.name.startswith('1. '))
        self.assertTrue(explanation.is_file())

    def test_recovery_rejects_external_edit_after_interruption(self):
        folder, a, b = self.prepare()
        original = self.publish(a, b)
        a.write_text(tech() + '\n新增兼容性证据，安全发布。', encoding='utf8')
        b.write_text(plain() + '\n新增验证步骤。', encoding='utf8')
        orig_atomic = reg.atomic
        with patch.object(reg, 'recover_transaction', side_effect=['CLEAN', reg.DocumentError('模拟异常中断')]):
            with patch.object(reg, 'atomic', side_effect=lambda p, data: (_ for _ in ()).throw(OSError('simulated')) if p == original[1] else orig_atomic(p, data)):
                with self.assertRaises(reg.DocumentError):
                    self.publish(a, b)
        self.assertTrue((folder / reg.TRANSACTION).is_dir())
        original[0].write_text('用户手工编辑，不可覆盖', encoding='utf8')
        with self.assertRaisesRegex(reg.DocumentError, '人工改动'):
            reg.init(self.ws, self.name)
        self.assertEqual('用户手工编辑，不可覆盖', original[0].read_text(encoding='utf8'))

    def test_interrupted_txn_recover_without_manual_changes(self):
        folder, a, b = self.prepare()
        original = self.publish(a, b)
        old = original[0].read_bytes()
        a.write_text(tech('重启后恢复版') + '\n新增可恢复检查。', encoding='utf8')
        b.write_text(plain('重启后恢复版') + '\n恢复说明完整。', encoding='utf8')
        atom = reg.atomic
        with patch.object(reg, 'recover_transaction', side_effect=['CLEAN', reg.DocumentError('模拟进程被中止')]):
            with patch.object(reg, 'atomic', side_effect=lambda path, data: (_ for _ in ()).throw(OSError('中止')) if path == original[1] else atom(path, data)):
                with self.assertRaises(reg.DocumentError):
                    self.publish(a, b)
        self.assertTrue(reg.verify_all(self.ws, self.name))
        with reg.exclusive(folder):
            self.assertEqual('ROLLED_BACK', reg.recover_transaction(folder))
        self.assertEqual(old, original[0].read_bytes())
        self.assertEqual([], reg.verify_all(self.ws, self.name))
        self.assertEqual(original, self.publish(a, b))
        self.assertEqual([], reg.verify_all(self.ws, self.name))


class ContentAndBusinessTests(unittest.TestCase):
    def test_preflight_reads_references_but_does_not_claim_agent_loaded(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'skills'
            for name in ('ai-coding-collaboration', 'intelligent-ui'):
                base = root / name
                (base / 'references').mkdir(parents=True)
                (base / 'SKILL.md').write_text('---\nname: ' + name + '\ndescription: test\n---\n# rules\n参见 references/usage.md', encoding='utf8')
                (base / 'references' / 'usage.md').write_text('# 真实规则内容', encoding='utf8')
            with patch('discover_skills.roots', return_value=[('codex-user', root)]):
                ready = check(Path(temp), load=True)
                self.assertEqual('READ_FILESYSTEM_CONTENT_AGENT_CONFIRMATION_REQUIRED', ready['preflight_status'])
                self.assertEqual(2, len(ready['skills']['intelligent-ui']['content_read']['files']))
                (root / 'intelligent-ui' / 'references' / 'usage.md').unlink()
                failed = check(Path(temp), load=True)
                self.assertEqual('BLOCKED_CONTENT_READ', failed['preflight_status'])

    def test_java_empty_assert_not_accepted_as_business_test(self):
        from test_report import _java_source_has_assertion
        with tempfile.TemporaryDirectory() as temp:
            f = Path(temp) / 'CalculatorTest.java'
            f.write_text('class CalculatorTest {\n @Test void testAdd(){ assertTrue(true); }\n}', encoding='utf8')
            self.assertFalse(_java_source_has_assertion(f, 'testAdd'))
            f.write_text('class CalculatorTest {\n @Test void testAdd(){ assertEquals(7, calculator.add(3,4)); }\n}', encoding='utf8')
            self.assertTrue(_java_source_has_assertion(f, 'testAdd'))

    def test_short_circuit_and_unrelated_assert_are_not_business_proofs(self):
        from tests.test_tools import EvidenceTests
        # Test the actual AST checker against a real application module.
        from test_report import _python_source_has_assertion
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp)
            (workspace / 'app.py').write_text('def compute(a):\n    return a * 3\n', encoding='utf8')
            test = workspace / 'test_business.py'
            for statement in ('assert True or compute(2) == 6', 'compute(2)\n    assert 1 == 1 or False', 'compute(2)\n    assert 2 * 3 == 6'):
                test.write_text('from app import compute\n\ndef test_behavior():\n    ' + statement + '\n', encoding='utf8')
                self.assertFalse(_python_source_has_assertion(test, 'test_behavior', workspace))
            test.write_text('from app import compute\n\ndef test_behavior():\n    assert compute(2) == 6\n', encoding='utf8')
            self.assertTrue(_python_source_has_assertion(test, 'test_behavior', workspace))
            # Confirm the real test becomes red if production logic is broken.
            (workspace / 'test_business.py').rename(workspace / 'test_behavior.py')
            good = subprocess.run([sys.executable, '-m', 'pytest', '-q', 'test_behavior.py'], cwd=workspace, capture_output=True, text=True)
            self.assertEqual(0, good.returncode, good.stdout + good.stderr)
            # Change the file length as well as behavior: CPython's timestamp+size pyc cache
            # can reuse stale bytecode if two subprocesses run within the same second on CI.
            (workspace / 'app.py').write_text('def compute(a):\n    return a * 400\n', encoding='utf8')
            bad = subprocess.run([sys.executable, '-m', 'pytest', '-q', 'test_behavior.py'], cwd=workspace, capture_output=True, text=True)
            self.assertNotEqual(0, bad.returncode, '变更真实业务结果后，测试必须失败')

class RealFrameRegression(unittest.TestCase):
    def test_real_pytest_short_circuit_fails_final_gate(self):
        # Reproduce the original reported exploit with a genuine pytest run,
        # not merely AST unit parsing.
        from tests.test_tools import EvidenceTests, run
        case = EvidenceTests('test_valid_evidence')
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.test_source.write_text('from app import add, sub\n\ndef test_add():\n    assert True or add(3,4)==7\n\ndef test_sub():\n    assert 1==1 or sub(5,3)==2\n', encoding='utf8')
        cmd = [sys.executable, str(SCRIPTS/'run_and_record.py'), '--workspace', str(case.ws), '--plan', str(case.plan),
               '--runs', str(case.runs), '--stage', 'integrated', '--cases', 'TC-207,TC-208',
               '--runner', 'pytest', '--report', '.idea/docs/验收方案/evidence/reports/{run_id}.xml',
               '--case-map', str(case.case_map), '--', sys.executable, '-m', 'pytest', '-q', 'tests/test_real.py', '--junitxml={report}']
        p = run(*cmd, cwd=case.ws)
        self.assertEqual(2, p.returncode, p.stdout + p.stderr)
        self.assertIn('没有可识别的断言', p.stdout)
        latest = json.loads(case.runs.read_text(encoding='utf8'))['runs'][-1]
        self.assertEqual('BLOCKED', latest['status'])
        for row in case.manifest_data['cases']:
            row['run_ids'] = [latest['run_id']]
        case.manifest_data['acceptance'][0]['run_ids'] = [latest['run_id']]
        case.write_manifest()
        self.assertTrue(case.check(), '不得将无效断言报告改名后当作最终验收')
