#!/usr/bin/env python3
"""Build a Host-installable ZIP: one top-level business-ui/ directory."""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIR = {
    ".adapter-certs",
    "__pycache__",
    ".pytest_cache",
    "scripts",
    "dist",
    "node_modules",
    ".vite",
    ".mypy_cache",
    ".ruff_cache",
}


def pack(dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT)
            if any(part in SKIP_DIR or part.endswith(".pyc") for part in rel.parts):
                continue
            zf.write(path, arcname=f"business-ui/{rel.as_posix()}")
    return dest


if __name__ == "__main__":
    out = ROOT / "dist" / "business-ui.zip"
    pack(out)
    print(out)
