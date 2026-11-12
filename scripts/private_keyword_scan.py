#!/usr/bin/env python3
"""Scan public source for keywords from a private list.

The list path is taken from PRIVATE_KEYWORD_LIST_PATH or the first argument.
The list itself is not part of this repository. Each non-empty, non-comment
line is a keyword. Hits are printed and the process exits with status 1.

Default scan roots (relative to the repository root): src, openapi, skills,
clients, examples, and README.md. Design documents under docs/ are left out
so internal implementation notes can live there until they are removed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

DEFAULT_ROOTS = ("src", "openapi", "skills", "clients", "examples", "README.md")
SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_keywords(path: Path) -> list[str]:
    keywords: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        keywords.append(line)
    return keywords


def iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for name in DEFAULT_ROOTS:
        target = root / name
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            for path in target.rglob("*"):
                if not path.is_file():
                    continue
                if any(part in SKIP_DIR_NAMES for part in path.parts):
                    continue
                if path.suffix.lower() in {
                    ".png",
                    ".jpg",
                    ".jpeg",
                    ".gif",
                    ".webp",
                    ".ico",
                    ".pdf",
                    ".woff",
                    ".woff2",
                }:
                    continue
                files.append(path)
    return files


def main(argv: list[str]) -> int:
    raw = argv[1] if len(argv) > 1 else os.environ.get("PRIVATE_KEYWORD_LIST_PATH", "").strip()
    if not raw:
        print(
            "PRIVATE_KEYWORD_LIST_PATH is not set and no list path was given; "
            "skipping private keyword scan."
        )
        return 0
    list_path = Path(raw)
    if not list_path.is_file():
        print(f"Keyword list file not found: {list_path}", file=sys.stderr)
        return 1
    keywords = load_keywords(list_path)
    if not keywords:
        print(f"Keyword list is empty: {list_path}")
        return 0
    root = repo_root()
    hits: list[str] = []
    lowered = [(keyword, keyword.lower()) for keyword in keywords]
    for file_path in iter_files(root):
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        haystack = text.lower()
        for original, needle in lowered:
            if needle in haystack:
                rel = file_path.relative_to(root)
                hits.append(f"{rel}: {original}")
    if hits:
        print("Private keyword scan found the following hits:")
        for hit in hits:
            print(f"  {hit}")
        return 1
    print(f"Private keyword scan passed ({len(keywords)} keywords, no hits).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
