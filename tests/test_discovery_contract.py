"""Guard bilingual discovery promises without pretending to measure search rankings."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_package import validate


class DiscoveryContractTests(unittest.TestCase):
    def test_package_and_all_markdown_links_resolve(self):
        self.assertEqual([], validate(ROOT))

    def test_skill_english_and_chinese_discovery(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        frontmatter = skill.split("---", 2)[1]
        for phrase in ("implementation", "review", "testing", "acceptance", "方案编写", "全流程"):
            self.assertIn(phrase, frontmatter)
        self.assertIn("code-pact", skill)
        self.assertIn("gen-ui", skill)
        self.assertIn("github.com/yeqiana/code-pact", skill)
        self.assertIn("github.com/yeqiana/gen-ui", skill)
        self.assertIn("BLOCKED", skill)
        self.assertIn("大白话解释/", skill)

    def test_english_host_metadata_not_only_chinese(self):
        metadata = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        for phrase in ("$plan-ship", "Evidence-driven", "testing", "acceptance", "方案"):
            self.assertIn(phrase, metadata)

    def test_documentation_does_not_claim_geo_success(self):
        baseline = (ROOT / "evals" / "discovery-baseline.md").read_text(encoding="utf-8")
        self.assertIn("NOT MEASURED", baseline)
        self.assertIn("NOT_RUN", baseline)
        self.assertIn("EN-01", baseline)
        self.assertIn("ZH-01", baseline)
        recommendations = (ROOT / "docs" / "github-metadata.md").read_text(encoding="utf-8")
        self.assertIn("proposed target", recommendations)
        self.assertIn("[ ] Topics", recommendations)

    def test_english_usage_and_faq_are_discoverable(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("$plan-ship plan:", readme)
        self.assertIn("docs/faq.md", readme)
        self.assertIn("docs/geo-methodology.md", readme)
        faq = (ROOT / "docs" / "faq.md").read_text(encoding="utf-8")
        self.assertIn("What is the best way", faq)
        self.assertIn("Does PlanShip prevent", faq)
        self.assertIn("not", faq.lower())

    def test_route_manager_preserves_stable_marker_and_supports_english(self):
        from route_manager import START, ROUTE
        self.assertIn("v1.0.0", START)  # stable installed marker, not the release number
        for phrase in ("implementation plan", "acceptance testing", "manual acceptance guide", "方案编写"):
            self.assertIn(phrase, ROUTE)

    def test_document_translation_does_not_overpromise_english_schema(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        policy = (ROOT / "docs" / "language-policy.md").read_text(encoding="utf-8")
        self.assertIn("fully English schema", skill)
        self.assertIn("Chinese structural headings", policy)

    def test_ci_runs_java_negative_control(self):
        flow = (ROOT / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
        self.assertIn("actions/setup-java@v4", flow)
        self.assertIn("unittest discover", flow)

    def test_core_technical_tools_unchanged_by_publication(self):
        # Smoke checks for the stable command paths; no test or execution bypass.
        for name in ("route_manager.py", "run_and_record.py", "validate_evidence.py", "doc_registry.py"):
            self.assertTrue((ROOT / "scripts" / name).is_file())


if __name__ == "__main__":
    unittest.main()
