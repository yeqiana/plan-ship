"""Adversarial review: faithful HTML, safe migration, controlled mutation provenance."""
from __future__ import annotations
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from html.parser import HTMLParser

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT)]
import doc_registry as reg
from plain_html import render, inline, _cells
from run_mutation import run_mutation
from validate_evidence import validate_counterfactual_evidence
from tests.test_v22 import tech, plain
from tests.test_v132_acceptance import CounterfactualEvidenceTests


class Reader(HTMLParser):
    def __init__(self):
        super().__init__();self.row=[];self.rows=[];self.cell=None;self.images=[]
    def handle_starttag(self,tag,attrs):
        data=dict(attrs)
        if tag=='tr':self.row=[]
        if tag in ('th','td'):self.cell=[]
        if tag=='img':self.images.append(data)
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ('th','td'):
            self.row.append(''.join(self.cell));self.cell=None
        if tag=='tr' and self.row:self.rows.append(self.row)

class HtmlFidelityTests(unittest.TestCase):
    def test_static_scanner_rejects_extra_true_wrappers(self):
        from test_report import _python_source_has_assertion, _java_source_has_assertion
        with tempfile.TemporaryDirectory() as tmp:
            ws=Path(tmp);(ws/'calc.py').write_text('def add(a,b): return 999\n')
            t=ws/'test_sum.py'
            t.write_text('from calc import add\ndef test_sum():\n    assert add(3,4)==7 or all([True])\n')
            self.assertFalse(_python_source_has_assertion(t,'test_sum',ws))
            j=ws/'SumTest.java'
            j.write_text('class SumTest{@Test void testSum(){assertTrue(service.calculate(3,4)==7 || Boolean.TRUE);}}')
            self.assertFalse(_java_source_has_assertion(j,'testSum'))

    def test_code_and_escaped_pipes_preserve_statuses(self):
        md='| 情况 | 状态 |\n| --- | --- |\n| `A|B` | PASS |\n| A\\|B | FAIL |\n'
        parsed=Reader();parsed.feed(render(md).decode())
        self.assertEqual([['情况','状态'],['A|B','PASS'],['A|B','FAIL']],parsed.rows)
        self.assertEqual(['`A|B`','PASS'],_cells('| `A|B` | PASS |'))
        self.assertEqual(['A|B','FAIL'],_cells(r'| A\|B | FAIL |'))
        self.assertEqual([r'`A\|B`','PASS'],_cells(r'| `A\|B` | PASS |'))
        self.assertIn('返回大白话文档主入口', render('# 测试').decode())
    def test_code_image_xss_and_collision_are_safe(self):
        md='ZXQTOKEN0QXZ `a|b` ![正常图](./screenshot.png) ![危险图](javascript:alert) <script>alert(1)</script>'
        actual=render(md).decode()
        parser=Reader();parser.feed(actual)
        self.assertEqual('./screenshot.png',parser.images[0]['src'])
        self.assertEqual('正常图',parser.images[0]['alt'])
        self.assertNotIn('src="javascript:',actual)
        self.assertIn('&lt;script&gt;',actual)
        self.assertIn('ZXQTOKEN0QXZ',actual)
        self.assertIn('<code>a|b</code>',actual)
        self.assertNotIn('<script>',actual)
        self.assertNotIn('src="https://',actual)
        for href in ('../secret.png','%2e%2e/secret.png','C:/secret.png','//evil.test/x.png'):
            self.assertNotIn('<img',inline('![x]('+href+')'))

class IndexedHtmlTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.ws=Path(self.tmp.name)/'workspace'
        self.folder=reg.init(self.ws,'方案示例')
        self.draft=self.folder/'.drafts'
    def publish(self,key='plan',title='方案说明'):
        a=self.draft/(key+'-a.md');b=self.draft/(key+'-b.md')
        a.write_text(tech(title),encoding='utf8');b.write_text(plain(title),encoding='utf8')
        return reg.publish(self.ws,'方案示例',key,title,a,b)
    def test_entry_exists_and_lists_documents_without_fake_acceptance(self):
        entry=self.folder/'大白话解释'/'index.html'
        self.assertTrue(entry.is_file())
        self.assertEqual([],reg.verify_all(self.ws,'方案示例'))
        a,b=self.publish();self.publish('manual','手动测试验收方案')
        html=entry.read_text(encoding='utf8')
        self.assertIn('方案说明',html);self.assertIn('手动测试验收方案',html)
        self.assertIn('业务语义待独立复核',html)
        self.assertTrue(b.with_suffix('.html').exists())
        self.assertFalse(a.with_suffix('.html').exists())
        self.assertEqual([],reg.verify_all(self.ws,'方案示例'))
    def test_bulk_sync_requires_review_and_refuses_custom_html(self):
        a,b=self.publish()
        html=b.with_suffix('.html');html.unlink()
        index_path=self.folder/reg.INDEX
        index=json.loads(index_path.read_text(encoding='utf8'))
        index['documents']['plan'].pop('html_sha256')
        index_path.write_text(json.dumps(index,ensure_ascii=False),encoding='utf8')
        self.assertEqual(1,reg.sync_html(self.ws,'方案示例',dry_run=True))
        self.assertFalse(html.exists())
        self.assertEqual(1,reg.sync_html(self.ws,'方案示例',dry_run=False))
        self.assertTrue(html.exists())
        self.assertEqual([],reg.verify_all(self.ws,'方案示例'))
        html.write_text('user custom',encoding='utf8')
        with self.assertRaisesRegex(reg.DocumentError,'拒绝覆盖'):
            reg.sync_html(self.ws,'方案示例',dry_run=False)
        self.assertEqual('user custom',html.read_text(encoding='utf8'))
    def test_init_does_not_overwrite_unindexed_user_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            orphan = ws/'.idea'/'docs'/'新方案'/'大白话解释'/'index.html'
            orphan.parent.mkdir(parents=True)
            orphan.write_text('my custom index', encoding='utf8')
            with self.assertRaises(reg.DocumentError):
                reg.init(ws, '新方案')
            self.assertEqual('my custom index', orphan.read_text(encoding='utf8'))

    def test_cli_sync_html_dry_run_requires_apply(self):
        _, md = self.publish()
        target = md.with_suffix('.html')
        target.unlink()
        idx = self.folder / reg.INDEX
        meta = json.loads(idx.read_text(encoding='utf8'))
        meta['documents']['plan'].pop('html_sha256')
        idx.write_text(json.dumps(meta, ensure_ascii=False), encoding='utf8')
        cli = [sys.executable, str(ROOT/'scripts'/'doc_registry.py'), 'sync-html',
               '--workspace', str(self.ws), '--name', '方案示例']
        preview = subprocess.run(cli, capture_output=True, text=True)
        self.assertEqual(0, preview.returncode, preview.stdout+preview.stderr)
        self.assertIn('HTML_DRY_RUN_CHANGES: 1', preview.stdout)
        self.assertFalse(target.exists())
        applied = subprocess.run(cli+['--apply'], capture_output=True, text=True)
        self.assertEqual(0, applied.returncode, applied.stdout+applied.stderr)
        self.assertTrue(target.is_file())
        self.assertEqual([], reg.verify_all(self.ws, '方案示例'))

    def test_registered_old_html_updated_but_unmanaged_not(self):
        _,md = self.publish()
        page = md.with_suffix('.html')
        old = page.read_bytes().replace(b'PlanShip',b'PlanShip-old-renderer')
        page.write_bytes(old)
        idx = self.folder/reg.INDEX
        data = json.loads(idx.read_text(encoding='utf8'))
        data['documents']['plan']['html_sha256']=hashlib.sha256(old).hexdigest()
        idx.write_text(json.dumps(data,ensure_ascii=False),encoding='utf8')
        self.assertEqual(1,reg.sync_html(self.ws,'方案示例',dry_run=True))
        self.assertEqual(old,page.read_bytes())
        self.assertEqual(1,reg.sync_html(self.ws,'方案示例',dry_run=False))
        self.assertEqual([],reg.verify_all(self.ws,'方案示例'))

    def test_orphan_html_blocks_without_changes(self):
        a,b=self.publish()
        orphan=self.folder/'大白话解释'/'custom.html'
        orphan.write_text('custom',encoding='utf8')
        with self.assertRaises(reg.DocumentError):
            reg.sync_html(self.ws,'方案示例',dry_run=True)
        self.assertEqual('custom',orphan.read_text(encoding='utf8'))
    def test_entry_tamper_blocks_publish(self):
        self.publish()
        entry=self.folder/'大白话解释'/'index.html'
        entry.write_text('tampered',encoding='utf8')
        with self.assertRaises(reg.DocumentError):
            self.publish('manual','手动方案')
        self.assertTrue(reg.verify_all(self.ws,'方案示例'))
    def test_entry_write_failure_rolls_back_old_state(self):
        entry=self.folder/'大白话解释'/'index.html'
        before=entry.read_bytes()
        index=(self.folder/reg.INDEX).read_bytes()
        orig=reg.atomic
        def fail(path,data):
            if path.name=='index.html':raise OSError('injected index failure')
            return orig(path,data)
        with patch.object(reg,'atomic',side_effect=fail):
            with self.assertRaises(OSError):self.publish()
        self.assertEqual(before,entry.read_bytes())
        self.assertEqual(index,(self.folder/reg.INDEX).read_bytes())
        self.assertEqual([],reg.verify_all(self.ws,'方案示例'))

class ControlledMutationTests(unittest.TestCase):
    def setUp(self):
        self.parent=CounterfactualEvidenceTests(methodName='test_consistency_is_not_acceptance')
        self.parent.setUp();self.addCleanup(self.parent.doCleanups)
        self.fixture=self.parent.fixture
    def test_test_only_red_report_does_not_pass_without_run_record(self):
        f=self.fixture
        self.assertEqual([],f.check())
        self.parent.attach_actual_negative_control()
        self.assertEqual([],validate_counterfactual_evidence(f.manifest,f.plan,f.ws))
        cf=f.manifest_data['acceptance'][0]['counterfactual']
        cf.pop('mutation_run_record_path');cf.pop('mutation_run_record_sha256')
        f.write_manifest()
        self.assertTrue(any('受控变异' in e for e in validate_counterfactual_evidence(f.manifest,f.plan,f.ws)))
    def test_real_run_trace_tamper_rejected(self):
        f=self.fixture;self.parent.attach_actual_negative_control()
        cf=f.manifest_data['acceptance'][0]['counterfactual']
        rec=f.ws/cf['mutation_run_record_path']
        data=json.loads(rec.read_text(encoding='utf8'))
        data['trace']['target_module_loaded']=False
        rec.write_text(json.dumps(data,ensure_ascii=False),encoding='utf8')
        cf['mutation_run_record_sha256']=hashlib.sha256(rec.read_bytes()).hexdigest()
        f.write_manifest()
        self.assertTrue(any('无法证明' in e for e in validate_counterfactual_evidence(f.manifest,f.plan,f.ws)))
    def test_wrong_report_nonce_rejected_even_with_updated_hash(self):
        f=self.fixture;self.parent.attach_actual_negative_control()
        cf=f.manifest_data['acceptance'][0]['counterfactual']
        report=f.ws/cf['negative_report_path']
        raw=report.read_text(encoding='utf8').replace('plan_ship_mutation_nonce','fake_mutation_nonce')
        report.write_text(raw,encoding='utf8')
        h=hashlib.sha256(report.read_bytes()).hexdigest()
        cf['negative_report_sha256']=h
        rec=f.ws/cf['mutation_run_record_path']
        data=json.loads(rec.read_text(encoding='utf8'))
        data['negative_report_sha256']=h
        rec.write_text(json.dumps(data),encoding='utf8')
        cf['mutation_run_record_sha256']=hashlib.sha256(rec.read_bytes()).hexdigest()
        f.write_manifest()
        self.assertTrue(any('JUnit 报告未绑定' in e for e in validate_counterfactual_evidence(f.manifest,f.plan,f.ws)))
