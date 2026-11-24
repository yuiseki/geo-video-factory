import re
import subprocess
import unittest
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = PIPELINE_DIR.parents[1]
MAX_MODULE_LINES = 400
# Directories under packages/pipeline that are not ours: a local virtualenv holds thousands of long third-party
# modules, and CI has none, so without this the size check passes there and fails on a developer's machine.
NOT_OURS = {"tests", ".venv", "venv", "site-packages", "__pycache__"}


def pipeline_modules() -> list[Path]:
    return sorted(
        p for p in PIPELINE_DIR.rglob("*.py") if not NOT_OURS.intersection(p.relative_to(PIPELINE_DIR).parts)
    )


class ArchitectureTests(unittest.TestCase):
    def test_pipeline_modules_stay_at_most_400_lines(self):
        oversized = []
        for path in pipeline_modules():
            line_count = len(path.read_text(encoding="utf-8").splitlines())
            if line_count > MAX_MODULE_LINES:
                oversized.append((path.name, line_count))
        self.assertEqual(
            oversized,
            [],
            f"split oversized modules by responsibility: {oversized}",
        )

    def test_the_size_check_looks_at_our_modules_only(self):
        modules = pipeline_modules()
        self.assertGreater(len(modules), 30)
        for path in modules:
            self.assertFalse(NOT_OURS.intersection(path.relative_to(PIPELINE_DIR).parts), path)

    def test_no_script_imports_a_pipeline_module_by_its_old_flat_name(self):
        """The modules live in subpackages (buildings, geo, photos, video, narration). A script that still says
        `import ambient_bgm` only fails when someone runs it, and the Blender scripts cannot be run in CI at all."""
        names = sorted({p.stem for p in pipeline_modules() if p.parent != PIPELINE_DIR and p.stem != "__init__"})
        flat = re.compile(r"^\s*(?:import (?:%s)\b|from (?:%s) import\b)" % ("|".join(names), "|".join(names)))
        tracked = subprocess.run(
            ["git", "ls-files", "-z", "--", "packages/*.py", "projects/*.py", ".agents/*.py"],
            cwd=REPO_DIR, capture_output=True, text=True, check=True,
        ).stdout.split("\0")
        stale = []
        for rel in filter(None, tracked):
            path = REPO_DIR / rel
            if "vendor-python" in path.parts or not path.is_file():
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if flat.match(line):
                    stale.append(f"{rel}:{number}: {line.strip()}")
        self.assertEqual(stale, [], "import these from their subpackage, e.g. `from narration import ambient_bgm`")


if __name__ == "__main__":
    unittest.main()
