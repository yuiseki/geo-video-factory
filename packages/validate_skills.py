#!/usr/bin/env python3
"""Validate skill bundles under .agents/skills/ (stdlib only)."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / ".agents" / "skills"
TEXT_SUFFIXES = {".md", ".html", ".js", ".css", ".yaml", ".yml", ".py", ".ts", ".json"}
MACHINE_PATH_RE = re.compile(r"/Users/[^/\s`'\"]+/|C:\\\\Users\\\\[^\\\\\s`'\"]+\\\\")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^\s)]+)\)")


def parse_frontmatter(content: str) -> dict[str, str] | None:
    """Extract top-level scalar keys from YAML frontmatter without PyYAML."""
    match = re.match(r"^---\n(.*?)\n---\n", content, re.S)
    if not match:
        return None
    values: dict[str, str] = {}
    current_key: str | None = None
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key_match = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if key_match and not line.startswith((" ", "\t")):
            current_key = key_match.group(1)
            values[current_key] = key_match.group(2).strip().strip("\"'")
        elif current_key and line.startswith((" ", "\t")):
            values[current_key] = (values[current_key] + " " + line.strip()).strip()
    return values


CODE_FENCE_RE = re.compile(r"```.*?```", re.S)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def strip_markdown_code(content: str) -> str:
    """Remove fenced and inline code spans before scanning Markdown links."""
    without_fences = CODE_FENCE_RE.sub("", content)
    return INLINE_CODE_RE.sub("", without_fences)


def format_source(source: Path, skills_root: Path) -> str:
    """Format path relative to repo ROOT when inside it, else relative to skills_root."""
    if source.is_relative_to(ROOT):
        return str(source.relative_to(ROOT))
    if source.is_relative_to(skills_root):
        return str(source.relative_to(skills_root))
    return str(source)


def check_markdown_links(source: Path, content: str, skills_root: Path, errors: list[str]) -> None:
    """Verify relative links in markdown files stay within skills_root and exist."""
    label = format_source(source, skills_root)
    for raw_href in LINK_RE.findall(strip_markdown_code(content)):
        href = raw_href.strip("<>")
        url = urlsplit(href)
        if url.scheme or url.netloc or not url.path:
            continue
        target = (source.parent / unquote(url.path)).resolve()
        if not target.is_relative_to(skills_root.resolve()):
            errors.append(f"{label}: link escapes skills dir: {href}")
        elif not target.exists():
            errors.append(f"{label}: missing link target: {href}")


def validate_skills(skills_dir: Path = SKILLS_DIR) -> list[str]:
    """Validate all skill directories and return a list of error strings."""
    errors: list[str] = []
    if not skills_dir.is_dir():
        return [f"Skills directory not found: {skills_dir}"]

    bundles = sorted(p for p in skills_dir.iterdir() if p.is_dir() and not p.name.startswith("."))
    if not bundles:
        return ["No skill bundles found"]

    for bundle in bundles:
        entry = bundle / "SKILL.md"
        if not entry.is_file():
            errors.append(f"{bundle.name}: missing SKILL.md")
            continue

        content = entry.read_text(encoding="utf-8")
        fm = parse_frontmatter(content)
        if fm is None:
            errors.append(f"{bundle.name}: missing YAML frontmatter in SKILL.md")
        else:
            name = fm.get("name", "")
            if name != bundle.name or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", bundle.name) or len(bundle.name) > 64:
                errors.append(f"{bundle.name}: invalid or mismatched skill name '{name}'")
            if not fm.get("description", "").strip():
                errors.append(f"{bundle.name}: missing description in SKILL.md")

        openai_yaml = bundle / "agents" / "openai.yaml"
        if bundle.name.startswith("geo-video-"):
            if not openai_yaml.is_file():
                errors.append(f"{bundle.name}: missing agents/openai.yaml")
            else:
                yaml_text = openai_yaml.read_text(encoding="utf-8")
                if "display_name:" not in yaml_text or "short_description:" not in yaml_text:
                    errors.append(f"{bundle.name}: agents/openai.yaml must define display_name and short_description")

        for source in sorted(bundle.rglob("*")):
            if source.is_symlink() or not source.is_file() or source.suffix not in TEXT_SUFFIXES:
                continue
            text = source.read_text(encoding="utf-8")
            if MACHINE_PATH_RE.search(text):
                errors.append(f"{format_source(source, skills_dir)}: machine-specific home path found")
            if source.suffix == ".md":
                check_markdown_links(source, text, skills_dir, errors)

    return errors


def main() -> int:
    errors = validate_skills()
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1
    count = len([p for p in SKILLS_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")])
    print(f"PASS: validated {count} skill bundle(s) under .agents/skills/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
