"""Changelog tooling.

    python packaging/changelog.py sync-readme      # copy latest entries into README.md
    python packaging/changelog.py notes v0.3.0     # print release notes for a version
    python packaging/changelog.py check            # CI: version has an entry, README in sync
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"
README = ROOT / "README.md"
START, END = "<!-- changelog:start -->", "<!-- changelog:end -->"
README_VERSIONS = 3


def current_version() -> str:
    text = (ROOT / "raja_capture" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)


def sections() -> list[tuple[str, str, str]]:
    """[(version, date, body)] newest first."""
    text = CHANGELOG.read_text(encoding="utf-8")
    out = []
    for m in re.finditer(r"^## \[([^\]]+)\](?: - (\S+))?\s*\n(.*?)(?=^## \[|^\[[^\]]+\]: |\Z)", text,
                         re.M | re.S):
        out.append((m.group(1), m.group(2) or "", m.group(3).strip()))
    return out


def notes(version: str) -> str:
    version = version.lstrip("v")
    for v, _date, body in sections():
        if v == version:
            return body
    raise SystemExit(f"CHANGELOG.md has no entry for {version}")


def readme_block() -> str:
    parts = []
    for v, date, body in sections()[:README_VERSIONS]:
        body = re.sub(r"^### ", "#### ", body, flags=re.M)
        parts.append(f"### {v}{f' — {date}' if date else ''}\n\n{body}")
    parts.append("See [CHANGELOG.md](CHANGELOG.md) for the full history.")
    return f"{START}\n" + "\n\n".join(parts) + f"\n{END}"


def synced_readme() -> str:
    text = README.read_text(encoding="utf-8")
    if START not in text or END not in text:
        raise SystemExit("README.md is missing the changelog markers")
    return re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _m: readme_block(), text, flags=re.S)


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv else "check"
    if cmd == "sync-readme":
        README.write_text(synced_readme(), encoding="utf-8")
        print("README.md changelog updated")
    elif cmd == "notes":
        print(notes(argv[1] if len(argv) > 1 else current_version()))
    elif cmd == "check":
        version = current_version()
        notes(version)
        if README.read_text(encoding="utf-8") != synced_readme():
            raise SystemExit("README.md changelog is out of date: run python packaging/changelog.py sync-readme")
        print(f"changelog OK for {version}")
    else:
        raise SystemExit(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
