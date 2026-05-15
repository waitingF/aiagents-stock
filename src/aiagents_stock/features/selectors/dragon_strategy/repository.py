"""SQLite persistence for dragon strategy reports and state history."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, List, Optional

from src.aiagents_stock.core.paths import data_path
from src.aiagents_stock.features.selectors.dragon_strategy.models import (
    DragonStrategyReport,
    LeaderCandidate,
    SectorSignal,
)


DEFAULT_DB_PATH = data_path("dragon_strategy.db")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _json_loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


class DragonStrategyRepository:
    """Storage for dragon reports, leader history, sector status, and runs."""

    def __init__(self, db_path: str | os.PathLike[str] = DEFAULT_DB_PATH) -> None:
        self.db_path = str(db_path)
        self._memory_connection: sqlite3.Connection | None = None
        self._ensure_parent_dir()
        if self.db_path == ":memory:":
            self._memory_connection = sqlite3.connect(self.db_path)
            self._memory_connection.row_factory = sqlite3.Row
        self._init_database()

    def _ensure_parent_dir(self) -> None:
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    @contextmanager
    def _get_connection(self) -> Iterator[sqlite3.Connection]:
        if self._memory_connection is not None:
            yield self._memory_connection
            return
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = MEMORY")
        conn.execute("PRAGMA synchronous = NORMAL")
        try:
            yield conn
        finally:
            conn.close()

    def _init_database(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS dragon_strategy_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    report_id INTEGER,
                    metadata_json TEXT,
                    error_message TEXT,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    finished_at TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS dragon_strategy_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_date TEXT NOT NULL,
                    report_type TEXT NOT NULL,
                    market_json TEXT NOT NULL,
                    leaders_json TEXT NOT NULL,
                    sectors_json TEXT NOT NULL,
                    trend_rotation_json TEXT NOT NULL,
                    trend_tracking_json TEXT NOT NULL,
                    markdown TEXT,
                    metadata_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS dragon_leader_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_date TEXT NOT NULL,
                    code TEXT NOT NULL,
                    name TEXT,
                    sector TEXT,
                    level TEXT,
                    board_type TEXT,
                    lianban_count INTEGER,
                    first_limit_time TEXT,
                    score REAL,
                    price REAL,
                    stop_loss REAL,
                    targets_json TEXT,
                    reasons_json TEXT,
                    risks_json TEXT,
                    raw_json TEXT,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(trade_date, code)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS dragon_sector_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_date TEXT NOT NULL,
                    name TEXT NOT NULL,
                    rank INTEGER,
                    pct_chg REAL,
                    limit_up_count INTEGER DEFAULT 0,
                    consecutive_days INTEGER DEFAULT 0,
                    stage TEXT,
                    rating INTEGER,
                    action TEXT,
                    status TEXT DEFAULT 'active',
                    amount REAL,
                    stock_count INTEGER,
                    up_stocks INTEGER,
                    raw_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(trade_date, name)
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_dragon_reports_date_type
                ON dragon_strategy_reports(report_date DESC, report_type)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_dragon_leader_code_date
                ON dragon_leader_history(code, trade_date DESC)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_dragon_sector_name_date
                ON dragon_sector_history(name, trade_date DESC)
                """
            )
            conn.commit()

    def create_run(self, run_type: str, metadata: Optional[dict[str, Any]] = None) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO dragon_strategy_runs(run_type, status, metadata_json, started_at)
                VALUES (?, 'running', ?, ?)
                """,
                (run_type, _json_dumps(metadata or {}), _now()),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def finish_run(
        self,
        run_id: int,
        status: str,
        report_id: Optional[int] = None,
        error_message: str = "",
    ) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE dragon_strategy_runs
                SET status = ?, report_id = ?, error_message = ?, finished_at = ?
                WHERE id = ?
                """,
                (status, report_id, error_message, _now(), run_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def save_report(self, report: DragonStrategyReport) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO dragon_strategy_reports
                (report_date, report_type, market_json, leaders_json, sectors_json,
                 trend_rotation_json, trend_tracking_json, markdown, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.report_date,
                    report.report_type,
                    _json_dumps(report.market.to_dict()),
                    _json_dumps([leader.to_dict() for leader in report.leaders]),
                    _json_dumps([sector.to_dict() for sector in report.sectors]),
                    _json_dumps(report.trend_rotation),
                    _json_dumps([item.to_dict() for item in report.trend_tracking]),
                    report.markdown,
                    _json_dumps(report.metadata),
                    _now(),
                ),
            )
            report_id = int(cursor.lastrowid)
            conn.commit()

        self.save_leaders(report.report_date, report.leaders)
        self.save_sector_signals(report.report_date, report.sectors)
        return report_id

    def list_reports(self, limit: int = 20, report_type: Optional[str] = None) -> List[dict[str, Any]]:
        where = ""
        values: list[Any] = []
        if report_type:
            where = "WHERE report_type = ?"
            values.append(report_type)
        values.append(limit)
        with self._get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT id, report_date, report_type, markdown, metadata_json, created_at
                FROM dragon_strategy_reports
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                values,
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["metadata"] = _json_loads(item.pop("metadata_json"), {})
                result.append(item)
            return result

    def get_report(self, report_id: int) -> Optional[dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM dragon_strategy_reports WHERE id = ?", (report_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        for key in [
            "market_json",
            "leaders_json",
            "sectors_json",
            "trend_rotation_json",
            "trend_tracking_json",
            "metadata_json",
        ]:
            item[key.replace("_json", "")] = _json_loads(item.pop(key), {} if key != "leaders_json" else [])
        return item

    def save_leaders(self, trade_date: str, leaders: list[LeaderCandidate]) -> None:
        with self._get_connection() as conn:
            for leader in leaders:
                plan = leader.trade_plan.to_dict() if leader.trade_plan else {}
                conn.execute(
                    """
                    INSERT INTO dragon_leader_history
                    (trade_date, code, name, sector, level, board_type, lianban_count,
                     first_limit_time, score, price, stop_loss, targets_json, reasons_json,
                     risks_json, raw_json, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                    ON CONFLICT(trade_date, code) DO UPDATE SET
                        name = excluded.name,
                        sector = excluded.sector,
                        level = excluded.level,
                        board_type = excluded.board_type,
                        lianban_count = excluded.lianban_count,
                        first_limit_time = excluded.first_limit_time,
                        score = excluded.score,
                        price = excluded.price,
                        stop_loss = excluded.stop_loss,
                        targets_json = excluded.targets_json,
                        reasons_json = excluded.reasons_json,
                        risks_json = excluded.risks_json,
                        raw_json = excluded.raw_json,
                        status = excluded.status,
                        updated_at = excluded.updated_at
                    """,
                    (
                        trade_date,
                        leader.code,
                        leader.name,
                        leader.sector,
                        leader.level,
                        leader.board_type,
                        leader.lianban_count,
                        leader.first_limit_time,
                        leader.score,
                        leader.price,
                        plan.get("stop_loss"),
                        _json_dumps(plan.get("targets", [])),
                        _json_dumps(leader.reasons),
                        _json_dumps(leader.risks),
                        _json_dumps(leader.raw),
                        _now(),
                        _now(),
                    ),
                )
            conn.commit()

    def list_latest_leaders(self, trade_date: Optional[str] = None, limit: int = 50) -> List[dict[str, Any]]:
        where = ""
        values: list[Any] = []
        if trade_date:
            where = "WHERE trade_date = ?"
            values.append(trade_date)
        values.append(limit)
        with self._get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM dragon_leader_history
                {where}
                ORDER BY trade_date DESC, score DESC, lianban_count DESC, id DESC
                LIMIT ?
                """,
                values,
            ).fetchall()
            return [self._decode_history_row(row) for row in rows]

    def get_leader_history(self, code: str, limit: int = 30) -> List[dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM dragon_leader_history
                WHERE code = ?
                ORDER BY trade_date DESC, id DESC
                LIMIT ?
                """,
                (code.strip().upper(), limit),
            ).fetchall()
            return [self._decode_history_row(row) for row in rows]

    def save_sector_signals(self, trade_date: str, signals: list[SectorSignal]) -> None:
        with self._get_connection() as conn:
            for signal in signals:
                conn.execute(
                    """
                    INSERT INTO dragon_sector_history
                    (trade_date, name, rank, pct_chg, limit_up_count, consecutive_days,
                     stage, rating, action, status, amount, stock_count, up_stocks,
                     raw_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(trade_date, name) DO UPDATE SET
                        rank = excluded.rank,
                        pct_chg = excluded.pct_chg,
                        limit_up_count = excluded.limit_up_count,
                        consecutive_days = excluded.consecutive_days,
                        stage = excluded.stage,
                        rating = excluded.rating,
                        action = excluded.action,
                        status = excluded.status,
                        amount = excluded.amount,
                        stock_count = excluded.stock_count,
                        up_stocks = excluded.up_stocks,
                        raw_json = excluded.raw_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        trade_date,
                        signal.name,
                        signal.rank,
                        signal.pct_chg,
                        signal.limit_up_count,
                        signal.consecutive_days,
                        signal.stage,
                        signal.rating,
                        signal.action,
                        signal.status,
                        signal.amount,
                        signal.stock_count,
                        signal.up_stocks,
                        _json_dumps(signal.raw),
                        _now(),
                        _now(),
                    ),
                )
            conn.commit()

    def get_recent_sector_history(
        self,
        limit_days: int = 60,
        name: Optional[str] = None,
    ) -> List[dict[str, Any]]:
        values: list[Any] = [limit_days]
        name_filter = ""
        if name:
            name_filter = "AND name = ?"
            values.append(name)
        with self._get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM dragon_sector_history
                WHERE trade_date IN (
                    SELECT DISTINCT trade_date
                    FROM dragon_sector_history
                    ORDER BY trade_date DESC
                    LIMIT ?
                )
                {name_filter}
                ORDER BY trade_date DESC, COALESCE(rank, 9999) ASC, rating DESC
                """,
                values,
            ).fetchall()
            return [self._decode_history_row(row) for row in rows]

    def _decode_history_row(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        for key in ["targets_json", "reasons_json", "risks_json", "raw_json", "metadata_json"]:
            if key in item:
                item[key.replace("_json", "")] = _json_loads(item.pop(key), [] if key != "raw_json" else {})
        return item


def get_dragon_strategy_repository(db_path: str | os.PathLike[str] = DEFAULT_DB_PATH) -> DragonStrategyRepository:
    return DragonStrategyRepository(db_path)
