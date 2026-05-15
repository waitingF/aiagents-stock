"""Shared persistence for macro analysis reports."""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.aiagents_stock.core.paths import data_path


class MacroReportHistoryRepository:
    """SQLite repository for macro-analysis and macro-cycle report history."""

    def __init__(self, db_path: str = "macro_reports.db") -> None:
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
            CREATE TABLE IF NOT EXISTS macro_report_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                model TEXT,
                result_json TEXT NOT NULL,
                summary TEXT,
                markdown TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_macro_report_module_created
            ON macro_report_history(module, created_at DESC)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_macro_report_module_timestamp
            ON macro_report_history(module, timestamp DESC)
            """
        )

        conn.commit()
        conn.close()

    def save_report(
        self,
        *,
        module: str,
        timestamp: Optional[str],
        model: Optional[str],
        result: Dict[str, Any],
        summary: str,
        markdown: str,
    ) -> int:
        report_time = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result_json = json.dumps(_to_jsonable(result), ensure_ascii=False)

        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO macro_report_history
            (module, timestamp, model, result_json, summary, markdown)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (module, report_time, model, result_json, summary, markdown),
        )
        report_id = int(cursor.lastrowid)
        conn.commit()
        conn.close()
        return report_id

    def list_reports(self, module: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit or 20), 100))
        conn = self.get_connection()
        cursor = conn.cursor()
        if module:
            cursor.execute(
                """
                SELECT id, module, timestamp, model, summary, markdown, created_at
                FROM macro_report_history
                WHERE module = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (module, limit),
            )
        else:
            cursor.execute(
                """
                SELECT id, module, timestamp, model, summary, markdown, created_at
                FROM macro_report_history
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            )

        reports = [self._row_to_report(row) for row in cursor.fetchall()]
        conn.close()
        return reports

    def get_report(self, report_id: int, module: Optional[str] = None) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        cursor = conn.cursor()
        if module:
            cursor.execute(
                """
                SELECT *
                FROM macro_report_history
                WHERE id = ? AND module = ?
                """,
                (report_id, module),
            )
        else:
            cursor.execute(
                """
                SELECT *
                FROM macro_report_history
                WHERE id = ?
                """,
                (report_id,),
            )
        row = cursor.fetchone()
        conn.close()
        if not row:
            return None
        return self._row_to_report(row, include_result=True)

    def _row_to_report(self, row: sqlite3.Row, include_result: bool = False) -> Dict[str, Any]:
        report = dict(row)
        report["analysis_type"] = report.get("module")
        report["report_type"] = _module_title(report.get("module"))
        report["report_date"] = report.get("timestamp")
        if include_result:
            report["result"] = _loads_json(report.get("result_json"))
        report.pop("result_json", None)
        return report


def _module_title(module: Optional[str]) -> str:
    return {
        "macro-analysis": "宏观分析报告",
        "macro-cycle": "宏观周期报告",
    }.get(module or "", "宏观报告")


def _loads_json(value: Any) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except Exception:
        return value


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

    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    return str(value)


macro_report_history = MacroReportHistoryRepository()
