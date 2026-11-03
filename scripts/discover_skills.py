#!/usr/bin/env python3
"""Read-only discovery of local Codex/Claude skills; never downloads or executes them."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.S)
NAME = re.compile(r"(?m)^name:\s*['\"]?([^'\"\n#]+)")


def metadata_name(file: Path) -> str | None:
    try:
        data = file.read_text(encoding="utf-8-sig")[:8192]
    except (OSError, UnicodeError):
        return None
    match = FRONTMATTER.search(data)
    if not match:
        return None
    name = NAME.search(match.group(1))
    return name.group(1).strip() if name else None


def repository_ancestors(project: Path) -> list[Path]:
    """Include current directory up to the nearest Git root, otherwise project only."""
    here = project.resolve()
    if here.is_file():
        here = here.parent
    if not here.is_dir():
        return []
    chain = [here]
    while not (here / ".git").exists() and here.parent != here:
        here = here.parent
        chain.append(here)
    if (here / ".git").exists():
        return chain
    return [project.resolve()]


def roots(project: Path) -> list[tuple[str, Path]]:
    home = Path.home()
    codex_home = Path(os.environ.get("CODEX_HOME", str(home / ".codex"))).expanduser()
    candidates = [
        ("codex-user-modern", home / ".agents" / "skills"),
        ("codex-user-legacy", codex_home / "skills"),
        ("claude-user", home / ".claude" / "skills"),
    ]
    for ancestor in repository_ancestors(project):
        candidates.extend([
            ("codex-project", ancestor / ".agents" / "skills"),
            ("claude-project", ancestor / ".claude" / "skills"),
        ])
    seen = set()
    ordered = []
    for source, path in candidates:
        key = str(path.resolve())
        if key not in seen:
            ordered.append((source, path))
            seen.add(key)
    return ordered


def discover(project: Path, name: str | None):
    matches = []
    checked = []
    for source, root in roots(project):
        checked.append({"source": source, "directory": str(root), "exists": root.is_dir()})
        if not root.is_dir():
            continue
        try:
            dirs = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name.casefold())
        except OSError:
            continue
        for candidate in dirs:
            skill_file = candidate / "SKILL.md"
            if not skill_file.is_file():
                continue
            actual = metadata_name(skill_file)
            if name and name.casefold() not in (candidate.name.casefold(), (actual or "").casefold()):
                continue
            matches.append({
                "source": source, "directory_name": candidate.name,
                "skill_name": actual, "path": str(skill_file.resolve()),
                "frontmatter_valid": actual is not None,
            })
    return {"matches": matches, "checked": checked, "found": bool(matches),
            "note": "Only filesystem-visible skills checked; host system/plugin/enterprise registries require host API discovery."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd(), help="Project/workspace directory")
    parser.add_argument("--name", help="Optional skill name, e.g. intelligent-ui")
    parser.add_argument("--json", action="store_true", help="Machine-readable discovery report")
    args = parser.parse_args()
    if args.name and ("/" in args.name or "\\" in args.name or args.name in (".", "..")):
        parser.error("--name must be a skill name, not a path")
    result = discover(args.project, args.name)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("默认目录查找结果（只读）:")
        for item in result["checked"]:
            print(f"  {'[存在]' if item['exists'] else '[缺失]'} {item['source']}: {item['directory']}")
        if not result["found"]:
            print(f"NOT FOUND: {args.name or 'no skills'}（宿主内建/插件技能未包含在文件系统检查中）")
        for idx, item in enumerate(result["matches"], 1):
            print(f"  {idx}. FOUND {item['source']} name={item['skill_name'] or '(frontmatter missing)'} path={item['path']}")
        if len(result["matches"]) > 1:
            print("注意：存在多个候选；请核对当前宿主实际选用的 Skill，不要自动拼接。")
    return 0 if result["found"] else 1


if __name__ == "__main__":
    sys.exit(main())
