from __future__ import annotations

import re
from pathlib import Path


TEXT_EXTENSIONS = {
    ".bat",
    ".cfg",
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".py",
    ".ps1",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}

SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
}

MOJIBAKE_MARKERS = set("鍒鏅鏁璧闈瀹杩鐨锛銆鈥馃绛浠涓骞熷濡鍙鎴娆姝")
SUSPICIOUS_RUN = re.compile(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\u20ac\ufffd]{4,}")
COMMON_REPAIRED_CHINESE = set("的一是在和数据分析失败成功板块资金智能策略保存获取市场股票")


def _iter_text_files() -> list[Path]:
    root = Path(__file__).resolve().parents[1]
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in TEXT_EXTENSIONS:
            files.append(path)
    return files


def _repair_utf8_read_as_gbk(text: str) -> str | None:
    if not any(marker in text for marker in MOJIBAKE_MARKERS):
        return None
    try:
        repaired = text.encode("gbk").decode("utf-8")
    except UnicodeError:
        return None
    if repaired == text or "\ufffd" in repaired:
        return None
    if not any(ch in repaired for ch in COMMON_REPAIRED_CHINESE):
        return None
    return repaired


def test_text_files_do_not_contain_reversible_chinese_mojibake():
    hits: list[str] = []
    for path in _iter_text_files():
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            hits.append(f"{path}: not valid UTF-8: {exc}")
            continue

        for line_no, line in enumerate(content.splitlines(), 1):
            for match in SUSPICIOUS_RUN.finditer(line):
                repaired = _repair_utf8_read_as_gbk(match.group(0))
                if repaired:
                    hits.append(f"{path}:{line_no}: {match.group(0)!r} -> {repaired!r}")

    assert not hits, "Found likely Chinese mojibake:\n" + "\n".join(hits[:50])
