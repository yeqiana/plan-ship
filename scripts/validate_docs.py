#!/usr/bin/env python3
"""Validate review gates and traceability. This is NOT a substitute for independent review."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from doc_registry import verify_file

REQUIRED = {
    "plan": ["需求与上下文", "现状与影响面", "技术实施", "测试用例", "验收与回滚", "评审与补强记录", "最终门禁"],
    "testcases": ["测试用例差距", "新增用例", "评审与补强记录", "最终门禁"],
    "manual": ["环境与前置条件", "逐步手动验收", "异常与清理", "评审与补强记录", "最终门禁"],
}
ROUND = re.compile(r"(?m)^###\s*第\s*(\d+)\s*轮[：:]\s*评审与补强\s*$")
HEADING = re.compile(r"(?m)^#{1,3}\s+")
FIELD = re.compile(r"(?m)^\s*-\s*([^：:\n]+)\s*[：:]\s*(.*?)\s*$")
PLACEHOLDER = re.compile(r"\{\{[^\n]*?\}\}|\bTODO\b|\bTBD\b", re.I)
REQ = re.compile(r"\bREQ-\d{3,}\b")
TC = re.compile(r"\bTC-\d{3,}\b")
MTC = re.compile(r"\bMTC-\d{3,}\b")
FIELDS = ("审查视角", "评审发现", "补强动作", "修改前", "修改后", "依据证据", "复核结论", "遗留阻断")
BAD_VALUES = {"无", "没有", "不适用", "略", "已处理", "已完成", "正常", "通过", "待完善", "未确认", "已核查", "无问题", "暂无"}


def sections(content: str) -> dict[str, str]:
    matches = list(re.finditer(r"(?m)^##\s+([^\n]+)$", content))
    return {m.group(1): content[m.end():matches[i+1].start() if i+1 < len(matches) else len(content)] for i,m in enumerate(matches)}


def section_of(content: str, key: str) -> str:
    return next((value for title, value in sections(content).items() if key in title), "")


def table_rows(text: str) -> list[list[str]]:
    return [[c.strip() for c in line.strip().strip("|").split("|")] for line in text.splitlines() if line.strip().startswith("|")]


def extract_trace(content: str, kind: str) -> tuple[set[str], dict[str, set[str]], list[str]]:
    """Parse first-column actual data rows; don't count IDs in prose or headers as coverage."""
    errors = []
    requirements: set[str] = set()
    test_cases: dict[str, set[str]] = {}
    if kind == "plan":
        req_sec = section_of(content, "需求与上下文")
        for row in table_rows(req_sec):
            if row and REQ.fullmatch(row[0]):
                if row[0] in requirements:
                    errors.append(f"需求 ID 重复：{row[0]}")
                requirements.add(row[0])
        if not requirements:
            errors.append("需求追踪表缺少有效的 REQ-xxx 行")
    if kind in ("plan", "testcases"):
        tc_sec = section_of(content, "测试用例" if kind == "plan" else "新增用例")
        for row in table_rows(tc_sec):
            if row and TC.fullmatch(row[0]):
                if row[0] in test_cases:
                    errors.append(f"测试用例 ID 重复：{row[0]}")
                refs = set(REQ.findall(row[1])) if len(row) > 1 else set()
                if not refs:
                    errors.append(f"用例 {row[0]} 缺少关联 REQ")
                test_cases[row[0]] = refs
        if not test_cases:
            errors.append("测试用例表缺少有效的 TC-xxx 行")
    if kind == "plan":
        for tc_id, refs in test_cases.items():
            for ref in refs - requirements:
                errors.append(f"用例 {tc_id} 引用不存在的需求 {ref}")
        covered = set().union(*test_cases.values()) if test_cases else set()
        for ref in requirements - covered:
            errors.append(f"需求 {ref} 没有关联测试用例")
        acceptance = section_of(content, "验收与回滚")
        accepted = {row[0] for row in table_rows(acceptance) if row and REQ.fullmatch(row[0])}
        for ref in requirements - accepted:
            errors.append(f"需求 {ref} 缺少验收条件")
    return requirements, test_cases, errors


def fields_for(text: str) -> tuple[dict[str, str], set[str]]:
    values: dict[str, str] = {}
    duplicates: set[str] = set()
    for name, value in FIELD.findall(text):
        name = name.strip()
        if name in values:
            duplicates.add(name)
        values[name] = value.strip()
    return values, duplicates


def review_errors(content: str) -> list[str]:
    errors: list[str] = []
    rounds = list(ROUND.finditer(content))
    numbers = [int(m.group(1)) for m in rounds]
    if len(rounds) < 2:
        errors.append("不足两轮『评审→补强』记录")
    if numbers != list(range(1, len(numbers) + 1)):
        errors.append(f"评审轮次必须严格按第1轮起连续递增，当前 {numbers}")
    review_section = section_of(content, "评审与补强记录")
    if len(ROUND.findall(review_section)) != len(rounds):
        errors.append("评审轮次必须全部位于『评审与补强记录』章节")
    found_actions: set[str] = set()
    for i, match in enumerate(rounds):
        tail = content[match.end():(rounds[i+1].start() if i+1 < len(rounds) else len(content))]
        stop = HEADING.search(tail)
        fields, duplicates = fields_for(tail[:stop.start()] if stop else tail)
        n = numbers[i]
        errors.extend(f"第{n}轮重复字段：{key}" for key in sorted(duplicates & set(FIELDS)))
        for key in FIELDS:
            if not fields.get(key):
                errors.append(f"第{n}轮缺少字段：{key}")
        for key in ("审查视角", "评审发现", "补强动作", "修改前", "修改后", "依据证据"):
            value = fields.get(key, "")
            if len(value) < 12 or value in BAD_VALUES:
                errors.append(f"第{n}轮『{key}』缺少可追踪的实质内容")
        if fields.get("修改前") == fields.get("修改后"):
            errors.append(f"第{n}轮修改前后内容完全一致，未体现实际补强")
        if fields.get("补强动作") in found_actions:
            errors.append(f"第{n}轮补强动作重复，疑似空转")
        found_actions.add(fields.get("补强动作", ""))
        if fields.get("复核结论") != "通过":
            errors.append(f"第{n}轮复核结论必须为『通过』")
        if fields.get("遗留阻断") != "无":
            errors.append(f"第{n}轮存在未清除阻断：{fields.get('遗留阻断','缺失')}")

    finals = list(re.finditer(r"(?m)^###\s*最终复核\s*$", content))
    if len(finals) != 1:
        errors.append("必须有且仅有一个『### 最终复核』")
    else:
        m = finals[0]
        if rounds and m.start() < rounds[-1].end():
            errors.append("最终复核必须在所有评审轮次之后")
        tail = content[m.end():]
        stop = HEADING.search(tail)
        final, duplicates = fields_for(tail[:stop.start()] if stop else tail)
        if duplicates:
            errors.append("最终复核存在重复字段")
        if final.get("最终结果") != "通过":
            errors.append("最终结果必须为『通过』")
        if final.get("遗留阻断") != "无":
            errors.append("最终复核遗留阻断必须为『无』")
        if len(final.get("证据索引", "")) < 12:
            errors.append("最终复核证据索引不足")
    return errors


def validate(content: str, kind: str, file: Path, workspace: Path | None, plan_content: str | None = None) -> list[str]:
    if kind not in REQUIRED:
        raise ValueError(kind)
    if not content.strip():
        return ["文件为空"]
    errors = []
    if workspace is None:
        errors.append("缺少项目根路径 --workspace")
    else:
        errors.extend(verify_file(file, workspace))
    if PLACEHOLDER.search(content):
        errors.append("存在未替换的模板占位符")
    heads = re.findall(r"(?m)^##\s+(.+)$", content)
    for h in REQUIRED[kind]:
        if not any(h in heading for heading in heads):
            errors.append(f"缺少二级章节：{h}")
    errors.extend(review_errors(content))
    if kind == "plan":
        _, _, trace_errors = extract_trace(content, kind)
        errors.extend(trace_errors)
        if "最小改动" not in content or "回归" not in content:
            errors.append("缺少最小变更边界或旧功能回归")
        if not re.search(r"修订版本\s*[：:]\s*v\d+", content):
            errors.append("缺少有效的修订版本（如 修订版本：v2）")
    elif kind == "testcases":
        _, cases, trace_errors = extract_trace(content, kind)
        errors.extend(trace_errors)
        if plan_content is None:
            errors.append("用例补充校验必须传入原正式方案 --plan")
        else:
            original_req, original_tc, errs = extract_trace(plan_content, "plan")
            errors.extend(f"原方案：{e}" for e in errs)
            for tc_id, refs in cases.items():
                if tc_id in original_tc:
                    errors.append(f"补充用例 {tc_id} 与原方案已有用例冲突")
                for req in refs - original_req:
                    errors.append(f"补充用例 {tc_id} 引用了方案中不存在的需求 {req}")
        for key in ("修订版本", "变更编号", "更新前", "更新后"):
            if key not in content:
                errors.append(f"用例补充缺少审计字段：{key}")
    else:
        manual = section_of(content, "逐步手动验收")
        if not MTC.search(manual):
            errors.append("手动验收章节缺少 MTC-xxx 场景")
        for key in ("操作", "预期结果", "通过判定", "测试后清理", "用户手动复验状态", "已执行的自动化测试与验收证据"):
            if key not in content:
                errors.append(f"手动验收缺少字段：{key}")
        if "用户手动复验状态：未执行" not in content:
            errors.append("不能把人工手动复验虚构为已经完成；应标记未执行")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--type", required=True, choices=sorted(REQUIRED))
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--plan", type=Path, help="For testcase supplement/manual validation")
    parser.add_argument("--manifest", type=Path, help="Required for final manual document")
    args = parser.parse_args()
    if not args.file.is_file():
        print(f"FAIL: 文件不存在：{args.file}")
        return 2
    try:
        plan_content = args.plan.read_text(encoding="utf-8-sig") if args.plan else None
        content = args.file.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        print(f"FAIL: 读取文件失败：{exc}")
        return 2
    errors = validate(content, args.type, args.file, args.workspace, plan_content)
    if args.type == "manual":
        if not args.plan or not args.manifest:
            errors.append("手动验收最终门禁要求 --plan 和 --manifest")
        else:
            from validate_evidence import validate_counterfactual_evidence
            errors.extend(f"交付证据：{e}" for e in validate_counterfactual_evidence(args.manifest, args.plan, args.workspace))
    if errors:
        print(f"FAIL ({len(errors)}):")
        for error in errors:
            print(" -", error)
        return 1
    print(f"PASS: {args.type} 文档目录、双副本、轮次与追踪门禁：{args.file}")
    print("注意：文档字段校验不等于内容独立评审；证据门禁也不等于人工复验。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
