"""Independent regression for v1.3.0 review findings (v1.3.1 remediation)."""
from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import doc_registry as registry
import preflight
import route_manager
from plain_quality import evaluate, main as plain_main
from test_report import _java_source_has_assertion, _python_source_has_assertion, validate_test_artifacts
from tests.test_v22 import tech, plain


class AssertionIntegrityTests(unittest.TestCase):
    def test_self_comparison_blocks_even_when_real_pytest_stays_green_after_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            ws=Path(temp)
            (ws/'calc.py').write_text('def add(a,b): return a+b\n',encoding='utf8')
            source=ws/'test_calc.py'
            source.write_text('from calc import add\n\ndef test_total():\n    assert add(3,4) == add(3,4)\n',encoding='utf8')
            case_map=ws/'case-map.json'
            case_map.write_text(json.dumps({'schema_version':'1.0','cases':{'TC-100':[{'test_id':'test_calc::test_total','source':'test_calc.py'}]}}),encoding='utf8')
            report=ws/'report.xml'
            for implementation in ('def add(a,b): return a+b\n','def add(a,b): return a+b+99\n'):
                (ws/'calc.py').write_text(implementation,encoding='utf8')
                run=subprocess.run([sys.executable,'-m','pytest','-q','test_calc.py',f'--junitxml={report}'],cwd=ws,capture_output=True,text=True)
                self.assertEqual(0,run.returncode,run.stdout+run.stderr)
                self.assertFalse(_python_source_has_assertion(source,'test_total',ws))
                problems,_=validate_test_artifacts(report,case_map,ws,{'TC-100'})
                self.assertTrue(any('没有可识别的断言' in p for p in problems),problems)

    def test_production_alias_self_comparison_and_two_calls_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=Path(tmp)
            (ws/'calc.py').write_text('def add(a,b):return a+b\n',encoding='utf8')
            test=ws/'test_calc.py'
            rejected=('assert add(3,4)==add(3,4)',
                      'actual=add(3,4)\n    assert actual == actual',
                      'left=add(3,4)\n    right=add(3,4)\n    assert left==right',
                      'actual=add(3,4)\n    duplicate=actual\n    assert actual==duplicate')
            for case in rejected:
                with self.subTest(case=case):
                    test.write_text('from calc import add\n\ndef test_total():\n    '+case+'\n',encoding='utf8')
                    self.assertFalse(_python_source_has_assertion(test,'test_total',ws))
            test.write_text('from calc import add\n\ndef test_total():\n    assert add(3,4)==7\n',encoding='utf8')
            self.assertTrue(_python_source_has_assertion(test,'test_total',ws))

    def test_java_constant_and_self_comparison_rejected_but_independent_oracle_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'CalculatorTest.java'
            cases={
                '@Test void testSum(){ service.calculate(3,4); assertEquals(1,1); }':False,
                '@Test void testSum(){ assertEquals(service.calculate(3,4),service.calculate(3,4)); }':False,
                '@Test void testSum(){ int actual=service.calculate(3,4); assertEquals(actual,actual); }':False,
                '@Test void testSum(){ int actual=service.calculate(3,4); int duplicate=actual; assertEquals(actual,duplicate); }':False,
                '@Test void testSum(){ int actual=service.calculate(3,4); assertEquals(7,actual); }':True,
                '@Test void testSum(){ assertEquals(7,service.calculate(3,4)); }':True,
                '@Test void testSum(){ assertEquals(7,service.calculate(3,4),"explanation"); }':True,
            }
            for code,wanted in cases.items():
                with self.subTest(code=code):
                    p.write_text('class CalculatorTest { '+code+' }',encoding='utf8')
                    self.assertEqual(wanted,_java_source_has_assertion(p,'testSum'))


class PlainReviewTests(unittest.TestCase):
    def test_parenthetical_keyword_dump_not_considered_business_explanation(self):
        doc=tech('IM历史消息冷热库拆分').replace('核心业务概念：新需求','核心业务概念：历史消息，冷库，归档')
        bogus=plain('模板演示').replace('改动后：用户可以使用新增能力','改动后：用户可以使用新增能力（历史消息、冷库、归档）')
        self.assertTrue(evaluate(doc,bogus), 'keyword dump must not pass')
        self.assertTrue(any('业务相关性' in m for m in evaluate(doc,bogus)))

    def test_cli_never_claims_plain_semantic_or_reader_validation_from_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'tech.md';b=Path(tmp)/'plain.md'
            a.write_text(tech(),encoding='utf8');b.write_text(plain(),encoding='utf8')
            with patch.object(sys,'argv',['plain_quality.py','--technical',str(a),'--plain',str(b)]),redirect_stdout(io.StringIO()) as out:
                code=plain_main()
            data=json.loads(out.getvalue())
            self.assertEqual(0,code)
            self.assertEqual('STRUCTURE_PASS_SEMANTIC_REVIEW_REQUIRED',data['status'])
            self.assertEqual('REVIEW_REQUIRED',data['semantic_review'])
            self.assertEqual('NOT_VALIDATED',data['reader_validation'])


class RouterConcurrencyTests(unittest.TestCase):
    def test_existing_user_rules_are_never_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)
            p=home/'.codex'/'AGENTS.md';p.parent.mkdir()
            p.write_text('# Rule A\n',encoding='utf8')
            result=route_manager.manage(home,'install',('codex',))['codex']
            self.assertEqual('MANUAL_PATCH_REQUIRED',result['state'])
            self.assertEqual('# Rule A\n',p.read_text(encoding='utf8'))
            self.assertFalse((p.parent/'.plan-ship-route.lock').exists())
            self.assertFalse((p.parent/'AGENTS.md.plan-ship.backup').exists())

    def test_second_writer_fails_when_cooperative_lock_held(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)
            directory=home/'.codex';directory.mkdir()
            lock=directory/'.plan-ship-route.lock';lock.write_text('other process',encoding='utf8')
            with self.assertRaisesRegex(ValueError,'BLOCKED_LOCK_CONFLICT'):
                route_manager.manage(home,'install',('codex',))
            self.assertEqual('other process',lock.read_text(encoding='utf8'))


class PreflightAccuracyTests(unittest.TestCase):
    def test_no_main_skill_reports_missing_not_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=Path(tmp)
            root=ws/'skills';root.mkdir()
            with patch('discover_skills.roots',return_value=[('codex-user',root)]):
                report=preflight.check(ws,host='codex')
            self.assertFalse(report['core_ready'])
            self.assertTrue(report['core_has_no_external_dependencies'])
            self.assertEqual('NOT_FOUND',report['plan_ship_activated'])
            self.assertTrue(report['preflight_status'].startswith('PLAN_SHIP_NOT_FOUND'))

    def test_visible_main_skill_still_does_not_prove_host_invocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=Path(tmp);root=ws/'skills';(root/'plan-ship').mkdir(parents=True)
            (root/'plan-ship'/'SKILL.md').write_text('---\nname: plan-ship\n---\n',encoding='utf8')
            with patch('discover_skills.roots',return_value=[('codex-user',root)]):
                report=preflight.check(ws,host='codex')
            self.assertFalse(report['core_ready'])
            self.assertEqual('NOT_VERIFIED',report['plan_ship_activated'])
            self.assertEqual(1,len(report['plan_ship_candidates']))


class RecoveryBeforeJournalTests(unittest.TestCase):
    def test_prepare_only_crash_recovers_when_original_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=Path(tmp)/'project';folder=registry.init(ws,'业务方案')
            source=folder/'.document-index.json'
            before=registry.digest(source.read_bytes())
            txn=folder/registry.TRANSACTION;txn.mkdir()
            files=[{'path': '.document-index.json','before':before,'after':'x'*64,'backup':'backup-0.bin'},
                   {'path':'1. 业务方案.md','before':None,'after':'y'*64,'backup':'backup-1.bin'},
                   {'path':'大白话解释/1. 业务方案.md','before':None,'after':'z'*64,'backup':'backup-2.bin'}]
            (txn/'prepare.json').write_text(json.dumps({'schema':'prepare-v1','files':files},ensure_ascii=False),encoding='utf8')
            (txn/'backup-0.bin').write_bytes(source.read_bytes())
            self.assertEqual('PREPARE_ABORTED_WITHOUT_TARGET_WRITES',registry.recover_transaction(folder))
            self.assertFalse(txn.exists())
            self.assertEqual(before,registry.digest(source.read_bytes()))

    def test_manual_change_or_unknown_file_blocks_orphan_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=Path(tmp)/'project';folder=registry.init(ws,'业务方案')
            txn=folder/registry.TRANSACTION;txn.mkdir()
            entry={'path':'.document-index.json','before':registry.digest((folder/'.document-index.json').read_bytes()),'after':'x'*64,'backup':'backup-0.bin'}
            blob={'schema':'prepare-v1','files':[entry,{'path':'1. 业务方案.md','before':None,'after':'y'*64,'backup':'backup-1.bin'}, {'path':'大白话解释/1. 业务方案.md','before':None,'after':'z'*64,'backup':'backup-2.bin'}]}
            (txn/'prepare.json').write_text(json.dumps(blob,ensure_ascii=False),encoding='utf8')
            (folder/'.document-index.json').write_text('user modified',encoding='utf8')
            with self.assertRaises(registry.DocumentError):registry.recover_transaction(folder)
            self.assertTrue(txn.exists())
            # unrelated content in orphan must not be deleted even when original matches
            (folder/'.document-index.json').write_text('{"recovered":true}',encoding='utf8')
            (txn/'my-own-note.txt').write_text('KEEP',encoding='utf8')
            with self.assertRaises(registry.DocumentError):registry.recover_transaction(folder)
            self.assertTrue((txn/'my-own-note.txt').exists())

    def test_crash_during_journal_temp_can_recover_without_deleting_user_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=Path(tmp)/'project';folder=registry.init(ws,'业务方案')
            original=folder/'.document-index.json'
            before=registry.digest(original.read_bytes())
            txn=folder/registry.TRANSACTION;txn.mkdir()
            entries=[{'path':'.document-index.json','before':before,'after':'a'*64,'backup':'backup-0.bin'},
                     {'path':'1. 业务方案.md','before':None,'after':'b'*64,'backup':'backup-1.bin'},
                     {'path':'大白话解释/1. 业务方案.md','before':None,'after':'c'*64,'backup':'backup-2.bin'}]
            (txn/'prepare.json').write_text(json.dumps({'schema':'prepare-v1','files':entries}),encoding='utf8')
            (txn/'.journal.json.12345.abcdef01.tmp').write_text('unfinished journal',encoding='utf8')
            (txn/'.restore-abcdef0123456789').write_bytes(b'partial-backup')
            self.assertEqual('PREPARE_ABORTED_WITHOUT_TARGET_WRITES',registry.recover_transaction(folder))
            self.assertEqual(before,registry.digest(original.read_bytes()))
            self.assertFalse(txn.exists())

    def test_crash_before_prepare_rename_only_known_temp_is_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=registry.init(Path(tmp)/'project','业务方案')
            txn=folder/registry.TRANSACTION;txn.mkdir()
            (txn/'.prepare.json.54321.abcdef01.tmp').write_bytes(b'incomplete prepare')
            self.assertEqual('PREPARE_TEMP_ABORTED',registry.recover_transaction(folder))
            self.assertFalse(txn.exists())

    def test_empty_interrupted_prepare_is_cleanable_but_legacy_orphan_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws=Path(tmp)/'project';folder=registry.init(ws,'业务方案')
            txn=folder/registry.TRANSACTION;txn.mkdir()
            self.assertEqual('EMPTY_PREPARE_ABORTED',registry.recover_transaction(folder))
            txn.mkdir();(txn/'backup-0.bin').write_bytes(b'legacy')
            with self.assertRaisesRegex(registry.DocumentError,'journal/prepare'):
                registry.recover_transaction(folder)
            self.assertTrue((txn/'backup-0.bin').exists())

if __name__=='__main__':unittest.main()
