import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class BuildTestDependencyRegression(unittest.TestCase):
    def test_icon_readability_uses_pillow_not_numpy(self):
        path = ROOT / "tests" / "test_icon_readability_v10233.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules = {node.names[0].name.split(".")[0] for node in ast.walk(tree)
                   if isinstance(node, ast.Import)}
        modules.update(node.module.split(".")[0] for node in ast.walk(tree)
                       if isinstance(node, ast.ImportFrom) and node.module)
        self.assertIn("PIL", modules)
        self.assertNotIn("numpy", modules)

    def test_dependencies_installed_before_tests(self):
        workflow = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
        reqs = (ROOT / "requirements-build.txt").read_text(encoding="utf-8")
        self.assertIn("Pillow", reqs)
        self.assertLess(workflow.index("pip install -r requirements.txt"),
                        workflow.index("python -m unittest discover"))
