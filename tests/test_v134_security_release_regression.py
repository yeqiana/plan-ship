"""Adversarial release and HTML/mutation correctness gates for PlanShip v1.3.4."""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT)]
import doc_registry as reg
from run_mutation import run_mutation
from validate_evidence import validate_counterfactual_evidence
from tests.test_v132_acceptance import CounterfactualEvidenceTests
from tests.test_v22 import tech, plain


class HtmlBoundaryRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name) / 'ws'
        self.folder = reg.init(self.ws, '文档项目')
        self.draft = self.folder / '.drafts'

    def publish(self, content=None):
        a = self.draft / 'tech.md'
        b = self.draft / 'plain.md'
        a.write_text(tech('手动方案'), encoding='utf8')
        b.write_text(content if content is not None else plain('手动方案'), encoding='utf8')
        return reg.publish(self.ws, '文档项目', 'plan', '手动方案', a, b)

    def test_explanation_link_outside_blocks_sync_and_preserves_external_content(self):
        _, md = self.publish()
        original = self.folder / '大白话解释'
        outside = Path(self.tmp.name) / 'external'
        outside.mkdir()
        sentinel = outside / md.with_suffix('.html').name
        sentinel.write_text('unchanged', encoding='utf8')
        original.rename(self.folder / 'saved_explanation')
        try:
            try:
                original.symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest('filesystem policy denies directory symlink')
            with self.assertRaises(reg.DocumentError):
                reg.sync_html(self.ws, '文档项目', dry_run=False)
            self.assertTrue(reg.verify_all(self.ws, '文档项目'))
            self.assertEqual('unchanged', sentinel.read_text(encoding='utf8'))
        finally:
            if original.is_symlink():
                original.unlink()
            if (self.folder / 'saved_explanation').exists():
                (self.folder / 'saved_explanation').rename(original)

    @unittest.skipUnless(os.name == 'nt', 'Windows junction only')
    def test_explanation_junction_outside_is_blocked(self):
        _, md = self.publish()
        original = self.folder / '大白话解释'
        outside = Path(self.tmp.name) / 'external'
        outside.mkdir()
        sentinel = outside / md.with_suffix('.html').name
        sentinel.write_text('unchanged', encoding='utf8')
        original.rename(self.folder / 'saved_explanation')
        try:
            process = subprocess.run(['cmd', '/c', 'mklink', '/J', str(original), str(outside)],
                                     capture_output=True, text=True, encoding='utf-8', errors='replace')
            if process.returncode:
                self.skipTest('Windows junction creation restricted')
            with self.assertRaises(reg.DocumentError):
                reg.sync_html(self.ws, '文档项目', dry_run=False)
            self.assertEqual('unchanged', sentinel.read_text(encoding='utf8'))
        finally:
            if original.exists() or original.is_symlink() or (hasattr(original, 'is_junction') and original.is_junction()):
                original.rmdir() if (hasattr(original, 'is_junction') and original.is_junction()) else original.unlink()
            if (self.folder / 'saved_explanation').exists():
                (self.folder / 'saved_explanation').rename(original)

    def test_missing_image_prevents_publish(self):
        text = plain('手动方案') + '\n![缺失截图](./screenshots/not-found.png)\n'
        with self.assertRaisesRegex(reg.DocumentError, '图片'):
            self.publish(text)
        self.assertEqual({}, reg.get_index(self.folder)['documents'])

    def test_existing_image_can_be_published_then_missing_image_breaks_verify(self):
        folder = self.folder / '大白话解释' / 'screenshots'
        folder.mkdir(parents=True)
        image = folder / 'sample.png'
        image.write_bytes(b'illustration-placeholder')
        self.publish(plain('手动方案') + '\n![截图](./screenshots/sample.png)\n')
        self.assertEqual([], reg.verify_all(self.ws, '文档项目'))
        image.unlink()
        self.assertTrue(any('图片' in err for err in reg.verify_all(self.ws, '文档项目')))

    def test_encoded_escape_and_linked_image_not_accepted(self):
        explanation = self.folder / '大白话解释'
        outside = Path(self.tmp.name) / 'outside.png'
        outside.write_bytes(b'not-a-real-image')
        self.assertTrue(reg.verify_local_images('![a](%2e%2e/outside.png)', explanation) or
                        '<img' not in reg.render_plain_html('![a](%2e%2e/outside.png)').decode())
        link = explanation / 'linked.png'
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest('symlink creation restricted')
        self.assertTrue(reg.verify_local_images('![linked](./linked.png)', explanation))


class MutationThreePhaseRegression(unittest.TestCase):
    def setUp(self):
        self.parent = CounterfactualEvidenceTests('test_consistency_is_not_acceptance')
        self.parent.setUp()
        self.addCleanup(self.parent.doCleanups)
        self.fixture = self.parent.fixture

    def prepare(self, poisoned_test=False):
        f = self.fixture
        if poisoned_test:
            test = f.ws / 'tests' / 'test_real.py'
            test.write_text(test.read_text(encoding='utf8').replace('== 7', '== 8'), encoding='utf8')
        source = f.file.relative_to(f.ws).as_posix()
        old = f.file.read_text(encoding='utf8')
        new = old.replace('return a + b', 'return a + b + 100')
        evidence = f.docs / 'evidence'
        snapshot = evidence / 'mutant.py.snapshot'
        patchfile = evidence / 'mutant.patch'
        snapshot.write_text(new, encoding='utf8')
        patchfile.write_text(''.join(difflib.unified_diff(
            old.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile='a/' + source, tofile='b/' + source)), encoding='utf8')
        return (f.ws, f.plan, source, snapshot.relative_to(f.ws).as_posix(),
                patchfile.relative_to(f.ws).as_posix(), 'tests/test_real.py',
                'tests/test_real.py::test_add', 'tests.test_real::test_add')

    def test_baseline_already_failed_must_never_claim_mutation_killed(self):
        inputs = self.prepare(poisoned_test=True)
        with self.assertRaisesRegex(ValueError, '原始代码.*PASS'):
            run_mutation(*inputs)
        records = list(self.fixture.docs.joinpath('evidence').glob('MUT-*.json'))
        self.assertEqual([], records)

    def test_all_three_phases_present_and_tamper_detected(self):
        result = run_mutation(*self.prepare())
        record = self.fixture.ws / result['record_path']
        data = json.loads(record.read_text(encoding='utf8'))
        self.assertEqual({'baseline':'PASS','mutation':'FAIL','restored':'PASS'}, data['phase_outcomes'])
        self.assertTrue(data['baseline_trace']['target_module_loaded'])
        self.assertFalse(data['restored_trace']['call_failed'])
        self.parent.attach_actual_negative_control()
        cf = self.fixture.manifest_data['acceptance'][0]['counterfactual']
        rec = self.fixture.ws / cf['mutation_run_record_path']
        raw = json.loads(rec.read_text(encoding='utf8'))
        raw['phase_outcomes']['baseline'] = 'FAIL'
        rec.write_text(json.dumps(raw, ensure_ascii=False), encoding='utf8')
        cf['mutation_run_record_sha256'] = hashlib.sha256(rec.read_bytes()).hexdigest()
        self.fixture.write_manifest()
        self.assertTrue(any('对照证据' in e for e in validate_counterfactual_evidence(
            self.fixture.manifest,self.fixture.plan,self.fixture.ws)))

class ReleaseArchiveRegression(unittest.TestCase):
    def setUp(self):
        import zipfile
        from verify_release_archive import check_zip, tracked_tree
        self.check_zip = check_zip
        self.tracked_tree = tracked_tree
        self.zipfile = zipfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.repo = self.folder / 'repo'
        self.repo.mkdir()
        def git(*args):
            result = subprocess.run(['git', '-C', str(self.repo), *args],
                                    capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
        git('init', '-q')
        git('config', 'user.name', 'PlanShip Test')
        git('config', 'user.email', 'test@example.invalid')
        (self.repo / 'README.md').write_text('# release test\n', encoding='utf8')
        (self.repo / 'config.txt').write_bytes(b'unchanged\n')
        git('add', '.')
        git('commit', '-q', '-m', 'test fixture')
        self.data = self.tracked_tree(self.repo, 'HEAD')
        self.archive = self.folder / 'candidate.zip'

    def zip(self, entries):
        with self.zipfile.ZipFile(self.archive, 'w') as bundle:
            for key, value in entries:
                bundle.writestr(key, value)

    def test_exact_git_tree_passes(self):
        self.zip(list(self.data.items()))
        self.assertEqual([], self.check_zip(self.repo, self.archive))

    def test_single_conventional_root_directory_passes(self):
        self.zip([('repo/' + name, body) for name, body in self.data.items()])
        self.assertEqual([], self.check_zip(self.repo, self.archive))

    def test_mixed_flat_and_root_wrapped_files_block(self):
        self.zip([('repo/README.md', self.data['README.md']),
                  ('config.txt', self.data['config.txt'])])
        self.assertTrue(any('混用' in err or '同时包含' in err
                            for err in self.check_zip(self.repo, self.archive)))

    def test_root_wrapped_stale_contents_block(self):
        rows = [('repo/' + key, b'outdated' if key == 'README.md' else value)
                for key, value in self.data.items()]
        self.zip(rows)
        self.assertTrue(any('不一致' in err for err in self.check_zip(self.repo, self.archive)))

    def test_stale_file_blocks_even_with_same_names(self):
        changed = [(key, b'old source bytes' if key == 'README.md' else value)
                   for key, value in self.data.items()]
        self.zip(changed)
        self.assertTrue(any('不一致' in err for err in self.check_zip(self.repo, self.archive)))

    def test_missing_extra_and_duplicate_entries_block(self):
        self.zip([('README.md', self.data['README.md'])])
        self.assertTrue(any('缺少' in err for err in self.check_zip(self.repo, self.archive)))
        self.zip(list(self.data.items()) + [('extra.txt', b'extra')])
        self.assertTrue(any('额外' in err for err in self.check_zip(self.repo, self.archive)))
        with patch('warnings.warn'):
            self.zip(list(self.data.items()) + [('README.md', self.data['README.md'])])
        self.assertTrue(any('重复' in err for err in self.check_zip(self.repo, self.archive)))

    def test_traversal_zip_entry_blocks_without_extraction(self):
        self.zip(list(self.data.items()) + [('../outside.md', b'escape')])
        self.assertTrue(any('不安全' in err for err in self.check_zip(self.repo, self.archive)))
        self.assertFalse((self.folder / 'outside.md').exists())
