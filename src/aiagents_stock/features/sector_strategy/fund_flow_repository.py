"""Persistence for the non-AI sector fund-flow feature."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from src.aiagents_stock.core.paths import data_path
from src.aiagents_stock.core.serialization import to_jsonable


class SectorFundFlowRepository:
    """SQLite storage for sector fund-flow cache and reports."""

    def __init__(self, db_path: str | Path = "sector_fund_flow.db") -> None:
        self.db_path = str(data_path(db_path))
        self.init_database()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def connection(self):
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_database(self) -> None:
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sector_member_cache (
                    sector_source TEXT NOT NULL,
                    sector_level TEXT NOT NULL,
                    sector_code TEXT NOT NULL,
                    sector_name TEXT NOT NULL,
                    ts_code TEXT NOT NULL,
                    stock_name TEXT,
                    refreshed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (sector_source, sector_level, sector_code, ts_code)
                );

                CREATE INDEX IF NOT EXISTS idx_sector_member_stock
                ON sector_member_cache(sector_source, sector_level, ts_code);

                CREATE TABLE IF NOT EXISTS sector_flow_daily (
                    trade_date TEXT NOT NULL,
                    sector_source TEXT NOT NULL,
                    sector_level TEXT NOT NULL,
                    sector_code TEXT NOT NULL,
                    sector_name TEXT NOT NULL,
                    net_mf_amount REAL DEFAULT 0,
                    main_net_amount REAL DEFAULT 0,
                    super_large_net_amount REAL DEFAULT 0,
                    large_net_amount REAL DEFAULT 0,
                    medium_net_amount REAL DEFAULT 0,
                    small_net_amount REAL DEFAULT 0,
                    stock_count INTEGER DEFAULT 0,
                    positive_stock_count INTEGER DEFAULT 0,
                    negative_stock_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (trade_date, sector_source, sector_level, sector_code)
                );

                CREATE INDEX IF NOT EXISTS idx_sector_flow_daily_range
                ON sector_flow_daily(sector_source, sector_level, trade_date);

                CREATE TABLE IF NOT EXISTS sector_flow_stock_daily (
                    trade_date TEXT NOT NULL,
                    sector_source TEXT NOT NULL,
                    sector_level TEXT NOT NULL,
                    sector_code TEXT NOT NULL,
                    sector_name TEXT NOT NULL,
                    ts_code TEXT NOT NULL,
                    stock_name TEXT,
                    close REAL,
                    pct_chg REAL,
                    net_mf_amount REAL DEFAULT 0,
                    main_net_amount REAL DEFAULT 0,
                    super_large_net_amount REAL DEFAULT 0,
                    large_net_amount REAL DEFAULT 0,
                    medium_net_amount REAL DEFAULT 0,
                    small_net_amount REAL DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (trade_date, sector_source, sector_level, sector_code, ts_code)
                );

                CREATE INDEX IF NOT EXISTS idx_sector_flow_stock_range
                ON sector_flow_stock_daily(sector_source, sector_level, trade_date, sector_code);

                CREATE TABLE IF NOT EXISTS sector_fund_flow_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_date TEXT NOT NULL,
                    range_type TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    trade_date TEXT,
                    sector_source TEXT NOT NULL,
                    sector_level TEXT NOT NULL,
                    top_sectors INTEGER DEFAULT 20,
                    top_stocks INTEGER DEFAULT 10,
                    summary_json TEXT,
                    result_json TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_sector_fund_flow_reports_date
                ON sector_fund_flow_reports(created_at DESC);
                """
            )

    def load_members(self, sector_source: str, sector_level: str) -> pd.DataFrame:
        with self.connection() as conn:
            return pd.read_sql_query(
                """
                SELECT sector_source, sector_level, sector_code, sector_name, ts_code, stock_name
                FROM sector_member_cache
                WHERE sector_source = ? AND sector_level = ?
                """,
                conn,
                params=[sector_source, sector_level],
            )

    def replace_members(self, sector_source: str, sector_level: str, rows: Iterable[dict[str, Any]]) -> int:
        row_list = list(rows)
        with self.connection() as conn:
            conn.execute(
                "DELETE FROM sector_member_cache WHERE sector_source = ? AND sector_level = ?",
                (sector_source, sector_level),
            )
            conn.executemany(
                """
                INSERT OR REPLACE INTO sector_member_cache
                (sector_source, sector_level, sector_code, sector_name, ts_code, stock_name, refreshed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        sector_source,
                        sector_level,
                        str(row.get("sector_code", "")),
                        str(row.get("sector_name", "")),
                        str(row.get("ts_code", "")),
                        str(row.get("stock_name", "")),
                        datetime.now().isoformat(timespec="seconds"),
                    )
                    for row in row_list
                    if row.get("sector_code") and row.get("ts_code")
                ],
            )
        return len(row_list)

    def load_daily_sector_flow(self, trade_date: str, sector_source: str, sector_level: str) -> pd.DataFrame:
        with self.connection() as conn:
            return pd.read_sql_query(
                """
                SELECT *
                FROM sector_flow_daily
                WHERE trade_date = ? AND sector_source = ? AND sector_level = ?
                """,
                conn,
                params=[trade_date, sector_source, sector_level],
            )

    def load_daily_stock_flow(self, trade_date: str, sector_source: str, sector_level: str) -> pd.DataFrame:
        with self.connection() as conn:
            return pd.read_sql_query(
                """
                SELECT *
                FROM sector_flow_stock_daily
                WHERE trade_date = ? AND sector_source = ? AND sector_level = ?
                """,
                conn,
                params=[trade_date, sector_source, sector_level],
            )

    def save_daily_flow(self, sector_rows: pd.DataFrame, stock_rows: pd.DataFrame) -> None:
        with self.connection() as conn:
            if sector_rows is not None and not sector_rows.empty:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO sector_flow_daily
                    (trade_date, sector_source, sector_level, sector_code, sector_name,
                     net_mf_amount, main_net_amount, super_large_net_amount, large_net_amount,
                     medium_net_amount, small_net_amount, stock_count, positive_stock_count,
                     negative_stock_count, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            row["trade_date"],
                            row["sector_source"],
                            row["sector_level"],
                            row["sector_code"],
                            row["sector_name"],
                            float(row.get("net_mf_amount", 0) or 0),
                            float(row.get("main_net_amount", 0) or 0),
                            float(row.get("super_large_net_amount", 0) or 0),
                            float(row.get("large_net_amount", 0) or 0),
                            float(row.get("medium_net_amount", 0) or 0),
                            float(row.get("small_net_amount", 0) or 0),
                            int(row.get("stock_count", 0) or 0),
                            int(row.get("positive_stock_count", 0) or 0),
                            int(row.get("negative_stock_count", 0) or 0),
                            datetime.now().isoformat(timespec="seconds"),
                        )
                        for _, row in sector_rows.iterrows()
                    ],
                )

            if stock_rows is not None and not stock_rows.empty:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO sector_flow_stock_daily
                    (trade_date, sector_source, sector_level, sector_code, sector_name,
                     ts_code, stock_name, close, pct_chg, net_mf_amount, main_net_amount,
                     super_large_net_amount, large_net_amount, medium_net_amount,
                     small_net_amount, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            row["trade_date"],
                            row["sector_source"],
                            row["sector_level"],
                            row["sector_code"],
                            row["sector_name"],
                            row["ts_code"],
                            row.get("stock_name", ""),
                            _optional_float(row.get("close")),
                            _optional_float(row.get("pct_chg")),
                            float(row.get("net_mf_amount", 0) or 0),
                            float(row.get("main_net_amount", 0) or 0),
                            float(row.get("super_large_net_amount", 0) or 0),
                            float(row.get("large_net_amount", 0) or 0),
                            float(row.get("medium_net_amount", 0) or 0),
                            float(row.get("small_net_amount", 0) or 0),
                            datetime.now().isoformat(timespec="seconds"),
                        )
                        for _, row in stock_rows.iterrows()
                    ],
                )

    def save_report(self, params: dict[str, Any], result: dict[str, Any]) -> int:
        summary = result.get("summary", {})
        range_info = result.get("range", {})
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO sector_fund_flow_reports
                (report_date, range_type, start_date, end_date, trade_date, sector_source,
                 sector_level, top_sectors, top_stocks, summary_json, result_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().strftime("%Y-%m-%d"),
                    str(params.get("range_type") or range_info.get("type") or ""),
                    str(range_info.get("start_date") or params.get("start_date") or ""),
                    str(range_info.get("end_date") or params.get("end_date") or ""),
                    params.get("trade_date"),
                    str(result.get("sector_source") or params.get("sector_source") or "SW2021"),
                    str(result.get("sector_level") or params.get("sector_level") or "L2"),
                    int(params.get("top_sectors") or 20),
                    int(params.get("top_stocks") or 10),
                    json.dumps(to_jsonable(summary), ensure_ascii=False),
                    json.dumps(to_jsonable(result), ensure_ascii=False),
                ),
            )
            return int(cursor.lastrowid)

    def list_reports(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM sector_fund_flow_reports
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [self._row_to_report(row) for row in rows]

    def get_report(self, report_id: int) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM sector_fund_flow_reports WHERE id = ?",
                (int(report_id),),
            ).fetchone()
        return self._row_to_report(row) if row else None

    def _row_to_report(self, row: sqlite3.Row) -> dict[str, Any]:
        summary = _loads(row["summary_json"], {})
        result = _loads(row["result_json"], {})
        if isinstance(result, dict):
            result.setdefault("report_id", row["id"])
        return {
            "id": row["id"],
            "report_id": row["id"],
            "report_date": row["report_date"],
            "range_type": row["range_type"],
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "trade_date": row["trade_date"],
            "sector_source": row["sector_source"],
            "sector_level": row["sector_level"],
            "top_sectors": row["top_sectors"],
            "top_stocks": row["top_stocks"],
            "summary": summary,
            "result": result,
            "created_at": row["created_at"],
        }


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default
