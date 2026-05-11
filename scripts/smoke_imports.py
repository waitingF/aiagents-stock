#!/usr/bin/env python3
"""Minimal import smoke test for the modularization migration."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

for path in (PROJECT_ROOT, SRC_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


SKIP_TOP_LEVEL = {"app", "run", "stm", "test_tdx_api", "update_env_example"}


def main() -> None:
    modules = {"aiagents_stock.features.stock_analysis.service"}

    for path in PROJECT_ROOT.glob("*.py"):
        if path.stem in SKIP_TOP_LEVEL:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")[:300]
        if "Compatibility shim" in text:
            modules.add(path.stem)

    for path in SRC_DIR.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        if path.match("*/app/main.py") or path.match("*/app/legacy.py"):
            continue
        relative = path.relative_to(SRC_DIR).with_suffix("")
        modules.add(".".join(relative.parts))

    for module_name in sorted(modules):
        importlib.import_module(module_name)
        print(f"import ok: {module_name}")


if __name__ == "__main__":
    main()
