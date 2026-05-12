"""Runtime loader for the stock-data-store git submodule."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from src.aiagents_stock.core.paths import PROJECT_ROOT


PACKAGE_NAME = "stock_data_store"
SUBMODULE_ROOT = PROJECT_ROOT / "vendor" / "stock-data-store"


def ensure_stock_data_store_loaded():
    """Load the submodule package under its expected import name."""
    existing = sys.modules.get(PACKAGE_NAME)
    if existing is not None:
        return existing

    init_path = SUBMODULE_ROOT / "__init__.py"
    if not init_path.exists():
        raise RuntimeError(
            "stock-data-store submodule is missing. Run "
            "`git submodule update --init --recursive` from the project root."
        )

    spec = importlib.util.spec_from_file_location(
        PACKAGE_NAME,
        init_path,
        submodule_search_locations=[str(SUBMODULE_ROOT)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load stock-data-store from {init_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE_NAME] = module
    spec.loader.exec_module(module)
    return module


def get_submodule_root() -> Path:
    return SUBMODULE_ROOT
