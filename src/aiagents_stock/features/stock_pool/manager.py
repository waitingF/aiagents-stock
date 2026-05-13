"""Business logic for stock pools."""

from __future__ import annotations

import csv
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import src.aiagents_stock.core.config as config
from src.aiagents_stock.core.paths import data_path
from src.aiagents_stock.features.stock_analysis.service import (
    analyze_single_stock_for_batch,
    parse_stock_list,
)
from src.aiagents_stock.features.stock_pool import review as pool_review
from src.aiagents_stock.features.stock_pool.repository import (
    HOLDING_POOL_NAME,
    StockPoolRepository,
    stock_pool_db,
)


def _extract_first_price_range(price_text) -> tuple:
    return pool_review.extract_first_price_range(price_text)


def _extract_first_price(price_text):
    return pool_review.extract_first_price(price_text)


def _safe_float(value):
    return pool_review.safe_float(value)


class StockPoolManager:
    """High-level stock pool operations."""

    def __init__(self, repository: StockPoolRepository = stock_pool_db, model: Optional[str] = None):
        self.db = repository
        self.model = model or config.DEFAULT_MODEL_NAME

    # ==================== pools ====================

    def list_pools(self) -> List[Dict[str, Any]]:
        return self.db.list_pools()

    def get_pool(self, pool_id: int) -> Optional[Dict[str, Any]]:
        return self.db.get_pool(pool_id)

    def get_holding_pool(self) -> Dict[str, Any]:
        return self.db.get_holding_pool()

    def create_pool(self, name: str, description: str = "", pool_type: str = "custom") -> Tuple[bool, str, Optional[int]]:
        try:
            pool_id = self.db.create_pool(name, pool_type=pool_type, description=description)
            return True, f"已创建股票池: {name}", pool_id
        except Exception as exc:
            return False, f"创建股票池失败: {exc}", None

    def update_pool(self, pool_id: int, **kwargs: Any) -> Tuple[bool, str]:
        try:
            success = self.db.update_pool(pool_id, **kwargs)
            return (True, "更新成功") if success else (False, "未找到股票池或没有更新内容")
        except Exception as exc:
            return False, f"更新失败: {exc}"

    def delete_pool(self, pool_id: int) -> Tuple[bool, str]:
        try:
            success = self.db.delete_pool(pool_id)
            return (True, "删除成功") if success else (False, "未找到股票池")
        except Exception as exc:
            return False, f"删除失败: {exc}"

    # ==================== items ====================

    def add_stock(
        self,
        pool_id: int,
        code: str,
        name: Optional[str] = None,
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
    ) -> Tuple[bool, str, Optional[int]]:
        try:
            code = code.strip().upper()
            if not code:
                return False, "股票代码不能为空", None
            resolved_name = self._resolve_stock_name(code, name)
            item_id = self.db.add_item(
                pool_id=pool_id,
                code=code,
                name=resolved_name,
                market=market,
                tags=tags,
                note=note,
                watch_reason=watch_reason,
                cost_price=cost_price,
                quantity=quantity,
                target_price=target_price,
                take_profit=take_profit,
                stop_loss=stop_loss,
                auto_monitor=auto_monitor,
            )
            return True, f"已添加 {code}", item_id
        except Exception as exc:
            return False, f"添加失败: {exc}", None

    def batch_import_stocks(self, pool_id: int, stock_input: str, default_tags: str = "") -> Dict[str, Any]:
        codes = parse_stock_list(stock_input)
        added = 0
        failed = []
        for code in codes:
            success, message, _ = self.add_stock(pool_id, code, tags=default_tags)
            if success:
                added += 1
            else:
                failed.append({"code": code, "error": message})
        return {"total": len(codes), "added": added, "failed": failed}

    def _resolve_stock_name(self, code: str, name: Optional[str]) -> str:
        """Resolve stock name without fetching quotes or historical bars."""
        provided_name = (name or "").strip()
        if provided_name and provided_name.upper() != code.upper() and provided_name != "未知":
            return provided_name

        resolved = self._resolve_name_from_static_sources(code)
        if resolved:
            return resolved

        return provided_name or code

    def _resolve_name_from_static_sources(self, code: str) -> Optional[str]:
        market = self._detect_market(code)
        resolvers = []
        if market == "a_share":
            resolvers = [
                self._resolve_name_from_local_stock_basic,
                self._resolve_a_share_name_from_tushare_stock_basic,
                self._resolve_a_share_name_from_akshare_code_name,
            ]
        elif market == "hk":
            resolvers = [
                self._resolve_hk_name_from_tushare_hk_basic,
            ]

        for resolver in resolvers:
            try:
                resolved = resolver(code)
            except Exception:
                resolved = None
            if resolved:
                return resolved
        return None

    def _detect_market(self, code: str) -> str:
        normalized = code.strip().upper()
        raw_code, suffix = self._split_code_suffix(normalized)
        if suffix in {"SH", "SZ", "BJ"}:
            return "a_share"
        if suffix == "HK" or normalized.startswith("HK"):
            return "hk"
        if raw_code.isdigit() and len(raw_code) == 6:
            return "a_share"
        if raw_code.isdigit() and 1 <= len(raw_code) <= 5:
            return "hk"
        return "unknown"

    def _split_code_suffix(self, code: str) -> Tuple[str, str]:
        normalized = code.strip().upper()
        if "." not in normalized:
            return normalized[2:] if normalized.startswith("HK") else normalized, "HK" if normalized.startswith("HK") else ""

        raw_code, suffix = normalized.rsplit(".", 1)
        return raw_code, suffix

    def _to_a_share_ts_code(self, code: str) -> str:
        raw_code, suffix = self._split_code_suffix(code)
        if suffix in {"SH", "SZ", "BJ"}:
            return f"{raw_code}.{suffix}"
        if raw_code.startswith("6"):
            return f"{raw_code}.SH"
        if raw_code.startswith(("0", "3")):
            return f"{raw_code}.SZ"
        if raw_code.startswith(("4", "8")):
            return f"{raw_code}.BJ"
        return raw_code

    def _resolve_name_from_local_stock_basic(self, code: str) -> Optional[str]:
        stock_basic_path = Path(data_path("stock_data/meta/stock_basic.csv"))
        if not stock_basic_path.exists():
            return None

        raw_code, _ = self._split_code_suffix(code)
        ts_code = self._to_a_share_ts_code(code)
        with stock_basic_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row.get("ts_code") == ts_code or row.get("symbol") == raw_code:
                    name = (row.get("name") or "").strip()
                    return name or None
        return None

    def _resolve_a_share_name_from_tushare_stock_basic(self, code: str) -> Optional[str]:
        token = os.getenv("TUSHARE_TOKEN", "")
        if not token:
            return None

        import tushare as ts

        ts_code = self._to_a_share_ts_code(code)
        pro = ts.pro_api(token)
        df = pro.stock_basic(ts_code=ts_code, fields="ts_code,name")
        if df is not None and not df.empty:
            return str(df.iloc[0].get("name") or "").strip() or None
        return None

    def _resolve_a_share_name_from_akshare_code_name(self, code: str) -> Optional[str]:
        import akshare as ak

        raw_code, _ = self._split_code_suffix(code)
        df = ak.stock_info_a_code_name()
        if df is None or df.empty:
            return None

        code_col = "code" if "code" in df.columns else "证券代码" if "证券代码" in df.columns else None
        name_col = "name" if "name" in df.columns else "证券简称" if "证券简称" in df.columns else None
        if not code_col or not name_col:
            return None

        matched = df[df[code_col].astype(str).str.zfill(6) == raw_code]
        if matched.empty:
            return None
        return str(matched.iloc[0].get(name_col) or "").strip() or None

    def _resolve_hk_name_from_tushare_hk_basic(self, code: str) -> Optional[str]:
        token = os.getenv("TUSHARE_TOKEN", "")
        if not token:
            return None

        import tushare as ts

        raw_code, _ = self._split_code_suffix(code)
        hk_code = raw_code.zfill(5)
        ts_code = f"{hk_code}.HK"
        pro = ts.pro_api(token)
        if not hasattr(pro, "hk_basic"):
            return None
        df = pro.hk_basic(ts_code=ts_code, fields="ts_code,name")
        if df is not None and not df.empty:
            return str(df.iloc[0].get("name") or "").strip() or None
        return None

    def update_stock(self, item_id: int, **kwargs: Any) -> Tuple[bool, str]:
        try:
            success = self.db.update_item(item_id, **kwargs)
            return (True, "更新成功") if success else (False, "未找到股票或没有更新内容")
        except Exception as exc:
            return False, f"更新失败: {exc}"

    def remove_stock(self, item_id: int) -> Tuple[bool, str]:
        try:
            success = self.db.remove_item(item_id)
            return (True, "移除成功") if success else (False, "未找到股票")
        except Exception as exc:
            return False, f"移除失败: {exc}"

    def list_stocks(self, pool_id: int, active_only: bool = True) -> List[Dict[str, Any]]:
        return self.db.list_items(pool_id, active_only=active_only)

    def copy_stock_to_pool(self, item_id: int, target_pool_id: int) -> Tuple[bool, str, Optional[int]]:
        item = self.db.get_item(item_id)
        if not item:
            return False, "未找到股票", None
        return self.add_stock(
            target_pool_id,
            code=item["code"],
            name=item["name"],
            market=item.get("market") or "",
            tags=item.get("tags") or "",
            note=item.get("note") or "",
            watch_reason=item.get("watch_reason") or "",
            cost_price=item.get("cost_price"),
            quantity=item.get("quantity"),
            target_price=item.get("target_price"),
            take_profit=item.get("take_profit"),
            stop_loss=item.get("stop_loss"),
            auto_monitor=bool(item.get("auto_monitor")),
        )

    def move_stock_to_pool(self, item_id: int, target_pool_id: int) -> Tuple[bool, str, Optional[int]]:
        success, message, new_item_id = self.copy_stock_to_pool(item_id, target_pool_id)
        if not success:
            return success, message, new_item_id
        self.remove_stock(item_id)
        return True, "移动成功", new_item_id

    # ==================== analysis targets ====================

    def build_analysis_targets(
        self,
        pool_ids: Iterable[int],
        scope: str = "today_unanalysed",
        selected_codes: Optional[Iterable[str]] = None,
        tag_filter: Optional[str] = None,
        trading_date: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        trading_date = trading_date or date.today().isoformat()
        items = self.db.list_items_for_pools(pool_ids, selected_codes=selected_codes)
        targets: Dict[str, List[Dict[str, Any]]] = {}
        tag_filter = (tag_filter or "").strip()

        for item in items:
            if tag_filter and tag_filter not in (item.get("tags") or ""):
                continue
            if scope == "today_unanalysed":
                latest_today = self.db.get_latest_analysis_by_code_date(
                    item["pool_id"], item["code"], trading_date
                )
                if latest_today:
                    continue
            code = item["code"]
            targets.setdefault(code, []).append(item)

        return targets

    # ==================== analysis execution ====================

    def analyze_single_stock(
        self,
        stock_code: str,
        period: str = "1y",
        selected_agents: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        enabled_analysts_config = self._build_enabled_analysts(selected_agents)
        return analyze_single_stock_for_batch(
            symbol=stock_code,
            period=period,
            enabled_analysts_config=enabled_analysts_config,
            selected_model=self.model,
        )

    def batch_analyze_pools(
        self,
        pool_ids: Iterable[int],
        scope: str = "today_unanalysed",
        selected_codes: Optional[Iterable[str]] = None,
        tag_filter: Optional[str] = None,
        mode: str = "sequential",
        period: str = "1y",
        selected_agents: Optional[List[str]] = None,
        max_workers: int = 3,
        progress_callback=None,
    ) -> Dict[str, Any]:
        pool_ids = [int(pool_id) for pool_id in pool_ids]
        targets = self.build_analysis_targets(
            pool_ids,
            scope=scope,
            selected_codes=selected_codes,
            tag_filter=tag_filter,
        )
        codes = list(targets.keys())
        if not codes:
            return {"success": False, "error": "没有选择可分析的股票", "results": [], "failed_stocks": []}

        run_id = self.db.create_analysis_run(pool_ids, codes, mode, len(codes))
        start_time = time.time()
        results: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []

        if mode == "parallel":
            results, failed = self._batch_analyze_parallel(
                codes,
                targets,
                period,
                selected_agents,
                max_workers,
                progress_callback,
            )
        else:
            results, failed = self._batch_analyze_sequential(
                codes,
                targets,
                period,
                selected_agents,
                progress_callback,
            )

        elapsed_time = time.time() - start_time
        succeeded = len(results)
        failed_count = len(failed)
        status = "success" if failed_count == 0 else ("partial_failed" if succeeded else "failed")
        self.db.update_analysis_run(run_id, status, succeeded, failed_count)

        response = {
            "success": True,
            "mode": mode,
            "run_id": run_id,
            "total": len(codes),
            "succeeded": succeeded,
            "failed": failed_count,
            "results": results,
            "failed_stocks": failed,
            "elapsed_time": elapsed_time,
        }
        saved_ids = self.save_analysis_results(response)
        response["saved_ids"] = saved_ids
        return response

    def _batch_analyze_sequential(
        self,
        codes: List[str],
        targets: Dict[str, List[Dict[str, Any]]],
        period: str,
        selected_agents: Optional[List[str]],
        progress_callback=None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        results = []
        failed = []
        total = len(codes)
        for index, code in enumerate(codes, 1):
            if progress_callback:
                progress_callback(index, total, code, "analyzing")
            try:
                result = self.analyze_single_stock(code, period, selected_agents)
                if result.get("success"):
                    results.append({"code": code, "result": result, "pool_items": targets[code]})
                    if progress_callback:
                        progress_callback(index, total, code, "success")
                else:
                    failed.append({"code": code, "error": result.get("error", "未知错误")})
                    if progress_callback:
                        progress_callback(index, total, code, "failed")
            except Exception as exc:
                failed.append({"code": code, "error": str(exc)})
                if progress_callback:
                    progress_callback(index, total, code, "error")
        return results, failed

    def _batch_analyze_parallel(
        self,
        codes: List[str],
        targets: Dict[str, List[Dict[str, Any]]],
        period: str,
        selected_agents: Optional[List[str]],
        max_workers: int,
        progress_callback=None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        results = []
        failed = []
        completed = 0
        total = len(codes)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_code = {
                executor.submit(self.analyze_single_stock, code, period, selected_agents): code
                for code in codes
            }
            for future in as_completed(future_to_code):
                code = future_to_code[future]
                completed += 1
                try:
                    result = future.result()
                    if result.get("success"):
                        results.append({"code": code, "result": result, "pool_items": targets[code]})
                        status = "success"
                    else:
                        failed.append({"code": code, "error": result.get("error", "未知错误")})
                        status = "failed"
                except Exception as exc:
                    failed.append({"code": code, "error": str(exc)})
                    status = "error"
                if progress_callback:
                    progress_callback(completed, total, code, status)
        return results, failed

    def _build_enabled_analysts(self, selected_agents: Optional[List[str]]) -> Dict[str, bool]:
        if selected_agents is None:
            return {
                "technical": True,
                "fundamental": True,
                "fund_flow": True,
                "risk": True,
                "sentiment": False,
                "news": False,
            }
        return {
            "technical": "technical" in selected_agents,
            "fundamental": "fundamental" in selected_agents,
            "fund_flow": "fund_flow" in selected_agents,
            "risk": "risk" in selected_agents,
            "sentiment": "sentiment" in selected_agents,
            "news": "news" in selected_agents,
        }

    # ==================== result persistence ====================

    def save_analysis_results(self, analysis_results: Dict[str, Any]) -> List[int]:
        saved_ids: List[int] = []
        if not analysis_results.get("success"):
            return saved_ids

        run_id = analysis_results.get("run_id")
        for item in analysis_results.get("results", []):
            result = item.get("result", {})
            if not result.get("success"):
                continue

            final_decision = result.get("final_decision", {})
            stock_info = result.get("stock_info", {})
            current_record = self._build_current_record(final_decision, stock_info)
            final_decision_json = json.dumps(final_decision, ensure_ascii=False, default=str)

            first_review = {}
            for pool_item in item.get("pool_items", []):
                previous = self.db.get_latest_analysis(pool_item["pool_id"], pool_item["id"])
                review = pool_review.build_pool_review(previous, current_record, pool_item, final_decision)
                if not first_review:
                    first_review = review
                review_json = json.dumps(review, ensure_ascii=False, default=str)
                history_id = self.db.save_analysis_history(
                    run_id=run_id,
                    pool_id=pool_item["pool_id"],
                    pool_item_id=pool_item["id"],
                    code=pool_item["code"],
                    name=stock_info.get("name", pool_item.get("name", "")),
                    rating=current_record["rating"],
                    confidence=current_record["confidence"],
                    current_price=current_record["current_price"],
                    target_price=current_record["target_price"],
                    entry_min=current_record["entry_min"],
                    entry_max=current_record["entry_max"],
                    take_profit=current_record["take_profit"],
                    stop_loss=current_record["stop_loss"],
                    summary=current_record["summary"],
                    operation_advice=current_record["operation_advice"],
                    holding_period=current_record["holding_period"],
                    position_size=current_record["position_size"],
                    risk_warning=current_record["risk_warning"],
                    final_decision_json=final_decision_json,
                    review_status=review.get("review_status", ""),
                    review_summary=review.get("review_summary", ""),
                    review_json=review_json,
                )
                saved_ids.append(history_id)

            result["pool_review"] = first_review
            result["portfolio_review"] = first_review

        return saved_ids

    def _build_current_record(self, final_decision: Dict[str, Any], stock_info: Dict[str, Any]) -> Dict[str, Any]:
        rating = final_decision.get("rating", "持有")
        confidence = self._safe_confidence(final_decision.get("confidence_level", 5.0))
        current_price = _safe_float(stock_info.get("current_price", 0.0)) or 0.0
        target_price = _extract_first_price(final_decision.get("target_price", ""))
        entry_min, entry_max = _extract_first_price_range(final_decision.get("entry_range", ""))
        take_profit = _extract_first_price(final_decision.get("take_profit", ""))
        stop_loss = _extract_first_price(final_decision.get("stop_loss", ""))
        operation_advice = final_decision.get(
            "operation_advice",
            final_decision.get("advice", final_decision.get("summary", "")),
        )
        return {
            "rating": rating,
            "confidence": confidence,
            "current_price": current_price,
            "target_price": target_price,
            "entry_min": entry_min,
            "entry_max": entry_max,
            "take_profit": take_profit,
            "stop_loss": stop_loss,
            "summary": operation_advice[:500] if operation_advice else "",
            "operation_advice": operation_advice or "",
            "holding_period": final_decision.get("holding_period", ""),
            "position_size": final_decision.get("position_size", ""),
            "risk_warning": final_decision.get("risk_warning", ""),
        }

    def _safe_confidence(self, value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            confidence = 5.0
        return max(0.0, min(10.0, confidence))

    # ==================== histories and summaries ====================

    def get_analysis_history(
        self,
        pool_id: Optional[int] = None,
        pool_item_id: Optional[int] = None,
        code: Optional[str] = None,
        trading_date: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        return self.db.get_analysis_history(pool_id, pool_item_id, code, trading_date, limit)

    def get_latest_analysis(self, pool_id: int, pool_item_id: int) -> Optional[Dict[str, Any]]:
        return self.db.get_latest_analysis(pool_id, pool_item_id)

    def get_daily_reviews(self, pool_id: int, trading_date: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.db.get_latest_daily_reviews(pool_id, trading_date or date.today().isoformat())

    def sync_results_to_monitor(self, analysis_results: Dict[str, Any], holding_first: bool = True) -> Dict[str, int]:
        from src.aiagents_stock.features.realtime_monitor.repository import monitor_db

        monitors_by_code: Dict[str, Dict[str, Any]] = {}
        for item in analysis_results.get("results", []):
            result = item.get("result", {})
            if not result.get("success"):
                continue
            final_decision = result.get("final_decision", {})
            stock_info = result.get("stock_info", {})
            entry_min, entry_max = _extract_first_price_range(final_decision.get("entry_range", ""))
            take_profit = _extract_first_price(final_decision.get("take_profit", ""))
            stop_loss = _extract_first_price(final_decision.get("stop_loss", ""))
            if not all([entry_min, entry_max, take_profit, stop_loss]):
                continue

            for pool_item in item.get("pool_items", []):
                if not pool_item.get("auto_monitor"):
                    continue
                code = pool_item["code"]
                candidate = {
                    "code": code,
                    "name": stock_info.get("name", pool_item.get("name", "")),
                    "rating": final_decision.get("rating", "持有"),
                    "entry_min": entry_min,
                    "entry_max": entry_max,
                    "take_profit": take_profit,
                    "stop_loss": stop_loss,
                    "pool_name": pool_item.get("pool_name", ""),
                }
                existing = monitors_by_code.get(code)
                if not existing:
                    monitors_by_code[code] = candidate
                elif holding_first and pool_item.get("pool_name") == HOLDING_POOL_NAME:
                    monitors_by_code[code] = candidate

        if not monitors_by_code:
            return {"added": 0, "updated": 0, "failed": 0, "total": 0}
        return monitor_db.batch_add_or_update_monitors(list(monitors_by_code.values()))


stock_pool_manager = StockPoolManager()
