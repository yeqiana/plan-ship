#!/usr/bin/env python3
"""Strict, fail-closed JUnit XML to TC mapping with source-level assertion checks.

This checks execution artifacts, not the semantic truth of an assertion. A capable
adversary with write access can tamper with inputs; controlled runners remain required.
"""
from __future__ import annotations

import ast
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from project_snapshot import safe_inside, sha256_file

MAX_XML_BYTES = 5 * 1024 * 1024
TEST_ID = re.compile(r"^[a-zA-Z_][\w.\-$]*(?:::[a-zA-Z_][\w\[\] ,.-]*)+$")
TC_ID = re.compile(r"^TC-\d{3,}$")


def _obvious_true(node: ast.AST) -> bool:
    """Reject common tautologies, including constant short-circuit expressions."""
    if isinstance(node, ast.Constant):
        return bool(node.value)
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.Or):
            return any(_obvious_true(v) for v in node.values)
        if isinstance(node.op, ast.And):
            return all(_obvious_true(v) for v in node.values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return _obvious_false(node.operand)
    if isinstance(node, ast.Compare):
        try:
            values = [ast.literal_eval(v) for v in [node.left, *node.comparators]]
        except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
            return False
        checks = []
        for op, lhs, rhs in zip(node.ops, values, values[1:]):
            try:
                checks.append((isinstance(op, ast.Eq) and lhs == rhs) or
                              (isinstance(op, ast.Is) and lhs is rhs) or
                              (isinstance(op, ast.NotEq) and lhs != rhs) or
                              (isinstance(op, ast.Gt) and lhs > rhs) or
                              (isinstance(op, ast.Lt) and lhs < rhs))
            except (ValueError, TypeError):
                return False
        return bool(checks) and all(checks)
    return False


def _obvious_false(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return not bool(node.value)
    if isinstance(node, ast.BoolOp):
        return all(_obvious_false(v) for v in node.values) if isinstance(node.op, ast.Or) else any(_obvious_false(v) for v in node.values)
    return False


def _project_imports(tree: ast.Module, workspace: Path, source: Path) -> tuple[set[str], set[str]]:
    """Only imports that resolve to a real, non-test project module count."""
    functions: set[str] = set()
    modules: set[str] = set()
    for part in tree.body:
        if isinstance(part, ast.ImportFrom) and part.level == 0 and part.module:
            names = [(part.module, alias.name, alias.asname or alias.name) for alias in part.names]
        elif isinstance(part, ast.Import):
            names = [(alias.name, None, alias.asname or alias.name.split('.')[0]) for alias in part.names]
        else:
            continue
        for module, func, alias in names:
            candidates = [workspace / (module.replace('.', '/') + '.py'), workspace / module.replace('.', '/') / '__init__.py']
            for candidate in candidates:
                if not candidate.is_file() or not safe_inside(candidate, workspace) or candidate.resolve() == source.resolve():
                    continue
                rel = candidate.relative_to(workspace)
                if any(piece in ('tests', 'test', 'test-dir', '.idea') for piece in rel.parts) or candidate.stem.startswith('test_'):
                    continue
                if func is None:
                    modules.add(alias)
                elif func != '*':
                    functions.add(alias)
    return functions, modules


def _production_calls(node: ast.AST, functions: set[str], modules: set[str]) -> set[str]:
    called = set()
    for part in ast.walk(node):
        if not isinstance(part, ast.Call):
            continue
        f = part.func
        if isinstance(f, ast.Name) and f.id in functions:
            called.add(f.id)
        elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in modules:
            called.add(f.value.id + '.' + f.attr)
    return called


def _python_source_has_assertion(path: Path, test_name: str, workspace: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'))
    except (SyntaxError, UnicodeError, OSError):
        return False
    base_name = test_name.split('[')[0]
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == base_name]
    if len(funcs) != 1:
        return False
    func = funcs[0]
    functions, modules = _project_imports(tree, workspace, path)
    if not functions and not modules:
        return False
    # Retain a conservative def-use relation: assertions must actually observe
    # the output/state of an imported production call, not an unrelated constant.
    assigned: set[str] = set()
    for stmt in ast.walk(func):
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            value = stmt.value
            if value and _production_calls(value, functions, modules):
                targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
                for target in targets:
                    assigned.update(n.id for n in ast.walk(target) if isinstance(n, ast.Name))
    for part in ast.walk(func):
        if isinstance(part, ast.Assert):
            if _obvious_true(part.test):
                continue
            referenced = {x.id for x in ast.walk(part.test) if isinstance(x, ast.Name)}
            if _production_calls(part.test, functions, modules) or assigned & referenced:
                return True
        if isinstance(part, ast.With):
            for item in part.items:
                ctx = item.context_expr
                if isinstance(ctx, ast.Call) and isinstance(ctx.func, ast.Attribute) and ctx.func.attr == 'raises':
                    if _production_calls(part, functions, modules):
                        return True
    return False


def _java_source_has_assertion(path: Path, test_name: str) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeError, OSError):
        return False
    # Conservative Java/JUnit check. The annotation and method must appear together;
    # read only the balanced method body, not arbitrary assertions elsewhere in class.
    name = re.escape(test_name.split("[")[0].split("(")[0])
    for match in re.finditer(r"\b(?:void|[A-Za-z_][\w<>\[\]]*)\s+" + name + r"\s*\([^)]*\)\s*(?:throws\s+[\w., ]+\s*)?\{", text):
        prefix = text[max(0, match.start() - 350):match.start()]
        if not re.search(r"@(?:org\.junit\.(?:jupiter\.api\.)?)?Test\b", prefix):
            continue
        depth, start = 1, match.end()
        for pos in range(start, len(text)):
            if text[pos] == "{":
                depth += 1
            elif text[pos] == "}":
                depth -= 1
                if depth == 0:
                    body = text[start:pos]
                    # A bare assertTrue(true)/assertEquals(1,1) is not proof.
                    if re.search(r"\bassertTrue\s*\(\s*true\s*\)", body):
                        body = re.sub(r"\bassertTrue\s*\(\s*true\s*\)\s*;?", "", body)
                    if not re.search(r"\b(?:assert\w+|fail|verify|assertThat)\s*\(|\bassert\s+", body):
                        break
                    # Static heuristic: must invoke a non-assert business method in
                    # the test method and link it to an expectation. Mockito-only
                    # interactions and fixture setup do not qualify.
                    calls = re.findall(r"\b([A-Za-z_]\w*)\s*\.\s*([A-Za-z_]\w*)\s*\(", body)
                    ignored = {'Assertions', 'Assert', 'assert', 'Mockito', 'System', 'Math', 'Thread', 'List', 'Collections', 'Stream', 'Paths', 'Files', 'logger', 'log', 'verify', 'assertThat'}
                    business_calls = [(obj, method) for obj, method in calls if obj not in ignored and not method.startswith('assert') and method not in ('verify','fail','raises','mock','when','thenReturn','print','println')]
                    if business_calls:
                        return True
                    break
    return False


def validate_test_artifacts(report: Path, case_map: Path, workspace: Path, required_cases: set[str]) -> tuple[list[str], dict[str, object]]:
    errors: list[str] = []
    workspace = workspace.resolve()
    if not safe_inside(report, workspace) or not safe_inside(case_map, workspace):
        return ["报告或用例映射路径超出工作区"], {}
    if not report.is_file() or not case_map.is_file():
        return ["缺少实际生成的 JUnit XML 报告或用例映射文件"], {}
    if report.stat().st_size > MAX_XML_BYTES:
        return ["测试报告超出 5MB 限额"], {}
    try:
        mapping = json.loads(case_map.read_text(encoding="utf-8"))
        root = ET.parse(report).getroot()
    except (ValueError, OSError, ET.ParseError, UnicodeError) as exc:
        return [f"无法解析真实测试报告或用例映射：{exc}"], {}
    if not isinstance(mapping, dict) or mapping.get("schema_version") != "1.0" or not isinstance(mapping.get("cases"), dict):
        return ["case-map 缺少 schema_version=1.0 或 cases 对象"], {}
    if root.tag not in ("testsuite", "testsuites"):
        return ["报告必须是 JUnit XML testsuite/testsuites"], {}

    found: dict[str, ET.Element] = {}
    for suite in ([root] if root.tag == "testsuite" else root.findall(".//testsuite")):
        # Never accept an empty report with a fabricated summary.
        if suite.tag != "testsuite":
            continue
        for test in suite.findall("testcase"):
            name, cls = test.get("name", ""), test.get("classname", "")
            key = f"{cls}::{name}"
            if not cls or not name or key in found:
                errors.append(f"测试标识缺失或重复：{key}")
            if test.find("failure") is not None or test.find("error") is not None or test.find("skipped") is not None:
                errors.append(f"测试存在失败、错误或跳过：{key}")
            found[key] = test
    if not found:
        errors.append("JUnit XML 没有任何真实 testcase 记录")

    case_defs = mapping["cases"]
    if set(case_defs) != required_cases:
        errors.append(f"用例映射必须准确对应本次 TC：期望 {sorted(required_cases)}，实际 {sorted(map(str, case_defs))}")
    used_ids: set[str] = set()
    sources: dict[str, str] = {}
    for case_id, tests in case_defs.items():
        if not isinstance(case_id, str) or not TC_ID.fullmatch(case_id) or not isinstance(tests, list) or not tests:
            errors.append(f"{case_id} 映射缺少有效的测试项")
            continue
        for item in tests:
            if not isinstance(item, dict) or not isinstance(item.get("test_id"), str) or not isinstance(item.get("source"), str):
                errors.append(f"{case_id} 测试项必须包含字符串 test_id 和 source")
                continue
            test_id, rel = item["test_id"], item["source"]
            if not TEST_ID.fullmatch(test_id):
                errors.append(f"{case_id} 的测试标识格式无效：{test_id}")
                continue
            if test_id in used_ids:
                errors.append(f"同一个框架测试不能冒充多个 TC：{test_id}")
            used_ids.add(test_id)
            if test_id not in found:
                errors.append(f"{case_id} 未在 JUnit XML 中实际执行：{test_id}")
            source = (workspace / rel).resolve()
            if not safe_inside(source, workspace) or not source.is_file() or source.suffix.lower() not in (".py", ".java"):
                errors.append(f"{case_id} 的测试源码缺失或不在工作区：{rel}")
                continue
            # Do not allow case ids to point at arbitrary unrelated assertion text.
            name = test_id.rsplit("::", 1)[-1]
            is_asserting = _python_source_has_assertion(source, name, workspace) if source.suffix.lower() == ".py" else _java_source_has_assertion(source, name)
            if not is_asserting:
                errors.append(f"{case_id} 的测试源码没有可识别的断言（需要关联真实业务代码调用与预期行为）：{test_id} / {rel}")
            sources[source.relative_to(workspace).as_posix()] = sha256_file(source)
    return errors, {"report_sha256": sha256_file(report), "case_map_sha256": sha256_file(case_map), "test_sources": sources, "verified_test_ids": sorted(used_ids)}
