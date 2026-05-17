"""Deterministic sector fund-flow aggregation based on Tushare 2000-point APIs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from src.aiagents_stock.core.parallel import ParallelTask, iter_parallel_results
from src.aiagents_stock.features.sector_strategy.fund_flow_repository import SectorFundFlowRepository


RANGE_DAYS = {
    "1w": 7,
    "2w": 14,
    "1m": 30,
    "2m": 60,
    "3m": 90,
}

RANGE_LABELS = {
    "1w": "最近一周",
    "2w": "最近两周",
    "1m": "最近一月",
    "2m": "最近两月",
    "3m": "最近三月",
    "day": "某天",
    "custom": "自定义区间",
}

LEVEL_CODE_COLUMNS = {"L1": "l1_code", "L2": "l2_code", "L3": "l3_code"}
LEVEL_NAME_COLUMNS = {"L1": "l1_name", "L2": "l2_name", "L3": "l3_name"}
CLASSIFY_LEVEL_NAMES = {"L1": "申万一级行业", "L2": "申万二级行业", "L3": "申万三级行业"}

AMOUNT_COLUMNS = [
    "net_mf_amount",
    "main_net_amount",
    "super_large_net_amount",
    "large_net_amount",
    "medium_net_amount",
    "small_net_amount",
]


@dataclass
class DateWindow:
    range_type: str
    start_date: str
    end_date: str
    trade_date: str | None = None


class SectorFundFlowAnalyzer:
    """Aggregate stock-level moneyflow into SW industry sector fund-flow reports."""

    def __init__(
        self,
        tushare_api: Any | None = None,
        repository: SectorFundFlowRepository | None = None,
        today_provider: Any | None = None,
    ) -> None:
        self.repository = repository or SectorFundFlowRepository()
        self.tushare_api = tushare_api
        self.today_provider = today_provider or (lambda: datetime.now().strftime("%Y%m%d"))

    def analyze(
        self,
        range_type: str = "1m",
        start_date: str | None = None,
        end_date: str | None = None,
        trade_date: str | None = None,
        sector_level: str = "L2",
        sector_source: str = "SW2021",
        top_sectors: int = 20,
        top_stocks: int = 10,
        max_workers: int = 4,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """Build and persist a non-AI sector fund-flow report."""
        api = self._get_api()
        if api is None:
            return {
                "success": False,
                "error": "未配置可用的 Tushare Token，无法获取板块资金流数据",
            }

        try:
            sector_level = _normalize_level(sector_level)
            window = self._resolve_window(range_type, start_date, end_date, trade_date)
            trade_dates = self._resolve_trade_dates(api, window.start_date, window.end_date)
            members = self._load_or_fetch_members(
                api=api,
                sector_source=sector_source,
                sector_level=sector_level,
                max_workers=max_workers,
                force_refresh=force_refresh,
            )

            if members.empty:
                return {"success": False, "error": "未获取到申万行业成分股数据"}
            if not trade_dates:
                return {
                    "success": False,
                    "error": "所选时间范围内未找到交易日",
                    "range": self._range_payload(window, []),
                }

            daily_frames, stock_frames, diagnostics = self._load_or_fetch_daily_flows(
                api=api,
                trade_dates=trade_dates,
                members=members,
                sector_source=sector_source,
                sector_level=sector_level,
                max_workers=max_workers,
                force_refresh=force_refresh,
            )

            result = self._build_report(
                window=window,
                trade_dates=trade_dates,
                sector_source=sector_source,
                sector_level=sector_level,
                top_sectors=max(1, int(top_sectors or 20)),
                top_stocks=max(1, int(top_stocks or 10)),
                sector_frames=daily_frames,
                stock_frames=stock_frames,
                diagnostics={**diagnostics, "member_count": int(len(members))},
            )
            if result.get("success"):
                result["report_id"] = self.repository.save_report(
                    {
                        "range_type": window.range_type,
                        "start_date": window.start_date,
                        "end_date": window.end_date,
                        "trade_date": window.trade_date,
                        "sector_source": sector_source,
                        "sector_level": sector_level,
                        "top_sectors": int(top_sectors or 20),
                        "top_stocks": int(top_stocks or 10),
                    },
                    result,
                )
            return result
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _get_api(self) -> Any | None:
        if self.tushare_api is not None:
            return self.tushare_api
        try:
            from src.aiagents_stock.integrations.market_data.providers import data_source_manager

            if data_source_manager.tushare_available:
                return data_source_manager.tushare_api
        except Exception:
            return None
        return None

    def _resolve_window(
        self,
        range_type: str,
        start_date: str | None,
        end_date: str | None,
        trade_date: str | None,
    ) -> DateWindow:
        normalized_type = str(range_type or "1m").strip().lower()
        today = _normalize_date(end_date or self.today_provider())

        if normalized_type in RANGE_DAYS:
            start = (datetime.strptime(today, "%Y%m%d") - timedelta(days=RANGE_DAYS[normalized_type])).strftime("%Y%m%d")
            return DateWindow(normalized_type, start, today)

        if normalized_type == "day":
            day = _normalize_date(trade_date or start_date or end_date or self.today_provider())
            return DateWindow("day", day, day, day)

        if normalized_type == "custom":
            if not start_date or not end_date:
                raise ValueError("自定义区间需要同时提供 start_date 和 end_date")
            start = _normalize_date(start_date)
            end = _normalize_date(end_date)
            if start > end:
                raise ValueError("start_date 不能晚于 end_date")
            return DateWindow("custom", start, end)

        raise ValueError(f"不支持的时间范围: {range_type}")

    def _resolve_trade_dates(self, api: Any, start_date: str, end_date: str) -> list[str]:
        try:
            df = api.trade_cal(
                exchange="",
                start_date=start_date,
                end_date=end_date,
                is_open="1",
                fields="cal_date,is_open",
            )
            if df is not None and not df.empty and "cal_date" in df.columns:
                dates = [str(item) for item in df["cal_date"].dropna().tolist()]
                return sorted(set(dates))
        except Exception:
            pass

        start = datetime.strptime(start_date, "%Y%m%d")
        end = datetime.strptime(end_date, "%Y%m%d")
        dates = []
        current = start
        while current <= end:
            if current.weekday() < 5:
                dates.append(current.strftime("%Y%m%d"))
            current += timedelta(days=1)
        return dates

    def _load_or_fetch_members(
        self,
        api: Any,
        sector_source: str,
        sector_level: str,
        max_workers: int,
        force_refresh: bool,
    ) -> pd.DataFrame:
        if not force_refresh:
            cached = self.repository.load_members(sector_source, sector_level)
            if cached is not None and not cached.empty:
                return cached

        sectors = self._fetch_sector_classify(api, sector_source, sector_level)
        if not sectors:
            return pd.DataFrame()

        rows: list[dict[str, Any]] = []
        tasks = [
            ParallelTask(
                sector["sector_code"],
                self._fetch_sector_members,
                args=(api, sector, sector_level),
            )
            for sector in sectors
        ]
        for task_result in iter_parallel_results(tasks, max_workers=max(1, min(int(max_workers or 4), 8))):
            if task_result.error is None and task_result.value:
                rows.extend(task_result.value)

        self.repository.replace_members(sector_source, sector_level, rows)
        return self.repository.load_members(sector_source, sector_level)

    def _fetch_sector_classify(self, api: Any, sector_source: str, sector_level: str) -> list[dict[str, str]]:
        df = api.index_classify(level=sector_level, src=sector_source)
        if df is None or df.empty:
            return []

        sectors = []
        for _, row in df.iterrows():
            is_pub = str(row.get("is_pub", "1"))
            if is_pub not in {"1", "Y", "True", "true", "nan"}:
                continue
            code = str(row.get("index_code") or row.get("industry_code") or "").strip()
            name = str(row.get("industry_name") or "").strip()
            if code and name:
                sectors.append({"sector_code": _strip_si(code), "sector_name": name})
        return sectors

    def _fetch_sector_members(self, api: Any, sector: dict[str, str], sector_level: str) -> list[dict[str, Any]]:
        code_param = LEVEL_CODE_COLUMNS[sector_level]
        kwargs = {code_param: _with_si(sector["sector_code"]), "is_new": "Y"}
        df = api.index_member_all(**kwargs)
        if df is None or df.empty:
            return []

        rows = []
        for _, row in df.iterrows():
            ts_code = str(row.get("ts_code") or "").strip()
            if not ts_code:
                continue
            rows.append(
                {
                    "sector_code": sector["sector_code"],
                    "sector_name": str(row.get(LEVEL_NAME_COLUMNS[sector_level]) or sector["sector_name"]),
                    "ts_code": ts_code,
                    "stock_name": str(row.get("name") or ""),
                }
            )
        return rows

    def _load_or_fetch_daily_flows(
        self,
        api: Any,
        trade_dates: list[str],
        members: pd.DataFrame,
        sector_source: str,
        sector_level: str,
        max_workers: int,
        force_refresh: bool,
    ) -> tuple[list[pd.DataFrame], list[pd.DataFrame], dict[str, Any]]:
        sector_frames: list[pd.DataFrame] = []
        stock_frames: list[pd.DataFrame] = []
        cached_dates = []
        fetch_dates = []
        empty_dates = []

        tasks = [
            ParallelTask(
                date,
                self._load_or_fetch_one_day,
                args=(api, date, members, sector_source, sector_level, force_refresh),
            )
            for date in trade_dates
        ]

        for task_result in iter_parallel_results(tasks, max_workers=max(1, min(int(max_workers or 4), 8))):
            date = task_result.key
            if task_result.error is not None:
                empty_dates.append(date)
                continue
            sector_df, stock_df, source = task_result.value
            if source == "cache":
                cached_dates.append(date)
            elif source == "api":
                fetch_dates.append(date)
            if sector_df is not None and not sector_df.empty:
                sector_frames.append(sector_df)
            else:
                empty_dates.append(date)
            if stock_df is not None and not stock_df.empty:
                stock_frames.append(stock_df)

        return sector_frames, stock_frames, {
            "cached_dates": cached_dates,
            "fetched_dates": fetch_dates,
            "empty_dates": sorted(set(empty_dates)),
            "api_call_count": len(fetch_dates),
        }

    def _load_or_fetch_one_day(
        self,
        api: Any,
        trade_date: str,
        members: pd.DataFrame,
        sector_source: str,
        sector_level: str,
        force_refresh: bool,
    ) -> tuple[pd.DataFrame, pd.DataFrame, str]:
        if not force_refresh:
            sector_cached = self.repository.load_daily_sector_flow(trade_date, sector_source, sector_level)
            stock_cached = self.repository.load_daily_stock_flow(trade_date, sector_source, sector_level)
            if (
                sector_cached is not None
                and not sector_cached.empty
                and stock_cached is not None
                and not stock_cached.empty
                and _stock_cache_has_prices(stock_cached)
            ):
                return sector_cached, stock_cached, "cache"

        flow_df = api.moneyflow(trade_date=trade_date)
        if flow_df is None or flow_df.empty:
            return pd.DataFrame(), pd.DataFrame(), "api"
        quote_df = self._fetch_daily_quotes(api, trade_date)

        sector_df, stock_df = self._aggregate_one_day(
            trade_date=trade_date,
            flow_df=flow_df,
            quote_df=quote_df,
            members=members,
            sector_source=sector_source,
            sector_level=sector_level,
        )
        if not sector_df.empty:
            self.repository.save_daily_flow(sector_df, stock_df)
        return sector_df, stock_df, "api"

    def _aggregate_one_day(
        self,
        trade_date: str,
        flow_df: pd.DataFrame,
        quote_df: pd.DataFrame,
        members: pd.DataFrame,
        sector_source: str,
        sector_level: str,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        flow = _normalize_moneyflow(flow_df)
        if flow.empty:
            return pd.DataFrame(), pd.DataFrame()

        quotes = _normalize_daily_quotes(quote_df)
        if not quotes.empty:
            flow = flow.merge(quotes, on="ts_code", how="left", suffixes=("", "_quote"))
            flow["close"] = flow["close_quote"].where(flow["close_quote"].notna(), flow["close"])
            flow["pct_chg"] = flow["pct_chg_quote"].where(flow["pct_chg_quote"].notna(), flow["pct_chg"])
            flow = flow.drop(columns=["close_quote", "pct_chg_quote"], errors="ignore")

        member_cols = ["sector_code", "sector_name", "ts_code", "stock_name"]
        clean_members = members[member_cols].drop_duplicates(subset=["sector_code", "ts_code"])
        merged = clean_members.merge(flow, on="ts_code", how="inner", suffixes=("_member", ""))
        if merged.empty:
            return pd.DataFrame(), pd.DataFrame()

        member_name_col = "stock_name_member" if "stock_name_member" in merged.columns else "stock_name"
        flow_name_col = "stock_name" if member_name_col == "stock_name_member" and "stock_name" in merged.columns else None
        member_names = merged[member_name_col].astype(str) if member_name_col in merged.columns else ""
        fallback_names = merged[flow_name_col].astype(str) if flow_name_col else ""
        merged["stock_name"] = member_names.where(member_names.str.len() > 0, fallback_names)
        merged["trade_date"] = trade_date
        merged["sector_source"] = sector_source
        merged["sector_level"] = sector_level

        stock_columns = [
            "trade_date",
            "sector_source",
            "sector_level",
            "sector_code",
            "sector_name",
            "ts_code",
            "stock_name",
            "close",
            "pct_chg",
            *AMOUNT_COLUMNS,
        ]
        stock_df = merged[stock_columns].copy()

        sector_df = (
            stock_df.groupby(["trade_date", "sector_source", "sector_level", "sector_code", "sector_name"], as_index=False)
            .agg(
                {
                    **{column: "sum" for column in AMOUNT_COLUMNS},
                    "ts_code": "nunique",
                }
            )
            .rename(columns={"ts_code": "stock_count"})
        )

        stock_net = stock_df.groupby(["sector_code", "ts_code"], as_index=False)["net_mf_amount"].sum()
        counts = stock_net.groupby("sector_code")["net_mf_amount"].agg(
            positive_stock_count=lambda item: int((item > 0).sum()),
            negative_stock_count=lambda item: int((item < 0).sum()),
        )
        sector_df = sector_df.merge(counts, on="sector_code", how="left")
        sector_df[["positive_stock_count", "negative_stock_count"]] = sector_df[
            ["positive_stock_count", "negative_stock_count"]
        ].fillna(0).astype(int)
        return sector_df, stock_df

    def _fetch_daily_quotes(self, api: Any, trade_date: str) -> pd.DataFrame:
        try:
            return api.daily(trade_date=trade_date, fields="ts_code,trade_date,close,pct_chg")
        except TypeError:
            try:
                return api.daily(trade_date=trade_date)
            except Exception:
                return pd.DataFrame()
        except Exception:
            return pd.DataFrame()

    def _build_report(
        self,
        window: DateWindow,
        trade_dates: list[str],
        sector_source: str,
        sector_level: str,
        top_sectors: int,
        top_stocks: int,
        sector_frames: list[pd.DataFrame],
        stock_frames: list[pd.DataFrame],
        diagnostics: dict[str, Any],
    ) -> dict[str, Any]:
        if not sector_frames:
            return {
                "success": False,
                "error": "未获取到所选时间范围内的资金流数据",
                "range": self._range_payload(window, trade_dates),
                "diagnostics": diagnostics,
            }

        sector_all = pd.concat(sector_frames, ignore_index=True)
        stock_all = pd.concat(stock_frames, ignore_index=True) if stock_frames else pd.DataFrame()

        sector_totals = (
            sector_all.groupby(["sector_code", "sector_name"], as_index=False)
            .agg(
                {
                    **{column: "sum" for column in AMOUNT_COLUMNS},
                    "stock_count": "max",
                    "positive_stock_count": "max",
                    "negative_stock_count": "max",
                }
            )
        )

        stock_totals = self._aggregate_range_stocks(stock_all)
        sector_totals = self._attach_range_stock_counts(sector_totals, stock_totals)
        sector_totals["rank"] = sector_totals["net_mf_amount"].rank(ascending=False, method="first").astype(int)
        sector_totals = sector_totals.sort_values("net_mf_amount", ascending=False).reset_index(drop=True)

        sector_rank = [
            self._sector_payload(row, stock_totals, top_stocks, ascending=False)
            for _, row in sector_totals.head(top_sectors).iterrows()
        ]
        outflow_rank = [
            self._sector_payload(row, stock_totals, top_stocks, ascending=True)
            for _, row in sector_totals.sort_values("net_mf_amount", ascending=True).head(top_sectors).iterrows()
        ]

        positive_total = float(sector_totals.loc[sector_totals["net_mf_amount"] > 0, "net_mf_amount"].sum())
        top5_positive = float(sector_totals.head(5).loc[sector_totals.head(5)["net_mf_amount"] > 0, "net_mf_amount"].sum())
        summary = {
            "sector_count": int(len(sector_totals)),
            "positive_sector_count": int((sector_totals["net_mf_amount"] > 0).sum()),
            "negative_sector_count": int((sector_totals["net_mf_amount"] < 0).sum()),
            "total_net_mf_amount": _round(float(sector_totals["net_mf_amount"].sum())),
            "total_main_net_amount": _round(float(sector_totals["main_net_amount"].sum())),
            "positive_net_mf_amount": _round(positive_total),
            "top5_concentration": _round(top5_positive / positive_total * 100 if positive_total else 0),
            "trade_days_count": int(len(trade_dates)),
        }

        return {
            "success": True,
            "source": "tushare",
            "data_method": "申万行业成分股 moneyflow 聚合",
            "sector_source": sector_source,
            "sector_level": sector_level,
            "sector_level_name": CLASSIFY_LEVEL_NAMES.get(sector_level, sector_level),
            "range": self._range_payload(window, trade_dates),
            "summary": summary,
            "sector_rank": sector_rank,
            "outflow_rank": outflow_rank,
            "diagnostics": diagnostics,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }

    def _aggregate_range_stocks(self, stock_all: pd.DataFrame) -> pd.DataFrame:
        if stock_all.empty:
            return pd.DataFrame()

        totals = (
            stock_all.groupby(["sector_code", "sector_name", "ts_code", "stock_name"], as_index=False)
            .agg({column: "sum" for column in AMOUNT_COLUMNS})
        )
        latest = (
            stock_all.sort_values("trade_date")
            .groupby(["sector_code", "ts_code"], as_index=False)
            .tail(1)[["sector_code", "ts_code", "close", "pct_chg"]]
        )
        return totals.merge(latest, on=["sector_code", "ts_code"], how="left")

    def _attach_range_stock_counts(self, sector_totals: pd.DataFrame, stock_totals: pd.DataFrame) -> pd.DataFrame:
        if stock_totals.empty:
            return sector_totals
        counts = stock_totals.groupby("sector_code").agg(
            stock_count=("ts_code", "nunique"),
            positive_stock_count=("net_mf_amount", lambda item: int((item > 0).sum())),
            negative_stock_count=("net_mf_amount", lambda item: int((item < 0).sum())),
        )
        merged = sector_totals.drop(columns=["stock_count", "positive_stock_count", "negative_stock_count"], errors="ignore")
        merged = merged.merge(counts, on="sector_code", how="left")
        merged[["stock_count", "positive_stock_count", "negative_stock_count"]] = merged[
            ["stock_count", "positive_stock_count", "negative_stock_count"]
        ].fillna(0).astype(int)
        return merged

    def _sector_payload(
        self,
        row: pd.Series,
        stock_totals: pd.DataFrame,
        top_stocks: int,
        ascending: bool,
    ) -> dict[str, Any]:
        sector_code = str(row["sector_code"])
        stocks = []
        if stock_totals is not None and not stock_totals.empty:
            sector_stocks = stock_totals[stock_totals["sector_code"] == sector_code].sort_values(
                "net_mf_amount",
                ascending=ascending,
            )
            stocks = [_stock_payload(stock_row) for _, stock_row in sector_stocks.head(top_stocks).iterrows()]

        return {
            "rank": int(row.get("rank", 0) or 0),
            "sector_code": sector_code,
            "sector_name": str(row["sector_name"]),
            **{column: _round(row.get(column, 0)) for column in AMOUNT_COLUMNS},
            "stock_count": int(row.get("stock_count", 0) or 0),
            "positive_stock_count": int(row.get("positive_stock_count", 0) or 0),
            "negative_stock_count": int(row.get("negative_stock_count", 0) or 0),
            "top_stocks": stocks,
        }

    def _range_payload(self, window: DateWindow, trade_dates: list[str]) -> dict[str, Any]:
        return {
            "type": window.range_type,
            "label": RANGE_LABELS.get(window.range_type, window.range_type),
            "start_date": window.start_date,
            "end_date": window.end_date,
            "trade_date": window.trade_date,
            "trade_dates": trade_dates,
        }


def _normalize_level(value: str) -> str:
    level = str(value or "L2").upper()
    if level not in LEVEL_CODE_COLUMNS:
        raise ValueError("sector_level 仅支持 L1、L2、L3")
    return level


def _normalize_date(value: str) -> str:
    text = str(value or "").strip().replace("-", "")
    if len(text) != 8 or not text.isdigit():
        raise ValueError(f"日期格式错误: {value}")
    return text


def _with_si(code: str) -> str:
    text = str(code).strip()
    return text if text.endswith(".SI") else f"{text}.SI"


def _strip_si(code: str) -> str:
    text = str(code).strip()
    return text[:-3] if text.endswith(".SI") else text


def _normalize_moneyflow(df: pd.DataFrame) -> pd.DataFrame:
    frame = df.copy()
    if "ts_code" not in frame.columns:
        return pd.DataFrame()

    for column in [
        "buy_sm_amount",
        "sell_sm_amount",
        "buy_md_amount",
        "sell_md_amount",
        "buy_lg_amount",
        "sell_lg_amount",
        "buy_elg_amount",
        "sell_elg_amount",
        "net_mf_amount",
        "close",
        "pct_chg",
    ]:
        if column not in frame.columns:
            frame[column] = 0
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)

    computed_net = (
        frame["buy_sm_amount"]
        + frame["buy_md_amount"]
        + frame["buy_lg_amount"]
        + frame["buy_elg_amount"]
        - frame["sell_sm_amount"]
        - frame["sell_md_amount"]
        - frame["sell_lg_amount"]
        - frame["sell_elg_amount"]
    )
    frame["net_mf_amount"] = frame["net_mf_amount"].where(frame["net_mf_amount"] != 0, computed_net)
    frame["super_large_net_amount"] = frame["buy_elg_amount"] - frame["sell_elg_amount"]
    frame["large_net_amount"] = frame["buy_lg_amount"] - frame["sell_lg_amount"]
    frame["medium_net_amount"] = frame["buy_md_amount"] - frame["sell_md_amount"]
    frame["small_net_amount"] = frame["buy_sm_amount"] - frame["sell_sm_amount"]
    frame["main_net_amount"] = frame["super_large_net_amount"] + frame["large_net_amount"]

    if "name" in frame.columns and "stock_name" not in frame.columns:
        frame["stock_name"] = frame["name"]
    if "stock_name" not in frame.columns:
        frame["stock_name"] = ""

    return frame[["ts_code", "stock_name", "close", "pct_chg", *AMOUNT_COLUMNS]]


def _normalize_daily_quotes(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or "ts_code" not in df.columns:
        return pd.DataFrame()
    frame = df.copy()
    for column in ["close", "pct_chg"]:
        if column not in frame.columns:
            frame[column] = pd.NA
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame[["ts_code", "close", "pct_chg"]].drop_duplicates(subset=["ts_code"], keep="last")


def _stock_cache_has_prices(stock_df: pd.DataFrame) -> bool:
    if stock_df is None or stock_df.empty or "close" not in stock_df.columns:
        return False
    close = pd.to_numeric(stock_df["close"], errors="coerce").fillna(0)
    return bool((close > 0).any())


def _stock_payload(row: pd.Series) -> dict[str, Any]:
    return {
        "ts_code": str(row.get("ts_code", "")),
        "stock_name": str(row.get("stock_name", "")),
        "close": _round(row.get("close")),
        "pct_chg": _round(row.get("pct_chg")),
        **{column: _round(row.get(column, 0)) for column in AMOUNT_COLUMNS},
    }


def _round(value: Any, digits: int = 2) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if pd.isna(number):
        return 0.0
    return round(number, digits)
