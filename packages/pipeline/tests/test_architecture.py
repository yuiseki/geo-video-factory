import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parents[1]
MAX_MODULE_LINES = 400


class ArchitectureTests(unittest.TestCase):
    def test_pipeline_modules_stay_at_most_400_lines(self):
        oversized = []
        for path in sorted([p for p in PIPELINE_DIR.rglob("*.py") if "tests" not in p.relative_to(PIPELINE_DIR).parts]):
            line_count = len(path.read_text(encoding="utf-8").splitlines())
            if line_count > MAX_MODULE_LINES:
                oversized.append((path.name, line_count))
        self.assertEqual(
            oversized,
            [],
            f"split oversized modules by responsibility: {oversized}",
        )


if __name__ == "__main__":
    unittest.main()
