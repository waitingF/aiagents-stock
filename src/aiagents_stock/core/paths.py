"""Filesystem paths used by the application."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"


def ensure_runtime_dirs() -> None:
    """Create runtime data and log directories."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def data_path(path: str | Path) -> Path:
    """Return an absolute path under data/ for plain filenames."""
    path = Path(path)
    ensure_runtime_dirs()
    if path.is_absolute() or path.parent != Path("."):
        return path
    return DATA_DIR / path


def log_path(path: str | Path) -> Path:
    """Return an absolute path under logs/ for plain filenames."""
    path = Path(path)
    ensure_runtime_dirs()
    if path.is_absolute() or path.parent != Path("."):
        return path
    return LOGS_DIR / path
