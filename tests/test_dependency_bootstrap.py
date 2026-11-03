"""Offline integration and adversarial tests for automatic dependency installation."""
from __future__ import annotations

import json
import io
from contextlib import redirect_stdout
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from ensure_dependencies import (REPOSITORIES, ensure_dependencies, existing_skill_roots,
                                 select_skill_root, _install_one)
from preflight import REQUIRED, check


def git(*argv: str) -> str:
    cp = subprocess.run(["git", *argv], capture_output=True, text=True, check=True)
    return cp.stdout.strip()


class DependencyBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"
        self.home.mkdir()
        self.root = self.home / ".agents" / "skills"
        self.root.mkdir(parents=True)
        self.repos = {}
        for name in REQUIRED:
            path = Path(self.temp.name) / "repo" / name
            path.mkdir(parents=True)
            git("init", "-b", "main", str(path))
            (path / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Fixture for {name}\n---\n\n# {name}\n", encoding="utf-8")
            git("-C", str(path), "add", "SKILL.md")
            git("-C", str(path), "-c", "user.name=Tests", "-c", "user.email=test@example.org",
                "commit", "-m", "test: add fixture")
            self.repos[name] = str(path)

    def ensure(self, **kwargs):
        return ensure_dependencies(home=self.home, env={}, repositories=self.repos, host=kwargs.pop("host", "codex"), **kwargs)

    def test_verified_canonical_sources(self):
        self.assertEqual(REQUIRED, tuple(REPOSITORIES))
        self.assertEqual("https://github.com/yeqiana/code-pact.git", REPOSITORIES["code-pact"])
        self.assertEqual("https://github.com/yeqiana/gen-ui.git", REPOSITORIES["gen-ui"])

    def test_real_local_git_clones_and_idempotency(self):
        result = self.ensure()
        self.assertEqual("INSTALLED_OR_PRESENT_AGENT_LOAD_REQUIRED", result["status"])
        for name in REQUIRED:
            item = result["skills"][name]
            self.assertEqual("INSTALLED", item["status"])
            self.assertEqual(40, len(item["revision"]))
            self.assertTrue((self.root / name / "SKILL.md").exists())
            self.assertEqual(self.repos[name], git("-C", str(self.root / name), "remote", "get-url", "origin"))
        again = self.ensure()
        self.assertEqual(["PRESENT_MATCHING_ORIGIN", "PRESENT_MATCHING_ORIGIN"], [again["skills"][n]["status"] for n in REQUIRED])
        self.assertEqual([], list(self.root.glob(".*-install-*")))

    def test_preflight_discovers_cloned_offline_fixtures(self):
        self.ensure()
        with patch.object(Path, "home", return_value=self.home):
            result = check(self.home, load=True, host='codex')
        self.assertEqual("READY_CORE_OPTIONAL_FILES_READ_AGENT_CONFIRMATION_REQUIRED", result["preflight_status"])
        for name in REQUIRED:
            self.assertTrue(result["skills"][name]["content_read"]["read_ok"])

    def test_choose_root_with_active_planship(self):
        alternate = self.home / ".claude" / "skills"
        alternate.mkdir(parents=True)
        (alternate / "plan-ship").mkdir()
        (alternate / "plan-ship" / "SKILL.md").write_text("---\nname: plan-ship\n---\n", encoding="utf8")
        result = self.ensure(host="claude")
        self.assertEqual(str(alternate), result["root"])
        self.assertTrue((alternate / "gen-ui" / "SKILL.md").exists())
        self.assertFalse((self.root / "gen-ui").exists())

    def test_missing_agent_roots_do_not_get_created(self):
        self.root.rmdir()
        result = self.ensure()
        self.assertEqual("BLOCKED_NO_EXISTING_SKILLS_ROOT", result["status"])
        self.assertFalse(self.root.exists())
        self.assertFalse((self.home / ".claude").exists())

    def test_existing_wrong_name_is_never_overwritten(self):
        dest = self.root / "gen-ui"
        dest.mkdir()
        file = dest / "SKILL.md"
        original = "---\nname: other-skill\n---\n# Owned by user\n"
        file.write_text(original, encoding="utf8")
        result = self.ensure()
        self.assertEqual("BLOCKED", result["status"])
        self.assertEqual("BLOCKED_CONFLICT", result["skills"]["gen-ui"]["status"])
        self.assertEqual(original, file.read_text(encoding="utf8"))

    def test_existing_unmodified_skill_does_not_clone(self):
        folder = self.root / "code-pact"
        folder.mkdir()
        (folder / "SKILL.md").write_text("---\nname: code-pact\n---\n", encoding="utf8")
        with patch("ensure_dependencies._run_git", side_effect=AssertionError("must not call Git")):
            result = self.ensure(names=("code-pact",))
        self.assertEqual("PRESENT_UNVERIFIED", result["skills"]["code-pact"]["status"])

    def test_existing_git_with_different_origin_is_blocked(self):
        first = self.ensure(names=("code-pact",))
        self.assertEqual("INSTALLED", first["skills"]["code-pact"]["status"])
        git("-C", str(self.root / "code-pact"), "remote", "set-url", "origin", "https://github.com/someone/other.git")
        second = self.ensure(names=("code-pact",))
        self.assertEqual("BLOCKED_CONFLICT", second["skills"]["code-pact"]["status"])
        self.assertTrue((self.root / "code-pact" / "SKILL.md").exists())

    def test_wrong_remote_skill_id_rejected_and_stage_cleaned(self):
        invalid = Path(self.repos["gen-ui"])
        (invalid / "SKILL.md").write_text("---\nname: impostor\n---\n", encoding="utf8")
        git("-C", str(invalid), "add", "SKILL.md")
        git("-C", str(invalid), "-c", "user.name=Tests", "-c", "user.email=test@example.org",
            "commit", "-m", "test: mismatched identity")
        result = self.ensure(names=("gen-ui",))
        self.assertEqual("BLOCKED_INVALID_SOURCE", result["skills"]["gen-ui"]["status"])
        self.assertFalse((self.root / "gen-ui").exists())
        self.assertEqual([], list(self.root.glob(".*-install-*")))

    def test_git_clone_failure_no_partial_install(self):
        from subprocess import CalledProcessError
        with patch("ensure_dependencies._run_git", side_effect=CalledProcessError(128, ["git", "clone"])):
            result = self.ensure(names=("code-pact",))
        self.assertEqual("BLOCKED_INSTALL_FAILED", result["skills"]["code-pact"]["status"])
        self.assertFalse((self.root / "code-pact").exists())
        self.assertEqual([], list(self.root.glob(".*-install-*")))

    def test_system_profile_is_not_treated_as_user_home(self):
        result = ensure_dependencies(home=Path("C:/Windows/System32/config/systemprofile"), env={},
                                     repositories=self.repos, host="codex")
        self.assertEqual("BLOCKED_SYSTEM_PROFILE", result["status"])

    def test_invalid_dependency_name_is_rejected(self):
        with self.assertRaises(ValueError):
            self.ensure(names=("arbitrary-package",))

    def test_symlink_host_root_is_skipped(self):
        other = self.home / "elsewhere"
        other.mkdir()
        self.root.rmdir()
        try:
            self.root.symlink_to(other, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symbolic links restricted on this OS")
        self.assertEqual([], existing_skill_roots(self.home, {}))
        self.assertEqual("BLOCKED_NO_EXISTING_SKILLS_ROOT", self.ensure()["status"])
        self.assertFalse((other / "code-pact").exists())

    def test_preflight_main_really_installs_missing_before_reading(self):
        import preflight
        with patch.object(Path, "home", return_value=self.home), \
             patch.object(preflight, "ensure_dependencies", side_effect=lambda **kw: self.ensure(**kw)), \
             patch.object(sys, "argv", ["preflight.py", "--project", str(self.home), "--host", "codex", "--install-optional", "--read-content", "--json"]), \
             redirect_stdout(io.StringIO()) as capture:
            code = preflight.main()
        self.assertEqual(0, code)
        report = json.loads(capture.getvalue())
        self.assertEqual("READY_CORE_OPTIONAL_FILES_READ_AGENT_CONFIRMATION_REQUIRED", report["preflight_status"])
        self.assertEqual("INSTALLED_OR_PRESENT_AGENT_LOAD_REQUIRED", report["bootstrap"]["status"])
        self.assertEqual(["INSTALLED", "INSTALLED"],
                         [report["bootstrap"]["skills"][name]["status"] for name in REQUIRED])

    def test_preflight_read_only_opt_out_never_clones(self):
        import preflight
        with patch.object(Path, "home", return_value=self.home), \
             patch.object(preflight, "ensure_dependencies", side_effect=AssertionError("unexpected install")), \
             patch.object(sys, "argv", ["preflight.py", "--project", str(self.home),
                                        "--host", "codex", "--read-content", "--json"]), \
             redirect_stdout(io.StringIO()) as capture:
            code = preflight.main()
        self.assertEqual(0, code)
        report = json.loads(capture.getvalue())
        self.assertEqual("READY_CORE_WITH_OPTIONAL_WARNINGS", report["preflight_status"])
        self.assertFalse((self.root / "code-pact").exists())

    def test_legacy_folder_with_new_skill_id_does_not_duplicate(self):
        import preflight
        old = self.root / "previous-local-folder"
        old.mkdir()
        (old / "SKILL.md").write_text("---\nname: code-pact\n---\n", encoding="utf8")
        self.ensure(names=("gen-ui",))
        with patch.object(Path, "home", return_value=self.home), \
             patch.object(preflight, "ensure_dependencies", side_effect=AssertionError("duplicate clone")), \
             patch.object(sys, "argv", ["preflight.py", "--project", str(self.home), "--host", "codex", "--json"]), \
             redirect_stdout(io.StringIO()) as capture:
            code = preflight.main()
        self.assertEqual(0, code)
        self.assertEqual("READY_CORE_OPTIONAL_FILES_FOUND_AGENT_CONFIRMATION_REQUIRED", json.loads(capture.getvalue())["preflight_status"])
        self.assertFalse((self.root / "code-pact").exists())

    def test_preflight_has_read_only_flag_and_default_bootstrap(self):
        import preflight
        parser = (ROOT / "scripts" / "preflight.py").read_text(encoding="utf8")
        self.assertIn("--no-auto-install", parser)
        self.assertIn("--install-optional", parser)
        self.assertIn("--host", parser)
        self.assertEqual(("code-pact", "gen-ui"), preflight.REQUIRED)


if __name__ == "__main__":
    unittest.main()
