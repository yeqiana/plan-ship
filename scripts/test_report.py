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


def _literal_value(node: ast.AST):
    """Evaluate only small side-effect-free literals; never evaluate Python code."""
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == 'bool' and len(node.args) == 1 and not node.keywords):
        return bool(_literal_value(node.args[0]))
    if isinstance(node, ast.IfExp):
        condition = _constant_bool(node.test)
        if condition is not None:
            return _literal_value(node.body if condition else node.orelse)
        raise ValueError('conditional value unknown')
    if isinstance(node, ast.Constant) and type(node.value) in (int, float, bool, str, type(None)):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.Not, ast.UAdd, ast.USub)):
        value = _literal_value(node.operand)
        if isinstance(node.op, ast.Not):
            return not value
        if type(value) in (int, float):
            return +value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult)):
        a, b = _literal_value(node.left), _literal_value(node.right)
        if type(a) in (int, float) and type(b) in (int, float) and abs(a) < 100000 and abs(b) < 100000:
            result = a+b if isinstance(node.op, ast.Add) else a-b if isinstance(node.op, ast.Sub) else a*b
            if abs(result) < 100000000:
                return result
    raise ValueError('not a bounded literal')


def _constant_bool(node: ast.AST) -> bool | None:
    if isinstance(node, ast.IfExp):
        condition = _constant_bool(node.test)
        if condition is not None:
            return _constant_bool(node.body if condition else node.orelse)
        left, right = _constant_bool(node.body), _constant_bool(node.orelse)
        return left if left is not None and left == right else None
    try:
        return bool(_literal_value(node))
    except (ValueError, TypeError, OverflowError):
        pass
    if isinstance(node, ast.Compare):
        try:
            values = [_literal_value(x) for x in [node.left, *node.comparators]]
            checks = []
            for op, a, b in zip(node.ops, values, values[1:]):
                if isinstance(op, (ast.Eq, ast.Is)): checks.append(a == b)
                elif isinstance(op, (ast.NotEq, ast.IsNot)): checks.append(a != b)
                elif isinstance(op, ast.Lt): checks.append(a < b)
                elif isinstance(op, ast.LtE): checks.append(a <= b)
                elif isinstance(op, ast.Gt): checks.append(a > b)
                elif isinstance(op, ast.GtE): checks.append(a >= b)
                else: return None
            return all(checks)
        except (ValueError, TypeError):
            return None
    if isinstance(node, ast.BoolOp):
        vals = [_constant_bool(x) for x in node.values]
        if isinstance(node.op, ast.Or):
            return True if True in vals else False if all(v is False for v in vals) else None
        if isinstance(node.op, ast.And):
            return False if False in vals else True if all(v is True for v in vals) else None
    return None


def _reachable_nodes(statements: list[ast.stmt]):
    """Conservative static reachability: skip literal-false branches and code after return."""
    for stmt in statements:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(stmt, ast.If):
            condition = _constant_bool(stmt.test)
            yield from _reachable_nodes(stmt.body if condition is True else stmt.orelse if condition is False else stmt.body + stmt.orelse)
            continue
        if isinstance(stmt, ast.While) and _constant_bool(stmt.test) is False:
            yield from _reachable_nodes(stmt.orelse)
            continue
        yield stmt
        if isinstance(stmt, (ast.With, ast.AsyncWith, ast.For, ast.AsyncFor, ast.While, ast.Try)):
            branches = [stmt.body, stmt.orelse] if hasattr(stmt, 'orelse') else [stmt.body]
            if isinstance(stmt, ast.Try):
                branches += [handler.body for handler in stmt.handlers] + [stmt.finalbody]
            for branch in branches:
                yield from _reachable_nodes(branch)
        if isinstance(stmt, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
            break


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
    return _constant_bool(node) is True


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


def _grounded_python_assertion(expr: ast.AST, functions: set[str],
                               modules: set[str], assigned: set[str]) -> bool:
    """Find a structurally independent expectation, not a self-confirming comparison.

    This is only a conservative *structural* check. Even a literal expectation
    can be wrong: real business acceptance still requires negative controls.
    """
    if _obvious_true(expr):
        return False
    if isinstance(expr, ast.IfExp):
        condition = _constant_bool(expr.test)
        if condition is not None:
            return _grounded_python_assertion(expr.body if condition else expr.orelse, functions, modules, assigned)
        return (_grounded_python_assertion(expr.body, functions, modules, assigned)
                and _grounded_python_assertion(expr.orelse, functions, modules, assigned))
    if isinstance(expr, ast.BoolOp):
        # An OR may pass without checking business results if any branch is a
        # known tautology. AND may fail before observing results; static scans
        # alone are never final proof, but exclude obvious bypasses.
        if isinstance(expr.op, ast.Or) and any(_constant_bool(x) is True for x in expr.values):
            return False
        if isinstance(expr.op, ast.And) and any(_constant_bool(x) is False for x in expr.values):
            return False
        return any(_grounded_python_assertion(x, functions, modules, assigned)
                   for x in expr.values)
    if isinstance(expr, ast.Compare):
        operands = [expr.left, *expr.comparators]
        if any(ast.dump(a, include_attributes=False) == ast.dump(b, include_attributes=False)
               for a, b in zip(operands, operands[1:])):
            return False
        observed = [bool(_production_calls(x, functions, modules) or
                         assigned.intersection(n.id for n in ast.walk(x) if isinstance(n, ast.Name)))
                    for x in operands]
        # Comparing two outputs from the code under test is not an independent
        # oracle; both can change together and still produce a green test.
        return any(observed) and any(not x for x in observed)
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not):
        return _grounded_python_assertion(expr.operand, functions, modules, assigned)
    return bool(_production_calls(expr, functions, modules) or
                assigned.intersection(n.id for n in ast.walk(expr) if isinstance(n, ast.Name)))


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
    reachable = list(_reachable_nodes(func.body))
    assigned: set[str] = set()
    for stmt in reachable:
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            value = stmt.value
            if value and _production_calls(value, functions, modules):
                targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
                for target in targets:
                    assigned.update(n.id for n in ast.walk(target) if isinstance(n, ast.Name))
    # Propagate simple aliases of production-derived values; comparing
    # `expected = actual` with `actual` must not be an independent oracle.
    for _ in range(4):
        earlier = len(assigned)
        for stmt in reachable:
            if isinstance(stmt, (ast.Assign, ast.AnnAssign)) and isinstance(stmt.value, ast.Name) and stmt.value.id in assigned:
                targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
                for target in targets:
                    assigned.update(n.id for n in ast.walk(target) if isinstance(n, ast.Name))
        if len(assigned) == earlier:
            break
    for part in reachable:
        if isinstance(part, ast.Assert) and _grounded_python_assertion(part.test, functions, modules, assigned):
            return True
        if isinstance(part, ast.With):
            for item in part.items:
                ctx = item.context_expr
                if isinstance(ctx, ast.Call) and isinstance(ctx.func, ast.Attribute) and ctx.func.attr == 'raises':
                    if _production_calls(part, functions, modules):
                        return True
    return False


def _java_arguments(source: str, start: int) -> list[str] | None:
    """Extract nested assertion arguments, rejecting incomplete parenthesis groups."""
    depth, begin, args = 0, start, []
    quote, escaped = None, False
    for i in range(start, len(source)):
        c = source[i]
        if quote:
            if escaped:
                escaped = False
            elif c == '\\':
                escaped = True
            elif c == quote:
                quote = None
            continue
        if c in ('"', "'"):
            quote = c
        elif c == '(':
            depth += 1
            if depth == 1:
                begin = i + 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                args.append(source[begin:i].strip())
                return args
        elif c == ',' and depth == 1:
            args.append(source[begin:i].strip())
            begin = i + 1
    return None


def _java_source_has_assertion(path: Path, test_name: str) -> bool:
    try:
        text = path.read_text(encoding='utf-8')
    except (UnicodeError, OSError):
        return False
    name = re.escape(test_name.split('[')[0].split('(')[0])
    for match in re.finditer(r"\b(?:void|[A-Za-z_][\w<>\[\]]*)\s+" + name + r"\s*\([^)]*\)\s*(?:throws\s+[\w., ]+\s*)?\{", text):
        prefix = text[max(0, match.start() - 350):match.start()]
        if not re.search(r"@(?:org\.junit\.(?:jupiter\.api\.)?)?Test\b", prefix):
            continue
        depth, start = 1, match.end()
        for pos in range(start, len(text)):
            if text[pos] == '{': depth += 1
            elif text[pos] == '}':
                depth -= 1
                if depth != 0: continue
                body = text[start:pos]
                # Remove comments and literal-false branches. This remains a
                # conservative source heuristic; real mutation tests are mandatory
                # for final critical acceptance.
                body = re.sub(r'/\*.*?\*/|//[^\n]*', '', body, flags=re.S)
                previous = None
                while body != previous:
                    previous = body
                    body = re.sub(r'\bif\s*\(\s*false\s*\)\s*\{[^{}]*\}', '', body)
                    body = re.sub(r'\bif\s*\(\s*false\s*\)\s*[^;{}]+;', '', body)
                ignored = {'Assertions', 'Assert', 'assert', 'Mockito', 'System', 'Math',
                           'Thread', 'List', 'Collections', 'Stream', 'Paths', 'Files',
                           'logger', 'log', 'verify', 'assertThat'}
                def business_calls(value: str) -> bool:
                    return any(obj not in ignored and not method.startswith('assert') and
                               method not in ('verify', 'fail', 'raises', 'mock', 'when', 'thenReturn', 'print', 'println')
                               for obj, method in re.findall(r'\b([A-Za-z_]\w*)\s*\.\s*([A-Za-z_]\w*)\s*\(', value))
                variables = set()
                for assign in re.finditer(r'\b([A-Za-z_]\w*)\s*=\s*([^;]+);', body):
                    if business_calls(assign.group(2)):
                        variables.add(assign.group(1))
                for _ in range(4):
                    start_count = len(variables)
                    for assign in re.finditer(r'\b([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*;', body):
                        if assign.group(2) in variables:
                            variables.add(assign.group(1))
                    if len(variables) == start_count:
                        break
                def depends(value: str) -> bool:
                    return business_calls(value) or any(re.search(r'\b'+re.escape(v)+r'\b', value) for v in variables)
                assertion = re.compile(r'\b(assertEquals|assertNotEquals|assertSame|assertNotSame|assertTrue|assertFalse|assertNull|assertNotNull|assertThrows|assertThat|verify)\s*\(')
                for a in assertion.finditer(body):
                    if a.group(1) == 'verify':
                        continue  # Mockito verification alone is not a value oracle.
                    args = _java_arguments(body, a.end()-1)
                    if not args:
                        continue
                    if a.group(1) in ('assertEquals', 'assertNotEquals', 'assertSame', 'assertNotSame'):
                        # JUnit supports message-first overloads; inspect the last
                        # two comparison operands after removing a leading literal.
                        compared = args[1:3] if len(args) >= 3 and args[0].strip().startswith('"') else args[:2]
                        if len(compared) != 2 or compared[0] == compared[1]:
                            continue
                        if sum(bool(depends(x)) for x in compared) != 1:
                            continue
                        return True
                    if a.group(1) in ('assertTrue', 'assertFalse'):
                        expr = args[0].strip()
                        if re.search(r'\|\|\s*(?:true|1\s*==\s*1)\b|\b(?:true|1\s*==\s*1)\s*\|\|', expr):
                            continue
                        comparison = re.match(r'(?s)^\s*(.+?)\s*(==|!=|<=|>=|<|>)\s*(.+?)\s*$', expr)
                        if comparison:
                            lhs, rhs = comparison.group(1), comparison.group(3)
                            if re.sub(r'\s+', '', lhs) == re.sub(r'\s+', '', rhs):
                                continue
                            if sum(bool(depends(x)) for x in (lhs, rhs)) != 1:
                                continue
                            return True
                        if depends(expr) and not re.search(r'\btrue\s*\|\||\|\|\s*true\b', expr):
                            return True
                        continue
                    if any(depends(x) for x in args):
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
    return errors, {"report_sha256": sha256_file(report), "case_map_sha256": sha256_file(case_map), "test_sources": sources, "verified_test_ids": sorted(used_ids), "assertion_check": "STRUCTURAL_CHECK_PASS_NOT_SEMANTIC_PROOF" if not errors else "BLOCKED"}
