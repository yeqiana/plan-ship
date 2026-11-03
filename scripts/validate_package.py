#!/usr/bin/env python3
"""Validate PlanShip's publishable file layout and links without running an Agent."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import unquote

REQUIRED_FILES = (
    "SKILL.md", "README.md", "README.zh-CN.md", "LICENSE", "CHANGELOG.md",
    "AGENTS.md", ".editorconfig", ".gitattributes", ".gitignore",
    "agents/openai.yaml", ".github/workflows/validate.yml",
    "references/module-plan.md", "references/module-execute.md",
    "references/plain-language.md", "references/skill-discovery.md",
    "scripts/route_manager.py", "scripts/test_input_probe.py", "scripts/doc_registry.py",
    "scripts/validate_evidence.py", "scripts/validate_package.py",
    "tests/test_tools.py", "tests/test_v24.py", "tests/test_package_contract.py",
    "docs/quality-gates.md", "docs/migration.md", "examples/quickstart.md",
    "evals/manual-evaluation.md", "evals/discovery-baseline.md",
    "docs/faq.md", "docs/architecture.md", "docs/comparison.md",
    "docs/language-policy.md", "docs/geo-methodology.md", "docs/github-metadata.md",
    "examples/java-order-total/README.md", "examples/java-order-total/src/OrderTotal.java",
    "examples/java-order-total/src/OrderTotalCheck.java",
    "tests/test_java_example.py", "tests/test_discovery_contract.py",
)
TEXT_SUFFIXES = {".md", ".py", ".yaml", ".yml", ".json", ".txt", ".ps1"}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "dist", "evidence"}
LINK = re.compile(r"(?<!!)\[[^\]\n]+\]\(([^)]+)\)")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
LEGACY_NAME = "project-" + "plan-" + "delivery"
LEGACY_ALLOWED = {"docs/migration.md", "scripts/route_manager.py"}


def check_links(root: Path, relative: str, content: str) -> list[str]:
    """Check normal relative Markdown links, ignoring fenced example code."""
    failures: list[str] = []
    fenced = None
    for number, line in enumerate(content.splitlines(), 1):
        marker = FENCE.match(line)
        if marker:
            prefix = marker.group(1)
            if fenced is None:
                fenced = prefix[0]
            elif fenced == prefix[0]:
                fenced = None
            continue
        if fenced is not None:
            continue
        for match in LINK.finditer(line):
            target = match.group(1).strip().strip("<>").split("#", 1)[0]
            if not target or re.match(r"^[a-z][a-z\d+.-]*:", target, re.I):
                continue
            if target.startswith("/") or "\\" in target:
                failures.append(f"{relative}:{number}: 不安全的本地链接 {target}")
                continue
            base = (root / relative).parent.resolve()
            wanted = (base / unquote(target)).resolve()
            if not wanted.is_relative_to(root.resolve()):
                failures.append(f"{relative}:{number}: 链接逃出仓库 {target}")
            elif not wanted.exists():
                failures.append(f"{relative}:{number}: 本地 Markdown 链接不存在 {target}")
    return failures


def validate(root: Path) -> list[str]:
    failures: list[str] = []
    if not root.is_dir():
        return [f"仓库目录不存在：{root}"]
    for name in REQUIRED_FILES:
        if not (root / name).is_file():
            failures.append(f"缺少发行文件：{name}")
    for path in root.rglob("*"):
        if not path.is_file() or any(p in SKIP_DIRS for p in path.relative_to(root).parts):
            continue
        relative = path.relative_to(root).as_posix()
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in ("LICENSE", ".editorconfig", ".gitattributes", ".gitignore"):
            continue
        try:
            data = path.read_bytes()
            content = data.decode("utf-8")
            if content.startswith("\ufeff"):
                failures.append(f"UTF-8 BOM 不允许：{relative}")
        except UnicodeError:
            failures.append(f"不能按 UTF-8 解析：{relative}")
            continue
        if LEGACY_NAME in content and relative not in LEGACY_ALLOWED:
            failures.append(f"仍存在旧 Skill 名称：{relative}")
        if path.suffix == ".md":
            failures.extend(check_links(root, relative, content))
    skill = (root / "SKILL.md")
    if skill.is_file():
        content = skill.read_text(encoding="utf-8")
        if not re.match(r"\A---\nname: plan-ship\n", content):
            failures.append("SKILL.md 的正式 name 不是 plan-ship")
        for marker in ("$plan-ship", "/plan-ship", "ai-coding-collaboration", "intelligent-ui", "test-dir", "两轮", "BLOCKED", "implementation plan", "acceptance", "review", "genuine", "No fake"):
            if marker not in content:
                failures.append(f"SKILL.md 缺少关键约束：{marker}")
    manifest = root / "agents/openai.yaml"
    if manifest.is_file():
        meta = manifest.read_text(encoding="utf-8")
        for marker in ("$plan-ship", "ai-coding-collaboration", "intelligent-ui", "plan", "test", "acceptance", "方案"):
            if marker not in meta:
                failures.append(f"agents/openai.yaml 缺少双语发现信息：{marker}")
    route = root / "scripts/route_manager.py"
    if route.is_file() and "plan-ship:route:start" not in route.read_text(encoding="utf-8"):
        failures.append("route_manager.py 未使用新路由标识")
    for name in ("README.md", "README.zh-CN.md"):
        path = root / name
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            for marker in ("$plan-ship", "plan-ship.git", "validate_package.py", "manual-evaluation.md"):
                if marker not in text:
                    failures.append(f"{name} 缺少安装、校验或行为说明：{marker}")
    english = root / "README.md"
    if english.is_file():
        readme = english.read_text(encoding="utf-8")
        for marker in ("docs/faq.md", "docs/comparison.md", "docs/geo-methodology.md", "examples/java-order-total/README.md", "$plan-ship plan:"):
            if marker not in readme:
                failures.append(f"README.md 缺少发现性文档或英文调用：{marker}")
    baseline = root / "evals/discovery-baseline.md"
    if baseline.is_file() and "NOT MEASURED" not in baseline.read_text(encoding="utf-8"):
        failures.append("发现性基线必须保留未测量状态，不能伪造 GEO 指标")
    flow = root / ".github/workflows/validate.yml"
    if flow.is_file():
        text = flow.read_text(encoding="utf-8")
        for marker in ("validate_package.py", "unittest discover", "pip install pytest", "setup-java@v4"):
            if marker not in text:
                failures.append(f"GitHub Actions 缺少真实校验：{marker}")
    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = ap.parse_args()
    errors = validate(args.root.resolve())
    print(json.dumps({"status": "PASS" if not errors else "FAIL", "errors": errors, "note": "这是发行结构校验，不是 Codex/Claude 宿主触发或业务验收"}, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
