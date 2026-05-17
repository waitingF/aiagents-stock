"""HTTP API routes for the React/Vite frontend."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Iterable, Optional

from fastapi import APIRouter, HTTPException

from src.aiagents_stock.api.jobs import job_manager
from src.aiagents_stock.api.serialization import to_jsonable
from src.aiagents_stock.core import config
from src.aiagents_stock.core.parallel import ParallelTask, iter_parallel_results


router = APIRouter(prefix="/api")


PAGES = [
    {"path": "/", "key": "dashboard", "title": "系统总览", "group": "总览"},
    {"path": "/stock-analysis", "key": "stock-analysis", "title": "股票分析", "group": "核心分析"},
    {"path": "/history", "key": "history", "title": "历史记录", "group": "核心分析"},
    {"path": "/main-force", "key": "main-force", "title": "主力选股", "group": "选股板块"},
    {"path": "/low-price-bull", "key": "low-price-bull", "title": "低价擒牛", "group": "选股板块"},
    {"path": "/small-cap", "key": "small-cap", "title": "小市值策略", "group": "选股板块"},
    {"path": "/profit-growth", "key": "profit-growth", "title": "净利增长", "group": "选股板块"},
    {"path": "/value-stock", "key": "value-stock", "title": "低估值策略", "group": "选股板块"},
    {"path": "/sector-strategy", "key": "sector-strategy", "title": "智策板块", "group": "策略研判"},
    {"path": "/dragon-strategy", "key": "dragon-strategy", "title": "龙头战法", "group": "选股板块"},
    {"path": "/longhubang", "key": "longhubang", "title": "智瞰龙虎", "group": "策略研判"},
    {"path": "/news-flow", "key": "news-flow", "title": "新闻流量", "group": "策略研判"},
    {"path": "/macro-analysis", "key": "macro-analysis", "title": "宏观分析", "group": "策略研判"},
    {"path": "/macro-cycle", "key": "macro-cycle", "title": "宏观周期", "group": "策略研判"},
    {"path": "/portfolio", "key": "portfolio", "title": "持仓分析", "group": "投资管理"},
    {"path": "/stock-pool", "key": "stock-pool", "title": "股票池", "group": "投资管理"},
    {"path": "/smart-monitor", "key": "smart-monitor", "title": "智能盯盘", "group": "投资管理"},
    {"path": "/realtime-monitor", "key": "realtime-monitor", "title": "实时监测", "group": "投资管理"},
    {"path": "/settings", "key": "settings", "title": "环境配置", "group": "系统"},
]


def _payload(body: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return body or {}


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes", "on"}


def _float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _job_response(name: str, fn, *args: Any, **kwargs: Any) -> Dict[str, Any]:
    job = job_manager.submit(name, fn, *args, **kwargs)
    return {"job_id": job.id, "job": job.snapshot()}


@router.get("/health")
def health() -> Dict[str, Any]:
    return {"status": "ok", "framework": "fastapi-react"}


@router.get("/pages")
def pages() -> Dict[str, Any]:
    return {"pages": PAGES}


@router.get("/jobs")
def list_jobs() -> Dict[str, Any]:
    return {"jobs": job_manager.list()}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> Dict[str, Any]:
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job.snapshot()


@router.get("/system/status")
def system_status() -> Dict[str, Any]:
    from src.aiagents_stock.features.realtime_monitor.repository import monitor_db
    from src.aiagents_stock.features.realtime_monitor.service import monitor_service
    from src.aiagents_stock.features.stock_analysis.repository import db

    stocks = monitor_db.get_monitored_stocks()
    notifications = monitor_db.get_pending_notifications()
    return to_jsonable(
        {
            "model": config.DEFAULT_MODEL_NAME,
            "api_configured": bool(config.DEEPSEEK_API_KEY),
            "monitor_running": monitor_service.running,
            "analysis_records": db.get_record_count(),
            "monitored_stocks": len(stocks),
            "pending_notifications": len(notifications),
        }
    )


# Stock analysis and history


@router.post("/stock-analysis/parse")
def parse_stock_codes(body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_analysis.service import parse_stock_list

    codes = parse_stock_list(str(_payload(body).get("input", "")))
    return {"codes": codes, "count": len(codes)}


@router.post("/stock-analysis/analyze")
def analyze_stock(body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = _payload(body)
    return _job_response("stock-analysis", _run_stock_analysis, payload)


@router.post("/stock-analysis/batch")
def analyze_batch(body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = _payload(body)
    return _job_response("batch-stock-analysis", _run_batch_stock_analysis, payload)


def _analyst_config(payload: Dict[str, Any]) -> Dict[str, bool]:
    analysts = payload.get("analysts") or {}
    return {
        "technical": _bool(analysts.get("technical"), True),
        "fundamental": _bool(analysts.get("fundamental"), True),
        "fund_flow": _bool(analysts.get("fund_flow"), True),
        "risk": _bool(analysts.get("risk"), True),
        "sentiment": _bool(analysts.get("sentiment"), False),
        "news": _bool(analysts.get("news"), False),
    }


def _run_stock_analysis(payload: Dict[str, Any]) -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_analysis.service import analyze_single_stock_for_batch

    symbol = str(payload.get("symbol", "")).strip()
    if not symbol:
        return {"success": False, "error": "symbol is required"}
    return analyze_single_stock_for_batch(
        symbol=symbol,
        period=str(payload.get("period") or "1y"),
        enabled_analysts_config=_analyst_config(payload),
        selected_model=payload.get("model") or config.DEFAULT_MODEL_NAME,
    )


def _run_batch_stock_analysis(payload: Dict[str, Any]) -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_analysis.service import (
        analyze_single_stock_for_batch,
        parse_stock_list,
    )

    codes = parse_stock_list(str(payload.get("input", "")))
    if not codes:
        return {"success": False, "error": "未填写股票代码", "results": [], "failed": []}
    period = str(payload.get("period") or "1y")
    max_workers = max(1, min(_int(payload.get("max_workers"), 3), 10))
    analysts = _analyst_config(payload)
    model = payload.get("model") or config.DEFAULT_MODEL_NAME
    results = []
    failed = []
    tasks = [
        ParallelTask(
            code,
            analyze_single_stock_for_batch,
            args=(code, period, analysts, model),
        )
        for code in codes
    ]
    for task_result in iter_parallel_results(tasks, max_workers=max_workers):
        code = task_result.key
        if task_result.error is None:
            try:
                result = task_result.value
                if result.get("success"):
                    results.append(result)
                else:
                    failed.append({"code": code, "error": result.get("error", "分析失败")})
            except Exception as exc:
                failed.append({"code": code, "error": str(exc)})
        else:
            failed.append({"code": code, "error": str(task_result.error)})
    return {
        "success": bool(results),
        "total": len(codes),
        "succeeded": len(results),
        "failed_count": len(failed),
        "results": results,
        "failed": failed,
    }


@router.get("/history")
def history_records() -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_analysis.repository import db

    return {"records": to_jsonable(db.get_all_records())}


@router.get("/history/{record_id}")
def history_record(record_id: int) -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_analysis.repository import db

    record = db.get_record_by_id(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    return to_jsonable(record)


@router.delete("/history/{record_id}")
def delete_history_record(record_id: int) -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_analysis.repository import db

    return {"success": db.delete_record(record_id)}


@router.post("/history/{record_id}/monitor")
def add_history_record_to_monitor(record_id: int, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from src.aiagents_stock.features.realtime_monitor.repository import monitor_db
    from src.aiagents_stock.features.stock_analysis.repository import db
    from src.aiagents_stock.features.stock_pool.review import extract_first_price, extract_first_price_range

    payload = _payload(body)
    record = db.get_record_by_id(record_id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    final_decision = record.get("final_decision") or {}
    stock_info = record.get("stock_info") or {}
    entry_min, entry_max = extract_first_price_range(final_decision.get("entry_range", ""))
    take_profit = extract_first_price(final_decision.get("take_profit", ""))
    stop_loss = extract_first_price(final_decision.get("stop_loss", ""))
    entry_min = _float(payload.get("entry_min"), entry_min)
    entry_max = _float(payload.get("entry_max"), entry_max)
    take_profit = _float(payload.get("take_profit"), take_profit)
    stop_loss = _float(payload.get("stop_loss"), stop_loss)
    if None in (entry_min, entry_max, take_profit, stop_loss):
        return {"success": False, "error": "进场区间、止盈和止损不能为空"}
    stock_id = monitor_db.add_monitored_stock(
        symbol=record.get("symbol") or stock_info.get("symbol"),
        name=record.get("stock_name") or stock_info.get("name") or record.get("symbol"),
        rating=final_decision.get("rating", "hold"),
        entry_range={"min": entry_min, "max": entry_max},
        take_profit=take_profit,
        stop_loss=stop_loss,
        check_interval=_int(payload.get("check_interval"), 30),
        notification_enabled=_bool(payload.get("notification_enabled"), True),
        trading_hours_only=_bool(payload.get("trading_hours_only"), True),
    )
    return {"success": True, "stock_id": stock_id}


# Settings


@router.get("/settings")
def settings() -> Dict[str, Any]:
    from src.aiagents_stock.app.pages.settings import config_manager

    return {"config": config_manager.get_config_info()}


@router.post("/settings")
def save_settings(body: Dict[str, Any]) -> Dict[str, Any]:
    from src.aiagents_stock.app.pages.settings import config_manager

    payload = _payload(body)
    values = payload.get("config") or payload
    ok, message = config_manager.validate_config(values)
    if not ok:
        return {"success": False, "message": message}
    saved = config_manager.write_env(values)
    if saved:
        config_manager.reload_config()
    return {"success": saved, "message": "保存成功" if saved else "保存失败"}


@router.post("/settings/test-notification")
def test_notification(body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from src.aiagents_stock.integrations.notification.service import notification_service

    kind = str(_payload(body).get("kind", "webhook"))
    if kind == "email":
        success, message = notification_service.send_test_email()
    else:
        success, message = notification_service.send_test_webhook()
    return {"success": success, "message": message}


# Realtime monitor


@router.get("/monitor")
def monitor_overview() -> Dict[str, Any]:
    from src.aiagents_stock.features.realtime_monitor.repository import monitor_db
    from src.aiagents_stock.features.realtime_monitor.service import monitor_service

    return to_jsonable(
        {
            "running": monitor_service.running,
            "stocks": monitor_db.get_monitored_stocks(),
            "pending_notifications": monitor_db.get_pending_notifications(),
            "recent_notifications": monitor_db.get_all_recent_notifications(limit=20),
        }
    )


@router.post("/monitor/start")
def monitor_start() -> Dict[str, Any]:
    from src.aiagents_stock.features.realtime_monitor.service import monitor_service

    monitor_service.start_monitoring()
    return {"success": True, "running": monitor_service.running}


@router.post("/monitor/stop")
def monitor_stop() -> Dict[str, Any]:
    from src.aiagents_stock.features.realtime_monitor.service import monitor_service

    monitor_service.stop_monitoring()
    return {"success": True, "running": monitor_service.running}


@router.post("/monitor/stocks")
def monitor_add_stock(body: Dict[str, Any]) -> Dict[str, Any]:
    from src.aiagents_stock.features.realtime_monitor.repository import monitor_db

    payload = _payload(body)
    stock_id = monitor_db.add_monitored_stock(
        symbol=str(payload.get("symbol", "")).strip().upper(),
        name=str(payload.get("name") or payload.get("symbol") or "").strip(),
        rating=str(payload.get("rating") or "hold"),
        entry_range={
            "min": _float(payload.get("entry_min"), 0.0),
            "max": _float(payload.get("entry_max"), 0.0),
        },
        take_profit=_float(payload.get("take_profit"), 0.0),
        stop_loss=_float(payload.get("stop_loss"), 0.0),
        check_interval=_int(payload.get("check_interval"), 30),
        notification_enabled=_bool(payload.get("notification_enabled"), True),
        trading_hours_only=_bool(payload.get("trading_hours_only"), True),
        quant_enabled=_bool(payload.get("quant_enabled"), False),
        quant_config=payload.get("quant_config"),
    )
    return {"success": True, "stock_id": stock_id}


@router.put("/monitor/stocks/{stock_id}")
def monitor_update_stock(stock_id: int, body: Dict[str, Any]) -> Dict[str, Any]:
    from src.aiagents_stock.features.realtime_monitor.repository import monitor_db

    payload = _payload(body)
    success = monitor_db.update_monitored_stock(
        stock_id,
        rating=str(payload.get("rating") or "hold"),
        entry_range={
            "min": _float(payload.get("entry_min"), 0.0),
            "max": _float(payload.get("entry_max"), 0.0),
        },
        take_profit=_float(payload.get("take_profit"), 0.0),
        stop_loss=_float(payload.get("stop_loss"), 0.0),
        check_interval=_int(payload.get("check_interval"), 30),
        notification_enabled=_bool(payload.get("notification_enabled"), True),
        trading_hours_only=_bool(payload.get("trading_hours_only"), True),
        quant_enabled=_bool(payload.get("quant_enabled"), False),
        quant_config=payload.get("quant_config"),
    )
    return {"success": success}


@router.delete("/monitor/stocks/{stock_id}")
def monitor_delete_stock(stock_id: int) -> Dict[str, Any]:
    from src.aiagents_stock.features.realtime_monitor.repository import monitor_db

    return {"success": monitor_db.remove_monitored_stock(stock_id)}


@router.post("/monitor/stocks/{stock_id}/update-price")
def monitor_update_price(stock_id: int) -> Dict[str, Any]:
    from src.aiagents_stock.features.realtime_monitor.service import monitor_service

    return {"success": monitor_service.manual_update_stock(stock_id)}


@router.post("/monitor/notifications/mark-read")
def monitor_mark_notifications() -> Dict[str, Any]:
    from src.aiagents_stock.features.realtime_monitor.repository import monitor_db

    return {"success": True, "count": monitor_db.mark_all_notifications_sent()}


@router.delete("/monitor/notifications")
def monitor_clear_notifications() -> Dict[str, Any]:
    from src.aiagents_stock.features.realtime_monitor.repository import monitor_db

    return {"success": True, "count": monitor_db.clear_all_notifications()}


# Stock pools and portfolio


@router.get("/stock-pools")
def stock_pools() -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_pool.manager import stock_pool_manager

    pools = stock_pool_manager.list_pools()
    return {"pools": to_jsonable(pools)}


@router.post("/stock-pools")
def stock_pool_create(body: Dict[str, Any]) -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_pool.manager import stock_pool_manager

    payload = _payload(body)
    success, message, pool_id = stock_pool_manager.create_pool(
        name=str(payload.get("name") or "").strip(),
        description=str(payload.get("description") or ""),
        pool_type=str(payload.get("pool_type") or "custom"),
    )
    return {"success": success, "message": message, "pool_id": pool_id}


@router.put("/stock-pools/{pool_id}")
def stock_pool_update(pool_id: int, body: Dict[str, Any]) -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_pool.manager import stock_pool_manager

    success, message = stock_pool_manager.update_pool(pool_id, **_payload(body))
    return {"success": success, "message": message}


@router.delete("/stock-pools/{pool_id}")
def stock_pool_delete(pool_id: int) -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_pool.manager import stock_pool_manager

    success, message = stock_pool_manager.delete_pool(pool_id)
    return {"success": success, "message": message}


@router.get("/stock-pools/{pool_id}/stocks")
def stock_pool_stocks(pool_id: int) -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_pool.manager import stock_pool_manager

    return {"stocks": to_jsonable(stock_pool_manager.list_stocks(pool_id))}


@router.post("/stock-pools/{pool_id}/stocks")
def stock_pool_add_stock(pool_id: int, body: Dict[str, Any]) -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_pool.manager import stock_pool_manager

    payload = _payload(body)
    success, message, item_id = stock_pool_manager.add_stock(
        pool_id=pool_id,
        code=str(payload.get("code") or "").strip(),
        name=payload.get("name"),
        market=str(payload.get("market") or ""),
        tags=str(payload.get("tags") or ""),
        note=str(payload.get("note") or ""),
        watch_reason=str(payload.get("watch_reason") or ""),
        cost_price=_float(payload.get("cost_price")),
        quantity=_int(payload.get("quantity"), 0) or None,
        target_price=_float(payload.get("target_price")),
        take_profit=_float(payload.get("take_profit")),
        stop_loss=_float(payload.get("stop_loss")),
        auto_monitor=_bool(payload.get("auto_monitor"), False),
    )
    return {"success": success, "message": message, "item_id": item_id}


@router.post("/stock-pools/{pool_id}/batch-import")
def stock_pool_batch_import(pool_id: int, body: Dict[str, Any]) -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_pool.manager import stock_pool_manager

    payload = _payload(body)
    result = stock_pool_manager.batch_import_stocks(
        pool_id=pool_id,
        stock_input=str(payload.get("input") or ""),
        default_tags=str(payload.get("tags") or ""),
    )
    return to_jsonable(result)


@router.put("/stock-pools/stocks/{item_id}")
def stock_pool_update_stock(item_id: int, body: Dict[str, Any]) -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_pool.manager import stock_pool_manager

    success, message = stock_pool_manager.update_stock(item_id, **_payload(body))
    return {"success": success, "message": message}


@router.delete("/stock-pools/stocks/{item_id}")
def stock_pool_remove_stock(item_id: int) -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_pool.manager import stock_pool_manager

    success, message = stock_pool_manager.remove_stock(item_id)
    return {"success": success, "message": message}


@router.post("/stock-pools/analyze")
def stock_pool_analyze(body: Dict[str, Any]) -> Dict[str, Any]:
    payload = _payload(body)
    return _job_response("stock-pool-analysis", _run_stock_pool_analysis, payload)


def _pool_ids(payload: Dict[str, Any]) -> list[int]:
    raw = payload.get("pool_ids") or []
    if isinstance(raw, str):
        raw = [item.strip() for item in raw.split(",") if item.strip()]
    return [int(item) for item in raw]


def _selected_codes(payload: Dict[str, Any]) -> Optional[list[str]]:
    raw = payload.get("selected_codes")
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = [item.strip() for item in raw.replace("，", ",").split(",") if item.strip()]
    elif not isinstance(raw, Iterable):
        raw = [raw]
    return [str(item).strip().upper() for item in raw if str(item).strip()]


def _run_stock_pool_analysis(payload: Dict[str, Any]) -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_pool.manager import stock_pool_manager

    result = stock_pool_manager.batch_analyze_pools(
        pool_ids=_pool_ids(payload),
        scope=str(payload.get("scope") or "today_unanalysed"),
        selected_codes=_selected_codes(payload),
        tag_filter=payload.get("tag_filter"),
        mode=str(payload.get("mode") or "sequential"),
        period=str(payload.get("period") or "1y"),
        selected_agents=payload.get("selected_agents"),
        max_workers=_int(payload.get("max_workers"), 3),
    )
    if result.get("success") and _bool(payload.get("auto_sync_monitor"), False):
        result["sync_result"] = stock_pool_manager.sync_results_to_monitor(result)
    return result


@router.get("/stock-pools/history")
def stock_pool_history(
    pool_id: Optional[int] = None,
    code: Optional[str] = None,
    trading_date: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_pool.manager import stock_pool_manager

    return {
        "records": to_jsonable(
            stock_pool_manager.get_analysis_history(
                pool_id=pool_id,
                code=code,
                trading_date=trading_date,
                limit=limit,
            )
        )
    }


@router.get("/stock-pools/reviews/{pool_id}")
def stock_pool_reviews(pool_id: int, trading_date: Optional[str] = None) -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_pool.manager import stock_pool_manager

    return {"records": to_jsonable(stock_pool_manager.get_daily_reviews(pool_id, trading_date))}


@router.get("/portfolio")
def portfolio() -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_pool.manager import stock_pool_manager

    pool = stock_pool_manager.get_holding_pool()
    return {"pool": to_jsonable(pool), "stocks": to_jsonable(stock_pool_manager.list_stocks(pool["id"]))}


@router.get("/stock-pool-scheduler")
def stock_pool_scheduler_status() -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_pool.scheduler import stock_pool_scheduler

    return to_jsonable(
        {
            "running": stock_pool_scheduler.is_running(),
            "schedule_times": stock_pool_scheduler.get_schedule_times(),
            "analysis_mode": stock_pool_scheduler.analysis_mode,
            "max_workers": stock_pool_scheduler.max_workers,
            "auto_monitor_sync": stock_pool_scheduler.auto_monitor_sync,
            "notification_enabled": stock_pool_scheduler.notification_enabled,
            "scope": stock_pool_scheduler.scope,
            "pool_ids": stock_pool_scheduler.pool_ids,
            "last_run_time": stock_pool_scheduler.last_run_time,
            "next_run_time": stock_pool_scheduler.get_next_run_time(),
        }
    )


@router.post("/stock-pool-scheduler")
def stock_pool_scheduler_configure(body: Dict[str, Any]) -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_pool.scheduler import stock_pool_scheduler

    payload = _payload(body)
    if payload.get("schedule_times"):
        stock_pool_scheduler.set_schedule_times(payload["schedule_times"])
    stock_pool_scheduler.update_config(
        analysis_mode=str(payload.get("analysis_mode") or "sequential"),
        max_workers=_int(payload.get("max_workers"), 3),
        auto_sync_monitor=_bool(payload.get("auto_monitor_sync"), True),
        send_notification=_bool(payload.get("notification_enabled"), True),
        scope=str(payload.get("scope") or "today_unanalysed"),
        pool_ids=payload.get("pool_ids"),
    )
    return {"success": True}


@router.post("/stock-pool-scheduler/start")
def stock_pool_scheduler_start() -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_pool.scheduler import stock_pool_scheduler

    return {"success": stock_pool_scheduler.start_scheduler()}


@router.post("/stock-pool-scheduler/stop")
def stock_pool_scheduler_stop() -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_pool.scheduler import stock_pool_scheduler

    return {"success": stock_pool_scheduler.stop_scheduler()}


@router.post("/stock-pool-scheduler/run")
def stock_pool_scheduler_run() -> Dict[str, Any]:
    from src.aiagents_stock.features.stock_pool.scheduler import stock_pool_scheduler

    return _job_response("stock-pool-scheduled-run", stock_pool_scheduler.run_analysis_now)


# Selectors and strategy pages


@router.post("/selectors/{selector_key}/run")
def selector_run(selector_key: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return _job_response(f"selector-{selector_key}", _run_selector, selector_key, _payload(body))


def _run_selector(selector_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    top_n = _int(payload.get("top_n"), 5)
    if selector_key == "low-price-bull":
        from src.aiagents_stock.features.selectors.low_price_bull.selector import LowPriceBullSelector

        success, frame, message = LowPriceBullSelector().get_low_price_stocks(top_n=top_n)
        return _save_selector_result(selector_key, payload, {"success": success, "message": message, "data": frame})
    if selector_key == "small-cap":
        from src.aiagents_stock.features.selectors.small_cap.selector import SmallCapSelector

        success, frame, message = SmallCapSelector().get_small_cap_stocks(top_n=top_n)
        return _save_selector_result(selector_key, payload, {"success": success, "message": message, "data": frame})
    if selector_key == "profit-growth":
        from src.aiagents_stock.features.selectors.profit_growth.selector import ProfitGrowthSelector

        success, frame, message = ProfitGrowthSelector().get_profit_growth_stocks(top_n=top_n)
        return _save_selector_result(selector_key, payload, {"success": success, "message": message, "data": frame})
    if selector_key == "value-stock":
        from src.aiagents_stock.features.selectors.value_stock.selector import ValueStockSelector

        success, frame, message = ValueStockSelector().get_value_stocks(top_n=top_n)
        return _save_selector_result(selector_key, payload, {"success": success, "message": message, "data": frame})
    if selector_key == "main-force":
        from src.aiagents_stock.features.selectors.main_force.analysis import MainForceAnalyzer

        start_date = payload.get("start_date") or None
        days_ago = None if start_date else _int(payload.get("days_ago"), 90)
        result = MainForceAnalyzer(model=payload.get("model")).run_full_analysis(
            start_date=start_date,
            days_ago=days_ago,
            final_n=_int(payload.get("final_n"), top_n) or None,
            max_range_change=_float(payload.get("max_range_change"), 30.0),
            min_market_cap=_float(payload.get("min_market_cap"), 50.0),
            max_market_cap=_float(payload.get("max_market_cap"), 5000.0),
        )
        return _save_selector_result(selector_key, payload, result)
    raise HTTPException(status_code=404, detail="未知选股策略")


def _save_selector_result(selector_key: str, payload: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from src.aiagents_stock.features.selectors.history_repository import selector_history

        history_id = selector_history.save_result(selector_key, payload, result)
        result["history_id"] = history_id
        result["saved_result"] = {"id": history_id, "selector_key": selector_key}
    except Exception as exc:
        result["persistence_error"] = str(exc)
    return result


@router.get("/selectors/{selector_key}/history")
def selector_history_records(selector_key: str, limit: int = 20) -> Dict[str, Any]:
    from src.aiagents_stock.features.selectors.history_repository import selector_history

    return {"reports": to_jsonable(selector_history.list_results(selector_key=selector_key, limit=limit))}


@router.get("/selectors/{selector_key}/history/{history_id}")
def selector_history_record(selector_key: str, history_id: int) -> Dict[str, Any]:
    from src.aiagents_stock.features.selectors.history_repository import selector_history

    return {"report": to_jsonable(selector_history.get_result(history_id, selector_key=selector_key))}


@router.get("/selectors/low-price-bull/monitor")
def low_price_bull_monitor() -> Dict[str, Any]:
    from src.aiagents_stock.features.selectors.low_price_bull.monitor import LowPriceBullMonitor

    monitor = LowPriceBullMonitor()
    return {
        "stocks": to_jsonable(monitor.get_monitored_stocks()),
        "alerts": to_jsonable(monitor.get_pending_alerts()),
        "history": to_jsonable(monitor.get_history_alerts()),
    }


@router.get("/selectors/profit-growth/monitor")
def profit_growth_monitor() -> Dict[str, Any]:
    from src.aiagents_stock.features.selectors.profit_growth.monitor import ProfitGrowthMonitor

    monitor = ProfitGrowthMonitor()
    return {
        "stocks": to_jsonable(monitor.get_monitoring_stocks()),
        "alerts": to_jsonable(monitor.get_unprocessed_alerts()),
        "history": to_jsonable(monitor.get_all_alerts()),
        "removed": to_jsonable(monitor.get_removed_stocks()),
    }


@router.post("/dragon-strategy/run")
def dragon_strategy_run(body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return _job_response("dragon-strategy", _run_dragon_strategy, _payload(body))


def _run_dragon_strategy(payload: Dict[str, Any]) -> Dict[str, Any]:
    from src.aiagents_stock.features.selectors.dragon_strategy.engine import DragonStrategyEngine

    engine = DragonStrategyEngine()
    action = str(payload.get("action") or "daily_report")
    trade_date = payload.get("date") or None
    if action == "mvp":
        return {"report": engine.run_dragon_mvp(date=trade_date)}
    if action == "sectors":
        report = engine.generate_sector_report(date=trade_date, top_n=_int(payload.get("top_n"), 20))
        return {
            "report": report,
            "signals": [_sector_signal_payload(signal) for signal in report.sectors],
            "diagnostics": engine.last_sector_diagnostics,
        }
    if action == "trends":
        report = engine.generate_trend_report(date=trade_date, top_n=_int(payload.get("top_n"), 20))
        return {"report": report, "candidates": report.trend_tracking}
    if action == "backtest":
        report = engine.generate_backtest_report(date=trade_date)
        return {"report": report, "note": "回测需要历史日线数据，当前已改为生成龙头评分报告。"}
    return {"report": engine.generate_daily_report(date=trade_date)}


def _sector_signal_payload(signal: Any) -> Dict[str, Any]:
    data = signal.to_dict() if hasattr(signal, "to_dict") else dict(signal)
    return {
        "name": data.get("name"),
        "rank": data.get("rank"),
        "pct_chg": data.get("pct_chg"),
        "amount": data.get("amount"),
        "stock_count": data.get("stock_count"),
        "up_stocks": data.get("up_stocks"),
        "limit_up_count": data.get("limit_up_count"),
        "consecutive_days": data.get("consecutive_days"),
        "stage": data.get("stage"),
        "rating": data.get("rating"),
        "action": data.get("action"),
        "status": data.get("status"),
        "raw": data.get("raw", {}),
    }


@router.get("/dragon-strategy/reports")
def dragon_strategy_reports(limit: int = 20) -> Dict[str, Any]:
    from src.aiagents_stock.features.selectors.dragon_strategy.repository import DragonStrategyRepository

    repo = DragonStrategyRepository()
    return {"reports": to_jsonable(repo.list_reports(limit=limit))}


@router.post("/sector-strategy/run")
def sector_strategy_run(body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return _job_response("sector-strategy", _run_sector_strategy, _payload(body))


def _run_sector_strategy(payload: Dict[str, Any]) -> Dict[str, Any]:
    from src.aiagents_stock.features.sector_strategy.data import SectorStrategyDataFetcher
    from src.aiagents_stock.features.sector_strategy.engine import SectorStrategyEngine

    data = SectorStrategyDataFetcher().get_cached_data_with_fallback()
    if not data.get("success"):
        return {"success": False, "error": "获取板块数据失败", "data": data}
    result = SectorStrategyEngine(model=payload.get("model")).run_comprehensive_analysis(data)
    if data.get("from_cache") or data.get("cache_warning"):
        result["cache_meta"] = {
            "from_cache": bool(data.get("from_cache")),
            "cache_warning": data.get("cache_warning", ""),
            "data_timestamp": data.get("timestamp"),
        }
    return result


@router.post("/sector-strategy/fund-flow/run")
def sector_strategy_fund_flow_run(body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return _job_response("sector-strategy-fund-flow", _run_sector_strategy_fund_flow, _payload(body))


def _run_sector_strategy_fund_flow(payload: Dict[str, Any]) -> Dict[str, Any]:
    from src.aiagents_stock.features.sector_strategy.fund_flow import SectorFundFlowAnalyzer

    return SectorFundFlowAnalyzer().analyze(
        range_type=str(payload.get("range_type") or "1m"),
        start_date=payload.get("start_date") or None,
        end_date=payload.get("end_date") or None,
        trade_date=payload.get("trade_date") or None,
        sector_level=str(payload.get("sector_level") or "L2"),
        sector_source=str(payload.get("sector_source") or "SW2021"),
        top_sectors=max(1, min(_int(payload.get("top_sectors"), 20), 100)),
        top_stocks=max(1, min(_int(payload.get("top_stocks"), 10), 50)),
        max_workers=max(1, min(_int(payload.get("max_workers"), 4), 8)),
        force_refresh=_bool(payload.get("force_refresh"), False),
    )


@router.get("/sector-strategy/fund-flow/reports")
def sector_strategy_fund_flow_reports(limit: int = 20) -> Dict[str, Any]:
    from src.aiagents_stock.features.sector_strategy.fund_flow_repository import SectorFundFlowRepository

    return {"reports": to_jsonable(SectorFundFlowRepository().list_reports(limit=limit))}


@router.get("/sector-strategy/fund-flow/reports/{report_id}")
def sector_strategy_fund_flow_report(report_id: int) -> Dict[str, Any]:
    from src.aiagents_stock.features.sector_strategy.fund_flow_repository import SectorFundFlowRepository

    report = SectorFundFlowRepository().get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="报告不存在")
    return {"report": to_jsonable(report)}


@router.get("/sector-strategy/reports")
def sector_strategy_reports(limit: int = 20) -> Dict[str, Any]:
    from src.aiagents_stock.features.sector_strategy.engine import SectorStrategyEngine

    return {"reports": to_jsonable(SectorStrategyEngine().get_historical_reports(limit=limit))}


@router.get("/sector-strategy/reports/{report_id}")
def sector_strategy_report(report_id: int) -> Dict[str, Any]:
    from src.aiagents_stock.features.sector_strategy.engine import SectorStrategyEngine

    return {"report": to_jsonable(SectorStrategyEngine().get_report_detail(report_id))}


@router.delete("/sector-strategy/reports/{report_id}")
def sector_strategy_delete_report(report_id: int) -> Dict[str, Any]:
    from src.aiagents_stock.features.sector_strategy.engine import SectorStrategyEngine

    return {"success": SectorStrategyEngine().delete_report(report_id)}


@router.post("/longhubang/run")
def longhubang_run(body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return _job_response("longhubang", _run_longhubang, _payload(body))


def _run_longhubang(payload: Dict[str, Any]) -> Dict[str, Any]:
    from src.aiagents_stock.features.longhubang.engine import LonghubangEngine

    return LonghubangEngine(model=payload.get("model")).run_comprehensive_analysis(
        date=payload.get("date") or None,
        days=_int(payload.get("days"), 1),
    )


@router.get("/longhubang/reports")
def longhubang_reports(limit: int = 20) -> Dict[str, Any]:
    from src.aiagents_stock.features.longhubang.engine import LonghubangEngine

    return {"reports": to_jsonable(LonghubangEngine().get_historical_reports(limit=limit))}


@router.get("/longhubang/reports/{report_id}")
def longhubang_report(report_id: int) -> Dict[str, Any]:
    from src.aiagents_stock.features.longhubang.engine import LonghubangEngine

    return {"report": to_jsonable(LonghubangEngine().get_report_detail(report_id))}


@router.get("/longhubang/statistics")
def longhubang_statistics() -> Dict[str, Any]:
    from src.aiagents_stock.features.longhubang.engine import LonghubangEngine

    engine = LonghubangEngine()
    return {
        "statistics": to_jsonable(engine.get_statistics()),
        "top_youzi": to_jsonable(engine.get_top_youzi(limit=20)),
        "top_stocks": to_jsonable(engine.get_top_stocks(limit=20)),
    }


@router.post("/news-flow/run")
def news_flow_run(body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return _job_response("news-flow", _run_news_flow, _payload(body))


def _run_news_flow(payload: Dict[str, Any]) -> Dict[str, Any]:
    from src.aiagents_stock.features.news_flow.engine import NewsFlowEngine

    engine = NewsFlowEngine()
    platforms = payload.get("platforms") or None
    category = payload.get("category") or None
    mode = str(payload.get("mode") or "quick")
    if mode == "full":
        return engine.run_full_analysis(platforms=platforms, category=category)
    if mode == "alerts":
        return engine.run_alert_check()
    return engine.run_quick_analysis(platforms=platforms, category=category)


@router.get("/news-flow/dashboard")
def news_flow_dashboard() -> Dict[str, Any]:
    from src.aiagents_stock.features.news_flow.engine import NewsFlowEngine

    engine = NewsFlowEngine()
    return {
        "dashboard": to_jsonable(engine.get_dashboard_data()),
        "trend": to_jsonable(engine.get_flow_trend(days=7)),
    }


@router.post("/macro-analysis/run")
def macro_analysis_run(body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return _job_response("macro-analysis", _run_macro_analysis, _payload(body))


def _run_macro_analysis(payload: Dict[str, Any]) -> Dict[str, Any]:
    from src.aiagents_stock.features.macro_analysis.engine import MacroAnalysisEngine

    return MacroAnalysisEngine(model=payload.get("model")).run_full_analysis()


@router.get("/macro-analysis/reports")
def macro_analysis_reports(limit: int = 20) -> Dict[str, Any]:
    from src.aiagents_stock.features.macro_report_history import macro_report_history

    return {"reports": to_jsonable(macro_report_history.list_reports(module="macro-analysis", limit=limit))}


@router.get("/macro-analysis/reports/{report_id}")
def macro_analysis_report(report_id: int) -> Dict[str, Any]:
    from src.aiagents_stock.features.macro_report_history import macro_report_history

    return {"report": to_jsonable(macro_report_history.get_report(report_id, module="macro-analysis"))}


@router.post("/macro-cycle/run")
def macro_cycle_run(body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return _job_response("macro-cycle", _run_macro_cycle, _payload(body))


def _run_macro_cycle(payload: Dict[str, Any]) -> Dict[str, Any]:
    from src.aiagents_stock.features.macro_cycle.engine import MacroCycleEngine

    return MacroCycleEngine(model=payload.get("model")).run_full_analysis()


@router.get("/macro-cycle/reports")
def macro_cycle_reports(limit: int = 20) -> Dict[str, Any]:
    from src.aiagents_stock.features.macro_report_history import macro_report_history

    return {"reports": to_jsonable(macro_report_history.list_reports(module="macro-cycle", limit=limit))}


@router.get("/macro-cycle/reports/{report_id}")
def macro_cycle_report(report_id: int) -> Dict[str, Any]:
    from src.aiagents_stock.features.macro_report_history import macro_report_history

    return {"report": to_jsonable(macro_report_history.get_report(report_id, module="macro-cycle"))}


@router.post("/smart-monitor/analyze")
def smart_monitor_analyze(body: Dict[str, Any]) -> Dict[str, Any]:
    return _job_response("smart-monitor", _run_smart_monitor, _payload(body))


def _run_smart_monitor(payload: Dict[str, Any]) -> Dict[str, Any]:
    from src.aiagents_stock.features.smart_monitor.engine import SmartMonitorEngine

    return SmartMonitorEngine().analyze_stock(
        stock_code=str(payload.get("stock_code") or "").strip(),
        auto_trade=_bool(payload.get("auto_trade"), False),
        notify=_bool(payload.get("notify"), True),
        has_position=_bool(payload.get("has_position"), False),
        position_cost=_float(payload.get("position_cost"), 0.0) or 0.0,
        position_quantity=_int(payload.get("position_quantity"), 0),
        trading_hours_only=_bool(payload.get("trading_hours_only"), True),
    )


@router.get("/smart-monitor/history")
def smart_monitor_history(limit: int = 50) -> Dict[str, Any]:
    from src.aiagents_stock.features.smart_monitor.repository import SmartMonitorDB

    db = SmartMonitorDB()
    methods = ["get_recent_decisions", "get_decision_history", "get_all_decisions"]
    for method_name in methods:
        method = getattr(db, method_name, None)
        if method:
            return {"records": to_jsonable(method(limit=limit))}
    return {"records": []}
