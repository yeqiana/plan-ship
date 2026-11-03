#!/usr/bin/env python3
"""Run one approved local test command without shell interpolation and record evidence.

Only run commands already authorized by the project owner. This tool cannot
prevent a build script itself from making network requests or remote Git writes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from project_snapshot import safe_inside, sha256_file, snapshot, SnapshotError
from test_report import validate_test_artifacts


def write_atomic(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    os.replace(tmp, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--stage", choices=("isolated", "integrated"), required=True)
    parser.add_argument("--cases", required=True, help="Comma-separated actual TC-xxx case IDs verified by this command")
    parser.add_argument("--cwd", type=Path, help="Execution directory, defaults to project root")
    parser.add_argument("--fixtures", default="", help="Comma-separated workspace-relative test input files (e.g. test-dir/a.json)")
    parser.add_argument("--runner", choices=("pytest", "maven", "gradle"), required=True, help="Only accepted real test frameworks")
    parser.add_argument("--report", required=True, help="Workspace-relative fresh JUnit XML report; use {run_id} for a unique name")
    parser.add_argument("--case-map", required=True, type=Path, help="JSON mapping each TC to framework test IDs and test source paths")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    plan = args.plan.resolve()
    runs = args.runs.resolve()
    docroot = (workspace / ".idea" / "docs").resolve()
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    cases = [c.strip() for c in args.cases.split(",")]
    if not command or not cases or any(not __import__("re").fullmatch(r"TC-\d{3,}", c) for c in cases) or len(set(cases)) != len(cases):
        parser.error("必须提供 -- 后的命令以及唯一、有效的 --cases TC-xxx 列表")
    plan_dir = plan.parent
    if plan_dir.parent != docroot or not plan.is_file():
        parser.error("--plan 必须是 .idea/docs/<方案名称>/ 中的正式方案")
    from doc_registry import verify_file
    errors = verify_file(plan, workspace)
    if errors:
        parser.error("--plan 技术/大白话双副本门禁未通过：" + "; ".join(errors))
    if not safe_inside(runs, plan_dir) or runs.suffix.lower() != ".json":
        parser.error("--runs 必须位于当前方案目录（不能跨方案写证据）")
    # A zero exit code is never enough: require a fresh framework report and source assertions.
    run_id = "RUN-" + uuid.uuid4().hex[:12].upper()
    report_name = args.report.replace("{run_id}", run_id)
    report = (workspace / report_name).resolve()
    mapping_file = args.case_map.resolve()
    if not safe_inside(report, plan_dir) or report.suffix.lower() != ".xml" or report.exists():
        parser.error("--report 必须指向工作区内尚不存在的新 JUnit XML 文件，建议使用 {run_id}")
    if not safe_inside(mapping_file, plan_dir) or not mapping_file.is_file():
        parser.error("--case-map 必须为工作区内存在的 JSON 文件")
    command = [arg.replace("{report}", str(report)) for arg in command]
    binary = Path(command[0]).name.lower()
    if args.runner == "pytest":
        uses_pytest = (binary in ("pytest", "pytest.exe") or
                       (binary.startswith("python") and len(command) >= 3 and command[1:3] == ["-m", "pytest"]))
        if not uses_pytest or not any(x in ("--junitxml=" + str(report), "--junit-xml=" + str(report)) for x in command):
            parser.error("pytest 模式必须真正执行 pytest，并指定 --junitxml={report} 产生新报告")
    elif args.runner == "maven":
        if binary not in ("mvn", "mvn.cmd", "mvnw", "mvnw.cmd", "mvnw.bat", "./mvnw") or not any(x in ("test", "verify") for x in command[1:]) or any("skipTests" in x or "maven.test.skip" in x for x in command):
            parser.error("maven 模式必须运行实际 test/verify，不允许跳过测试")
    elif args.runner == "gradle":
        if binary not in ("gradle", "gradle.bat", "gradlew", "gradlew.bat", "./gradlew") or not any(x == "test" or x.endswith(":test") for x in command[1:]) or "-x" in command:
            parser.error("gradle 模式必须运行实际 test，不允许 -x 排除测试")
    cwd = (args.cwd or workspace).resolve()
    if not safe_inside(cwd, workspace) or not cwd.is_dir():
        parser.error("--cwd 必须是本工作区内存在的目录")
    # Always bind all test-dir files, including Git-ignored test inputs, to this run.
    declared = {v.strip() for v in args.fixtures.split(",") if v.strip()}
    test_dir = workspace / "test-dir"
    if test_dir.is_dir():
        for file in test_dir.rglob("*"):
            if file.is_symlink():
                parser.error(f"test-dir 不允许符号链接输入：{file}")
            if file.is_file():
                declared.add(file.relative_to(workspace).as_posix())
    fixtures = []
    for raw in sorted(declared):
        candidate = (workspace / raw).resolve()
        if not safe_inside(candidate, workspace) or not candidate.is_file():
            parser.error(f"测试文件不存在或超出工作区：{raw}")
        fixtures.append({"path": candidate.relative_to(workspace).as_posix(), "sha256": sha256_file(candidate)})
    # Prevent obvious remote write attempts; never promise full process-level isolation.
    forbidden = {"push", "fetch", "pull", "clone", "remote"}
    if Path(command[0]).name.lower() in ("git", "git.exe") and len(command) > 1 and command[1].lower() in forbidden:
        parser.error("此测试采集器禁止直接执行远端 Git 命令")
    try:
        identity = snapshot(workspace)
        plan_hash = sha256_file(plan)
    except (SnapshotError, OSError) as exc:
        print("BLOCKED:", exc)
        return 2
    runs.parent.mkdir(parents=True, exist_ok=True)
    log_dir = runs.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f"{run_id}.log"
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    report.parent.mkdir(parents=True, exist_ok=True)
    with log.open("wb") as stream:
        stream.write((f"RUN: {run_id}\nTIMESTAMP: {now}\nCOMMAND: {json.dumps(command, ensure_ascii=False)}\n\n").encode())
        try:
            status = subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, check=False).returncode
        except OSError as exc:
            status = 127
            stream.write(f"\n命令无法启动：{exc}\n".encode())
    # Detect commands that mutate tracked/untracked source or relevant test files.
    try:
        after = snapshot(workspace)
    except (SnapshotError, OSError) as exc:
        print("BLOCKED: 测试后无法确认工作树完整性：", exc)
        return 2
    changed_during_run = after != identity
    # Fail closed: even a zero-exit command with a PASS-looking log is BLOCKED
    # until every TC has an executed framework testcase and test source assertion.
    if status == 0 and not changed_during_run:
        report_errors, verified = validate_test_artifacts(report, mapping_file, workspace, set(cases))
    else:
        report_errors, verified = ["测试命令执行失败或执行过程中修改了源码"], {}
    entry = {
        "run_id": run_id, "timestamp": now, "stage": args.stage,
        "case_ids": cases, "command": command,
        "cwd": cwd.relative_to(workspace).as_posix() or ".",
        "exit_code": status, "status": ("BLOCKED" if changed_during_run or (status == 0 and report_errors) else ("PASS" if status == 0 else "FAIL")),
        "runner": args.runner, "report_path": report.relative_to(workspace).as_posix(),
        "case_map_path": mapping_file.relative_to(workspace).as_posix(),
        "report_validation_errors": report_errors, **verified,
        "source_modified_during_run": changed_during_run,
        "log_path": log.relative_to(workspace).as_posix(), "log_sha256": sha256_file(log),
        "plan_sha256": plan_hash, "fixtures": fixtures, **identity,
    }
    try:
        record = json.loads(runs.read_text(encoding="utf8")) if runs.exists() else {"schema_version": "2.1", "runs": []}
        if record.get("schema_version") != "2.1" or not isinstance(record.get("runs"), list):
            raise ValueError("runs.json schema 不匹配")
        record["runs"].append(entry)
        write_atomic(runs, record)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("BLOCKED: 无法安全记录运行证据：", exc)
        return 2
    outcome = entry["status"]
    print(f"{outcome}: {run_id} exit={status}; 日志 {log}; 指纹 {identity['source_fingerprint']}")
    if changed_during_run:
        print("BLOCKED: 测试运行修改了 Git 追踪范围内的工作树；请核对产物隔离后重新测试")
        return 2
    if report_errors and status == 0:
        print("BLOCKED: 测试报告或断言证据不满足严格门禁：", "; ".join(report_errors))
        return 2
    return status if 0 <= status <= 125 else 1


if __name__ == "__main__":
    sys.exit(main())
