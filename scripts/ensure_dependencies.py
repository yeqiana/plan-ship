#!/usr/bin/env python3
"""Safely bootstrap PlanShip's two official Skill dependencies (no script execution)."""
from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Mapping

from discover_skills import metadata_name

# Official, allowlisted repositories. CLI does not accept arbitrary download URLs.
REPOSITORIES = {
    "code-pact": "https://github.com/yeqiana/code-pact.git",
    "gen-ui": "https://github.com/yeqiana/gen-ui.git",
}


def is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    if hasattr(path, "is_junction") and path.is_junction():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        return False
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def existing_skill_roots(home: Path | None = None, env: Mapping[str, str] | None = None) -> list[Path]:
    """Prefer a root already containing PlanShip, otherwise the first existing host root."""
    home = home or Path.home()
    env = os.environ if env is None else env
    codex_home = Path(env.get("CODEX_HOME") or (home / ".codex")).expanduser()
    candidates = [home / ".agents" / "skills", codex_home / "skills", home / ".claude" / "skills"]
    available: list[Path] = []
    for root in candidates:
        if not root.is_absolute() or not root.is_dir() or is_link_or_junction(root) or is_link_or_junction(root.parent):
            continue
        if root not in available:
            available.append(root)
    return available


def current_host_skill_root(roots: list[Path]) -> Path | None:
    """When invoked from an installed PlanShip, use that host's exact Skills root."""
    folder = Path(__file__).resolve().parents[1]
    if folder.name == "plan-ship" and folder.parent in roots and metadata_name(folder / "SKILL.md") == "plan-ship":
        return folder.parent
    return None


def select_skill_root(roots: list[Path]) -> Path | None:
    effective = current_host_skill_root(roots)
    if effective is not None:
        return effective
    installed = [r for r in roots if (r / "plan-ship" / "SKILL.md").is_file()
                 and metadata_name(r / "plan-ship" / "SKILL.md") == "plan-ship"
                 and not is_link_or_junction(r / "plan-ship")]
    return installed[0] if installed else (roots[0] if roots else None)


def _system_profile(home: Path) -> bool:
    normal = str(home).replace("/", "\\").lower()
    return normal.endswith("\\windows\\system32\\config\\systemprofile")


def _run_git(arguments: list[str], timeout: int = 90) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GCM_INTERACTIVE"] = "never"
    return subprocess.run(["git", *arguments], check=True, capture_output=True,
                          text=True, timeout=timeout, env=environment)


def _install_one(name: str, url: str, root: Path) -> dict:
    target = root / name
    if target.exists() or target.is_symlink() or is_link_or_junction(target):
        if target.is_dir() and not is_link_or_junction(target) and metadata_name(target / "SKILL.md") == name:
            # Existing ZIP installs have no Git metadata. Existing Git checkouts must match
            # the official source; don't silently accept a wrong remote with a valid name.
            if (target / ".git").exists():
                try:
                    existing_remote = _run_git(["-C", str(target), "remote", "get-url", "origin"]).stdout.strip()
                except (OSError, subprocess.SubprocessError):
                    existing_remote = None
                allowed = (url, f"git@github.com:yeqiana/{name}.git")
                if existing_remote not in allowed:
                    return {"status": "BLOCKED_CONFLICT", "path": str(target), "repository": url,
                            "error": "Existing Git Skill has a different or unreadable origin; no overwrite."}
            return {"status": "PRESENT", "path": str(target / "SKILL.md"), "repository": url,
                    "note": "Present Skill was not overwritten; host must still load and verify it."}
        return {"status": "BLOCKED_CONFLICT", "path": str(target), "repository": url,
                "error": "Target already exists but its Skill name or path is unsafe; manual review required."}
    # Use staging within the validated existing root. Never clone directly into the final target.
    try:
        with tempfile.TemporaryDirectory(prefix=f".{name}-install-", dir=root) as stage:
            checkout = Path(stage) / "checkout"
            _run_git(["clone", "--depth", "1", "--branch", "main", "--", url, str(checkout)])
            source = (checkout / "SKILL.md")
            if not source.is_file() or is_link_or_junction(source) or metadata_name(source) != name:
                return {"status": "BLOCKED_INVALID_SOURCE", "repository": url,
                        "error": f"Cloned repository SKILL.md did not declare name: {name}."}
            remote = _run_git(["-C", str(checkout), "remote", "get-url", "origin"]).stdout.strip()
            if remote != url:
                return {"status": "BLOCKED_INVALID_SOURCE", "repository": url,
                        "error": "Clone source URL changed unexpectedly."}
            revision = _run_git(["-C", str(checkout), "rev-parse", "HEAD"]).stdout.strip()
            if target.exists() or target.is_symlink() or is_link_or_junction(target):
                return {"status": "BLOCKED_CONFLICT", "path": str(target), "repository": url,
                        "error": "Another process created the target during installation."}
            checkout.rename(target)
            return {"status": "INSTALLED", "path": str(target / "SKILL.md"),
                    "repository": url, "revision": revision,
                    "note": "Installation alone does NOT demonstrate the Agent actually loaded the Skill."}
    except (OSError, subprocess.SubprocessError) as error:
        return {"status": "BLOCKED_INSTALL_FAILED", "repository": url,
                "error": f"Git clone or filesystem install failed ({type(error).__name__})."}


def ensure_dependencies(home: Path | None = None, env: Mapping[str, str] | None = None,
                        names: tuple[str, ...] | None = None,
                        repositories: Mapping[str, str] | None = None) -> dict:
    """Install missing allowlisted Skills into ONE existing host root; no host root creation.

    Test-only callers may inject a local repository mapping; the CLI never permits this.
    """
    home = home or Path.home()
    wanted = names or tuple(REPOSITORIES)
    configured = dict(REPOSITORIES if repositories is None else repositories)
    if not set(wanted).issubset(REPOSITORIES) or not set(wanted).issubset(configured):
        raise ValueError("Only PlanShip's two known dependency names can be installed.")
    if _system_profile(home):
        return {"status": "BLOCKED_SYSTEM_PROFILE", "root": None, "skills": {},
                "error": "Windows service SYSTEM profile is not an interactive Agent home; use the real user's Agent environment."}
    roots = existing_skill_roots(home, env)
    root = select_skill_root(roots)
    if root is None:
        return {"status": "BLOCKED_NO_EXISTING_SKILLS_ROOT", "root": None, "skills": {},
                "error": "No existing Codex/Claude Skills root; refusing to create a new Agent directory."}
    output = {name: _install_one(name, configured[name], root) for name in wanted}
    ok = all(item["status"] in ("PRESENT", "INSTALLED") for item in output.values())
    return {"status": "INSTALLED_OR_PRESENT_AGENT_LOAD_REQUIRED" if ok else "BLOCKED",
            "root": str(root), "skills": output,
            "checked_roots": [str(p) for p in roots],
            "note": "The host/Agent must read and apply code-pact and gen-ui before project analysis; clone alone is not loading."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = ensure_dependencies()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result["status"])
        print(json.dumps(result["skills"], ensure_ascii=False, indent=2))
    return 0 if result["status"] == "INSTALLED_OR_PRESENT_AGENT_LOAD_REQUIRED" else 2


if __name__ == "__main__":
    sys.exit(main())
