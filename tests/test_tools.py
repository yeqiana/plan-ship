from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from validate_docs import validate, extract_trace
from validate_evidence import validate_evidence
from discover_skills import roots
from doc_registry import init, publish, verify_all, verify_file, DocumentError
from preflight import check as check_preflight


def make_plain(title: str) -> str:
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


def publish_test_doc(workspace: Path, name: str, key: str, title: str, content: str) -> Path:
    folder = init(workspace, name)
    draft = folder / '.drafts' / (key + '-tech.md')
    plain = folder / '.drafts' / (key + '-plain.md')
    draft.write_text(content, encoding='utf-8')
    plain.write_text(make_plain(title), encoding='utf-8')
    final, _ = publish(workspace, name, key, title, draft, plain)
    return final


def fill_template(name: str) -> str:
    text = (ROOT / "assets" / "templates" / name).read_text(encoding="utf8")
    counter = iter(range(1, 200))
    return re.sub(r"\{\{[^{}\n]*\}\}", lambda m: f"实际代码 src/main/Task.java 第{next(counter)}处逻辑、输入和预期校验已写清", text)


def run(*cmd, cwd=None):
    return subprocess.run(list(map(str, cmd)), cwd=cwd, capture_output=True, text=True, check=False)


class DocsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ws = Path(self.temp.name) / "项目 根"
        self.docs = init(self.ws, "演示方案")
        self.plan_text = fill_template("plan.md")
        self.plan = publish_test_doc(self.ws, "演示方案", "plan", "演示方案-实施测试验收方案", self.plan_text)

    def check(self, kind="plan", content=None, path=None, **kw):
        content = content if content is not None else (self.plan_text if kind == "plan" else fill_template("testcase-addendum.md" if kind == "testcases" else "manual-acceptance.md"))
        title = "演示方案-实施测试验收方案" if kind == "plan" else "演示方案-" + kind
        target = path or publish_test_doc(self.ws, "演示方案", kind, title, content)
        return validate(content, kind, target, self.ws, kw.get("plan_content", self.plan_text))

    def test_three_templates_pass(self):
        for kind in ("plan", "testcases", "manual"):
            with self.subTest(kind=kind):
                self.assertEqual([], self.check(kind), kind)

    def test_review_out_of_order_rejected(self):
        text = self.plan_text.replace("第1轮：评审与补强", "第X轮：评审与补强").replace("第2轮：评审与补强", "第1轮：评审与补强").replace("第X轮：评审与补强", "第2轮：评审与补强")
        self.assertTrue(any("轮次" in e for e in self.check(content=text)))

    def test_review_failed_rejected(self):
        text = self.plan_text.replace("复核结论：通过", "复核结论：未通过", 1)
        self.assertTrue(any("复核结论" in e for e in self.check(content=text)))

    def test_review_blocked_rejected(self):
        text = self.plan_text.replace("遗留阻断：无", "遗留阻断：存在未修复风险", 1)
        self.assertTrue(any("遗留阻断" in e or "阻断" in e for e in self.check(content=text)))

    def test_empty_changes_rejected(self):
        text = re.sub(r"(?m)^(- 修改后：).+$", r"\1同前", self.plan_text)
        text = re.sub(r"(?m)^(- 修改前：).+$", r"\1同前", text)
        self.assertTrue(any("修改前后" in e for e in self.check(content=text)))

    def test_final_failed_rejected(self):
        text = self.plan_text.replace("最终结果：通过", "最终结果：未通过")
        self.assertTrue(any("最终结果" in e for e in self.check(content=text)))

    def test_missing_round_rejected(self):
        text = re.sub(r"### 第2轮：评审与补强[\s\S]+?(?=\n## 七、)", "", self.plan_text)
        self.assertTrue(any("两轮" in e for e in self.check(content=text)))

    def test_no_hardcoded_001_ids(self):
        self.assertEqual([], self.check())
        self.assertEqual({"REQ-207"}, extract_trace(self.plan_text, "plan")[0])

    def test_unknown_req_rejected(self):
        text = self.plan_text.replace("| TC-208 | REQ-207", "| TC-208 | REQ-301")
        self.assertTrue(any("不存在的需求" in e for e in self.check(content=text)))

    def test_duplicate_tc_rejected(self):
        text = self.plan_text.replace("| TC-208 | REQ-207", "| TC-207 | REQ-207")
        self.assertTrue(any("重复" in e for e in self.check(content=text)))

    def test_missing_acceptance_rejected(self):
        text = self.plan_text.replace("| REQ-207 | 实际代码", "| REQ-207 | 实际代码", 1)
        # Replace only the acceptance table's last requirement row.
        at = text.index("## 五、验收与回滚")
        text = text[:at] + text[at:].replace("| REQ-207 |", "| REQ-999 |", 1)
        self.assertTrue(any("缺少验收条件" in e for e in self.check(content=text)))

    def test_workspace_required(self):
        self.assertTrue(any("workspace" in e for e in validate(self.plan_text, "plan", self.docs / "plan.md", None)))

    def test_wrong_path_rejected(self):
        self.assertTrue(any("必须位于" in e for e in self.check(path=self.ws / "plan.md")))

    def test_placeholder_rejected(self):
        with self.assertRaisesRegex(DocumentError, "占位符"):
            self.check(content=self.plan_text + "\n{{x}}")

    def test_skills_search_priority(self):
        self.assertEqual(["codex-user-modern", "codex-user-legacy", "claude-user"], [x[0] for x in roots(self.ws)[:3]])


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ws = Path(self.temp.name) / "root with spaces"
        self.ws.mkdir()
        self.docs = init(self.ws, "验收方案")
        self.plan = publish_test_doc(self.ws, "验收方案", "plan", "验收方案-实施测试验收方案", fill_template("plan.md"))
        self.file = self.ws / "app.py"
        self.file.write_text("def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n", encoding="utf8")
        (self.ws / "tests").mkdir()
        self.test_source = self.ws / "tests" / "test_real.py"
        self.test_source.write_text("from app import add, sub\n\ndef test_add():\n    assert add(3, 4) == 7\n\ndef test_sub():\n    assert sub(5, 3) == 2\n", encoding="utf8")
        (self.ws / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n", encoding="utf8")
        self.case_map = self.docs / "case-map.json"
        self.case_map.write_text(json.dumps({"schema_version":"1.0", "cases":{
            "TC-207":[{"test_id":"tests.test_real::test_add", "source":"tests/test_real.py"}],
            "TC-208":[{"test_id":"tests.test_real::test_sub", "source":"tests/test_real.py"}]}}), encoding="utf8")
        for args in (("init",), ("config", "user.name", "Test Bot"), ("config", "user.email", "test@invalid.example"), ("add", "app.py", "tests/test_real.py", ".gitignore"), ("commit", "-m", "init")):
            proc = run("git", *args, cwd=self.ws)
            self.assertEqual(0, proc.returncode, proc.stderr)
        self.runs = self.docs / "evidence" / "runs.json"
        self.manifest = self.docs / "manifest.json"
        self.record()
        run_id = json.loads(self.runs.read_text(encoding="utf8"))["runs"][0]["run_id"]
        self.record_id = run_id
        self.manifest_data = {
            "schema_version": "2.1", "plan_file": self.plan.relative_to(self.ws).as_posix(),
            "runs_file": self.runs.relative_to(self.ws).as_posix(),
            "integration": {"worktrees_used": False, "merged": True, "merge_audit": ""},
            "cases": [
                {"id": "TC-207", "status": "PASS", "run_ids": [run_id]},
                {"id": "TC-208", "status": "PASS", "run_ids": [run_id]},
            ],
            "acceptance": [
                {"id": "ACC-207", "requirement_id": "REQ-207", "status": "PASS", "run_ids": [run_id],
                 "notes": "已检查运行日志和可重复的最终版本测试结论"},
            ],
        }
        self.write_manifest()

    def record(self, stage="integrated", success=True):
        cmd = [sys.executable, str(SCRIPTS / "run_and_record.py"), "--workspace", str(self.ws), "--plan", str(self.plan), "--runs", str(self.runs), "--stage", stage, "--cases", "TC-207,TC-208",
               "--runner", "pytest", "--report", ".idea/docs/验收方案/evidence/reports/{run_id}.xml", "--case-map", str(self.case_map),
               "--", sys.executable, "-m", "pytest", "-q", "tests/test_real.py", "--junitxml={report}"]
        proc = run(*cmd, cwd=self.ws)
        self.assertEqual(0 if success else 1, proc.returncode, proc.stdout + proc.stderr)

    def write_manifest(self):
        self.manifest.write_text(json.dumps(self.manifest_data, ensure_ascii=False), encoding="utf8")

    def check(self):
        return validate_evidence(self.manifest, self.plan, self.ws)

    def test_valid_evidence(self):
        self.assertEqual([], self.check())

    def test_source_change_blocks_stale_run(self):
        self.file.write_text("print('changed')", encoding="utf8")
        self.assertTrue(any("需要重测" in e for e in self.check()))

    def test_plan_change_blocks_stale_run(self):
        publish_test_doc(self.ws, "验收方案", "plan", "验收方案-实施测试验收方案", self.plan.read_text(encoding="utf8") + "\n# later update\n")
        self.assertTrue(any("方案版本" in e for e in self.check()))

    def test_log_tamper_blocks(self):
        item = json.loads(self.runs.read_text(encoding="utf8"))["runs"][0]
        log = self.ws / item["log_path"]
        log.write_text("fake result", encoding="utf8")
        self.assertTrue(any("日志内容已改变" in e for e in self.check()))

    def test_missing_case_blocks(self):
        self.manifest_data["cases"].pop()
        self.write_manifest()
        self.assertTrue(any("必测用例未覆盖" in e for e in self.check()))

    def test_failed_case_blocks(self):
        self.manifest_data["cases"][0]["status"] = "FAIL"
        self.write_manifest()
        self.assertTrue(any("未标记 PASS" in e for e in self.check()))

    def test_nonintegrated_run_blocks(self):
        data = json.loads(self.runs.read_text(encoding="utf8"))
        data["runs"][0]["stage"] = "isolated"
        self.runs.write_text(json.dumps(data), encoding="utf8")
        self.assertTrue(any("未集成阶段" in e for e in self.check()))

    def test_failed_run_blocks(self):
        data = json.loads(self.runs.read_text(encoding="utf8"))
        data["runs"][0]["exit_code"] = 1
        data["runs"][0]["status"] = "FAIL"
        self.runs.write_text(json.dumps(data), encoding="utf8")
        self.assertTrue(any("失败" in e for e in self.check()))

    def test_worktree_merge_audit_required(self):
        self.manifest_data["integration"]["worktrees_used"] = True
        self.write_manifest()
        self.assertTrue(any("合并审计" in e for e in self.check()))

    def test_acceptance_missing_blocks(self):
        self.manifest_data["acceptance"] = []
        self.write_manifest()
        self.assertTrue(any("缺少验收结果" in e for e in self.check()))

    def test_run_without_coverage_blocks(self):
        data = json.loads(self.runs.read_text(encoding="utf8"))
        data["runs"][0]["case_ids"] = ["TC-207"]
        self.runs.write_text(json.dumps(data), encoding="utf8")
        self.assertTrue(any("未声明覆盖" in e for e in self.check()))

    def test_fixture_tamper_blocks(self):
        fixture = self.ws / "test-dir" / "input.json"
        fixture.parent.mkdir()
        fixture.write_text('{"id":1}', encoding="utf8")
        cmd = [sys.executable, str(SCRIPTS / "run_and_record.py"), "--workspace", str(self.ws), "--plan", str(self.plan), "--runs", str(self.runs), "--stage", "integrated", "--cases", "TC-207,TC-208", "--fixtures", "test-dir/input.json", "--runner", "pytest", "--report", ".idea/docs/验收方案/evidence/reports/{run_id}.xml", "--case-map", str(self.case_map), "--", sys.executable, "-m", "pytest", "-q", "tests/test_real.py", "--junitxml={report}"]
        proc = run(*cmd, cwd=self.ws)
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        newer = json.loads(self.runs.read_text(encoding="utf8"))["runs"][-1]["run_id"]
        for c in self.manifest_data["cases"]:
            c["run_ids"] = [newer]
        self.manifest_data["acceptance"][0]["run_ids"] = [newer]
        self.write_manifest()
        self.assertEqual([], self.check())
        fixture.write_text('{"id":2}', encoding="utf8")
        self.assertTrue(any("测试输入已缺失或改变" in e or "需要重测" in e for e in self.check()))

    def test_command_modifies_source_is_blocked(self):
        # The runner must detect a real pytest test that writes into production source.
        self.test_source.write_text(self.test_source.read_text(encoding="utf8") +
            "\ndef test_mutate():\n    from pathlib import Path\n    Path('app.py').write_text('mutated')\n    assert True\n", encoding="utf8")
        cmd = [sys.executable, str(SCRIPTS / "run_and_record.py"), "--workspace", str(self.ws), "--plan", str(self.plan), "--runs", str(self.runs), "--stage", "integrated", "--cases", "TC-207,TC-208", "--runner", "pytest", "--report", ".idea/docs/验收方案/evidence/reports/{run_id}.xml", "--case-map", str(self.case_map), "--", sys.executable, "-m", "pytest", "-q", "tests/test_real.py", "--junitxml={report}"]
        proc = run(*cmd, cwd=self.ws)
        self.assertEqual(2, proc.returncode, proc.stdout + proc.stderr)
        self.assertEqual("BLOCKED", json.loads(self.runs.read_text(encoding="utf8"))["runs"][-1]["status"])

    def test_print_pass_cannot_claim_a_test(self):
        cmd = [sys.executable, str(SCRIPTS / "run_and_record.py"), "--workspace", str(self.ws), "--plan", str(self.plan), "--runs", str(self.runs), "--stage", "integrated", "--cases", "TC-207,TC-208", "--runner", "pytest", "--report", ".idea/docs/验收方案/evidence/reports/{run_id}.xml", "--case-map", str(self.case_map), "--", sys.executable, "-c", "print('PASS')"]
        proc = run(*cmd, cwd=self.ws)
        self.assertNotEqual(0, proc.returncode)
        self.assertIn("必须真正执行 pytest", proc.stderr)

    def test_no_assertion_is_blocked(self):
        self.test_source.write_text("def test_add():\n    print('PASS')\ndef test_sub():\n    return True\n", encoding="utf8")
        cmd = [sys.executable, str(SCRIPTS / "run_and_record.py"), "--workspace", str(self.ws), "--plan", str(self.plan), "--runs", str(self.runs), "--stage", "integrated", "--cases", "TC-207,TC-208", "--runner", "pytest", "--report", ".idea/docs/验收方案/evidence/reports/{run_id}.xml", "--case-map", str(self.case_map), "--", sys.executable, "-m", "pytest", "-q", "tests/test_real.py", "--junitxml={report}"]
        p = run(*cmd, cwd=self.ws)
        self.assertEqual(2, p.returncode, p.stdout + p.stderr)
        self.assertIn("没有可识别的断言", p.stdout)

    def test_report_tamper_is_blocked(self):
        entry = json.loads(self.runs.read_text(encoding="utf8"))["runs"][0]
        file = self.ws / entry["report_path"]
        file.write_text("<testsuite/>", encoding="utf8")
        self.assertTrue(any("报告" in e or "report_sha256" in e for e in self.check()))

    def test_case_map_tamper_is_blocked(self):
        obj = json.loads(self.case_map.read_text(encoding="utf8"))
        obj["cases"].pop("TC-207")
        self.case_map.write_text(json.dumps(obj), encoding="utf8")
        self.assertTrue(any("映射" in e for e in self.check()))

    def test_missing_plan_review_blocks_final_gate(self):
        content = self.plan.read_text(encoding="utf8")
        self.plan.write_text(re.sub(r"## 六、评审与补强记录[\s\S]+?(?=\n## 七、)", "", content), encoding="utf8")
        self.assertTrue(any("正式方案 P 门禁" in e for e in self.check()))

    def test_old_self_reported_schema_rejected(self):
        self.manifest_data["schema_version"] = "2.0"
        self.write_manifest()
        self.assertTrue(any("旧版" in e for e in self.check()))

    def test_invalid_run_case_ids_are_rejected_without_crash(self):
        obj = json.loads(self.runs.read_text(encoding="utf8"))
        obj["runs"][0]["case_ids"] = [{"fake": 1}]
        self.runs.write_text(json.dumps(obj), encoding="utf8")
        self.assertTrue(any("case_ids" in e or "未声明覆盖" in e for e in self.check()))

    def test_trivial_assert_true_is_rejected(self):
        self.test_source.write_text("def test_add():\n    assert True\ndef test_sub():\n    assert 1 == 1\n", encoding="utf8")
        cmd = [sys.executable, str(SCRIPTS / "run_and_record.py"), "--workspace", str(self.ws), "--plan", str(self.plan), "--runs", str(self.runs), "--stage", "integrated", "--cases", "TC-207,TC-208", "--runner", "pytest", "--report", ".idea/docs/验收方案/evidence/reports/{run_id}.xml", "--case-map", str(self.case_map), "--", sys.executable, "-m", "pytest", "-q", "tests/test_real.py", "--junitxml={report}"]
        p = run(*cmd, cwd=self.ws)
        self.assertEqual(2, p.returncode, p.stdout + p.stderr)
        self.assertIn("没有可识别的断言", p.stdout)

    def test_auto_hash_test_dir_inputs(self):
        folder = self.ws / "test-dir"
        folder.mkdir()
        (folder / "data.json").write_text('{"sample":1}', encoding="utf8")
        self.record()
        entry = json.loads(self.runs.read_text(encoding="utf8"))["runs"][-1]
        self.assertTrue(any(i["path"] == "test-dir/data.json" for i in entry["fixtures"]))
        for case in self.manifest_data["cases"]:
            case["run_ids"] = [entry["run_id"]]
        self.manifest_data["acceptance"][0]["run_ids"] = [entry["run_id"]]
        self.write_manifest()
        self.assertEqual([], self.check())
        (folder / "data.json").write_text('{"sample":2}', encoding="utf8")
        self.assertTrue(any("已缺失或改变" in e or "需要重测" in e for e in self.check()))

    def test_invalid_run_id_type_fails_cleanly(self):
        self.manifest_data["cases"][0]["run_ids"] = [[123]]
        self.write_manifest()
        self.assertTrue(any("非法 RUN" in e for e in self.check()))

    def test_malformed_manifest_ids_fail_cleanly(self):
        self.manifest_data["acceptance"][0]["id"] = ["ACC-207"]
        self.manifest_data["cases"][0]["id"] = ["TC-207"]
        self.write_manifest()
        self.assertTrue(any("无效或重复" in e or "不存在或重复" in e for e in self.check()))

    def test_cross_working_directory_and_spaces(self):
        p = run(sys.executable, str(SCRIPTS / "validate_evidence.py"), "--workspace", self.ws, "--plan", self.plan, "--manifest", self.manifest, cwd=ROOT)
        self.assertEqual(0, p.returncode, p.stdout + p.stderr)

    def test_cross_plan_manifest_rejected(self):
        other = init(self.ws, "其他方案")
        wrong = other / "evidence" / "manifest.json"
        wrong.parent.mkdir(parents=True, exist_ok=True)
        wrong.write_text(self.manifest.read_text(encoding="utf8"), encoding="utf8")
        self.assertTrue(any("同一" in e for e in validate_evidence(wrong, self.plan, self.ws)))

    def test_cross_plan_runs_rejected(self):
        other = init(self.ws, "其他方案")
        other_runs = other / "evidence" / "runs.json"
        other_runs.parent.mkdir(parents=True, exist_ok=True)
        other_runs.write_text(self.runs.read_text(encoding="utf8"), encoding="utf8")
        self.manifest_data["runs_file"] = other_runs.relative_to(self.ws).as_posix()
        self.write_manifest()
        self.assertTrue(any("runs_file" in e for e in self.check()))

    def test_manual_gate_calls_evidence_gate(self):
        manual = publish_test_doc(self.ws, "验收方案", "manual", "验收方案-手动测试验收方案", fill_template("manual-acceptance.md"))
        cmd = [sys.executable, str(SCRIPTS / "validate_docs.py"), "--type", "manual", "--workspace", str(self.ws), "--file", str(manual), "--plan", str(self.plan), "--manifest", str(self.manifest)]
        p = run(*cmd, cwd=ROOT)
        self.assertEqual(0, p.returncode, p.stdout + p.stderr)
        self.file.write_text('print("modified")', encoding="utf8")
        p = run(*cmd, cwd=ROOT)
        self.assertEqual(1, p.returncode, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
