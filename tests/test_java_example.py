"""Execute a real tiny Java example and an isolated deliberately wrong implementation."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "java-order-total" / "src"


@unittest.skipUnless(shutil.which("javac") and shutil.which("java"), "JDK not available")
class JavaOrderTotalExampleTests(unittest.TestCase):
    def _run(self, mutate: bool) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = (EXAMPLE / "OrderTotal.java").read_text(encoding="utf-8")
            if mutate:
                original = "total = Math.addExact(total, amount);"
                self.assertIn(original, source)
                source = source.replace(original, "total = Math.addExact(total, amount) + 1;", 1)
            (folder / "OrderTotal.java").write_text(source, encoding="utf-8")
            shutil.copy2(EXAMPLE / "OrderTotalCheck.java", folder / "OrderTotalCheck.java")
            compile_result = subprocess.run(
                ["javac", "-d", str(folder), str(folder / "OrderTotal.java"), str(folder / "OrderTotalCheck.java")],
                capture_output=True, text=True, timeout=25,
            )
            self.assertEqual(0, compile_result.returncode, compile_result.stderr)
            return subprocess.run(["java", "-cp", str(folder), "OrderTotalCheck"], capture_output=True, text=True, timeout=15)

    def test_correct_java_logic_actually_passes(self):
        result = self._run(False)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("passed (3 checks)", result.stdout)

    def test_deliberate_wrong_java_logic_actually_fails(self):
        result = self._run(True)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("AssertionError", result.stderr)
        self.assertIn("expected 400 cents", result.stderr)


if __name__ == "__main__":
    unittest.main()
