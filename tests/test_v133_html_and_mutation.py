"""PlanShip v1.3.3: plain-language HTML pairing and mutation provenance boundaries."""
from __future__ import annotations
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import doc_registry as reg
from plain_html import render, inline
from test_report import _python_source_has_assertion, _java_source_has_assertion
from tests.test_v22 import tech, plain


class HtmlPresentationTests(unittest.TestCase):
    def test_offline_html_escapes_unsafe_input_and_preserves_semantics(self):
        source='''# 大白话测试\n\n## 为什么\n\n这是 **真实状态**：未验证。<script>alert(1)</script>\n\n[安全页面](https://example.com) [危险地址](javascript:alert)\n\n| 用例 | 结果 |\n| --- | --- |\n| TC-001 | BLOCKED |\n\n```mermaid\nflowchart LR\nA-->B\n```\n'''
        result=render(source,'我的说明').decode()
        self.assertIn('<!DOCTYPE html>',result)
        self.assertIn('name="viewport"',result)
        self.assertIn('Content-Security-Policy',result)
        self.assertIn('<strong>真实状态</strong>',result)
        self.assertIn('未验证',result)
        self.assertIn('<table>',result)
        self.assertIn('&lt;script&gt;',result)
        self.assertNotIn('<script>',result)
        self.assertNotIn('href="javascript:',result)
        self.assertIn('离线文本表示',result)
        self.assertEqual(render(source,'我的说明'),render(source,'我的说明'))

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ws=Path(self.temp.name)/'workspace'
        self.folder=reg.init(self.ws,'示例业务')
        self.t=self.folder/'.drafts'/'plan.md'
        self.p=self.folder/'.drafts'/'plain.md'
        self.t.write_text(tech(),encoding='utf8')
        self.p.write_text(plain(),encoding='utf8')

    def publish(self):
        return reg.publish(self.ws,'示例业务','plan','实施与测试方案',self.t,self.p)

    def test_publishes_only_plain_html_not_technical(self):
        technical, explanation=self.publish()
        rendered=explanation.with_suffix('.html')
        self.assertTrue(rendered.is_file())
        self.assertFalse(technical.with_suffix('.html').exists())
        self.assertEqual([],reg.verify_all(self.ws,'示例业务'))
        self.assertEqual([x.name for x in explanation.parent.glob('*.html')],[rendered.name])
        self.assertIn('plan-ship-source-sha256',rendered.read_text(encoding='utf8'))

    def test_republish_updates_html_same_number_and_detects_missing_or_tampered(self):
        _,md=self.publish()
        html=md.with_suffix('.html')
        old=html.read_bytes()
        self.p.write_text(plain()+'\n## 补充\n仅用于核对旧功能风险。\n',encoding='utf8')
        self.publish()
        self.assertNotEqual(old,html.read_bytes())
        self.assertEqual([],reg.verify_all(self.ws,'示例业务'))
        html.write_text('manually changed',encoding='utf8')
        self.assertTrue(any('HTML' in x for x in reg.verify_all(self.ws,'示例业务')))
        with self.assertRaisesRegex(reg.DocumentError,'HTML'):
            self.publish()
        html.unlink()
        self.assertTrue(any('HTML' in x for x in reg.verify_all(self.ws,'示例业务')))

    def test_four_file_publish_rollback_on_html_error(self):
        original=reg.atomic
        def fault(path,content):
            if path.suffix == '.html':
                raise OSError('injected html publish failure')
            return original(path,content)
        with patch.object(reg,'atomic',side_effect=fault):
            with self.assertRaises(OSError):
                self.publish()
        self.assertFalse(list((self.folder/'大白话解释').glob('*.md')))
        self.assertFalse(list((self.folder/'大白话解释').glob('*.html')))
        self.assertEqual({},reg.get_index(self.folder)['documents'])
        self.assertEqual('CLEAN',reg.recover_transaction(self.folder))

    def test_legacy_index_backfill_and_no_existing_html_overwrite(self):
        _,md=self.publish()
        html=md.with_suffix('.html')
        index=self.folder/reg.INDEX
        metadata=json.loads(index.read_text(encoding='utf8'))
        del metadata['documents']['plan']['html_sha256']
        index.write_text(json.dumps(metadata,ensure_ascii=False),encoding='utf8')
        html.unlink()
        self.assertEqual(1,reg.sync_html(self.ws,'示例业务'))
        self.assertEqual(0,reg.sync_html(self.ws,'示例业务'))
        self.assertEqual([],reg.verify_all(self.ws,'示例业务'))
        metadata=json.loads(index.read_text(encoding='utf8'))
        del metadata['documents']['plan']['html_sha256']
        index.write_text(json.dumps(metadata,ensure_ascii=False),encoding='utf8')
        with self.assertRaisesRegex(reg.DocumentError,'拒绝覆盖'):
            reg.sync_html(self.ws,'示例业务')

    def test_unregistered_existing_html_not_overwritten(self):
        target=self.folder/'大白话解释'/'1. 实施与测试方案.html'
        target.write_text('user-written html',encoding='utf8')
        with self.assertRaisesRegex(reg.DocumentError,'拒绝覆盖'):
            self.publish()
        self.assertEqual('user-written html',target.read_text(encoding='utf8'))

    def test_symlink_html_target_rejected(self):
        _,md=self.publish()
        html=md.with_suffix('.html');html.unlink()
        outside=Path(self.temp.name)/'outside.html';outside.write_text('do not touch',encoding='utf8')
        try:
            html.symlink_to(outside)
        except OSError:
            self.skipTest('symlinks not allowed')
        with self.assertRaises(reg.DocumentError):
            self.publish()
        self.assertEqual('do not touch',outside.read_text(encoding='utf8'))


class StaticScanReviewTests(unittest.TestCase):
    def test_python_unreachable_ternaries_and_literal_bool_bypass_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            ws=Path(t);(ws/'calc.py').write_text('def add(a,b): return a+b\n',encoding='utf8')
            source=ws/'test_calc.py'
            rejected=[
              'assert add(3,4)==7 or bool(True)',
              'assert add(3,4)==7 if False else True',
              'if bool(False):\n        assert add(3,4)==7\n    assert True',
              'assert (add(3,4)==7) if bool(False) else (1==1)',
            ]
            for assertion in rejected:
                with self.subTest(assertion=assertion):
                    source.write_text('from calc import add\ndef test_total():\n    '+assertion+'\n',encoding='utf8')
                    self.assertFalse(_python_source_has_assertion(source,'test_total',ws))
            source.write_text('from calc import add\ndef test_total():\n    assert add(3,4)==7\n',encoding='utf8')
            self.assertTrue(_python_source_has_assertion(source,'test_total',ws))

    def test_java_rejects_business_self_comparison_in_assert_true(self):
        with tempfile.TemporaryDirectory() as t:
            source=Path(t)/'CalcTest.java'
            for assertion in (
              'assertTrue(service.calculate(3,4) == service.calculate(3,4));',
              'assertTrue(service.calculate(3,4) == 7 || true);',
            ):
                with self.subTest(assertion=assertion):
                    source.write_text('class CalcTest{@Test void testSum(){'+assertion+'}}',encoding='utf8')
                    self.assertFalse(_java_source_has_assertion(source,'testSum'))
            source.write_text('class CalcTest{@Test void testSum(){assertTrue(service.calculate(3,4)==7);}}',encoding='utf8')
            self.assertTrue(_java_source_has_assertion(source,'testSum'))
