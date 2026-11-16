import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "packages") not in sys.path:
    sys.path.insert(0, str(ROOT / "packages"))

import validate_skills  # noqa: E402


class ValidateSkillsTests(unittest.TestCase):
    def test_repository_skills_pass_validation(self) -> None:
        self.assertEqual(validate_skills.validate_skills(), [])

    def test_detects_missing_link_and_machine_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skills_root = Path(tmp)
            skill = skills_root / "geo-video-sample"
            (skill / "agents").mkdir(parents=True)
            (skill / "agents" / "openai.yaml").write_text(
                'interface:\n  display_name: "Sample"\n  short_description: "Sample"\n',
                encoding="utf-8",
            )
            (skill / "SKILL.md").write_text(
                "---\nname: geo-video-sample\ndescription: Sample skill.\n---\n"
                "See [broken](references/missing.md) and `/Users/alice/work`.\n",
                encoding="utf-8",
            )
            errors = validate_skills.validate_skills(skills_root)
            self.assertTrue(any("missing link target" in e for e in errors))
            self.assertTrue(any("machine-specific home path" in e for e in errors))

    def test_ignores_markdown_links_inside_code_spans(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skills_root = Path(tmp)
            skill = skills_root / "geo-video-sample"
            (skill / "agents").mkdir(parents=True)
            (skill / "agents" / "openai.yaml").write_text(
                'interface:\n  display_name: "Sample"\n  short_description: "Sample"\n',
                encoding="utf-8",
            )
            (skill / "SKILL.md").write_text(
                "---\nname: geo-video-sample\ndescription: Sample skill.\n---\n"
                "Example `[text](URL)` and:\n```md\n[ignored](missing.md)\n```\n",
                encoding="utf-8",
            )
            self.assertEqual(validate_skills.validate_skills(skills_root), [])


if __name__ == "__main__":
    unittest.main()
