"""
宏观分析板块 - 数据采集与标准化
优先通过 Tushare/AKShare/国家统计局发布稿获取核心宏观数据，并补充A股市场快照与候选标的池。
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import akshare as ak
import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()


class MacroAnalysisDataFetcher:
    """宏观分析板块数据获取器"""

    NBS_URL = "https://data.stats.gov.cn/easyquery.htm"
    CACHE_PATH = Path("data") / "macro_analysis" / "macro_series_cache.json"
    REQUEST_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }

    CORE_MACRO_KEYS = (
        "gdp_yoy",
        "gdp_qoq",
        "industrial_yoy",
        "cpi_yoy",
        "ppi_yoy",
        "manufacturing_pmi",
        "non_manufacturing_pmi",
        "composite_pmi",
    )

    SOURCE_LABELS = {
        "cache": "本地缓存",
        "tushare": "Tushare Pro",
        "akshare": "AKShare",
        "stats_release": "国家统计局发布稿",
        "nbs_easyquery": "国家统计局 easyquery",
        "tushare_proxy": "Tushare Pro 代理计算",
    }

    # 这里直接绑定统计局指标编码，避免运行时频繁遍历指标树
    NBS_SERIES_CONFIG = {
        "gdp_yoy": {
            "dbcode": "hgjd",
            "group_code": "A0103",
            "series_code": "A010301",
            "label": "GDP当季同比",
            "unit": "%",
            "period": "LAST8",
            "transform": "index_minus_100",
        },
        "gdp_qoq": {
            "dbcode": "hgjd",
            "group_code": "A0104",
            "series_code": "A010401",
            "label": "GDP环比增长",
            "unit": "%",
            "period": "LAST8",
        },
        "industrial_yoy": {
            "dbcode": "hgyd",
            "group_code": "A0201",
            "series_code": "A020101",
            "label": "规上工业增加值同比",
            "unit": "%",
            "period": "LAST8",
        },
        "cpi_yoy": {
            "dbcode": "hgyd",
            "group_code": "A01010J",
            "series_code": "A01010J01",
            "label": "CPI同比",
            "unit": "%",
            "period": "LAST8",
            "transform": "index_minus_100",
        },
        "ppi_yoy": {
            "dbcode": "hgyd",
            "group_code": "A010801",
            "series_code": "A01080101",
            "label": "PPI同比",
            "unit": "%",
            "period": "LAST8",
            "transform": "index_minus_100",
        },
        "manufacturing_pmi": {
            "dbcode": "hgyd",
            "group_code": "A0B01",
            "series_code": "A0B0101",
            "label": "制造业PMI",
            "unit": "",
            "period": "LAST8",
        },
        "non_manufacturing_pmi": {
            "dbcode": "hgyd",
            "group_code": "A0B02",
            "series_code": "A0B0201",
            "label": "非制造业商务活动指数",
            "unit": "",
            "period": "LAST8",
        },
        "composite_pmi": {
            "dbcode": "hgyd",
            "group_code": "A0B03",
            "series_code": "A0B0301",
            "label": "综合PMI产出指数",
            "unit": "",
            "period": "LAST8",
        },
        "m2_yoy": {
            "dbcode": "hgyd",
            "group_code": "A0D01",
            "series_code": "A0D0102",
            "label": "M2同比",
            "unit": "%",
            "period": "LAST8",
        },
        "retail_sales_yoy": {
            "dbcode": "hgyd",
            "group_code": "A0701",
            "series_code": "A070104",
            "label": "社零累计同比",
            "unit": "%",
            "period": "LAST8",
        },
        "fixed_asset_yoy": {
            "dbcode": "hgyd",
            "group_code": "A0401",
            "series_code": "A040102",
            "label": "固定资产投资累计同比",
            "unit": "%",
            "period": "LAST8",
        },
        "real_estate_invest_yoy": {
            "dbcode": "hgyd",
            "group_code": "A0601",
            "series_code": "A060102",
            "label": "房地产开发投资累计同比",
            "unit": "%",
            "period": "LAST8",
        },
        "urban_unemployment": {
            "dbcode": "hgyd",
            "group_code": "A0E01",
            "series_code": "A0E0101",
            "label": "全国城镇调查失业率",
            "unit": "%",
            "period": "LAST8",
        },
    }

    TUSHARE_SERIES_CONFIG = {
        "gdp_yoy": {
            "api": "cn_gdp",
            "fields": "quarter,gdp,gdp_yoy",
            "period_col": "quarter",
            "value_col": "gdp_yoy",
            "period_type": "quarter",
        },
        "cpi_yoy": {
            "api": "cn_cpi",
            "fields": "month,nt_yoy",
            "period_col": "month",
            "value_col": "nt_yoy",
            "period_type": "month",
        },
        "ppi_yoy": {
            "api": "cn_ppi",
            "fields": "month,ppi_yoy",
            "period_col": "month",
            "value_col": "ppi_yoy",
            "period_type": "month",
        },
        "manufacturing_pmi": {
            "api": "cn_pmi",
            "fields": "month,pmi010000,pmi020100,pmi030000",
            "period_col": "month",
            "value_col": "pmi010000",
            "period_type": "month",
        },
        "non_manufacturing_pmi": {
            "api": "cn_pmi",
            "fields": "month,pmi010000,pmi020100,pmi030000",
            "period_col": "month",
            "value_col": "pmi020100",
            "period_type": "month",
        },
        "composite_pmi": {
            "api": "cn_pmi",
            "fields": "month,pmi010000,pmi020100,pmi030000",
            "period_col": "month",
            "value_col": "pmi030000",
            "period_type": "month",
        },
    }

    AKSHARE_SERIES_CONFIG = {
        "gdp_yoy": {
            "functions": ["macro_china_gdp"],
            "period_col": "季度",
            "value_col": "国内生产总值-同比增长",
            "period_type": "quarter_date",
        },
        "industrial_yoy": {
            "functions": ["macro_china_gyzjz", "macro_china_industrial_production_yoy"],
            "period_col": "月份",
            "value_col": "同比增长",
            "period_type": "month_text",
        },
        "cpi_yoy": {
            "functions": ["macro_china_cpi", "macro_china_cpi_monthly"],
            "period_col": "月份",
            "value_col": "全国-同比增长",
            "period_type": "month_text",
        },
        "ppi_yoy": {
            "functions": ["macro_china_ppi", "macro_china_ppi_yearly"],
            "period_col": "月份",
            "value_col": "当月同比增长",
            "period_type": "month_text",
        },
        "manufacturing_pmi": {
            "functions": ["macro_china_pmi", "macro_china_pmi_yearly"],
            "period_col": "月份",
            "value_col": "制造业-指数",
            "period_type": "month_text",
        },
        "non_manufacturing_pmi": {
            "functions": ["macro_china_pmi"],
            "period_col": "月份",
            "value_col": "非制造业-指数",
            "period_type": "month_text",
        },
    }

    STATS_RELEASE_KEYS = {"gdp_qoq", "industrial_yoy"}
    PROXY_KEYS = {"gdp_qoq"}
    STATS_RELEASE_LIST_URLS = (
        "https://www.stats.gov.cn/sj/zxfb/",
        "https://www.stats.gov.cn/sj/zxfbhjd/",
    )

    A_SHARE_INDEX_CONFIG = {
        "上证指数": "sh000001",
        "深证成指": "sz399001",
        "创业板指": "sz399006",
        "沪深300": "sh000300",
    }

    SECTOR_STOCK_POOLS = {
        "银行": [
            {"code": "600036", "name": "招商银行"},
            {"code": "601166", "name": "兴业银行"},
            {"code": "600919", "name": "江苏银行"},
        ],
        "券商": [
            {"code": "600030", "name": "中信证券"},
            {"code": "300059", "name": "东方财富"},
            {"code": "601688", "name": "华泰证券"},
        ],
        "保险": [
            {"code": "601318", "name": "中国平安"},
            {"code": "601628", "name": "中国人寿"},
            {"code": "601601", "name": "中国太保"},
        ],
        "公用事业": [
            {"code": "600900", "name": "长江电力"},
            {"code": "600025", "name": "华能水电"},
            {"code": "600674", "name": "川投能源"},
        ],
        "电网设备": [
            {"code": "600406", "name": "国电南瑞"},
            {"code": "000400", "name": "许继电气"},
            {"code": "600312", "name": "平高电气"},
        ],
        "半导体": [
            {"code": "002371", "name": "北方华创"},
            {"code": "688981", "name": "中芯国际"},
            {"code": "603986", "name": "兆易创新"},
        ],
        "算力AI": [
            {"code": "300308", "name": "中际旭创"},
            {"code": "601138", "name": "工业富联"},
            {"code": "000977", "name": "浪潮信息"},
        ],
        "软件信创": [
            {"code": "688111", "name": "金山办公"},
            {"code": "600588", "name": "用友网络"},
            {"code": "600536", "name": "中国软件"},
        ],
        "消费电子": [
            {"code": "002475", "name": "立讯精密"},
            {"code": "002241", "name": "歌尔股份"},
            {"code": "300433", "name": "蓝思科技"},
        ],
        "食品饮料": [
            {"code": "600519", "name": "贵州茅台"},
            {"code": "600887", "name": "伊利股份"},
            {"code": "603288", "name": "海天味业"},
        ],
        "家电": [
            {"code": "000333", "name": "美的集团"},
            {"code": "000651", "name": "格力电器"},
            {"code": "600690", "name": "海尔智家"},
        ],
        "创新药": [
            {"code": "600276", "name": "恒瑞医药"},
            {"code": "688235", "name": "百济神州"},
            {"code": "002422", "name": "科伦药业"},
        ],
        "汽车整车": [
            {"code": "002594", "name": "比亚迪"},
            {"code": "000625", "name": "长安汽车"},
            {"code": "600066", "name": "宇通客车"},
        ],
        "工程机械": [
            {"code": "600031", "name": "三一重工"},
            {"code": "000425", "name": "徐工机械"},
            {"code": "000157", "name": "中联重科"},
        ],
        "有色金属": [
            {"code": "601899", "name": "紫金矿业"},
            {"code": "603993", "name": "洛阳钼业"},
            {"code": "601600", "name": "中国铝业"},
        ],
        "黄金": [
            {"code": "600547", "name": "山东黄金"},
            {"code": "600489", "name": "中金黄金"},
            {"code": "600988", "name": "赤峰黄金"},
        ],
        "石油石化": [
            {"code": "600938", "name": "中国海油"},
            {"code": "601857", "name": "中国石油"},
            {"code": "600028", "name": "中国石化"},
        ],
        "煤炭": [
            {"code": "601088", "name": "中国神华"},
            {"code": "601225", "name": "陕西煤业"},
            {"code": "601898", "name": "中煤能源"},
        ],
        "通信运营商": [
            {"code": "600941", "name": "中国移动"},
            {"code": "601728", "name": "中国电信"},
            {"code": "600050", "name": "中国联通"},
        ],
        "旅游酒店": [
            {"code": "601888", "name": "中国中免"},
            {"code": "600258", "name": "首旅酒店"},
            {"code": "600754", "name": "锦江酒店"},
        ],
        "房地产": [
            {"code": "600048", "name": "保利发展"},
            {"code": "001979", "name": "招商蛇口"},
            {"code": "000002", "name": "万科A"},
        ],
        "建材家居": [
            {"code": "002271", "name": "东方雨虹"},
            {"code": "000786", "name": "北新建材"},
            {"code": "603833", "name": "欧派家居"},
        ],
        "农业": [
            {"code": "002714", "name": "牧原股份"},
            {"code": "002311", "name": "海大集团"},
            {"code": "000998", "name": "隆平高科"},
        ],
        "军工": [
            {"code": "600760", "name": "中航沈飞"},
            {"code": "000768", "name": "中航西飞"},
            {"code": "600893", "name": "航发动力"},
        ],
    }

    SECTOR_ALIASES = {
        "高股息": ["银行", "保险", "公用事业", "煤炭", "通信运营商"],
        "红利": ["银行", "保险", "公用事业", "煤炭", "通信运营商"],
        "电力": ["公用事业"],
        "电网": ["电网设备"],
        "算力": ["算力AI"],
        "AI": ["算力AI"],
        "信创": ["软件信创"],
        "医药": ["创新药"],
        "消费": ["食品饮料", "家电", "旅游酒店"],
        "顺周期": ["有色金属", "工程机械", "石油石化", "煤炭"],
    }

    def __init__(
        self,
        tushare_api: Any = None,
        cache_path: Optional[Path | str] = None,
        cache_ttl_hours: int = 24,
    ) -> None:
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            logging.basicConfig(
                level=logging.INFO,
                format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            )
        self._tushare_api = tushare_api
        self._tushare_api_checked = tushare_api is not None
        self._tushare_df_cache: Dict[tuple[str, str], pd.DataFrame] = {}
        self.cache_path = Path(cache_path) if cache_path is not None else self.CACHE_PATH
        self.cache_ttl_seconds = max(cache_ttl_hours, 0) * 3600

    def fetch_all_data(self) -> Dict[str, Any]:
        """获取完整宏观分析所需数据"""
        result = {
            "success": False,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "macro_series": {},
            "macro_snapshot": {},
            "macro_tables": {},
            "market_indices": {},
            "news": [],
            "candidate_pools": self.SECTION_POOLS_FOR_PROMPT(),
            "rule_based_sector_view": {},
            "errors": [],
        }

        for key in self.CORE_MACRO_KEYS:
            config = self.NBS_SERIES_CONFIG[key]
            try:
                series = self._fetch_macro_series(key, config)
                result["macro_series"][key] = series
            except Exception as exc:
                result["errors"].append(f"{config['label']}: {exc}")
                self.logger.warning("获取宏观指标失败 %s: %s", config["label"], exc)

        result["macro_snapshot"] = self._build_macro_snapshot(result["macro_series"])
        result["macro_tables"] = self._build_macro_tables(result["macro_series"])
        result["rule_based_sector_view"] = self.build_rule_based_sector_view(
            result["macro_snapshot"]
        )

        try:
            result["market_indices"] = self._fetch_market_indices()
        except Exception as exc:
            result["errors"].append(f"市场指数: {exc}")
            self.logger.warning("获取市场指数失败: %s", exc)

        try:
            result["news"] = self._fetch_macro_news()
        except Exception as exc:
            result["errors"].append(f"宏观新闻: {exc}")
            self.logger.warning("获取宏观新闻失败: %s", exc)

        result["success"] = bool(result["macro_snapshot"])
        return result

    def SECTION_POOLS_FOR_PROMPT(self) -> Dict[str, List[Dict[str, str]]]:
        """提供给AI的候选板块池"""
        return self.SECTOR_STOCK_POOLS

    def _fetch_macro_series(self, key: str, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        cached = self._read_cached_series(key, allow_stale=False)
        if cached:
            return cached

        errors: List[str] = []
        fetchers = []
        if key in self.TUSHARE_SERIES_CONFIG:
            fetchers.append(("tushare", lambda: self._fetch_tushare_series(key, config)))
        if key in self.AKSHARE_SERIES_CONFIG:
            fetchers.append(("akshare", lambda: self._fetch_akshare_series(key, config)))
        if key in self.STATS_RELEASE_KEYS:
            fetchers.append(("stats_release", lambda: self._fetch_stats_release_series(key, config)))
        if key in self.PROXY_KEYS:
            fetchers.append(("tushare_proxy", lambda: self._compute_proxy_series(key, config)))

        for source, fetcher in fetchers:
            try:
                series = fetcher()
                if series:
                    self._write_cached_series(key, series)
                    return series
                errors.append(f"{self.SOURCE_LABELS.get(source, source)}: 无数据")
            except Exception as exc:
                errors.append(f"{self.SOURCE_LABELS.get(source, source)}: {exc}")
                self.logger.warning(
                    "宏观指标源失败 %s / %s: %s",
                    config["label"],
                    self.SOURCE_LABELS.get(source, source),
                    exc,
                )

        stale_cached = self._read_cached_series(key, allow_stale=True)
        if stale_cached:
            self.logger.warning("远端数据源均失败，使用过期缓存: %s", config["label"])
            return stale_cached

        raise RuntimeError("; ".join(errors) or "无可用数据源")

    def _read_cached_series(self, key: str, allow_stale: bool) -> List[Dict[str, Any]]:
        cache_data = self._read_cache_file()
        payload = cache_data.get(key)
        if not isinstance(payload, dict):
            return []

        cached_at = self._parse_cached_at(payload.get("cached_at"))
        if not cached_at:
            return []
        age_seconds = (datetime.now() - cached_at).total_seconds()
        if not allow_stale and age_seconds > self.cache_ttl_seconds:
            return []

        rows = payload.get("series")
        if not isinstance(rows, list):
            return []
        result = []
        for row in rows:
            if isinstance(row, dict):
                item = row.copy()
                item["from_cache"] = True
                item["cache_age_seconds"] = round(age_seconds, 0)
                result.append(item)
        return result

    def _write_cached_series(self, key: str, series: List[Dict[str, Any]]) -> None:
        if not series:
            return
        try:
            cache_data = self._read_cache_file()
            rows = []
            for row in series:
                item = row.copy()
                item.pop("from_cache", None)
                item.pop("cache_age_seconds", None)
                rows.append(item)
            cache_data[key] = {
                "cached_at": datetime.now().isoformat(timespec="seconds"),
                "series": rows,
            }
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(cache_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            self.logger.warning("写入宏观数据缓存失败 %s: %s", key, exc)

    def _read_cache_file(self) -> Dict[str, Any]:
        try:
            if not self.cache_path.exists():
                return {}
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            self.logger.warning("读取宏观数据缓存失败: %s", exc)
            return {}

    @staticmethod
    def _parse_cached_at(value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def _get_tushare_api(self) -> Any:
        if self._tushare_api is not None:
            return self._tushare_api
        if self._tushare_api_checked:
            raise RuntimeError("Tushare API 不可用")

        self._tushare_api_checked = True
        token = os.getenv("TUSHARE_TOKEN", "").strip()
        if not token:
            raise RuntimeError("未配置 TUSHARE_TOKEN")

        import tushare as ts

        self._tushare_api = ts.pro_api(token)
        return self._tushare_api

    def _get_tushare_dataframe(self, api_name: str, fields: str) -> pd.DataFrame:
        cache_key = (api_name, fields)
        if cache_key in self._tushare_df_cache:
            return self._tushare_df_cache[cache_key]

        api = self._get_tushare_api()
        method = getattr(api, api_name)
        df = method(fields=fields)
        if df is None or df.empty:
            raise RuntimeError(f"{api_name} 返回空数据")
        self._tushare_df_cache[cache_key] = df
        return df

    def _fetch_tushare_series(self, key: str, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        source_config = self.TUSHARE_SERIES_CONFIG[key]
        df = self._get_tushare_dataframe(source_config["api"], source_config["fields"])
        return self._series_from_dataframe(
            df=df,
            key=key,
            config=config,
            period_col=source_config["period_col"],
            value_col=source_config["value_col"],
            period_type=source_config["period_type"],
            source="tushare",
            is_official=False,
            is_proxy=False,
        )

    def _fetch_akshare_series(self, key: str, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        source_config = self.AKSHARE_SERIES_CONFIG[key]
        method = None
        method_name = ""
        for candidate in source_config["functions"]:
            method = getattr(ak, candidate, None)
            if method is not None:
                method_name = candidate
                break
        if method is None:
            raise RuntimeError("当前 AKShare 版本缺少可用宏观接口")

        df = method()
        if df is None or df.empty:
            raise RuntimeError(f"{method_name} 返回空数据")
        return self._series_from_dataframe(
            df=df,
            key=key,
            config=config,
            period_col=source_config["period_col"],
            value_col=source_config["value_col"],
            period_type=source_config["period_type"],
            source="akshare",
            is_official=False,
            is_proxy=False,
        )

    def _series_from_dataframe(
        self,
        df: pd.DataFrame,
        key: str,
        config: Dict[str, Any],
        period_col: str,
        value_col: str,
        period_type: str,
        source: str,
        is_official: bool,
        is_proxy: bool,
    ) -> List[Dict[str, Any]]:
        if period_col not in df.columns or value_col not in df.columns:
            raise RuntimeError(f"缺少字段 {period_col}/{value_col}")

        rows: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            value = self._to_float(row.get(value_col))
            if value is None:
                continue
            period_code, period_label = self._normalize_period(row.get(period_col), period_type)
            if not period_code:
                continue
            rows.append(
                self._macro_row(
                    key=key,
                    config=config,
                    period_code=period_code,
                    period_label=period_label,
                    value_raw=value,
                    value=value,
                    source=source,
                    is_official=is_official,
                    is_proxy=is_proxy,
                )
            )

        rows.sort(key=lambda item: self._period_sort_key(item["period_code"]), reverse=True)
        return rows[:8]

    def _fetch_stats_release_series(self, key: str, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        for url in self._find_stats_release_urls(key):
            try:
                title, text = self._fetch_stats_release_text(url)
                row = self._parse_stats_release_row(key, config, title, text, url)
                if row:
                    return [row]
            except Exception as exc:
                self.logger.warning("解析国家统计局发布稿失败 %s: %s", url, exc)
        raise RuntimeError("未在国家统计局发布稿中解析到可用数据")

    def _find_stats_release_urls(self, key: str) -> List[str]:
        if key == "gdp_qoq":
            keywords = ["国内生产总值", "GDP"]
        elif key == "industrial_yoy":
            keywords = ["规模以上工业增加值"]
        else:
            return []

        urls: List[str] = []
        for list_url in self.STATS_RELEASE_LIST_URLS:
            response = requests.get(
                list_url,
                headers=self.REQUEST_HEADERS,
                timeout=20,
            )
            response.raise_for_status()
            response.encoding = response.apparent_encoding or response.encoding
            soup = BeautifulSoup(response.text, "html.parser")
            for link in soup.find_all("a"):
                title = link.get_text(" ", strip=True)
                href = str(link.get("href") or "")
                if not title or not href:
                    continue
                if href.lower().endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx")):
                    continue
                if not any(keyword in title for keyword in keywords):
                    continue
                urls.append(urljoin(list_url, href))

        unique_urls = list(dict.fromkeys(urls))
        return unique_urls[:12]

    def _fetch_stats_release_text(self, url: str) -> tuple[str, str]:
        response = requests.get(url, headers=self.REQUEST_HEADERS, timeout=20)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding
        soup = BeautifulSoup(response.text, "html.parser")
        title_node = soup.find("h1") or soup.find("title")
        title = title_node.get_text(" ", strip=True) if title_node else ""
        text = soup.get_text(" ", strip=True)
        return title, text

    def _parse_stats_release_row(
        self,
        key: str,
        config: Dict[str, Any],
        title: str,
        text: str,
        url: str,
    ) -> Optional[Dict[str, Any]]:
        if key == "gdp_qoq":
            period_code, period_label = self._extract_quarter_from_text(title or text)
            patterns = [
                r"从环比看，?[^。]{0,80}?国内生产总值增长\s*([+-]?\d+(?:\.\d+)?)%",
                r"国内生产总值[^。]{0,80}?环比增长\s*([+-]?\d+(?:\.\d+)?)%",
                r"GDP[^。]{0,80}?环比增长\s*([+-]?\d+(?:\.\d+)?)%",
            ]
        elif key == "industrial_yoy":
            period_code, period_label = self._extract_month_from_text(title or text)
            patterns = [
                r"规模以上工业增加值同比实际增长\s*([+-]?\d+(?:\.\d+)?)%",
                r"规模以上工业增加值同比增长\s*([+-]?\d+(?:\.\d+)?)%",
                r"规模以上工业增加值增长\s*([+-]?\d+(?:\.\d+)?)%",
            ]
        else:
            return None

        if not period_code:
            return None
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            value = round(float(match.group(1)), 2)
            return self._macro_row(
                key=key,
                config=config,
                period_code=period_code,
                period_label=period_label,
                value_raw=value,
                value=value,
                source="stats_release",
                is_official=True,
                is_proxy=False,
                url=url,
            )
        if key == "gdp_qoq":
            table_value = self._parse_gdp_qoq_table_value(text, period_code)
            if table_value is not None:
                return self._macro_row(
                    key=key,
                    config=config,
                    period_code=period_code,
                    period_label=period_label,
                    value_raw=table_value,
                    value=table_value,
                    source="stats_release",
                    is_official=True,
                    is_proxy=False,
                    url=url,
                )
        return None

    @staticmethod
    def _parse_gdp_qoq_table_value(text: str, period_code: str) -> Optional[float]:
        match = re.fullmatch(r"(\d{4})Q([1-4])", period_code)
        if not match:
            return None
        year = match.group(1)
        quarter_index = int(match.group(2)) - 1
        section_start = text.find("GDP 环比增长速度")
        if section_start < 0:
            section_start = text.find("GDP环比增长速度")
        if section_start < 0:
            return None
        section = text[section_start:]
        row_match = re.search(
            rf"{year}\s+([+-]?\d+(?:\.\d+)?(?:\s+[+-]?\d+(?:\.\d+)?){{0,3}})",
            section,
        )
        if not row_match:
            return None
        values = [float(item) for item in row_match.group(1).split()]
        if len(values) <= quarter_index:
            return None
        return round(values[quarter_index], 2)

    def _compute_proxy_series(self, key: str, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        if key != "gdp_qoq":
            raise RuntimeError("未配置代理计算")

        df = self._get_tushare_dataframe("cn_gdp", "quarter,gdp")
        points = []
        for _, row in df.iterrows():
            quarter = str(row.get("quarter") or "").strip()
            value = self._to_float(row.get("gdp"))
            match = re.fullmatch(r"(\d{4})Q([1-4])", quarter)
            if not match or value is None:
                continue
            points.append(
                {
                    "year": int(match.group(1)),
                    "quarter": int(match.group(2)),
                    "period_code": quarter,
                    "period_label": quarter,
                    "cumulative_gdp": value,
                }
            )

        points.sort(key=lambda item: (item["year"], item["quarter"]))
        previous_cumulative_by_year: Dict[int, float] = {}
        single_quarter_points = []
        for point in points:
            year = point["year"]
            quarter = point["quarter"]
            cumulative = point["cumulative_gdp"]
            if quarter == 1:
                single_gdp = cumulative
            else:
                previous_cumulative = previous_cumulative_by_year.get(year)
                if previous_cumulative is None:
                    previous_cumulative_by_year[year] = cumulative
                    continue
                single_gdp = cumulative - previous_cumulative
            previous_cumulative_by_year[year] = cumulative
            if single_gdp <= 0:
                continue
            single_quarter_points.append({**point, "single_gdp": single_gdp})

        rows: List[Dict[str, Any]] = []
        for index in range(1, len(single_quarter_points)):
            current = single_quarter_points[index]
            previous = single_quarter_points[index - 1]
            if previous["single_gdp"] == 0:
                continue
            value = round((current["single_gdp"] / previous["single_gdp"] - 1) * 100, 2)
            rows.append(
                self._macro_row(
                    key=key,
                    config=config,
                    period_code=current["period_code"],
                    period_label=current["period_label"],
                    value_raw=value,
                    value=value,
                    source="tushare_proxy",
                    is_official=False,
                    is_proxy=True,
                    note="由Tushare累计GDP拆分单季名义GDP后计算，非官方季调环比。",
                )
            )

        rows.sort(key=lambda item: self._period_sort_key(item["period_code"]), reverse=True)
        return rows[:8]

    def _post_query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        response = requests.post(
            self.NBS_URL,
            params=params,
            headers=self.REQUEST_HEADERS,
            verify=False,
            allow_redirects=True,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("returncode") != 200:
            raise ValueError(data.get("returndata", "统计局接口返回异常"))
        return data["returndata"]

    def _fetch_nbs_series(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        params = {
            "m": "QueryData",
            "dbcode": config["dbcode"],
            "rowcode": "zb",
            "colcode": "sj",
            "wds": "[]",
            "dfwds": json.dumps(
                [
                    {"wdcode": "zb", "valuecode": config["group_code"]},
                    {"wdcode": "sj", "valuecode": config["period"]},
                ],
                ensure_ascii=False,
            ),
            "k1": str(int(time.time() * 1000)),
        }
        data = self._post_query(params)
        wdnodes = data["wdnodes"]
        indicator_nodes = {item["code"]: item for item in wdnodes[0]["nodes"]}
        time_nodes = {item["code"]: item for item in wdnodes[1]["nodes"]}

        rows: List[Dict[str, Any]] = []
        for node in data["datanodes"]:
            match = re.search(r"zb\.([^_]+)_sj\.([^_]+)", node["code"])
            if not match:
                continue
            series_code, period_code = match.groups()
            if series_code != config["series_code"]:
                continue
            node_data = node.get("data", {}) or {}
            value = node_data.get("data")
            if node_data.get("strdata", "") == "":
                continue
            if value in ("", None):
                continue
            rows.append(
                self._macro_row(
                    key="nbs",
                    config=config,
                    period_code=period_code,
                    period_label=time_nodes.get(period_code, {}).get(
                        "cname", period_code
                    ),
                    value_raw=float(value),
                    value=self._transform_value(float(value), config),
                    source="nbs_easyquery",
                    is_official=True,
                    is_proxy=False,
                    series_code=series_code,
                    series_label=indicator_nodes.get(series_code, {}).get(
                        "cname", config["label"]
                    ),
                )
            )

        rows.sort(key=lambda item: item["period_code"], reverse=True)
        return rows

    @staticmethod
    def _transform_value(value: float, config: Dict[str, Any]) -> float:
        if config.get("transform") == "index_minus_100":
            return round(value - 100, 2)
        return round(value, 2)

    def _macro_row(
        self,
        key: str,
        config: Dict[str, Any],
        period_code: str,
        period_label: str,
        value_raw: float,
        value: float,
        source: str,
        is_official: bool,
        is_proxy: bool,
        series_code: Optional[str] = None,
        series_label: Optional[str] = None,
        url: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        row = {
            "series_code": series_code or config.get("series_code", key),
            "series_label": series_label or config["label"],
            "period_code": period_code,
            "period_label": period_label,
            "value_raw": round(float(value_raw), 4),
            "value": round(float(value), 2),
            "unit": config.get("unit", ""),
            "source": source,
            "source_label": self.SOURCE_LABELS.get(source, source),
            "is_official": is_official,
            "is_proxy": is_proxy,
        }
        if url:
            row["source_url"] = url
        if note:
            row["note"] = note
        return row

    def _normalize_period(self, value: Any, period_type: str) -> tuple[str, str]:
        raw = str(value or "").strip()
        if not raw:
            return "", ""

        if period_type == "quarter":
            match = re.fullmatch(r"(\d{4})Q([1-4])", raw)
            if match:
                return raw, raw
            return self._extract_quarter_from_text(raw)

        if period_type == "quarter_date":
            match = re.search(r"(\d{4})[-/年](\d{1,2})", raw)
            if not match:
                return self._extract_quarter_from_text(raw)
            year = int(match.group(1))
            month = int(match.group(2))
            quarter = min(max((month - 1) // 3 + 1, 1), 4)
            code = f"{year}Q{quarter}"
            return code, code

        if period_type in {"month", "month_text"}:
            return self._extract_month_from_text(raw)

        return raw, raw

    @staticmethod
    def _period_sort_key(period_code: str) -> int:
        quarter_match = re.fullmatch(r"(\d{4})Q([1-4])", str(period_code))
        if quarter_match:
            return int(quarter_match.group(1)) * 10 + int(quarter_match.group(2))

        month_match = re.fullmatch(r"(\d{4})(\d{2})", str(period_code))
        if month_match:
            return int(month_match.group(1)) * 100 + int(month_match.group(2))

        digits = re.sub(r"\D", "", str(period_code))
        return int(digits[:8] or 0)

    @staticmethod
    def _extract_quarter_from_text(text: str) -> tuple[str, str]:
        quarter_map = {
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "1": 1,
            "2": 2,
            "3": 3,
            "4": 4,
        }
        match = re.search(r"(\d{4})年(?:第?([一二三四1-4])季度|([一二三四1-4])季度)", text)
        if match:
            year = int(match.group(1))
            quarter_token = match.group(2) or match.group(3)
            quarter = quarter_map[quarter_token]
            code = f"{year}Q{quarter}"
            return code, code

        match = re.search(r"(\d{4})Q([1-4])", text)
        if match:
            code = f"{match.group(1)}Q{match.group(2)}"
            return code, code
        return "", ""

    @staticmethod
    def _extract_month_from_text(text: str) -> tuple[str, str]:
        range_match = re.search(r"(\d{4})年(\d{1,2})\s*[—\-~至]\s*(\d{1,2})月份?", text)
        if range_match:
            year = int(range_match.group(1))
            start_month = int(range_match.group(2))
            end_month = int(range_match.group(3))
            return f"{year}{end_month:02d}", f"{year}年{start_month}-{end_month}月"

        match = re.search(r"(\d{4})年(\d{1,2})月份?", text)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            return f"{year}{month:02d}", f"{year}年{month:02d}月"

        match = re.search(r"(\d{4})[-/](\d{1,2})(?:[-/]\d{1,2})?", text)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            return f"{year}{month:02d}", f"{year}年{month:02d}月"

        match = re.fullmatch(r"(\d{4})(\d{2})", text)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            return f"{year}{month:02d}", f"{year}年{month:02d}月"
        return "", ""

    def _build_macro_snapshot(self, macro_series: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
        snapshot: Dict[str, Any] = {}
        for key, series in macro_series.items():
            if not series:
                continue
            latest = series[0]
            previous = series[1] if len(series) > 1 else None
            change = None
            if previous:
                change = round(latest["value"] - previous["value"], 2)

            snapshot[key] = {
                "label": self.NBS_SERIES_CONFIG[key]["label"],
                "value": latest["value"],
                "value_raw": latest["value_raw"],
                "unit": latest["unit"],
                "period_label": latest["period_label"],
                "previous_value": previous["value"] if previous else None,
                "previous_period_label": previous["period_label"] if previous else None,
                "change": change,
                "source": latest.get("source", ""),
                "source_label": latest.get("source_label", ""),
                "is_official": latest.get("is_official", False),
                "is_proxy": latest.get("is_proxy", False),
                "from_cache": latest.get("from_cache", False),
                "note": latest.get("note", ""),
            }
        return snapshot

    def _build_macro_tables(self, macro_series: Dict[str, List[Dict[str, Any]]]) -> Dict[str, pd.DataFrame]:
        tables: Dict[str, pd.DataFrame] = {}
        for key, series in macro_series.items():
            if not series:
                continue
            table = pd.DataFrame(
                [
                    {
                        "期间": item["period_label"],
                        "数值": item["value"],
                        "原始值": item["value_raw"],
                        "单位": item["unit"] or "-",
                        "来源": item.get("source_label", "-"),
                        "代理值": "是" if item.get("is_proxy") else "否",
                    }
                    for item in series
                ]
            )
            tables[key] = table
        return tables

    def _fetch_market_indices(self) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        for label, symbol in self.A_SHARE_INDEX_CONFIG.items():
            df = ak.stock_zh_index_daily(symbol=symbol)
            if df is None or df.empty:
                continue
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest
            pct_20 = self._calc_return(df, 20)
            pct_60 = self._calc_return(df, 60)
            result[label] = {
                "close": round(float(latest["close"]), 2),
                "date": str(latest["date"]),
                "daily_change_pct": round(
                    ((float(latest["close"]) - float(prev["close"])) / float(prev["close"])) * 100,
                    2,
                )
                if float(prev["close"]) != 0
                else 0.0,
                "pct_20d": pct_20,
                "pct_60d": pct_60,
            }
        return result

    @staticmethod
    def _calc_return(df: pd.DataFrame, days: int) -> float:
        if len(df) <= days:
            return 0.0
        latest = float(df.iloc[-1]["close"])
        base = float(df.iloc[-days - 1]["close"])
        if base == 0:
            return 0.0
        return round((latest - base) / base * 100, 2)

    def _fetch_macro_news(self, limit: int = 12) -> List[Dict[str, str]]:
        df = ak.stock_info_global_em()
        if df is None or df.empty:
            return []

        keywords = [
            "财政",
            "货币",
            "央行",
            "国常会",
            "国务院",
            "地产",
            "消费",
            "PMI",
            "CPI",
            "PPI",
            "失业率",
            "投资",
            "论坛",
        ]
        rows: List[Dict[str, str]] = []
        for _, row in df.iterrows():
            title = str(row.get("标题", ""))
            summary = str(row.get("摘要", ""))
            if keywords and not any(word in title or word in summary for word in keywords):
                continue
            rows.append(
                {
                    "title": title,
                    "summary": summary[:180],
                    "publish_time": str(row.get("发布时间", "")),
                    "url": str(row.get("链接", "")),
                }
            )
            if len(rows) >= limit:
                break
        return rows

    def build_rule_based_sector_view(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """在AI失败时仍能给出一份可解释的板块映射结果"""
        scores = {sector: 0 for sector in self.SECTOR_STOCK_POOLS.keys()}
        reasons = {sector: [] for sector in self.SECTOR_STOCK_POOLS.keys()}

        def value_of(key: str) -> Optional[float]:
            return snapshot.get(key, {}).get("value")

        def change_of(key: str) -> Optional[float]:
            return snapshot.get(key, {}).get("change")

        manufacturing_pmi = value_of("manufacturing_pmi")
        non_manufacturing_pmi = value_of("non_manufacturing_pmi")
        cpi_yoy = value_of("cpi_yoy")
        ppi_yoy = value_of("ppi_yoy")
        m2_yoy = value_of("m2_yoy")
        retail_sales_yoy = value_of("retail_sales_yoy")
        fixed_asset_yoy = value_of("fixed_asset_yoy")
        real_estate_yoy = value_of("real_estate_invest_yoy")
        unemployment = value_of("urban_unemployment")
        industrial_yoy = value_of("industrial_yoy")

        if m2_yoy is not None and m2_yoy >= 7:
            for sector in ["银行", "券商", "保险", "公用事业", "通信运营商"]:
                scores[sector] += 2
                reasons[sector].append("流动性保持充裕")

        if cpi_yoy is not None and cpi_yoy <= 1:
            for sector in ["银行", "公用事业", "食品饮料", "家电"]:
                scores[sector] += 1
                reasons[sector].append("通胀温和为估值修复留出空间")

        if manufacturing_pmi is not None and manufacturing_pmi >= 50:
            for sector in ["工程机械", "有色金属", "半导体", "算力AI", "软件信创"]:
                scores[sector] += 2
                reasons[sector].append("制造业景气改善")
        elif manufacturing_pmi is not None:
            for sector in ["工程机械", "有色金属", "半导体"]:
                scores[sector] -= 1
                reasons[sector].append("制造业景气仍在荣枯线下")

        if non_manufacturing_pmi is not None and non_manufacturing_pmi >= 50:
            for sector in ["旅游酒店", "食品饮料", "家电", "汽车整车"]:
                scores[sector] += 1
                reasons[sector].append("服务消费活跃度改善")

        if retail_sales_yoy is not None and retail_sales_yoy >= 4:
            for sector in ["食品饮料", "家电", "旅游酒店", "汽车整车"]:
                scores[sector] += 2
                reasons[sector].append("消费数据偏强")

        if fixed_asset_yoy is not None and fixed_asset_yoy >= 3:
            for sector in ["工程机械", "电网设备", "有色金属"]:
                scores[sector] += 2
                reasons[sector].append("投资端仍有托底")

        if industrial_yoy is not None and industrial_yoy >= 5:
            for sector in ["工程机械", "有色金属", "军工", "半导体"]:
                scores[sector] += 1
                reasons[sector].append("工业生产维持扩张")

        if ppi_yoy is not None and ppi_yoy < 0:
            for sector in ["煤炭", "石油石化", "有色金属"]:
                scores[sector] -= 1
                reasons[sector].append("工业品价格仍承压")

        if real_estate_yoy is not None and real_estate_yoy < 0:
            for sector in ["房地产", "建材家居"]:
                scores[sector] -= 3
                reasons[sector].append("地产投资仍弱")

        if unemployment is not None and unemployment >= 5.3:
            for sector in ["可选消费", "旅游酒店"]:
                if sector in scores:
                    scores[sector] -= 1
                    reasons[sector].append("就业压力抑制可选消费")

        bullish = sorted(
            [
                {
                    "sector": sector,
                    "score": score,
                    "logic": "；".join(reasons[sector][:3]) or "宏观环境相对受益",
                }
                for sector, score in scores.items()
                if score > 0
            ],
            key=lambda item: item["score"],
            reverse=True,
        )[:6]

        bearish = sorted(
            [
                {
                    "sector": sector,
                    "score": score,
                    "logic": "；".join(reasons[sector][:3]) or "宏观环境相对承压",
                }
                for sector, score in scores.items()
                if score < 0
            ],
            key=lambda item: item["score"],
        )[:4]

        return {
            "market_view": self._infer_market_view(snapshot),
            "bullish_sectors": bullish,
            "bearish_sectors": bearish,
            "watch_signals": self._build_watch_signals(snapshot),
        }

    def _infer_market_view(self, snapshot: Dict[str, Any]) -> str:
        growth_score = 0
        if snapshot.get("gdp_yoy", {}).get("value", 0) >= 4.5:
            growth_score += 1
        if snapshot.get("manufacturing_pmi", {}).get("value", 0) >= 50:
            growth_score += 1
        if snapshot.get("retail_sales_yoy", {}).get("value", 0) >= 4:
            growth_score += 1
        if snapshot.get("real_estate_invest_yoy", {}).get("value", 0) < 0:
            growth_score -= 1
        if snapshot.get("urban_unemployment", {}).get("value", 0) >= 5.3:
            growth_score -= 1

        if growth_score >= 2:
            return "震荡偏多"
        if growth_score <= -1:
            return "震荡偏谨慎"
        return "结构性机会为主"

    def _build_watch_signals(self, snapshot: Dict[str, Any]) -> List[str]:
        signals = []
        for key in ["manufacturing_pmi", "retail_sales_yoy", "m2_yoy", "real_estate_invest_yoy"]:
            item = snapshot.get(key)
            if not item:
                continue
            signals.append(
                f"{item['label']} 最新 {item['period_label']} 为 {item['value']}{item['unit']}，"
                f"较上一期变动 {item['change']:+.2f}{item['unit'] if item['change'] is not None else ''}"
                if item.get("change") is not None
                else f"{item['label']} 最新 {item['period_label']} 为 {item['value']}{item['unit']}"
            )
        return signals

    def build_stock_candidates_for_sectors(
        self, sectors: List[str], limit_per_sector: int = 3, total_limit: int = 12
    ) -> List[Dict[str, Any]]:
        selected_sector_keys: List[str] = []
        for sector in sectors:
            matched = self._match_sector_keys(sector)
            for key in matched:
                if key not in selected_sector_keys:
                    selected_sector_keys.append(key)

        if not selected_sector_keys:
            selected_sector_keys = ["银行", "公用事业", "食品饮料", "半导体"]

        candidates: List[Dict[str, Any]] = []
        for sector_key in selected_sector_keys:
            for stock in self.SECTOR_STOCK_POOLS.get(sector_key, [])[:limit_per_sector]:
                enriched = self._enrich_stock_snapshot(stock["code"], stock["name"], sector_key)
                if enriched:
                    candidates.append(enriched)
                if len(candidates) >= total_limit:
                    return candidates
        return candidates

    def _match_sector_keys(self, sector_name: str) -> List[str]:
        if sector_name in self.SECTOR_STOCK_POOLS:
            return [sector_name]

        matches = [
            key for key in self.SECTOR_STOCK_POOLS.keys() if sector_name in key or key in sector_name
        ]
        if matches:
            return matches

        for alias, mapped in self.SECTOR_ALIASES.items():
            if alias in sector_name:
                return mapped
        return []

    def _enrich_stock_snapshot(
        self, code: str, fallback_name: str, sector_name: str
    ) -> Optional[Dict[str, Any]]:
        info_map = {}
        try:
            info_df = ak.stock_individual_info_em(symbol=code)
            if info_df is not None and not info_df.empty:
                info_map = {
                    str(row["item"]).strip(): str(row["value"]).strip()
                    for _, row in info_df.iterrows()
                }
        except Exception as exc:
            self.logger.warning("获取个股静态信息失败 %s: %s", code, exc)

        try:
            start_date = (datetime.now() - timedelta(days=180)).strftime("%Y%m%d")
            end_date = datetime.now().strftime("%Y%m%d")
            hist_df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq",
            )
            if hist_df is None or hist_df.empty:
                return {
                    "code": code,
                    "name": info_map.get("股票简称", fallback_name),
                    "sector": sector_name,
                    "industry": info_map.get("行业", sector_name),
                    "price": None,
                    "daily_change_pct": None,
                    "change_amount": None,
                    "turnover_rate": None,
                    "volume": None,
                    "pe_ratio": self._to_float(info_map.get("市盈率(动态)")),
                    "pb_ratio": self._to_float(info_map.get("市净率")),
                    "market_cap": self._to_float(info_map.get("总市值")),
                    "recent_20d_return": None,
                    "recent_60d_return": None,
                    "listed_date": info_map.get("上市时间", ""),
                }

            latest = hist_df.iloc[-1]

            return {
                "code": code,
                "name": info_map.get("股票简称", fallback_name),
                "sector": sector_name,
                "industry": info_map.get("行业", sector_name),
                "price": round(float(latest["收盘"]), 2),
                "daily_change_pct": round(float(latest["涨跌幅"]), 2),
                "change_amount": round(float(latest["涨跌额"]), 2),
                "turnover_rate": self._to_float(latest.get("换手率")),
                "volume": self._to_float(latest.get("成交量")),
                "pe_ratio": self._to_float(info_map.get("市盈率(动态)")),
                "pb_ratio": self._to_float(info_map.get("市净率")),
                "market_cap": self._to_float(info_map.get("总市值")),
                "recent_20d_return": self._calc_hist_return(hist_df, 20),
                "recent_60d_return": self._calc_hist_return(hist_df, 60),
                "listed_date": info_map.get("上市时间", ""),
            }
        except Exception as exc:
            self.logger.warning("获取候选股数据失败 %s: %s", code, exc)
            return {
                "code": code,
                "name": info_map.get("股票简称", fallback_name),
                "sector": sector_name,
                "industry": info_map.get("行业", sector_name),
                "price": None,
                "daily_change_pct": None,
                "change_amount": None,
                "turnover_rate": None,
                "volume": None,
                "pe_ratio": self._to_float(info_map.get("市盈率(动态)")),
                "pb_ratio": self._to_float(info_map.get("市净率")),
                "market_cap": self._to_float(info_map.get("总市值")),
                "recent_20d_return": None,
                "recent_60d_return": None,
                "listed_date": info_map.get("上市时间", ""),
            }

    @staticmethod
    def _calc_hist_return(hist_df: pd.DataFrame, days: int) -> float:
        if len(hist_df) <= days:
            return 0.0
        latest = float(hist_df.iloc[-1]["收盘"])
        base = float(hist_df.iloc[-days - 1]["收盘"])
        if base == 0:
            return 0.0
        return round((latest - base) / base * 100, 2)

    @staticmethod
    def _to_float(value: Any) -> Optional[float]:
        if value in (None, "", "-", "--"):
            return None
        try:
            return round(float(str(value).replace(",", "")), 2)
        except Exception:
            return None

    def build_prompt_context(self, data: Dict[str, Any]) -> str:
        snapshot = data.get("macro_snapshot", {})
        lines = ["===== 当前国内宏观数据快照（多源校验） ====="]
        for key in self.CORE_MACRO_KEYS:
            item = snapshot.get(key)
            if not item:
                continue
            change_str = (
                f"，较上一期变动 {item['change']:+.2f}{item['unit']}"
                if item.get("change") is not None
                else ""
            )
            source_label = item.get("source_label") or "未知来源"
            proxy_label = "，代理值" if item.get("is_proxy") else ""
            lines.append(
                f"- {item['label']}: {item['value']}{item['unit']} "
                f"({item['period_label']}，来源：{source_label}{proxy_label}){change_str}"
            )
            if item.get("note"):
                lines.append(f"  口径说明：{item['note']}")

        lines.append("")
        lines.append("===== A股指数快照 =====")
        for name, info in data.get("market_indices", {}).items():
            lines.append(
                f"- {name}: {info['close']}，日涨跌 {info['daily_change_pct']:+.2f}%，20日 {info['pct_20d']:+.2f}%，60日 {info['pct_60d']:+.2f}%"
            )

        if data.get("news"):
            lines.append("")
            lines.append("===== 宏观新闻样本 =====")
            for item in data["news"][:8]:
                lines.append(
                    f"- {item['publish_time']} | {item['title']} | {item['summary']}"
                )

        lines.append("")
        lines.append("===== 可选行业板块池（供AI输出时严格从中选择） =====")
        lines.append("、".join(self.SECTOR_STOCK_POOLS.keys()))
        return "\n".join(lines)
