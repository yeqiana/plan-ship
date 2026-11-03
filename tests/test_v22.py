from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from doc_registry import init, publish, verify_file, verify_all, DocumentError
from preflight import check


def tech(title='新方案'):
    return f'''# {title}\n\n## 概述\n\n核心业务概念：新需求\n\n根据实际需求修改对应模块，只添加一个接口，保留旧功能兼容行为；用例先验证输入和错误状态，再执行回归测试。\n\n## 检验\n\n每个新需求用真实测试用例关联一个断言，记录实际运行的日志和系统输出；未执行的步骤不可声称已经完成。\n'''


def plain(title='新方案'):
    return f'''# {title}：大白话解释

## 一句话结论

这次只给当前系统增加一个必要的小能力，并且让原本能正常使用的功能继续正常使用；所有结果都要通过实际操作而不是口头宣布成功。

## 为什么要做

假设原来的服务只能处理一种简单请求，现在用户多了一种新需求。如果完全重建系统，反而容易让已经正常的旧功能发生故障，所以优先沿用原有组件。

## 改动前后

改动前：用户只能使用现有功能；改动后：用户可以使用新增能力，而老用户原来的操作方式保持不变。新需求范围以技术版中的实际需求与验收条件为准。

## 生活类比

打个比方，一间已经营业的商店要增加一个服务窗口。只在空闲位置安装窗口，其他柜台继续营业；新窗口试运行失败时暂停新窗口，而不是关闭整家商店。

## 图解：从请求到验收

```mermaid
flowchart LR
 A[用户提出新需求] --> B[只增加必要逻辑] --> C[运行真实测试] --> D[人工手动复验]
```

图解说明：图中的箭头表示执行顺序，先约定需要改变什么，再实施最小改动，最后必须看到真实测试和手动操作的结果。图不代表相关测试已经执行。

## 怎么验证

第一步，打开原来的功能，确认常用操作依然正常；第二步，输入本次新增功能要求的样本，记录可观察结果；第三步，提供错误输入，检查系统是否明确拒绝或返回预期提示。测试日志和断言必须可追溯。

## 风险与状态

如果新增能力出错，应回退本次新增代码，并重新验证旧功能。当前说明只是示例，不能冒充实际验收；如果测试未执行，状态明确写未执行；权限不足写 BLOCKED；测试失败标记未通过。

## 术语小词典

| 术语 | 用日常语言解释 |
|---|---|
| 回归测试 | 改好新功能后，重新检查老功能有没有被意外弄坏 |
| 断言 | 测试时事先约定必须看到的结果，实际结果不同就报错 |
'''


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = Path(self.tmp.name) / 'work space'
        self.dir = init(self.ws, 'IM冷热库拆分')

    def do_publish(self, key='plan', title='IM冷热库拆分-实施测试验收方案', content=None, explanation=None):
        stage = self.dir / '.drafts'
        a, b = stage / f'{key}-tech.md', stage / f'{key}-plain.md'
        a.write_text(content or tech(title), encoding='utf-8')
        b.write_text(explanation or plain(title), encoding='utf-8')
        return publish(self.ws, 'IM冷热库拆分', key, title, a, b)

    def test_folder_is_idempotent(self):
        self.assertEqual(self.dir, init(self.ws, 'IM冷热库拆分'))
        self.assertTrue((self.dir / '大白话解释').is_dir())

    def test_first_document_numbered(self):
        a, b = self.do_publish()
        self.assertEqual(a.name, '1. IM冷热库拆分-实施测试验收方案.md')
        self.assertEqual(a.name, b.name)
        self.assertEqual([], verify_file(a, self.ws))

    def test_repeat_does_not_add_or_renumber(self):
        a1, _ = self.do_publish()
        a2, _ = self.do_publish(content=tech() + '\n## 补充\n新增了真实的出错路径校验，避免旧功能回归遗漏。\n')
        self.assertEqual(a1, a2)
        self.assertEqual(len(list(self.dir.glob('*.md'))), 1)
        self.assertEqual([], verify_all(self.ws, 'IM冷热库拆分'))

    def test_optional_case_addendum_controls_next_number(self):
        self.do_publish()
        a, _ = self.do_publish('manual', 'IM冷热库拆分-手动测试验收方案')
        self.assertTrue(a.name.startswith('2. '))
        self.assertEqual([], verify_all(self.ws, 'IM冷热库拆分'))

    def test_addendum_before_manual_makes_three(self):
        self.do_publish()
        a, _ = self.do_publish('testcases', 'IM冷热库拆分-测试用例补充')
        b, _ = self.do_publish('manual', 'IM冷热库拆分-手动测试验收方案')
        self.assertTrue(a.name.startswith('2. '))
        self.assertTrue(b.name.startswith('3. '))

    def test_missing_plain_blocks(self):
        a, b = self.do_publish()
        b.unlink()
        self.assertTrue(any('缺少' in x for x in verify_file(a, self.ws)))

    def test_stale_technical_blocks(self):
        a, b = self.do_publish()
        a.write_text(a.read_text(encoding='utf-8') + '\n# 热修正\n', encoding='utf-8')
        self.assertTrue(any('未同步' in x for x in verify_file(a, self.ws)))

    def test_stale_explanation_blocks(self):
        a, b = self.do_publish()
        b.write_text(b.read_text(encoding='utf-8') + '\n错误引用\n', encoding='utf-8')
        self.assertTrue(any('大白话' in x for x in verify_file(a, self.ws)))

    def test_overwrite_unregistered_manual_edit_is_rejected(self):
        a, b = self.do_publish()
        a.write_text(a.read_text(encoding='utf-8') + '\n用户手工修改', encoding='utf-8')
        with self.assertRaisesRegex(DocumentError, '拒绝覆盖'):
            self.do_publish(content=tech() + '\n## 新改动\n真实覆盖边界\n')

    def test_nested_markdown_unpaired_blocks(self):
        self.do_publish()
        (self.dir / 'evidence').mkdir()
        (self.dir / 'evidence' / 'test-report.md').write_text('# 额外文档', encoding='utf-8')
        self.assertTrue(any('必须登记' in x for x in verify_all(self.ws, 'IM冷热库拆分')))

    def test_orphan_markdown_blocks(self):
        self.do_publish()
        (self.dir / '7. 未登记.md').write_text('# orphan', encoding='utf-8')
        self.assertTrue(any('未登记' in x for x in verify_all(self.ws, 'IM冷热库拆分')))

    def test_reuse_key_different_title_blocks(self):
        self.do_publish()
        with self.assertRaises(DocumentError):
            self.do_publish(title='换一个名称')

    def test_outside_draft_blocks(self):
        a = self.ws / 'outside.md'
        a.write_text(tech(), encoding='utf-8')
        b = self.dir / '.drafts' / 'explanation.md'
        b.write_text(plain(), encoding='utf-8')
        with self.assertRaises(DocumentError):
            publish(self.ws, 'IM冷热库拆分', 'plan', '计划', a, b)

    def test_invalid_windows_name_blocks(self):
        with self.assertRaises(DocumentError):
            init(self.ws, '../逃逸')
        with self.assertRaises(DocumentError):
            init(self.ws, 'CON')

    def test_no_fake_plain_provenance(self):
        content = plain().replace('未执行', '已通过').replace('未通过', '已通过').replace('BLOCKED', '已通过')
        a, b = self.do_publish(explanation=content)
        self.assertTrue(any('未执行' in x for x in verify_file(a, self.ws)))

    def test_registry_cli_from_different_directory(self):
        self.do_publish()
        p = subprocess.run([sys.executable, str(SCRIPTS / 'doc_registry.py'), 'verify', '--workspace', str(self.ws), '--name', 'IM冷热库拆分'], cwd=tempfile.gettempdir(), capture_output=True, text=True)
        self.assertEqual(0, p.returncode, p.stdout + p.stderr)

    def test_concurrent_publish_different_keys(self):
        import concurrent.futures
        stage = self.dir / '.drafts'
        work = []
        for key in ('review1', 'review2', 'manual'):
            title = 'IM冷热库拆分-' + key
            a, b = stage / (key + '.md'), stage / (key + '-plain.md')
            a.write_text(tech(title), encoding='utf-8')
            b.write_text(plain(title), encoding='utf-8')
            work.append((key, title, a, b))
        def job(item):
            key, title, a, b = item
            p = subprocess.run([sys.executable, str(SCRIPTS / 'doc_registry.py'), 'publish', '--workspace', str(self.ws), '--name', 'IM冷热库拆分', '--key', key, '--title', title, '--technical-file', str(a), '--plain-file', str(b)], capture_output=True, text=True)
            return p.returncode, p.stdout, p.stderr
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            out = list(pool.map(job, work))
        self.assertEqual([0, 0, 0], [x[0] for x in out], out)
        self.assertEqual([], verify_all(self.ws, 'IM冷热库拆分'))
        values = json.loads((self.dir / '.document-index.json').read_text(encoding='utf-8'))['documents'].values()
        self.assertEqual({1, 2, 3}, {x['number'] for x in values})


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.ws = self.home / 'work'
        self.ws.mkdir()

    def test_missing_skills_blocks(self):
        with patch('discover_skills.roots', return_value=[('codex-user-modern', self.home / '.agents' / 'skills')]):
            result = check(self.ws, host='codex')
        self.assertEqual('READY_CORE_WITH_OPTIONAL_WARNINGS', result['preflight_status'])

    def test_two_skills_found_ready_for_loading(self):
        root = self.home / '.agents' / 'skills'
        for name in ('code-pact', 'gen-ui'):
            directory = root / name
            directory.mkdir(parents=True)
            (directory / 'SKILL.md').write_text('---\nname: ' + name + '\ndescription: Test\n---\n\n# Skill\n', encoding='utf-8')
        with patch('discover_skills.roots', return_value=[('codex-user-modern', root)]):
            result = check(self.ws, host='codex')
        self.assertEqual('READY_CORE_OPTIONAL_FILES_FOUND_AGENT_CONFIRMATION_REQUIRED', result['preflight_status'])
        self.assertTrue(all(result['skills'][x]['found'] for x in ('code-pact', 'gen-ui')))

    def test_bad_frontmatter_fails_closed(self):
        root = self.home / '.claude' / 'skills' / 'code-pact'
        root.mkdir(parents=True)
        (root / 'SKILL.md').write_text('# 不是合法 Skill Frontmatter\n', encoding='utf-8')
        with patch('discover_skills.roots', return_value=[('claude-user', root.parent)]):
            self.assertEqual('READY_CORE_WITH_OPTIONAL_WARNINGS', check(self.ws, host='claude')['preflight_status'])


if __name__ == '__main__':
    unittest.main()
