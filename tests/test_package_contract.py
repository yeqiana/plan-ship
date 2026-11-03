"""Test PlanShip's release metadata without pretending to test a host runtime."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_package import check_links, validate
from route_manager import START, END, LEGACY_START, LEGACY_END, manage


class PackageContractTests(unittest.TestCase):
    def test_release_manifest_and_links(self):
        self.assertEqual([], validate(ROOT))

    def test_public_skill_identity(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: plan-ship", skill.split("---", 2)[1])
        self.assertIn("$plan-ship", skill)
        self.assertIn("/plan-ship", skill)
        self.assertIn("plan-ship:route:start", (ROOT / "scripts/route_manager.py").read_text(encoding="utf-8"))

    def test_no_old_route_marker(self):
        self.assertIn("plan-ship", START)
        self.assertIn("plan-ship", END)
        self.assertNotIn("delivery:route:start", START)

    def test_link_fence_examples_not_interpreted(self):
        sample = "# Example\n\n```md\n[not real](missing.md)\n```\n[real](README.md)\n"
        self.assertEqual([], check_links(ROOT, "sample.md", sample))

    def test_broken_links_are_rejected(self):
        self.assertTrue(check_links(ROOT, "sample.md", "[x](missing.md)"))
        self.assertTrue(check_links(ROOT, "sample.md", "[x](../../outside.md)"))

    def test_route_installer_is_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.assertEqual("missing", manage(home, "check")["codex"]["state"])
            self.assertFalse((home / ".codex").exists())

    def test_legacy_route_requires_explicit_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            file = home / ".codex" / "AGENTS.md"
            file.parent.mkdir(parents=True)
            legacy = "user notes\n" + LEGACY_START + " v2.4 -->\nold rules\n" + LEGACY_END + "\n"
            file.write_text(legacy, encoding="utf-8")
            self.assertEqual("legacy_conflict", manage(home, "check", ("codex",))["codex"]["state"])
            with self.assertRaisesRegex(ValueError, "旧名称路由"):
                manage(home, "install", ("codex",))
            self.assertEqual(legacy, file.read_text(encoding="utf-8"))

    def test_build_refuses_fake_success_terminology(self):
        # A local static checker is not a claim of user project acceptance.
        readme = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        self.assertIn("不等于你的业务系统已经验收通过", readme)


if __name__ == "__main__":
    unittest.main()
