#!/usr/bin/env python3
"""Reject incomplete/stale delivery evidence. It cannot certify honest test execution."""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from project_snapshot import safe_inside, sha256_file, snapshot, SnapshotError
from validate_docs import extract_trace, validate as validate_document
from test_report import validate_test_artifacts


def load_json(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding="utf8"))
    if not isinstance(obj, dict):
        raise ValueError(f"JSON 根节点必须为 object: {path}")
    return obj


def local_file(workspace: Path, rel: str) -> Path | None:
    if not isinstance(rel, str) or not rel:
        return None
    candidate = (workspace / rel).resolve()
    return candidate if safe_inside(candidate, workspace) and candidate.is_file() else None


def validate_evidence(manifest_file: Path, plan_file: Path, workspace: Path) -> list[str]:
    errors = []
    workspace = workspace.resolve()
    docroot = (workspace / ".idea" / "docs").resolve()
    manifest_file, plan_file = manifest_file.resolve(), plan_file.resolve()
    plan_dir = plan_file.parent
    if (plan_dir.parent != docroot or not safe_inside(manifest_file, plan_dir)
            or not safe_inside(plan_file, docroot)):
        return ["manifest 与方案必须属于同一 .idea/docs/<方案名称>/ 目录"]
    try:
        manifest = load_json(manifest_file)
        plan = plan_file.read_text(encoding="utf-8-sig")
        fingerprint = snapshot(workspace)
        plan_hash = sha256_file(plan_file)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, SnapshotError) as exc:
        return [f"前置读取或 Git 指纹检查失败：{exc}"]
    plan_errors = validate_document(plan, "plan", plan_file, workspace)
    if plan_errors:
        return [f"正式方案 P 门禁未通过：{x}" for x in plan_errors]
    if manifest.get("schema_version") != "2.1":
        errors.append("manifest.schema_version 必须为 2.1（旧版自报测试证据不准入）")
    expected_plan = plan_file.relative_to(workspace).as_posix()
    if manifest.get("plan_file") != expected_plan:
        errors.append("manifest.plan_file 与当前正式方案不一致")
    run_file = local_file(workspace, manifest.get("runs_file"))
    if not run_file or not safe_inside(run_file, plan_dir):
        return errors + ["runs_file 不存在或超出 .idea/docs"]
    try:
        runs_data = load_json(run_file)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return errors + [f"runs_file 无法读取：{exc}"]
    if runs_data.get("schema_version") != "2.1" or not isinstance(runs_data.get("runs"), list):
        return errors + ["runs_file 必须为 v2.1 真实框架报告证据，旧版拒绝"]
    run_index = {}
    for run in runs_data["runs"]:
        if not isinstance(run, dict):
            errors.append("run 必须为对象")
            continue
        run_id = run.get("run_id")
        if not isinstance(run_id, str) or not re.fullmatch(r"RUN-[A-F0-9]{12}", run_id):
            errors.append(f"run_id 无效：{run_id}")
            continue
        if run_id in run_index:
            errors.append(f"run_id 重复：{run_id}")
        run_index[run_id] = run
    req_ids, test_cases, trace_errors = extract_trace(plan, "plan")
    errors.extend(trace_errors)
    if not req_ids or not test_cases:
        return errors + ["正式方案没有可用的需求与用例追踪"]
    integration = manifest.get("integration")
    if not isinstance(integration, dict):
        integration = {}
        errors.append("缺少 integration 集成审计")
    if integration.get("merged") is not True:
        errors.append("集成合并状态不是 true")
    if not isinstance(integration.get("worktrees_used"), bool):
        errors.append("integration.worktrees_used 必须为布尔值")
    if integration.get("worktrees_used") is True:
        audit = local_file(workspace, integration.get("merge_audit"))
        if not audit or not safe_inside(audit, plan_dir):
            errors.append("使用 worktree 时必须提供 .idea/docs 内的合并审计 JSON")
        else:
            try:
                report = load_json(audit)
                if report.get("merged_local") is not True:
                    errors.append("merge_audit.merged_local 非 true")
                if report.get("integration_head") != fingerprint["git_head"]:
                    errors.append("merge_audit.integration_head 与最终代码 HEAD 不一致")
                if report.get("source_fingerprint") != fingerprint["source_fingerprint"]:
                    errors.append("merge_audit.source_fingerprint 已过期")
                if not report.get("reviewed_worktrees") or not report.get("conflict_resolution"):
                    errors.append("merge_audit 缺少 worktree 审查记录或冲突处置")
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"merge_audit 解析失败：{exc}")
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        cases = []
        errors.append("manifest.cases 必须为数组")
    coverage = {}
    for case in cases:
        if not isinstance(case, dict):
            errors.append("case 必须是对象")
            continue
        case_id = case.get("id")
        if not isinstance(case_id, str) or case_id not in test_cases or case_id in coverage:
            errors.append(f"不存在或重复的用例：{case_id}")
            continue
        coverage[case_id] = case
    for case_id in test_cases.keys() - coverage.keys():
        errors.append(f"正式方案必测用例未覆盖：{case_id}")
    accepted_runs = {}
    def check_run(run_id: str, expected_case_ids: set[str], owner: str) -> None:
        if not isinstance(run_id, str):
            errors.append(f"{owner} 使用了非法 RUN 编号类型")
            return
        run = run_index.get(run_id)
        if not run:
            errors.append(f"{owner} 的执行记录不存在：{run_id}")
            return
        if run.get("stage") != "integrated":
            errors.append(f"{owner} 引用了未集成阶段的测试 {run_id}")
        if run.get("source_modified_during_run") is not False:
            errors.append(f"{run_id} 未证明测试过程中源码保持不变")
        if run.get("status") != "PASS" or run.get("exit_code") != 0:
            errors.append(f"{owner} 引用了失败、阻断或未执行的测试 {run_id}")
        if not isinstance(run.get("command"), list) or not run["command"] or not all(isinstance(x, str) and x for x in run["command"]):
            errors.append(f"{run_id} 缺少实际执行命令")
        case_ids = run.get("case_ids")
        if (not isinstance(case_ids, list)
                or any(not isinstance(x, str) for x in case_ids)
                or not expected_case_ids.issubset(set(case_ids))):
            errors.append(f"{run_id} 未声明覆盖所引用用例：{expected_case_ids}")
            case_ids = []
        if run.get("runner") not in ("pytest", "maven", "gradle"):
            errors.append(f"{run_id} 缺少可信测试框架标识")
        if run.get("report_validation_errors") != []:
            errors.append(f"{run_id} 报告校验曾失败：{run.get('report_validation_errors')}")
        report_file = local_file(workspace, run.get("report_path"))
        map_file = local_file(workspace, run.get("case_map_path"))
        if report_file is None or map_file is None or not safe_inside(report_file, plan_dir) or not safe_inside(map_file, plan_dir):
            errors.append(f"{run_id} 缺少当前方案目录中的框架报告或 TC→测试方法映射")
        elif not isinstance(run.get("case_ids"), list) or not all(isinstance(x, str) for x in run["case_ids"]):
            errors.append(f"{run_id} case_ids 字段类型非法，拒绝校验报告")
        else:
            verified_errors, proof = validate_test_artifacts(report_file, map_file, workspace, set(case_ids))
            errors.extend(f"{run_id} 测试报告：{err}" for err in verified_errors)
            for field in ("report_sha256", "case_map_sha256", "test_sources", "verified_test_ids"):
                if run.get(field) != proof.get(field):
                    errors.append(f"{run_id} {field} 与实际框架报告或测试源码不一致")
        if run.get("git_head") != fingerprint["git_head"] or run.get("source_fingerprint") != fingerprint["source_fingerprint"]:
            errors.append(f"{run_id} 执行后代码发生变化：需要重测最终合并状态")
        if run.get("plan_sha256") != plan_hash:
            errors.append(f"{run_id} 执行时方案版本与当前不一致：需要重测")
        if not isinstance(run.get("timestamp"), str):
            errors.append(f"{run_id} 缺少测试时间")
        else:
            try:
                t = dt.datetime.fromisoformat(run["timestamp"])
                if t.tzinfo is None:
                    errors.append(f"{run_id} 时间戳缺少时区")
            except ValueError:
                errors.append(f"{run_id} 时间戳不可解析")
        log = local_file(workspace, run.get("log_path"))
        if not log or not safe_inside(log, plan_dir):
            errors.append(f"{run_id} 缺少真实本地日志文件")
        elif sha256_file(log) != run.get("log_sha256"):
            errors.append(f"{run_id} 日志内容已改变")
        if not isinstance(run.get("fixtures"), list):
            errors.append(f"{run_id} 测试输入记录类型错误")
        for fixture in (run.get("fixtures") if isinstance(run.get("fixtures"), list) else []):
            if not isinstance(fixture, dict):
                errors.append(f"{run_id} 测试附件记录非法")
                continue
            f = local_file(workspace, fixture.get("path"))
            if f is None or sha256_file(f) != fixture.get("sha256"):
                errors.append(f"{run_id} 使用的 test-dir / 测试输入已缺失或改变：{fixture.get('path')}")
        accepted_runs[run_id] = run
    for case_id, case in coverage.items():
        ids = case.get("run_ids")
        if case.get("status") != "PASS":
            errors.append(f"{case_id} 未标记 PASS")
        if not isinstance(ids, list) or not ids:
            errors.append(f"{case_id} 缺少运行记录")
            continue
        for run_id in ids:
            check_run(run_id, {case_id}, case_id)
    acceptance = manifest.get("acceptance")
    if not isinstance(acceptance, list):
        acceptance = []
        errors.append("manifest.acceptance 必须为数组")
    accepted_req: set[str] = set()
    acc_ids: set[str] = set()
    for item in acceptance:
        if not isinstance(item, dict):
            errors.append("acceptance 必须为对象")
            continue
        aid = item.get("id")
        if not isinstance(aid, str) or not re.fullmatch(r"ACC-\d{3,}", aid) or aid in acc_ids:
            errors.append(f"验收编号无效或重复：{aid}")
        if isinstance(aid, str):
            acc_ids.add(aid)
        req = item.get("requirement_id")
        if not isinstance(req, str) or req not in req_ids:
            errors.append(f"验收 {aid} 未关联正式方案的需求：{req}")
        elif req in accepted_req:
            errors.append(f"需求 {req} 重复验收条目")
        else:
            accepted_req.add(req)
        if item.get("status") != "PASS":
            errors.append(f"验收 {aid} 未通过")
        if not isinstance(item.get("notes"), str) or len(item["notes"].strip()) < 12:
            errors.append(f"验收 {aid} 缺少可查的验收结论描述")
        run_ids = item.get("run_ids")
        if not isinstance(run_ids, list) or not run_ids:
            errors.append(f"验收 {aid} 没有相关测试运行证据")
            continue
        related = {case_id for case_id, related_req in test_cases.items() if req in related_req}
        if not any(isinstance(run_id, str) and run_id in accepted_runs
                   and isinstance(accepted_runs[run_id].get("case_ids"), list)
                   and bool({c for c in accepted_runs[run_id]["case_ids"] if isinstance(c, str)} & related)
                   for run_id in run_ids):
            errors.append(f"验收 {aid} 运行记录无法证明其关联需求 {req} 的测试")
        for run_id in run_ids:
            if not isinstance(run_id, str) or run_id not in accepted_runs:
                errors.append(f"验收 {aid} 引用了未在用例中合格使用的 RUN：{run_id}")
    for req in req_ids - accepted_req:
        errors.append(f"需求 {req} 缺少验收结果")
    return errors


def _check_controlled_mutation_run(evidence: dict, workspace: Path, plan_dir: Path, aid: str, restored_run: dict | None) -> list[str]:
    """Bind provenance artifacts to ONE instrumented execution.

    Local writable data is auditable but not cryptographically authentic.
    Independent reruns and reviewer inspection are still required.
    """
    errors = []
    rel = evidence.get('mutation_run_record_path')
    recorded_sha = evidence.get('mutation_run_record_sha256')
    if not isinstance(rel, str) or not isinstance(recorded_sha, str):
        return [f'{aid} ACCEPTANCE_NOT_VERIFIED：缺少受控变异执行记录及哈希']
    record_file = local_file(workspace, rel)
    if not record_file or not safe_inside(record_file, plan_dir) or 'evidence' not in record_file.relative_to(plan_dir).parts:
        return [f'{aid} 受控变异执行记录必须位于本方案 evidence 目录']
    if sha256_file(record_file) != recorded_sha:
        return [f'{aid} 变异执行记录哈希不匹配']
    try:
        data = load_json(record_file)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f'{aid} 变异执行记录无法解析：{exc}']
    if (data.get('schema_version') != '1.0' or data.get('runner_version') != '1.3.4' or
            data.get('runner') != 'pytest' or
            data.get('runner_script_sha256') != sha256_file(Path(__file__).with_name('run_mutation.py')) or
            not isinstance(data.get('command'), list) or
            data.get('status') != 'MUTATION_KILLED_HUMAN_REVIEW_REQUIRED' or
            data.get('execution_mode') != 'isolated_temporary_copy_not_security_sandbox' or
            not re.fullmatch(r'MUT-[0-9A-F]{12}', str(data.get('run_id'))) or
            not re.fullmatch(r'[0-9a-f]{32}', str(data.get('nonce'))) or
            data.get('exit_code') == 0 or not isinstance(data.get('exit_code'), int)):
        errors.append(f'{aid} 受控变异执行版本、模式或失败状态无效')
    links = {'mutation_source_path': 'mutation_source_path',
             'baseline_source_sha256': 'baseline_source_sha256',
             'mutated_snapshot_path': 'mutated_snapshot_path',
             'mutated_source_sha256': 'mutated_source_sha256',
             'mutation_patch_path': 'mutation_patch_path',
             'mutation_patch_sha256': 'mutation_patch_sha256',
             'negative_report_path': 'negative_report_path',
             'negative_report_sha256': 'negative_report_sha256',
             'negative_log_path': 'negative_log_path',
             'negative_log_sha256': 'negative_log_sha256',
             'test_id': 'test_id'}
    for field, bound in links.items():
        if data.get(field) != evidence.get(bound):
            errors.append(f'{aid} 执行记录 {field} 与正式反事实证据不一致')
    mapped_sources = restored_run.get('test_sources', {}) if isinstance(restored_run, dict) else {}
    if not isinstance(mapped_sources, dict) or mapped_sources.get(data.get('test_source_path')) != data.get('test_source_sha256'):
        errors.append(f'{aid} 变异执行使用的测试源码不属于恢复后 RUN 映射的同一测试文件')
    test_file = local_file(workspace, data.get('test_source_path'))
    if not test_file or sha256_file(test_file) != data.get('test_source_sha256') or data.get('test_source_sha256') != evidence.get('negative_test_source_sha256'):
        errors.append(f'{aid} 运行时测试源码与恢复后测试源码不一致')
    trace = data.get('trace')
    if (not isinstance(trace, dict) or trace.get('nodeid') != data.get('pytest_nodeid') or
            trace.get('target_module_loaded') is not True or trace.get('call_failed') is not True or
            trace.get('test_source_sha256') != data.get('test_source_sha256') or
            data.get('mutated_source_sha256') not in trace.get('loaded_hashes', [])):
        errors.append(f'{aid} 无法证明目标 pytest 测试在实际执行时加载了变异生产源码')
    phases = data.get('phase_outcomes')
    if phases != {'baseline':'PASS','mutation':'FAIL','restored':'PASS'}:
        errors.append(f'{aid} 缺少原始 PASS → 变异 FAIL → 恢复 PASS 的完整对照证据')
    for phase in ('baseline_trace','restored_trace'):
        proof=data.get(phase)
        if (not isinstance(proof,dict) or proof.get('nodeid')!=data.get('pytest_nodeid') or
                proof.get('target_module_loaded') is not True or proof.get('call_failed') is not False or
                proof.get('test_source_sha256')!=data.get('test_source_sha256') or
                data.get('baseline_source_sha256') not in proof.get('loaded_hashes',[])):
            errors.append(f'{aid} {phase} 原始/恢复阶段缺少有效 PASS 加载证明')
    report = local_file(workspace, data.get('negative_report_path'))
    log = local_file(workspace, data.get('negative_log_path'))
    if (not report or not log or not safe_inside(report, plan_dir) or not safe_inside(log, plan_dir)
            or sha256_file(report) != data.get('negative_report_sha256')
            or sha256_file(log) != data.get('negative_log_sha256')):
        errors.append(f'{aid} 受控执行报告/日志文件哈希不匹配')
        return errors
    try:
        xml = ET.parse(report).getroot()
        props = {item.get('name'):item.get('value') for item in xml.iter('property')}
        if (props.get('plan_ship_mutation_run_id') != data.get('run_id') or
                props.get('plan_ship_mutation_nonce') != data.get('nonce') or
                props.get('plan_ship_mutated_source_sha256') != data.get('mutated_source_sha256')):
            errors.append(f'{aid} JUnit 报告未绑定本次受控变异 run_id、nonce、源码指纹')
    except ET.ParseError as exc:
        errors.append(f'{aid} 受控执行 JUnit XML 解析失败：{exc}')
    if data.get('run_id') not in log.read_text(encoding='utf8',errors='replace') or data.get('nonce') not in log.read_text(encoding='utf8',errors='replace'):
        errors.append(f'{aid} 受控执行日志未记录本次变异 run_id/nonce')
    return errors


def validate_counterfactual_evidence(manifest_file: Path, plan_file: Path,
                                      workspace: Path) -> list[str]:
    """Additional FINAL gate. A green integration report is only consistency.

    Evidence is locally writable and cannot prove authorship. This demands a
    separately captured failing JUnit testcase and its immutable-at-check-time
    log hashes for each accepted requirement, plus a restored integrated run.
    Human review of the controlled mutation is still required.
    """
    errors = validate_evidence(manifest_file, plan_file, workspace)
    if errors:
        return errors
    workspace = workspace.resolve()
    plan_dir = plan_file.resolve().parent
    try:
        manifest = load_json(manifest_file)
        runs = load_json(workspace / manifest['runs_file'])['runs']
    except (OSError, KeyError, TypeError, ValueError) as exc:
        return ['无法读取反事实验收关联的测试运行记录：' + str(exc)]
    run_index = {r.get('run_id'): r for r in runs if isinstance(r, dict)}
    acceptance = manifest.get('acceptance', [])
    for item in acceptance:
        if not isinstance(item, dict):
            errors.append('反事实验收条目必须是对象')
            continue
        aid = item.get('id', 'UNKNOWN')
        evidence = item.get('counterfactual')
        if not isinstance(evidence, dict):
            errors.append(f'{aid} 缺少反事实失败证据：一致性检查通过不等于业务验收通过')
            continue
        expected = ('test_id', 'mutation_description', 'negative_report_path',
                    'negative_report_sha256', 'negative_log_path', 'negative_log_sha256',
                    'restored_run_id')
        if any(not isinstance(evidence.get(field), str) or not evidence[field].strip()
               for field in expected):
            errors.append(f'{aid} 反事实记录字段不完整：{expected}')
            continue
        if len(evidence['mutation_description'].strip()) < 12:
            errors.append(f'{aid} 未说明具体故障注入和业务预期')
        # Bind negative control to a concrete PRODUCTION source mutation, not
        # a changed test expectation. This verifies a replayable source delta;
        # it cannot authenticate the actor that ran the negative test.
        proof_fields = ('mutation_source_path', 'baseline_source_sha256',
                        'mutated_snapshot_path', 'mutated_source_sha256',
                        'mutation_patch_path', 'mutation_patch_sha256',
                        'negative_test_source_sha256')
        if any(not isinstance(evidence.get(k), str) or not evidence[k].strip() for k in proof_fields):
            errors.append(f'{aid} 缺少生产源码变异及未改变测试源码的绑定证据：{proof_fields}')
            continue
        rel_source = Path(evidence['mutation_source_path'])
        forbidden = {'.idea', '.git', 'tests', 'test', 'test-dir', '__pycache__', '.venv', 'node_modules'}
        source = local_file(workspace, evidence['mutation_source_path'])
        if (not source or rel_source.is_absolute() or '..' in rel_source.parts
                or set(rel_source.parts) & forbidden or source.stem.startswith('test_')
                or source.suffix.lower() not in ('.py', '.java', '.js', '.ts', '.go', '.rs')):
            errors.append(f'{aid} 变异目标必须是当前工作区内的生产源码，不能修改测试、配置或证据文件')
            continue
        mutated_snapshot = local_file(workspace, evidence['mutated_snapshot_path'])
        mutation_patch = local_file(workspace, evidence['mutation_patch_path'])
        if (not mutated_snapshot or not mutation_patch or
                not safe_inside(mutated_snapshot, plan_dir) or
                not safe_inside(mutation_patch, plan_dir) or
                'evidence' not in mutated_snapshot.relative_to(plan_dir).parts or
                'evidence' not in mutation_patch.relative_to(plan_dir).parts):
            errors.append(f'{aid} 变异快照与差异记录必须位于当前方案 evidence/ 内')
            continue
        try:
            baseline = source.read_bytes()
            mutated = mutated_snapshot.read_bytes()
            patch_bytes = mutation_patch.read_bytes()
            expected_patch = ''.join(difflib.unified_diff(
                baseline.decode('utf-8').replace('\r\n','\n').splitlines(keepends=True),
                mutated.decode('utf-8').replace('\r\n','\n').splitlines(keepends=True),
                fromfile='a/' + rel_source.as_posix(),
                tofile='b/' + rel_source.as_posix())).encode('utf-8')
            if (not expected_patch or baseline == mutated or
                    len(baseline) > 2*1024*1024 or len(mutated) > 2*1024*1024 or
                    sha256_file(source) != evidence['baseline_source_sha256'] or
                    sha256_file(mutated_snapshot) != evidence['mutated_source_sha256'] or
                    sha256_file(mutation_patch) != evidence['mutation_patch_sha256'] or
                    patch_bytes.replace(b'\r\n',b'\n') != expected_patch):
                errors.append(f'{aid} 生产源码变异前后指纹或可重建补丁不匹配')
        except (OSError, UnicodeError, ValueError) as exc:
            errors.append(f'{aid} 无法读取源码变异快照或差异：{exc}')
        restored_run = run_index.get(evidence['restored_run_id'])
        sources = restored_run.get('test_sources') if isinstance(restored_run, dict) else None
        if (not isinstance(sources, dict) or
                evidence['negative_test_source_sha256'] not in sources.values() or
                not any(sha256_file(local_file(workspace, path)) == digest
                        for path, digest in sources.items()
                        if local_file(workspace, path))):
            errors.append(f'{aid} 负向测试必须绑定恢复后未改动的测试源码指纹')
        restored = run_index.get(evidence['restored_run_id'])
        if not restored or evidence['restored_run_id'] not in item.get('run_ids', []):
            errors.append(f'{aid} 恢复后执行记录未关联最终验收 RUN')
        elif evidence['test_id'] not in restored.get('verified_test_ids', []):
            errors.append(f'{aid} 恢复后 RUN 未真实覆盖该反事实 test_id')
        report = local_file(workspace, evidence['negative_report_path'])
        log = local_file(workspace, evidence['negative_log_path'])
        if not report or not log or not safe_inside(report, plan_dir) or not safe_inside(log, plan_dir):
            errors.append(f'{aid} 反事实报告或日志必须位于同一方案目录')
            continue
        if sha256_file(report) != evidence['negative_report_sha256'] or sha256_file(log) != evidence['negative_log_sha256']:
            errors.append(f'{aid} 反事实失败报告或日志哈希不一致')
            continue
        if report.stat().st_size > 5 * 1024 * 1024 or not log.stat().st_size:
            errors.append(f'{aid} 反事实报告超限或日志为空')
            continue
        try:
            xml = ET.parse(report).getroot()
            cases = xml.findall('.//testcase') if xml.tag == 'testsuites' else xml.findall('.//testcase')
            failures = [case for case in cases
                        if f"{case.get('classname', '')}::{case.get('name', '')}" == evidence['test_id']
                        and (case.find('failure') is not None or case.find('error') is not None)]
            if not failures:
                errors.append(f'{aid} 反事实报告没有目标测试真实失败的 JUnit 记录')
        except ET.ParseError as exc:
            errors.append(f'{aid} 反事实 JUnit 报告无法解析：{exc}')
        errors.extend(_check_controlled_mutation_run(evidence, workspace, plan_dir, aid, restored_run))
    return errors


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--plan", required=True, type=Path)
    p.add_argument("--workspace", required=True, type=Path)
    p.add_argument('--gate', choices=('consistency', 'acceptance'), default='consistency',
                   help='Only acceptance requires actual counterfactual failure evidence')
    args = p.parse_args()
    errs = (validate_counterfactual_evidence(args.manifest, args.plan, args.workspace)
            if args.gate == 'acceptance' else
            validate_evidence(args.manifest, args.plan, args.workspace))
    if errs:
        print(f"FAIL ({len(errs)} 项证据门禁)")
        for err in errs:
            print(" -", err)
        return 1
    if args.gate == 'acceptance':
        print('CONTROLLED_MUTATION_RUN_LINKED_HUMAN_REVIEW_REQUIRED: 运行记录、加载的变异源码及 JUnit 报告已关联；本地证据仍可被伪造，必须独立复核。')
    else:
        print('CONSISTENCY_PASS_ACCEPTANCE_NOT_VERIFIED: 只验证证据文件一致性，未检查故障注入，不可宣称业务验收通过。')
    return 0


if __name__ == "__main__":
    sys.exit(main())
