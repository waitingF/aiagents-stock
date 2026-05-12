"""Update the local full-market stock data store."""

from __future__ import annotations

import argparse

from src.aiagents_stock.integrations.stock_data_store.loader import ensure_stock_data_store_loaded
from src.aiagents_stock.integrations.stock_data_store.service import stock_data_store_service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Update local A-share daily bars and fundamentals.")
    parser.add_argument("--daily", action="store_true", help="Update daily K-line data")
    parser.add_argument("--fundamental", action="store_true", help="Update fundamental datasets")
    parser.add_argument("--all", action="store_true", help="Update daily K-line data and fundamentals")
    parser.add_argument("--symbols", help="Comma-separated symbols, such as 600519.SH,000001.SZ")
    parser.add_argument("--start-date", help="Optional start date, e.g. 2020-01-01")
    parser.add_argument("--end-date", help="Optional end date, default is today")
    parser.add_argument("--limit", type=int, help="Limit the stock universe")
    parser.add_argument("--force", action="store_true", help="Force full refresh")
    parser.add_argument("--refresh-stock-basic", action="store_true", help="Refresh stock_basic before update")
    parser.add_argument("--reset-progress", action="store_true", help="Restart resumable update progress")
    parser.add_argument("--max-workers", type=int, help="Daily update worker threads")
    parser.add_argument("--requests-per-second", type=float, help="Global Tushare request rate limit")
    parser.add_argument("--datasets", help="Fundamental datasets, e.g. daily_basic,fina_indicator,income")
    parser.add_argument("--no-adjustment-detect", action="store_true", help="Disable qfq drift detection")
    parser.add_argument("--adjustment-price-tolerance", type=float, help="Relative qfq drift tolerance")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run_daily = args.all or args.daily or not args.fundamental
    run_fundamental = args.all or args.fundamental

    ensure_stock_data_store_loaded()

    with stock_data_store_service.stock_data_environment():
        if run_daily:
            from stock_data_store.cli import update_daily

            code = update_daily.main(_daily_args(args))
            if code:
                return code

        if run_fundamental:
            from stock_data_store.cli import update_fundamental

            code = update_fundamental.main(_fundamental_args(args))
            if code:
                return code

    return 0


def _daily_args(args: argparse.Namespace) -> list[str]:
    result: list[str] = []
    _append_value(result, "--symbols", args.symbols)
    _append_value(result, "--start-date", args.start_date)
    _append_value(result, "--end-date", args.end_date)
    _append_value(result, "--limit", args.limit)
    _append_flag(result, "--force", args.force)
    _append_flag(result, "--refresh-stock-basic", args.refresh_stock_basic)
    _append_flag(result, "--reset-progress", args.reset_progress)
    _append_value(result, "--max-workers", args.max_workers)
    _append_value(result, "--requests-per-second", args.requests_per_second)
    _append_flag(result, "--no-adjustment-detect", args.no_adjustment_detect)
    _append_value(result, "--adjustment-price-tolerance", args.adjustment_price_tolerance)
    return result


def _fundamental_args(args: argparse.Namespace) -> list[str]:
    result: list[str] = []
    _append_value(result, "--symbols", args.symbols)
    _append_value(result, "--datasets", args.datasets)
    _append_value(result, "--end-date", args.end_date)
    _append_value(result, "--limit", args.limit)
    _append_flag(result, "--force", args.force)
    _append_flag(result, "--refresh-stock-basic", args.refresh_stock_basic)
    _append_flag(result, "--reset-progress", args.reset_progress)
    _append_value(result, "--requests-per-second", args.requests_per_second)
    return result


def _append_flag(target: list[str], flag: str, enabled: bool) -> None:
    if enabled:
        target.append(flag)


def _append_value(target: list[str], flag: str, value) -> None:
    if value is not None:
        target.extend([flag, str(value)])


if __name__ == "__main__":
    raise SystemExit(main())
