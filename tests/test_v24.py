"""v2.4 routes, test material checks and reader-oriented explanations."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from route_manager import manage, update_text, START, END
from test_input_probe import probe
from plain_quality import evaluate
from doc_registry import init,publish,verify_file
from tests.test_v22 import plain as good_plain, tech


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name)
    def test_absent_is_check_only(self):
        result=manage(self.home,'check')
        self.assertEqual('missing',result['codex']['state'])
        self.assertFalse((self.home/'.codex').exists())
    def test_install_returns_manual_patch_when_user_rules_already_exist(self):
        path=self.home/'.codex'/'AGENTS.md';path.parent.mkdir()
        path.write_text('# 用户已有的永久规则\n\n只使用本地 Runner。\n',encoding='utf8')
        before=path.read_text(encoding='utf8')
        result=manage(self.home,'install',('codex',))['codex']
        self.assertEqual('MANUAL_PATCH_REQUIRED',result['state'])
        self.assertIn(START,result['route_snippet'])
        self.assertEqual(before,path.read_text(encoding='utf8'))
        self.assertFalse(path.with_name(path.name+'.plan-ship.backup').exists())
        # Missing route files can be created exclusively without overwriting anything.
        manage(self.home,'install',('claude',))
        self.assertIn(START,(self.home/'.claude'/'CLAUDE.md').read_text(encoding='utf8'))
        self.assertEqual('unchanged',manage(self.home,'install',('claude',))['claude']['state'])
    def test_corrupt_markers_rejected(self):
        with self.assertRaisesRegex(ValueError,'标记'):
            update_text('私有指令\n'+START,'install')
    def test_claude_install_and_remove(self):
        manage(self.home,'install',('claude',))
        self.assertTrue((self.home/'.claude'/'CLAUDE.md').is_file())
        self.assertFalse((self.home/'.codex').exists())
        result=manage(self.home,'remove',('claude',))['claude']
        self.assertEqual('MANUAL_PATCH_REQUIRED',result['state'])
        self.assertIn(START,(self.home/'.claude'/'CLAUDE.md').read_text())
    def test_route_symlink_refused(self):
        folder=self.home/'.codex';folder.mkdir()
        target=self.home/'outside';target.write_text('用户文件',encoding='utf8')
        try:(folder/'AGENTS.md').symlink_to(target)
        except (OSError,NotImplementedError): self.skipTest('OS symlink restricted')
        with self.assertRaisesRegex(ValueError,'符号链接'):
            manage(self.home,'install',('codex',))
        self.assertEqual('用户文件',target.read_text(encoding='utf8'))

class FixtureProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.ws=Path(self.tmp.name)/'project';self.ws.mkdir()
    def test_no_dir_does_not_prompt(self):
        value=probe(self.ws)
        self.assertEqual('OPTIONAL_ABSENT',value['status']);self.assertFalse(value['ask_user'])
    def test_missing_essential_prompts(self):
        value=probe(self.ws,['chat-history.json'])
        self.assertEqual('BLOCKED_MISSING_REQUIRED',value['status']);self.assertTrue(value['ask_user'])
    def test_present_file_sha_and_missing_remainder(self):
        d=self.ws/'test-dir';d.mkdir();(d/'sample.json').write_text('{"ok":1}',encoding='utf8')
        value=probe(self.ws,['sample.json','missing.json'])
        self.assertEqual(['missing.json'],value['missing'])
        self.assertEqual(64,len(value['files'][0]['sha256']))
    def test_sensitive_excluded(self):
        d=self.ws/'test-dir';d.mkdir();(d/'secret.key').write_text('private')
        value=probe(self.ws)
        self.assertEqual('SENSITIVE_SKIPPED',value['files'][0]['status'])
        self.assertNotIn('sha256',value['files'][0])
    def test_traversal_rejected(self):
        value=probe(self.ws,['../secrets.json']);self.assertEqual('BLOCKED',value['status'])
    def test_symlink_rejected(self):
        d=self.ws/'test-dir';d.mkdir(); external=self.ws/'ext';external.write_text('private')
        try:(d/'link.txt').symlink_to(external)
        except (OSError,NotImplementedError):self.skipTest('OS symlink restricted')
        self.assertEqual('BLOCKED',probe(self.ws)['status'])

class ReaderQualityTests(unittest.TestCase):
    def test_realistic_explanation_passes(self):
        self.assertEqual([],evaluate(tech(),good_plain()))
    def test_only_markdown_title_and_mermaid_rejected(self):
        errors=evaluate(tech(),'# 解释\n\n## 图解\n```mermaid\nflowchart LR\n A-->B\n```')
        self.assertTrue(any('章节' in x for x in errors))
    def test_mismatch_status_rejected(self):
        broken=good_plain().replace('未执行','已成功').replace('BLOCKED','成功').replace('未通过','通过')
        errors=evaluate(tech(),broken)
        self.assertTrue(any('状态' in x for x in errors))
    def test_unexplained_chart_rejected(self):
        broken=good_plain().replace('图解说明：图中的箭头表示','该画面的节点顺序就是')
        errors=evaluate(tech(),broken)
        self.assertTrue(any('文字解释' in x for x in errors))
    def test_verifier_rejects_low_quality_even_if_paired(self):
        ws=Path(tempfile.mkdtemp());self.addCleanup(lambda:__import__('shutil').rmtree(ws))
        folder=init(ws,'示例需求')
        a=folder/'.drafts'/'tech.md';b=folder/'.drafts'/'plain.md'
        a.write_text(tech(),encoding='utf8')
        b.write_text('# 不好懂\n\n## 图解\n\n'+('只需要照做。'*35),encoding='utf8')
        final,_=publish(ws,'示例需求','plan','示例计划',a,b)
        self.assertTrue(any('大白话解释缺少' in err for err in verify_file(final,ws)))

if __name__=='__main__':unittest.main()
