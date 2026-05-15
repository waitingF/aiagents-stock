"""Shared persistence for selector run results."""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.aiagents_stock.core.paths import data_path


SELECTOR_TITLES = {
    "main-force": "主力选股",
    "low-price-bull": "低价擒牛",
    "small-cap": "小市值策略",
    "profit-growth": "净利增长",
    "value-stock": "低估值策略",
}


class SelectorHistoryRepository:
    """SQLite repository for selector result history."""

    def __init__(self, db_path: str = "selector_results.db") -> None:
        self.db_path = str(data_path(db_path))
        self.init_database()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_database(self) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS selector_result_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                selector_key TEXT NOT NULL,
                title TEXT,
                timestamp TEXT NOT NULL,
                params_json TEXT,
                success INTEGER NOT NULL DEFAULT 0,
                message TEXT,
                result_json TEXT NOT NULL,
                summary TEXT,
                markdown TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_selector_history_key_created
            ON selector_result_history(selector_key, created_at DESC)
            """
        )
        conn.commit()
        conn.close()

    def save_result(self, selector_key: str, params: Dict[str, Any], result: Dict[str, Any]) -> int:
        safe_result = _to_jsonable(result)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        title = SELECTOR_TITLES.get(selector_key, selector_key)
        summary = _build_summary(selector_key, safe_result)
        markdown = _build_markdown(selector_key, timestamp, params, safe_result, summary)

        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO selector_result_history
            (selector_key, title, timestamp, params_json, success, message,
             result_json, summary, markdown)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                selector_key,
                title,
                timestamp,
                json.dumps(_to_jsonable(params or {}), ensure_ascii=False),
                1 if safe_result.get("success") else 0,
                str(safe_result.get("message") or safe_result.get("error") or ""),
                json.dumps(safe_result, ensure_ascii=False),
                summary,
                markdown,
            ),
        )
        history_id = int(cursor.lastrowid)
        conn.commit()
        conn.close()
        return history_id

    def list_results(self, selector_key: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit or 20), 100))
        conn = self.get_connection()
        cursor = conn.cursor()
        if selector_key:
            cursor.execute(
                """
                SELECT *
                FROM selector_result_history
                WHERE selector_key = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (selector_key, limit),
            )
        else:
            cursor.execute(
                """
                SELECT *
                FROM selector_result_history
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            )
        rows = [self._row_to_item(row, include_result=True) for row in cursor.fetchall()]
        conn.close()
        return rows

    def get_result(self, history_id: int, selector_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        if selector_key:
            cursor.execute(
                "SELECT * FROM selector_result_history WHERE id = ? AND selector_key = ?",
                (history_id, selector_key),
            )
        else:
            cursor.execute("SELECT * FROM selector_result_history WHERE id = ?", (history_id,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_item(row, include_result=True) if row else None

    def _row_to_item(self, row: sqlite3.Row, include_result: bool = False) -> Dict[str, Any]:
        item = dict(row)
        item["success"] = bool(item.get("success"))
        item["params"] = _loads_json(item.pop("params_json", None), {})
        item["analysis_type"] = item.get("title") or item.get("selector_key")
        item["report_type"] = item["analysis_type"]
        item["report_date"] = item.get("timestamp")
        if include_result:
            item["result"] = _loads_json(item.pop("result_json", None), {})
        else:
            item.pop("result_json", None)
        return item


def _build_summary(selector_key: str, result: Dict[str, Any]) -> str:
    if not result.get("success"):
        return f"运行失败: {result.get('error') or result.get('message') or '未知错误'}"

    if selector_key == "main-force":
        recs = result.get("final_recommendations") or []
        total = result.get("total_stocks", 0)
        filtered = result.get("filtered_stocks", 0)
        names = _record_names(recs)[:5]
        suffix = f"，推荐: {'、'.join(names)}" if names else ""
        return f"获取 {total} 只，筛选通过 {filtered} 只，最终推荐 {len(recs)} 只{suffix}"

    records = _extract_records(result)
    names = _record_names(records)[:8]
    suffix = f": {'、'.join(names)}" if names else ""
    return f"{SELECTOR_TITLES.get(selector_key, selector_key)}成功返回 {len(records)} 条结果{suffix}"


def _build_markdown(
    selector_key: str,
    timestamp: str,
    params: Dict[str, Any],
    result: Dict[str, Any],
    summary: str,
) -> str:
    title = SELECTOR_TITLES.get(selector_key, selector_key)
    lines = [
        f"# {title}结果",
        "",
        f"**运行时间**: {timestamp}",
        f"**运行状态**: {'成功' if result.get('success') else '失败'}",
        f"**摘要**: {summary}",
    ]
    if result.get("message"):
        lines.append(f"**消息**: {result.get('message')}")
    if result.get("error"):
        lines.append(f"**错误**: {result.get('error')}")
    if params:
        lines.extend(["", "## 参数"])
        lines.extend(f"- {key}: {value}" for key, value in params.items())

    if selector_key == "main-force":
        recs = result.get("final_recommendations") or []
        lines.extend(["", "## 最终推荐"])
        if recs:
            for index, rec in enumerate(recs, 1):
                name = _record_name(rec) or f"标的 {index}"
                reason = rec.get("reason") or rec.get("analysis_reason") or rec.get("highlights") or ""
                lines.append(f"- {index}. {name}: {reason}")
        else:
            lines.append("- 暂无推荐结果")
        return "\n".join(lines)

    records = _extract_records(result)
    lines.extend(["", "## 选股结果"])
    if records:
        for index, rec in enumerate(records[:50], 1):
            lines.append(f"- {index}. {_record_name(rec) or json.dumps(rec, ensure_ascii=False)[:120]}")
    else:
        lines.append("- 暂无结果")
    return "\n".join(lines)


def _extract_records(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = result.get("data")
    if isinstance(data, dict) and isinstance(data.get("records"), list):
        return [item for item in data["records"] if isinstance(item, dict)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _record_names(records: List[Dict[str, Any]]) -> List[str]:
    return [name for name in (_record_name(item) for item in records) if name]


def _record_name(record: Dict[str, Any]) -> str:
    code = _first_value(record, ["code", "symbol", "stock_code", "股票代码", "代码"])
    name = _first_value(record, ["name", "stock_name", "股票简称", "股票名称", "简称", "名称"])
    if code and name:
        return f"{name}({code})"
    return str(name or code or "")


def _first_value(record: Dict[str, Any], keys: List[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def _loads_json(value: Any, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return _to_jsonable(asdict(value))
    if hasattr(value, "model_dump"):
        return _to_jsonable(value.model_dump())

    try:
        import numpy as np

        if isinstance(value, np.generic):
            return _to_jsonable(value.item())
        if isinstance(value, np.ndarray):
            return _to_jsonable(value.tolist())
    except Exception:
        pass

    try:
        import pandas as pd

        if isinstance(value, pd.DataFrame):
            frame = value.copy()
            frame = frame.where(pd.notnull(frame), None)
            return {
                "type": "dataframe",
                "columns": [str(column) for column in frame.columns],
                "records": _to_jsonable(frame.to_dict("records")),
                "row_count": int(len(frame)),
            }
        if isinstance(value, pd.Series):
            return _to_jsonable(value.to_dict())
    except Exception:
        pass

    if hasattr(value, "to_dict"):
        try:
            return _to_jsonable(value.to_dict())
        except Exception:
            pass

    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    return str(value)


selector_history = SelectorHistoryRepository()
