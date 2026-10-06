"""Dependency-free fallback for the two simple staged SKILL.md frontmatters."""

import re
from pathlib import Path


root = Path(r"C:\Users\hp\Documents\Codex\2026-09-15\g\work\skill-staging")
for folder in ("flow-erp-sales-request", "flow-erp-sales-order"):
    text = (root / folder / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert match, f"frontmatter missing: {folder}"
    fields = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(": ")
        assert sep and key in ("name", "description") and key not in fields, f"invalid YAML field: {folder}"
        fields[key] = value
    assert set(fields) == {"name", "description"}, f"required fields missing: {folder}"
    assert fields["name"] == folder and len(folder) <= 64 and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", folder)
    assert fields["description"] and len(fields["description"]) <= 1024
    assert not any(char in fields["description"] for char in "<>")
    assert "[TODO:" not in text and "C:\\Users\\hp\\Downloads" not in text
    assert "997" not in text and "987" not in text
    print(f"VALID {folder}: name, description, no placeholders or example IDs")
