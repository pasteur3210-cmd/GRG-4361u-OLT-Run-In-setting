import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class BuildDependenciesTests(unittest.TestCase):
    def test_pillow_declared_for_icon_regression_test(self):
        requirements = (ROOT / "requirements-build.txt").read_text(encoding="utf-8").lower()
        self.assertRegex(requirements, r"(?m)^pillow==[0-9.]+$")

    def test_github_installs_and_checks_dependencies_before_testing(self):
        workflow = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
        self.assertIn("pip install -r requirements.txt -r requirements-build.txt", workflow)
        self.assertIn("python -m pip check", workflow)
        self.assertIn("from PIL import Image", workflow)
        self.assertLess(workflow.index("Install dependencies"), workflow.index("Verify installed dependencies"))
        self.assertLess(workflow.index("Verify installed dependencies"), workflow.index("Compile and test"))

    def test_icon_not_changed(self):
        self.assertTrue((ROOT / "CT.ico").is_file())
        self.assertGreater((ROOT / "CT.ico").stat().st_size, 1024)
