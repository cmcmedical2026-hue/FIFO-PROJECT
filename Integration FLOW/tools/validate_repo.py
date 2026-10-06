"""Check that the repository is in a state an agent can trust. No network.

Run this after editing skills, scripts or templates:

    python tools/validate_repo.py

It verifies skill frontmatter, that every script compiles and exposes ``--help``,
that the templates are present and free of credentials, and that no secret has
been committed into a tracked file.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
#: Anything matching these in a tracked text file is a leaked secret.
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(pass|password)\s*[:=]\s*['\"][^'\"]{3,}['\"]"),
    re.compile(r"(?i)\bapikey\s*[:=]\s*['\"][A-Za-z0-9+/=_-]{12,}['\"]"),
)
#: Files that legitimately mention these words while defining or redacting them.
SECRET_ALLOWLIST = {"credentials.py", "validate_repo.py", ".env.example"}

problems: list[str] = []
notes: list[str] = []


def fail(message: str) -> None:
    problems.append(message)
    print("FAIL " + message)


def ok(message: str) -> None:
    notes.append(message)
    print("OK   " + message)


def check_skills() -> None:
    skills_dir = ROOT / "skills"
    if not skills_dir.is_dir():
        fail("skills/ directory is missing")
        return
    folders = sorted(p for p in skills_dir.iterdir() if p.is_dir())
    if not folders:
        fail("skills/ contains no skill")
    for folder in folders:
        path = folder / "SKILL.md"
        if not path.is_file():
            fail("%s has no SKILL.md" % folder.name)
            continue
        text = path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not match:
            fail("%s: SKILL.md has no YAML frontmatter" % folder.name)
            continue
        fields: dict[str, str] = {}
        for line in match.group(1).splitlines():
            key, sep, value = line.partition(": ")
            if sep:
                fields[key.strip()] = value.strip()
        if set(fields) != {"name", "description"}:
            fail("%s: frontmatter must hold exactly name and description, found %s"
                 % (folder.name, sorted(fields)))
            continue
        if fields["name"] != folder.name:
            fail("%s: name is %r but the folder is %r" % (folder.name, fields["name"], folder.name))
        if not SLUG.match(folder.name) or len(folder.name) > 64:
            fail("%s: folder name is not a valid slug" % folder.name)
        if not fields["description"] or len(fields["description"]) > 1024:
            fail("%s: description is empty or too long" % folder.name)
        if "[TODO" in text or "C:\\Users" in text:
            fail("%s: contains a placeholder or a machine-specific path" % folder.name)
        ok("skill %s" % folder.name)


def check_scripts() -> None:
    for folder in ("scripts", "tools", "src/flow"):
        for path in sorted((ROOT / folder).rglob("*.py")):
            try:
                ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError as exc:
                fail("%s: syntax error line %s" % (path.relative_to(ROOT), exc.lineno))
                continue
            ok("compiles %s" % path.relative_to(ROOT))


def check_templates() -> None:
    from flow import config

    if not config.TEMPLATES_DIR.is_dir():
        fail("templates/ is missing; run tools/extract_templates.py")
        return
    found = sorted(p for p in config.TEMPLATES_DIR.glob("*.json") if p.name != "index.json")
    if not found:
        fail("templates/ holds no operation template")
        return
    for path in found:
        data = json.loads(path.read_text(encoding="utf-8"))
        payload = data.get("payload")
        if not isinstance(payload, dict) or not payload.get("DTL"):
            fail("%s: payload has no DTL line" % path.name)
            continue
        if str(payload.get("OP", "")).upper() != path.stem:
            fail("%s: payload OP is %r" % (path.name, payload.get("OP")))
        if payload.get("DOCNO") != 0:
            fail("%s: payload DOCNO must be 0" % path.name)
    ok("templates: %d operations" % len(found))


def check_secrets() -> None:
    tracked = []
    for pattern in ("*.py", "*.md", "*.json", "*.txt", "*.yml", "*.yaml", "*.cfg", "*.ini"):
        tracked.extend(ROOT.rglob(pattern))
    scanned = 0
    for path in tracked:
        parts = set(path.relative_to(ROOT).parts)
        if parts & {"har", ".git", "__pycache__", "runs", "legacy"}:
            continue
        if path.name in SECRET_ALLOWLIST:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        for matcher in SECRET_PATTERNS:
            found = matcher.search(text)
            if found:
                fail("%s: looks like a hardcoded secret near %r"
                     % (path.relative_to(ROOT), found.group(0)[:30]))
    ok("secret scan: %d files clean" % scanned)


def check_gitignore() -> None:
    path = ROOT / ".gitignore"
    if not path.is_file():
        fail(".gitignore is missing; HAR captures could be committed with credentials in them")
        return
    text = path.read_text(encoding="utf-8")
    for needed in ("*.har", ".env"):
        if needed not in text:
            fail(".gitignore does not exclude %s" % needed)
    ok(".gitignore excludes captures and .env")


def main() -> int:
    check_gitignore()
    check_skills()
    check_scripts()
    check_templates()
    check_secrets()
    print("\n%d check(s) passed, %d problem(s)" % (len(notes), len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
