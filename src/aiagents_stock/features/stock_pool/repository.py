"""SQLite repository for stock pools.

The stock pool module is the unified storage layer for watchlists and holdings.
Legacy portfolio tables are read once for migration, then all business writes go
to the stock_pool_* tables.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

from src.aiagents_stock.core.paths import data_path


DEFAULT_DB_PATH = data_path("stock_pools.db")
LEGACY_PORTFOLIO_DB_PATH = data_path("portfolio_stocks.db")
HOLDING_POOL_NAME = "持仓"
WATCHLIST_POOL_NAME = "自选"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _to_bool(value: Any) -> bool:
    return bool(value) if value is not None else False


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


class StockPoolRepository:
    """Database access for stock pools, pool items, runs, and histories."""

    def __init__(
        self,
        db_path: str | os.PathLike[str] = DEFAULT_DB_PATH,
        legacy_portfolio_db_path: str | os.PathLike[str] = LEGACY_PORTFOLIO_DB_PATH,
        auto_migrate: bool = True,
    ):
        self.db_path = str(db_path)
        self.legacy_portfolio_db_path = str(legacy_portfolio_db_path)
        self._ensure_parent_dir()
        self._init_database()
        self.ensure_system_pools()
        if auto_migrate:
            self.migrate_legacy_portfolio()

    def _ensure_parent_dir(self) -> None:
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    @contextmanager
    def _get_connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    def _init_database(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS stock_pools (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    type TEXT DEFAULT 'custom',
                    description TEXT,
                    is_system BOOLEAN DEFAULT 0,
                    is_default BOOLEAN DEFAULT 0,
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS stock_pool_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pool_id INTEGER NOT NULL,
                    code TEXT NOT NULL,
                    name TEXT NOT NULL,
                    market TEXT,
                    tags TEXT,
                    note TEXT,
                    watch_reason TEXT,
                    cost_price REAL,
                    quantity INTEGER,
                    target_price REAL,
                    take_profit REAL,
                    stop_loss REAL,
                    auto_monitor BOOLEAN DEFAULT 0,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    removed_at TIMESTAMP,
                    FOREIGN KEY (pool_id) REFERENCES stock_pools(id) ON DELETE CASCADE,
                    UNIQUE(pool_id, code)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS stock_pool_analysis_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pool_ids_json TEXT,
                    selected_codes_json TEXT,
                    mode TEXT,
                    status TEXT,
                    total_count INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    failed_count INTEGER DEFAULT 0,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    finished_at TIMESTAMP,
                    error_message TEXT
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS stock_pool_analysis_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER,
                    pool_id INTEGER NOT NULL,
                    pool_item_id INTEGER,
                    code TEXT NOT NULL,
                    name TEXT,
                    trading_date TEXT,
                    analysis_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    rating TEXT,
                    confidence REAL,
                    current_price REAL,
                    target_price REAL,
                    entry_min REAL,
                    entry_max REAL,
                    take_profit REAL,
                    stop_loss REAL,
                    summary TEXT,
                    operation_advice TEXT,
                    holding_period TEXT,
                    position_size TEXT,
                    risk_warning TEXT,
                    final_decision_json TEXT,
                    review_status TEXT,
                    review_summary TEXT,
                    review_json TEXT,
                    FOREIGN KEY (run_id) REFERENCES stock_pool_analysis_runs(id) ON DELETE SET NULL,
                    FOREIGN KEY (pool_id) REFERENCES stock_pools(id) ON DELETE CASCADE,
                    FOREIGN KEY (pool_item_id) REFERENCES stock_pool_items(id) ON DELETE SET NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS stock_pool_migrations (
                    key TEXT PRIMARY KEY,
                    migrated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_pool_items_pool_code
                ON stock_pool_items(pool_id, code)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_pool_history_pool_item_time
                ON stock_pool_analysis_history(pool_id, pool_item_id, analysis_time DESC)
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_pool_history_code_date
                ON stock_pool_analysis_history(code, trading_date)
                """
            )
            conn.commit()

    # ==================== pools ====================

    def ensure_system_pools(self) -> None:
        self.create_pool(
            HOLDING_POOL_NAME,
            pool_type="holding",
            description="系统持仓股票池",
            is_system=True,
            is_default=True,
            sort_order=0,
        )
        self.create_pool(
            WATCHLIST_POOL_NAME,
            pool_type="watchlist",
            description="系统自选股票池",
            is_system=True,
            is_default=True,
            sort_order=1,
        )

    def create_pool(
        self,
        name: str,
        pool_type: str = "custom",
        description: str = "",
        is_system: bool = False,
        is_default: bool = False,
        sort_order: int = 100,
    ) -> int:
        name = name.strip()
        if not name:
            raise ValueError("股票池名称不能为空")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO stock_pools
                (name, type, description, is_system, is_default, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    type = excluded.type,
                    description = COALESCE(NULLIF(excluded.description, ''), stock_pools.description),
                    is_system = CASE WHEN stock_pools.is_system = 1 THEN 1 ELSE excluded.is_system END,
                    is_default = CASE WHEN stock_pools.is_default = 1 THEN 1 ELSE excluded.is_default END,
                    sort_order = MIN(stock_pools.sort_order, excluded.sort_order),
                    updated_at = excluded.updated_at
                """,
                (
                    name,
                    pool_type,
                    description,
                    int(is_system),
                    int(is_default),
                    sort_order,
                    _now(),
                    _now(),
                ),
            )
            conn.commit()
            return self.get_pool_by_name(name)["id"]

    def get_pool_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM stock_pools WHERE name = ?", (name,)).fetchone()
            return dict(row) if row else None

    def get_pool(self, pool_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM stock_pools WHERE id = ?", (pool_id,)).fetchone()
            return dict(row) if row else None

    def get_holding_pool(self) -> Dict[str, Any]:
        pool = self.get_pool_by_name(HOLDING_POOL_NAME)
        if not pool:
            self.ensure_system_pools()
            pool = self.get_pool_by_name(HOLDING_POOL_NAME)
        return pool

    def get_watchlist_pool(self) -> Dict[str, Any]:
        pool = self.get_pool_by_name(WATCHLIST_POOL_NAME)
        if not pool:
            self.ensure_system_pools()
            pool = self.get_pool_by_name(WATCHLIST_POOL_NAME)
        return pool

    def list_pools(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT p.*,
                       COUNT(CASE WHEN i.status = 'active' THEN 1 END) AS active_count
                FROM stock_pools p
                LEFT JOIN stock_pool_items i ON p.id = i.pool_id
                GROUP BY p.id
                ORDER BY p.sort_order ASC, p.created_at ASC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def update_pool(self, pool_id: int, **kwargs: Any) -> bool:
        allowed = {"name", "description", "sort_order", "type"}
        update_fields = {key: value for key, value in kwargs.items() if key in allowed}
        if not update_fields:
            return False

        pool = self.get_pool(pool_id)
        if not pool:
            return False
        if pool.get("is_system") and "name" in update_fields:
            raise ValueError("系统股票池不允许重命名")

        update_fields["updated_at"] = _now()
        clause = ", ".join([f"{key} = ?" for key in update_fields])
        values = list(update_fields.values()) + [pool_id]
        with self._get_connection() as conn:
            cursor = conn.execute(f"UPDATE stock_pools SET {clause} WHERE id = ?", values)
            conn.commit()
            return cursor.rowcount > 0

    def delete_pool(self, pool_id: int) -> bool:
        pool = self.get_pool(pool_id)
        if not pool:
            return False
        if pool.get("is_system"):
            raise ValueError("系统股票池不允许删除")

        with self._get_connection() as conn:
            cursor = conn.execute("DELETE FROM stock_pools WHERE id = ?", (pool_id,))
            conn.commit()
            return cursor.rowcount > 0

    # ==================== items ====================

    def add_item(
        self,
        pool_id: int,
        code: str,
        name: str,
        market: str = "",
        tags: str = "",
        note: str = "",
        watch_reason: str = "",
        cost_price: Optional[float] = None,
        quantity: Optional[int] = None,
        target_price: Optional[float] = None,
        take_profit: Optional[float] = None,
        stop_loss: Optional[float] = None,
        auto_monitor: bool = False,
        created_at: Any = None,
    ) -> int:
        code = code.strip().upper()
        if not code:
            raise ValueError("股票代码不能为空")
        if not name:
            name = code
        created_at = created_at or _now()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO stock_pool_items
                (pool_id, code, name, market, tags, note, watch_reason, cost_price,
                 quantity, target_price, take_profit, stop_loss, auto_monitor, status,
                 created_at, updated_at, removed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, NULL)
                ON CONFLICT(pool_id, code) DO UPDATE SET
                    name = excluded.name,
                    market = excluded.market,
                    tags = COALESCE(NULLIF(excluded.tags, ''), stock_pool_items.tags),
                    note = COALESCE(NULLIF(excluded.note, ''), stock_pool_items.note),
                    watch_reason = COALESCE(NULLIF(excluded.watch_reason, ''), stock_pool_items.watch_reason),
                    cost_price = COALESCE(excluded.cost_price, stock_pool_items.cost_price),
                    quantity = COALESCE(excluded.quantity, stock_pool_items.quantity),
                    target_price = COALESCE(excluded.target_price, stock_pool_items.target_price),
                    take_profit = COALESCE(excluded.take_profit, stock_pool_items.take_profit),
                    stop_loss = COALESCE(excluded.stop_loss, stock_pool_items.stop_loss),
                    auto_monitor = excluded.auto_monitor,
                    status = 'active',
                    updated_at = excluded.updated_at,
                    removed_at = NULL
                """,
                (
                    pool_id,
                    code,
                    name,
                    market,
                    tags,
                    note,
                    watch_reason,
                    cost_price,
                    quantity,
                    target_price,
                    take_profit,
                    stop_loss,
                    int(auto_monitor),
                    created_at,
                    _now(),
                ),
            )
            conn.commit()
            return self.get_item_by_code(pool_id, code)["id"]

    def update_item(self, item_id: int, **kwargs: Any) -> bool:
        allowed = {
            "name",
            "market",
            "tags",
            "note",
            "watch_reason",
            "cost_price",
            "quantity",
            "target_price",
            "take_profit",
            "stop_loss",
            "auto_monitor",
            "status",
        }
        update_fields = {key: value for key, value in kwargs.items() if key in allowed}
        if not update_fields:
            return False

        update_fields["updated_at"] = _now()
        if update_fields.get("status") == "removed":
            update_fields["removed_at"] = _now()

        clause = ", ".join([f"{key} = ?" for key in update_fields])
        values = list(update_fields.values()) + [item_id]
        with self._get_connection() as conn:
            cursor = conn.execute(f"UPDATE stock_pool_items SET {clause} WHERE id = ?", values)
            conn.commit()
            return cursor.rowcount > 0

    def remove_item(self, item_id: int) -> bool:
        return self.update_item(item_id, status="removed")

    def get_item(self, item_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM stock_pool_items WHERE id = ?", (item_id,)).fetchone()
            return dict(row) if row else None

    def get_item_by_code(self, pool_id: int, code: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM stock_pool_items WHERE pool_id = ? AND code = ?",
                (pool_id, code.strip().upper()),
            ).fetchone()
            return dict(row) if row else None

    def list_items(self, pool_id: int, active_only: bool = True) -> List[Dict[str, Any]]:
        where = "WHERE pool_id = ?"
        values: List[Any] = [pool_id]
        if active_only:
            where += " AND status = 'active'"
        with self._get_connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM stock_pool_items {where} ORDER BY created_at DESC",
                values,
            ).fetchall()
            return [dict(row) for row in rows]

    def list_items_for_pools(
        self,
        pool_ids: Iterable[int],
        selected_codes: Optional[Iterable[str]] = None,
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        pool_ids = [int(pool_id) for pool_id in pool_ids]
        if not pool_ids:
            return []

        values: List[Any] = pool_ids
        placeholders = ",".join("?" for _ in pool_ids)
        where = [f"i.pool_id IN ({placeholders})"]
        if active_only:
            where.append("i.status = 'active'")
        if selected_codes is not None:
            codes = [code.strip().upper() for code in selected_codes if code and code.strip()]
            if not codes:
                return []
            where.append(f"i.code IN ({','.join('?' for _ in codes)})")
            values.extend(codes)

        with self._get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT i.*, p.name AS pool_name, p.type AS pool_type
                FROM stock_pool_items i
                JOIN stock_pools p ON i.pool_id = p.id
                WHERE {' AND '.join(where)}
                ORDER BY p.sort_order ASC, i.created_at DESC
                """,
                values,
            ).fetchall()
            return [dict(row) for row in rows]

    def count_items(self, pool_id: int, active_only: bool = True) -> int:
        where = "pool_id = ?"
        if active_only:
            where += " AND status = 'active'"
        with self._get_connection() as conn:
            row = conn.execute(f"SELECT COUNT(*) AS count FROM stock_pool_items WHERE {where}", (pool_id,)).fetchone()
            return int(row["count"])

    # ==================== runs and history ====================

    def create_analysis_run(self, pool_ids: List[int], selected_codes: List[str], mode: str, total_count: int) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO stock_pool_analysis_runs
                (pool_ids_json, selected_codes_json, mode, status, total_count, started_at)
                VALUES (?, ?, ?, 'running', ?, ?)
                """,
                (_json_dumps(pool_ids), _json_dumps(selected_codes), mode, total_count, _now()),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def update_analysis_run(
        self,
        run_id: int,
        status: str,
        success_count: int = 0,
        failed_count: int = 0,
        error_message: str = "",
    ) -> bool:
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                UPDATE stock_pool_analysis_runs
                SET status = ?, success_count = ?, failed_count = ?,
                    error_message = ?, finished_at = ?
                WHERE id = ?
                """,
                (status, success_count, failed_count, error_message, _now(), run_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def save_analysis_history(
        self,
        run_id: Optional[int],
        pool_id: int,
        pool_item_id: Optional[int],
        code: str,
        name: str = "",
        trading_date: Optional[str] = None,
        analysis_time: Any = None,
        rating: str = "",
        confidence: Optional[float] = None,
        current_price: Optional[float] = None,
        target_price: Optional[float] = None,
        entry_min: Optional[float] = None,
        entry_max: Optional[float] = None,
        take_profit: Optional[float] = None,
        stop_loss: Optional[float] = None,
        summary: str = "",
        operation_advice: str = "",
        holding_period: str = "",
        position_size: str = "",
        risk_warning: str = "",
        final_decision_json: str = "",
        review_status: str = "",
        review_summary: str = "",
        review_json: str = "",
    ) -> int:
        analysis_time = analysis_time or _now()
        trading_date = trading_date or date.today().isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO stock_pool_analysis_history
                (run_id, pool_id, pool_item_id, code, name, trading_date, analysis_time,
                 rating, confidence, current_price, target_price, entry_min, entry_max,
                 take_profit, stop_loss, summary, operation_advice, holding_period,
                 position_size, risk_warning, final_decision_json, review_status,
                 review_summary, review_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    pool_id,
                    pool_item_id,
                    code,
                    name,
                    trading_date,
                    analysis_time,
                    rating,
                    confidence,
                    current_price,
                    target_price,
                    entry_min,
                    entry_max,
                    take_profit,
                    stop_loss,
                    summary,
                    operation_advice,
                    holding_period,
                    position_size,
                    risk_warning,
                    final_decision_json,
                    review_status,
                    review_summary,
                    review_json,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def get_latest_analysis(self, pool_id: int, pool_item_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM stock_pool_analysis_history
                WHERE pool_id = ? AND pool_item_id = ?
                ORDER BY analysis_time DESC, id DESC
                LIMIT 1
                """,
                (pool_id, pool_item_id),
            ).fetchone()
            return dict(row) if row else None

    def get_analysis_history(
        self,
        pool_id: Optional[int] = None,
        pool_item_id: Optional[int] = None,
        code: Optional[str] = None,
        trading_date: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        where = []
        values: List[Any] = []
        if pool_id is not None:
            where.append("h.pool_id = ?")
            values.append(pool_id)
        if pool_item_id is not None:
            where.append("h.pool_item_id = ?")
            values.append(pool_item_id)
        if code:
            where.append("h.code = ?")
            values.append(code.strip().upper())
        if trading_date:
            where.append("h.trading_date = ?")
            values.append(trading_date)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        values.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT h.*, p.name AS pool_name, i.note, i.tags
                FROM stock_pool_analysis_history h
                JOIN stock_pools p ON h.pool_id = p.id
                LEFT JOIN stock_pool_items i ON h.pool_item_id = i.id
                {where_sql}
                ORDER BY h.analysis_time DESC, h.id DESC
                LIMIT ?
                """,
                values,
            ).fetchall()
            return [dict(row) for row in rows]

    def get_latest_analysis_by_code_date(self, pool_id: int, code: str, trading_date: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM stock_pool_analysis_history
                WHERE pool_id = ? AND code = ? AND trading_date = ?
                ORDER BY analysis_time DESC, id DESC
                LIMIT 1
                """,
                (pool_id, code.strip().upper(), trading_date),
            ).fetchone()
            return dict(row) if row else None

    def get_latest_daily_reviews(self, pool_id: int, trading_date: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT h.*, p.name AS pool_name
                FROM stock_pool_analysis_history h
                JOIN stock_pools p ON h.pool_id = p.id
                JOIN (
                    SELECT pool_item_id, MAX(analysis_time) AS max_time
                    FROM stock_pool_analysis_history
                    WHERE pool_id = ? AND trading_date = ?
                    GROUP BY pool_item_id
                ) latest
                ON h.pool_item_id = latest.pool_item_id AND h.analysis_time = latest.max_time
                WHERE h.pool_id = ? AND h.trading_date = ?
                ORDER BY h.analysis_time DESC, h.id DESC
                """,
                (pool_id, trading_date, pool_id, trading_date),
            ).fetchall()
            return [dict(row) for row in rows]

    # ==================== migration ====================

    def migrate_legacy_portfolio(self) -> None:
        migration_key = "portfolio_to_stock_pool_v1"
        if self._migration_done(migration_key):
            return
        if not Path(self.legacy_portfolio_db_path).exists():
            self._mark_migration_done(migration_key)
            return

        holding_pool = self.get_holding_pool()
        with sqlite3.connect(self.legacy_portfolio_db_path) as legacy_conn:
            legacy_conn.row_factory = sqlite3.Row
            legacy_cursor = legacy_conn.cursor()
            try:
                legacy_stocks = legacy_cursor.execute("SELECT * FROM portfolio_stocks").fetchall()
            except sqlite3.OperationalError:
                self._mark_migration_done(migration_key)
                return

            legacy_id_to_item: Dict[int, Dict[str, Any]] = {}
            for stock in legacy_stocks:
                item_id = self.add_item(
                    holding_pool["id"],
                    code=stock["code"],
                    name=stock["name"],
                    note=stock["note"] or "",
                    cost_price=stock["cost_price"],
                    quantity=stock["quantity"],
                    auto_monitor=_to_bool(stock["auto_monitor"]),
                    created_at=stock["created_at"] or _now(),
                )
                item = self.get_item(item_id)
                legacy_id_to_item[int(stock["id"])] = item

            try:
                legacy_history = legacy_cursor.execute(
                    "SELECT * FROM portfolio_analysis_history ORDER BY analysis_time ASC, id ASC"
                ).fetchall()
            except sqlite3.OperationalError:
                legacy_history = []

            for record in legacy_history:
                item = legacy_id_to_item.get(int(record["portfolio_stock_id"]))
                if not item:
                    continue
                self.save_analysis_history(
                    run_id=None,
                    pool_id=holding_pool["id"],
                    pool_item_id=item["id"],
                    code=item["code"],
                    name=item["name"],
                    trading_date=str(record["analysis_time"])[:10] if record["analysis_time"] else None,
                    analysis_time=record["analysis_time"] or _now(),
                    rating=record["rating"] or "",
                    confidence=record["confidence"],
                    current_price=record["current_price"],
                    target_price=record["target_price"],
                    entry_min=record["entry_min"],
                    entry_max=record["entry_max"],
                    take_profit=record["take_profit"],
                    stop_loss=record["stop_loss"],
                    summary=record["summary"] or "",
                    operation_advice=self._legacy_col(record, "operation_advice") or "",
                    holding_period=self._legacy_col(record, "holding_period") or "",
                    position_size=self._legacy_col(record, "position_size") or "",
                    risk_warning=self._legacy_col(record, "risk_warning") or "",
                    final_decision_json=self._legacy_col(record, "final_decision_json") or "",
                    review_status=self._legacy_col(record, "review_status") or "",
                    review_summary=self._legacy_col(record, "review_summary") or "",
                    review_json=self._legacy_col(record, "review_json") or "",
                )

        self._mark_migration_done(migration_key)

    def _legacy_col(self, row: sqlite3.Row, column: str) -> Any:
        return row[column] if column in row.keys() else None

    def _migration_done(self, key: str) -> bool:
        with self._get_connection() as conn:
            row = conn.execute("SELECT key FROM stock_pool_migrations WHERE key = ?", (key,)).fetchone()
            return bool(row)

    def _mark_migration_done(self, key: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO stock_pool_migrations(key, migrated_at) VALUES (?, ?)",
                (key, _now()),
            )
            conn.commit()


stock_pool_db = StockPoolRepository()
