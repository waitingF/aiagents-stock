"""Data adapters and normalization helpers for dragon strategy inputs."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import pandas as pd

from src.aiagents_stock.infrastructure.network.proxy import without_proxy_env


def _first_matching_column(frame: pd.DataFrame, patterns: list[str]) -> Optional[str]:
    for pattern in patterns:
        for col in frame.columns:
            if pattern in str(col):
                return col
    return None


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        multiplier = 1.0
        if cleaned.endswith("亿"):
            multiplier = 100000000.0
            cleaned = cleaned[:-1]
        elif cleaned.endswith("万"):
            multiplier = 10000.0
            cleaned = cleaned[:-1]
        try:
            return float(cleaned) * multiplier
        except ValueError:
            return default
    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_time(value: Any) -> str:
    """Normalize akshare board-time values into HH:MM:SS strings."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    if ":" in text:
        parts = text.split(":")
        if len(parts) == 2:
            return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:00"
        if len(parts) >= 3:
            return f"{parts[0].zfill(2)}:{parts[1].zfill(2)}:{parts[2].zfill(2)}"
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) == 6:
        return f"{digits[:2]}:{digits[2:4]}:{digits[4:6]}"
    if len(digits) == 4:
        return f"{digits[:2]}:{digits[2:4]}:00"
    return text


def normalize_stock_code(value: Any) -> str:
    text = str(value).strip().upper()
    if "." in text:
        text = text.split(".")[0]
    return text.zfill(6) if text.isdigit() and len(text) < 6 else text


def to_ts_code(code: str) -> str:
    code = normalize_stock_code(code)
    if "." in code:
        return code
    if code.startswith(("6", "9")):
        return f"{code}.SH"
    if code.startswith(("0", "2", "3")):
        return f"{code}.SZ"
    if code.startswith(("4", "8")):
        return f"{code}.BJ"
    return f"{code}.SZ"


def normalize_limit_up_pool(frame: pd.DataFrame | None) -> pd.DataFrame:
    """Normalize AKShare limit-up pool columns to stable English names."""
    if frame is None or frame.empty:
        return pd.DataFrame()
    result = frame.copy()
    col_map = {
        "code": _first_matching_column(result, ["代码"]),
        "name": _first_matching_column(result, ["名称", "简称"]),
        "first_limit_time": _first_matching_column(result, ["首次封板时间", "涨停时间", "首次"]),
        "seal_amount": _first_matching_column(result, ["封单金额", "封板资金", "封单", "封板"]),
        "lianban_count": _first_matching_column(result, ["连板数", "连板"]),
        "sector": _first_matching_column(result, ["所属板块", "所属行业", "行业"]),
        "pct_chg": _first_matching_column(result, ["涨跌幅"]),
        "circ_market_cap": _first_matching_column(result, ["流通市值"]),
        "explode_count": _first_matching_column(result, ["炸板次数"]),
        "latest_price": _first_matching_column(result, ["最新价", "收盘", "价格"]),
    }

    normalized = pd.DataFrame(index=result.index)
    for target, source in col_map.items():
        normalized[target] = result[source] if source else None

    normalized["code"] = normalized["code"].apply(normalize_stock_code)
    normalized["name"] = normalized["name"].fillna("").astype(str)
    normalized["first_limit_time"] = normalized["first_limit_time"].apply(normalize_time)
    normalized["seal_amount"] = normalized["seal_amount"].apply(_to_float)
    normalized["lianban_count"] = pd.to_numeric(normalized["lianban_count"], errors="coerce").fillna(1).astype(int)
    normalized["sector"] = normalized["sector"].fillna("未分类").astype(str)
    normalized["pct_chg"] = pd.to_numeric(normalized["pct_chg"], errors="coerce").fillna(0.0)
    normalized["circ_market_cap"] = normalized["circ_market_cap"].apply(lambda value: _to_float(value, default=0.0))
    normalized["explode_count"] = pd.to_numeric(normalized["explode_count"], errors="coerce").fillna(0).astype(int)
    normalized["latest_price"] = normalized["latest_price"].apply(lambda value: _to_float(value, default=0.0))
    normalized["raw"] = result.to_dict("records")
    return normalized.reset_index(drop=True)


def normalize_daily_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    """Normalize daily OHLCV data from AKShare/Tushare/local cache."""
    if frame is None or frame.empty:
        return pd.DataFrame()
    result = frame.copy()
    rename = {}
    for col in result.columns:
        text = str(col).lower()
        if col in ("日期", "trade_date", "date", "ts"):
            rename[col] = "date"
        elif col in ("开盘", "open"):
            rename[col] = "open"
        elif col in ("最高", "high"):
            rename[col] = "high"
        elif col in ("最低", "low"):
            rename[col] = "low"
        elif col in ("收盘", "close"):
            rename[col] = "close"
        elif col in ("成交量", "volume", "vol"):
            rename[col] = "volume"
        elif col in ("成交额", "amount"):
            rename[col] = "amount"
        elif "换手" in str(col) or text == "turnover_rate":
            rename[col] = "turnover"
        elif "量比" in str(col) or text == "volume_ratio":
            rename[col] = "volume_ratio"
        elif "涨跌幅" in str(col) or text == "pct_chg":
            rename[col] = "pct_chg"
    result = result.rename(columns=rename)
    for col in ["open", "high", "low", "close", "volume", "amount", "turnover", "volume_ratio", "pct_chg"]:
        if col in result.columns:
            result[col] = pd.to_numeric(result[col], errors="coerce")
    if "date" in result.columns:
        result["date"] = pd.to_datetime(result["date"], errors="coerce")
        result = result.sort_values("date")
    return result.reset_index(drop=True)


class AkshareDragonDataProvider:
    """AKShare-backed data provider.

    Network calls are delayed until methods are invoked, so core algorithms can
    be tested without importing or installing AKShare.
    """

    def _ak(self):
        import akshare as ak

        return ak

    def is_trade_day(self, date: str | None = None) -> bool:
        trade_date = date or datetime.now().strftime("%Y%m%d")
        normalized = str(trade_date).replace("-", "")
        try:
            with without_proxy_env():
                tool_df = self._ak().tool_trade_date_hist_sina()
            return normalized in tool_df["trade_date"].astype(str).str.replace("-", "").values
        except Exception:
            dt = datetime.strptime(normalized, "%Y%m%d")
            holiday_2026 = {f"202602{day:02d}" for day in range(16, 23)}
            return dt.weekday() not in (5, 6) and normalized not in holiday_2026

    def get_limit_up_pool(self, date: str | None = None) -> pd.DataFrame:
        trade_date = (date or datetime.now().strftime("%Y%m%d")).replace("-", "")
        try:
            with without_proxy_env():
                return normalize_limit_up_pool(self._ak().stock_zt_pool_em(date=trade_date))
        except Exception:
            return pd.DataFrame()

    def get_limit_down_pool(self, date: str | None = None) -> pd.DataFrame:
        trade_date = (date or datetime.now().strftime("%Y%m%d")).replace("-", "")
        ak = self._ak()
        for method in ("stock_dt_pool_em", "stock_zt_pool_dt_em"):
            if hasattr(ak, method):
                try:
                    with without_proxy_env():
                        return getattr(ak, method)(date=trade_date)
                except Exception:
                    continue
        return pd.DataFrame()

    def get_strong_pool(self, date: str | None = None) -> pd.DataFrame:
        trade_date = (date or datetime.now().strftime("%Y%m%d")).replace("-", "")
        try:
            with without_proxy_env():
                return self._ak().stock_zt_pool_strong_em(date=trade_date)
        except Exception:
            return pd.DataFrame()

    def get_explode_pool(self, date: str | None = None) -> pd.DataFrame:
        trade_date = (date or datetime.now().strftime("%Y%m%d")).replace("-", "")
        try:
            with without_proxy_env():
                return self._ak().stock_zt_pool_zbgc_em(date=trade_date)
        except Exception:
            return pd.DataFrame()

    def get_board_pool(self, date: str | None = None) -> pd.DataFrame:
        trade_date = (date or datetime.now().strftime("%Y%m%d")).replace("-", "")
        try:
            with without_proxy_env():
                return self._ak().stock_zt_pool_board_em(date=trade_date)
        except Exception:
            return pd.DataFrame()

    def get_industry_ranking(self, date: str | None = None) -> pd.DataFrame:
        """Return current industry/sector ranking from direct Eastmoney or AKShare fallbacks."""
        _ = date
        ak = self._ak()
        direct_fetchers = [
            (lambda: self._fetch_eastmoney_board_ranking("industry"), "eastmoney_industry_direct"),
            (lambda: self._fetch_eastmoney_board_ranking("concept"), "eastmoney_concept_direct"),
        ]
        akshare_fetchers = [
            (ak.stock_board_industry_name_em, "eastmoney_industry_akshare"),
            (getattr(ak, "stock_board_industry_summary_ths", None), "ths_industry_akshare"),
            (getattr(ak, "stock_board_concept_name_em", None), "eastmoney_concept_akshare"),
        ]
        fetchers = direct_fetchers + akshare_fetchers
        for fetcher, source in fetchers:
            if fetcher is None:
                continue
            frame = self._safe_frame(fetcher)
            if frame is not None and not frame.empty:
                frame = frame.copy()
                frame["source"] = source
                return frame
        return pd.DataFrame()

    def _safe_frame(self, fetcher: Any) -> pd.DataFrame:
        try:
            with without_proxy_env():
                frame = fetcher()
        except Exception:
            return pd.DataFrame()
        return frame if isinstance(frame, pd.DataFrame) else pd.DataFrame()

    def _fetch_eastmoney_board_ranking(self, board_type: str) -> pd.DataFrame:
        """Fetch Eastmoney board ranking directly, bypassing broken env proxies."""
        import requests

        board = {
            "industry": {"fs": "m:90 t:2 f:!50", "host": "17", "source_type": "行业"},
            "concept": {"fs": "m:90 t:3 f:!50", "host": "79", "source_type": "概念"},
        }[board_type]
        fields = [
            "f2",
            "f3",
            "f4",
            "f6",
            "f8",
            "f12",
            "f14",
            "f20",
            "f104",
            "f105",
            "f106",
            "f128",
            "f136",
        ]
        params = {
            "pn": "1",
            "pz": "200",
            "po": "1",
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",
            "fs": board["fs"],
            "fields": ",".join(fields),
        }
        session = requests.Session()
        session.trust_env = False
        hosts = [f"{board['host']}.push2.eastmoney.com", "push2.eastmoney.com"]
        data = None
        last_error: Exception | None = None
        for host in dict.fromkeys(hosts):
            url = f"https://{host}/api/qt/clist/get"
            try:
                response = session.get(url, params=params, timeout=3)
                response.raise_for_status()
                data = response.json().get("data", {}).get("diff", [])
                if data:
                    break
            except Exception as exc:
                last_error = exc
        if not data:
            if last_error:
                raise last_error
            return pd.DataFrame()

        raw = pd.DataFrame(data)
        result = pd.DataFrame(
            {
                "板块名称": raw.get("f14"),
                "板块代码": raw.get("f12"),
                "最新价": pd.to_numeric(raw.get("f2"), errors="coerce"),
                "涨跌幅": pd.to_numeric(raw.get("f3"), errors="coerce"),
                "涨跌额": pd.to_numeric(raw.get("f4"), errors="coerce"),
                "成交额": pd.to_numeric(raw.get("f6"), errors="coerce"),
                "总市值": pd.to_numeric(raw.get("f20"), errors="coerce"),
                "换手率": pd.to_numeric(raw.get("f8"), errors="coerce"),
                "上涨家数": pd.to_numeric(raw.get("f104"), errors="coerce"),
                "下跌家数": pd.to_numeric(raw.get("f105"), errors="coerce"),
                "平盘家数": pd.to_numeric(raw.get("f106"), errors="coerce"),
                "领涨股票": raw.get("f128"),
                "领涨股票-涨跌幅": pd.to_numeric(raw.get("f136"), errors="coerce"),
                "source_type": board["source_type"],
            }
        )
        result = result.dropna(subset=["板块名称"]).sort_values("涨跌幅", ascending=False, na_position="last")
        result.insert(0, "排名", range(1, len(result) + 1))
        return result.reset_index(drop=True)

    def get_realtime_quotes(self) -> pd.DataFrame:
        try:
            with without_proxy_env():
                return self._ak().stock_zh_a_spot_em()
        except Exception:
            return pd.DataFrame()

    def get_index_daily(self, start_date: str, end_date: str) -> pd.DataFrame:
        try:
            with without_proxy_env():
                return normalize_daily_frame(
                    self._ak().index_zh_a_hist(
                        symbol="000001",
                        period="daily",
                        start_date=start_date.replace("-", ""),
                        end_date=end_date.replace("-", ""),
                    )
                )
        except Exception:
            return pd.DataFrame()

    def get_stock_info(self, code: str) -> Dict[str, Any]:
        try:
            with without_proxy_env():
                info_df = self._ak().stock_individual_info_em(symbol=normalize_stock_code(code))
        except Exception:
            return {}
        if info_df is None or info_df.empty:
            return {}
        return dict(zip(info_df["item"], info_df["value"]))

    def get_stock_daily(self, code: str, date: str | None = None, lookback_days: int = 90) -> pd.DataFrame:
        end = (date or datetime.now().strftime("%Y%m%d")).replace("-", "")
        start = (datetime.strptime(end, "%Y%m%d") - timedelta(days=lookback_days)).strftime("%Y%m%d")
        try:
            with without_proxy_env():
                frame = self._ak().stock_zh_a_hist(
                    symbol=normalize_stock_code(code),
                    period="daily",
                    start_date=start,
                    end_date=end,
                    adjust="qfq",
                )
            return normalize_daily_frame(frame)
        except Exception:
            return pd.DataFrame()

    def get_yesterday_limit_up_count(self, date: str) -> int:
        previous = (datetime.strptime(date.replace("-", ""), "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
        try:
            if not self.is_trade_day(previous):
                return 0
            frame = self.get_limit_up_pool(previous)
            return int(len(frame))
        except Exception:
            return 0

    def get_north_money(self) -> float:
        try:
            with without_proxy_env():
                frame = self._ak().stock_em_hsgt_north_net_flow_in(symbol="北向资金")
            if frame is not None and not frame.empty:
                return _to_float(frame["净流入"].iloc[-1], default=-100.0)
        except Exception:
            pass
        return -100.0

    def get_market_activity(self) -> tuple[int, int]:
        try:
            with without_proxy_env():
                frame = self._ak().stock_market_activity_legu_em()
            if frame is not None and not frame.empty:
                return int(frame["上涨家数"].iloc[0]), int(frame["下跌家数"].iloc[0])
        except Exception:
            pass
        return 0, 1
