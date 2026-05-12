"""
数据源管理器
实现Tushare优先、AKShare降级和本地每日缓存机制
"""

import os
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from typing import Optional

from src.aiagents_stock.integrations.market_data.cache import LocalDataCache

# 加载环境变量
load_dotenv()


class DataSourceManager:
    """数据源管理器 - Tushare优先，AKShare作为实时/特色数据降级源"""

    def __init__(self, tushare_api=None, cache: Optional[LocalDataCache] = None, start_cache_scheduler: bool = True):
        self.tushare_token = os.getenv('TUSHARE_TOKEN', '')
        self.tushare_available = False
        self.tushare_api = tushare_api
        self.cache = cache or LocalDataCache()

        # 初始化tushare
        if self.tushare_api is not None:
            self.tushare_available = True
        elif self.tushare_token:
            try:
                import tushare as ts
                ts.set_token(self.tushare_token)
                self.tushare_api = ts.pro_api(self.tushare_token)
                self.tushare_available = True
                print("✅ Tushare数据源初始化成功")
            except Exception as e:
                print(f"⚠️ Tushare数据源初始化失败: {e}")
                self.tushare_available = False
        else:
            print("ℹ️ 未配置Tushare Token，将仅使用Akshare数据源")

        if start_cache_scheduler:
            self.cache.start_daily_auto_update(os.getenv("MARKET_DATA_CACHE_UPDATE_TIME", "18:30"))
    
    def get_stock_hist_data(self, symbol, start_date=None, end_date=None, adjust='qfq'):
        """
        获取股票历史数据（优先Tushare，失败时使用AKShare）
        
        Args:
            symbol: 股票代码（6位数字）
            start_date: 开始日期（格式：'20240101'或'2024-01-01'）
            end_date: 结束日期
            adjust: 复权类型（'qfq'前复权, 'hfq'后复权, ''不复权）
            
        Returns:
            DataFrame: 包含日期、开盘、收盘、最高、最低、成交量等列
        """
        # 标准化日期格式
        if start_date:
            start_date = start_date.replace('-', '')
        if end_date:
            end_date = end_date.replace('-', '')
        else:
            end_date = datetime.now().strftime('%Y%m%d')
        
        # 优先使用Tushare，并写入每日本地缓存
        if self.tushare_available:
            try:
                print(f"[Tushare] 正在获取 {symbol} 的历史数据...")
                df = self._get_tushare_hist_data(symbol, start_date, end_date, adjust)
                if df is not None and not df.empty:
                    print(f"[Tushare] ✅ 成功获取 {len(df)} 条数据")
                    return df
            except Exception as e:
                print(f"[Tushare] ❌ 获取失败: {e}")

        # Tushare失败，降级到AKShare
        try:
            import akshare as ak
            print(f"[Akshare] 正在获取 {symbol} 的历史数据（备用数据源）...")
            
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust=adjust
            )
            
            if df is not None and not df.empty:
                # 标准化列名
                df = df.rename(columns={
                    '日期': 'date',
                    '开盘': 'open',
                    '收盘': 'close',
                    '最高': 'high',
                    '最低': 'low',
                    '成交量': 'volume',
                    '成交额': 'amount',
                    '振幅': 'amplitude',
                    '涨跌幅': 'pct_change',
                    '涨跌额': 'change',
                    '换手率': 'turnover'
                })
                df['date'] = pd.to_datetime(df['date'])
                print(f"[Akshare] ✅ 成功获取 {len(df)} 条数据")
                return df
        except Exception as e:
            print(f"[Akshare] ❌ 获取失败: {e}")
        
        # 两个数据源都失败
        print("❌ 所有数据源均获取失败")
        return None
    
    def get_stock_basic_info(self, symbol):
        """
        获取股票基本信息（优先Tushare，失败时使用AKShare）
        
        Args:
            symbol: 股票代码
            
        Returns:
            dict: 股票基本信息
        """
        info = {
            "symbol": symbol,
            "name": "未知",
            "industry": "未知",
            "market": "未知"
        }
        
        # 优先使用Tushare基础信息 + daily_basic估值字段
        if self.tushare_available:
            try:
                print(f"[Tushare] 正在获取 {symbol} 的基本信息...")
                ts_code = self._convert_to_ts_code(symbol)
                basic_df = self._cache_call(
                    "stock_basic",
                    {"ts_code": ts_code, "fields": "ts_code,name,area,industry,market,list_date"},
                    lambda: self.tushare_api.stock_basic(
                        ts_code=ts_code,
                        fields='ts_code,name,area,industry,market,list_date'
                    ),
                )

                if basic_df is not None and not basic_df.empty:
                    row = basic_df.iloc[0]
                    info['name'] = row.get('name', info['name'])
                    info['industry'] = row.get('industry', info['industry'])
                    info['market'] = row.get('market', info['market'])
                    info['area'] = row.get('area', '')
                    info['list_date'] = row.get('list_date', '')

                daily_basic = self.get_latest_daily_basic(symbol)
                if daily_basic is not None and not daily_basic.empty:
                    row = daily_basic.iloc[0]
                    info['pe_ratio'] = row.get('pe_ttm', row.get('pe', 'N/A'))
                    info['pb_ratio'] = row.get('pb', 'N/A')
                    info['market_cap'] = row.get('total_mv', 'N/A')
                    info['circulating_market_cap'] = row.get('circ_mv', 'N/A')
                    info['turnover_rate'] = row.get('turnover_rate', 'N/A')
                    info['trade_date'] = row.get('trade_date', '')

                if info['name'] != "未知" or info.get('pe_ratio') != 'N/A':
                    print(f"[Tushare] ✅ 成功获取基本信息")
                    return info
            except Exception as e:
                print(f"[Tushare] ❌ 获取失败: {e}")

        # Tushare失败，降级到AKShare
        try:
            import akshare as ak
            print(f"[Akshare] 正在获取 {symbol} 的基本信息（备用数据源）...")
            
            stock_info = ak.stock_individual_info_em(symbol=symbol)
            if stock_info is not None and not stock_info.empty:
                for _, row in stock_info.iterrows():
                    key = row['item']
                    value = row['value']
                    
                    if key == '股票简称':
                        info['name'] = value
                    elif key == '所处行业':
                        info['industry'] = value
                    elif key == '上市时间':
                        info['list_date'] = value
                    elif key == '总市值':
                        info['market_cap'] = value
                    elif key == '流通市值':
                        info['circulating_market_cap'] = value
                
                print(f"[Akshare] ✅ 成功获取基本信息")
                return info
        except Exception as e:
            print(f"[Akshare] ❌ 获取失败: {e}")
        
        return info
    
    def get_realtime_quotes(self, symbol):
        """
        获取行情快照数据（优先Tushare盘后数据，失败时使用AKShare实时快照）
        
        Args:
            symbol: 股票代码
            
        Returns:
            dict: 实时行情数据
        """
        quotes = {}
        
        # 优先使用Tushare盘后数据。Tushare不是严格盘中实时源，但适合作为每日缓存快照。
        if self.tushare_available:
            try:
                print(f"[Tushare] 正在获取 {symbol} 的行情快照...")
                daily_basic = self.get_latest_daily_basic(symbol)
                if daily_basic is None or daily_basic.empty:
                    daily_basic = pd.DataFrame()
                    trade_date = None
                else:
                    trade_date = daily_basic.iloc[0].get('trade_date')

                ts_code = self._convert_to_ts_code(symbol)
                daily_df = self._cache_call(
                    "daily_snapshot",
                    {"ts_code": ts_code, "trade_date": trade_date},
                    lambda: self.tushare_api.daily(
                        ts_code=ts_code,
                        trade_date=trade_date,
                        fields='ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount'
                    ) if trade_date else self.tushare_api.daily(ts_code=ts_code, end_date=datetime.now().strftime('%Y%m%d')),
                )

                if daily_df is not None and not daily_df.empty:
                    row = daily_df.sort_values('trade_date', ascending=False).iloc[0]
                    basic_row = daily_basic.iloc[0] if not daily_basic.empty else {}
                    quotes = {
                        'symbol': symbol,
                        'name': self.get_stock_basic_info(symbol).get('name', 'N/A'),
                        'price': row.get('close'),
                        'change_percent': row.get('pct_chg'),
                        'change': row.get('change'),
                        'volume': row.get('vol', 0) * 100,
                        'amount': row.get('amount', 0) * 1000,
                        'high': row.get('high'),
                        'low': row.get('low'),
                        'open': row.get('open'),
                        'pre_close': row.get('pre_close'),
                        'turnover_rate': basic_row.get('turnover_rate', 'N/A') if hasattr(basic_row, 'get') else 'N/A',
                        'trade_date': row.get('trade_date'),
                        'data_source': 'tushare'
                    }
                    print(f"[Tushare] ✅ 成功获取行情快照")
                    return quotes
            except Exception as e:
                print(f"[Tushare] ❌ 获取失败: {e}")

        # Tushare失败，降级到AKShare实时快照
        try:
            import akshare as ak
            print(f"[Akshare] 正在获取 {symbol} 的实时行情（备用数据源）...")
            
            df = ak.stock_zh_a_spot_em()
            stock_df = df[df['代码'] == symbol]
            
            if not stock_df.empty:
                row = stock_df.iloc[0]
                quotes = {
                    'symbol': symbol,
                    'name': row['名称'],
                    'price': row['最新价'],
                    'change_percent': row['涨跌幅'],
                    'change': row['涨跌额'],
                    'volume': row['成交量'],
                    'amount': row['成交额'],
                    'high': row['最高'],
                    'low': row['最低'],
                    'open': row['今开'],
                    'pre_close': row['昨收']
                }
                print(f"[Akshare] ✅ 成功获取实时行情")
                return quotes
        except Exception as e:
            print(f"[Akshare] ❌ 获取失败: {e}")
        
        return quotes
    
    def get_financial_data(self, symbol, report_type='income'):
        """
        获取财务数据（优先Tushare，失败时使用AKShare）
        
        Args:
            symbol: 股票代码
            report_type: 报表类型（'income'利润表, 'balance'资产负债表, 'cashflow'现金流量表）
            
        Returns:
            DataFrame: 财务数据
        """
        # 优先使用Tushare
        if self.tushare_available:
            try:
                print(f"[Tushare] 正在获取 {symbol} 的财务数据...")
                df = self._get_tushare_financial_data(symbol, report_type)
                if df is not None and not df.empty:
                    print(f"[Tushare] ✅ 成功获取财务数据")
                    return df
            except Exception as e:
                print(f"[Tushare] ❌ 获取失败: {e}")

        # Tushare失败，降级到AKShare
        try:
            import akshare as ak
            print(f"[Akshare] 正在获取 {symbol} 的财务数据（备用数据源）...")
            
            if report_type == 'income':
                df = ak.stock_financial_report_sina(stock=symbol, symbol="利润表")
            elif report_type == 'balance':
                df = ak.stock_financial_report_sina(stock=symbol, symbol="资产负债表")
            elif report_type == 'cashflow':
                df = ak.stock_financial_report_sina(stock=symbol, symbol="现金流量表")
            else:
                df = None
            
            if df is not None and not df.empty:
                print(f"[Akshare] ✅ 成功获取财务数据")
                return df
        except Exception as e:
            print(f"[Akshare] ❌ 获取失败: {e}")

        return None

    def get_latest_daily_basic(self, symbol):
        """获取最近一个交易日的估值/换手/市值数据。"""
        if not self.tushare_available:
            return None

        ts_code = self._convert_to_ts_code(symbol)
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
        fields = 'ts_code,trade_date,close,turnover_rate,turnover_rate_f,volume_ratio,pe,pe_ttm,pb,total_mv,circ_mv'
        df = self._cache_call(
            "daily_basic_latest",
            {"ts_code": ts_code, "start_date": start_date, "end_date": end_date, "fields": fields},
            lambda: self.tushare_api.daily_basic(
                ts_code=ts_code,
                start_date=start_date,
                end_date=end_date,
                fields=fields
            ),
        )
        if df is not None and not df.empty and 'trade_date' in df.columns:
            df = df.sort_values('trade_date', ascending=False).head(1).reset_index(drop=True)
        return df

    def get_moneyflow_data(self, symbol, start_date=None, end_date=None):
        """获取个股资金流数据（Tushare moneyflow，带每日缓存）。"""
        if not self.tushare_available:
            return None
        ts_code = self._convert_to_ts_code(symbol)
        end_date = (end_date or datetime.now().strftime('%Y%m%d')).replace('-', '')
        start_date = (start_date or (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')).replace('-', '')
        return self._cache_call(
            "moneyflow",
            {"ts_code": ts_code, "start_date": start_date, "end_date": end_date},
            lambda: self.tushare_api.moneyflow(ts_code=ts_code, start_date=start_date, end_date=end_date),
        )

    def get_financial_indicator_data(self, symbol):
        """获取财务指标数据（Tushare fina_indicator，带每日缓存）。"""
        if not self.tushare_available:
            return None
        ts_code = self._convert_to_ts_code(symbol)
        return self._cache_call(
            "fina_indicator",
            {"ts_code": ts_code},
            lambda: self.tushare_api.fina_indicator(ts_code=ts_code),
        )

    def _get_tushare_hist_data(self, symbol, start_date=None, end_date=None, adjust='qfq'):
        ts_code = self._convert_to_ts_code(symbol)
        start_date = start_date.replace('-', '') if start_date else None
        end_date = (end_date.replace('-', '') if end_date else datetime.now().strftime('%Y%m%d'))
        adjust = adjust or ''

        def fetch():
            if adjust in ('qfq', 'hfq'):
                import tushare as ts
                return ts.pro_bar(ts_code=ts_code, start_date=start_date, end_date=end_date, adj=adjust)
            return self.tushare_api.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)

        df = self._cache_call(
            "hist_daily",
            {"ts_code": ts_code, "start_date": start_date, "end_date": end_date, "adjust": adjust},
            fetch,
        )
        return self._normalize_tushare_daily(df)

    def _get_tushare_financial_data(self, symbol, report_type='income'):
        ts_code = self._convert_to_ts_code(symbol)
        fetchers = {
            'income': self.tushare_api.income,
            'balance': self.tushare_api.balancesheet,
            'cashflow': self.tushare_api.cashflow,
        }
        fetcher = fetchers.get(report_type)
        if not fetcher:
            return None
        return self._cache_call(
            f"financial_{report_type}",
            {"ts_code": ts_code},
            lambda: fetcher(ts_code=ts_code),
        )

    def _normalize_tushare_daily(self, df):
        if df is None or df.empty:
            return df
        df = df.copy()
        df = df.rename(columns={
            'trade_date': 'date',
            'vol': 'volume',
            'pct_chg': 'pct_change',
        })
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)
        if 'volume' in df.columns:
            df['volume'] = pd.to_numeric(df['volume'], errors='coerce') * 100
        if 'amount' in df.columns:
            df['amount'] = pd.to_numeric(df['amount'], errors='coerce') * 1000
        return df

    def _cache_call(self, namespace, params, fetcher):
        return self.cache.get_or_fetch(namespace, params, fetcher)
    
    def _convert_to_ts_code(self, symbol):
        """
        将6位股票代码转换为tushare格式（带市场后缀）
        
        Args:
            symbol: 6位股票代码
            
        Returns:
            str: tushare格式代码（如：000001.SZ）
        """
        if not symbol or len(symbol) != 6:
            return symbol
        
        # 根据代码判断市场
        if symbol.startswith('6'):
            # 上海主板
            return f"{symbol}.SH"
        elif symbol.startswith('0') or symbol.startswith('3'):
            # 深圳主板和创业板
            return f"{symbol}.SZ"
        elif symbol.startswith('8') or symbol.startswith('4'):
            # 北交所
            return f"{symbol}.BJ"
        else:
            # 默认深圳
            return f"{symbol}.SZ"
    
    def _convert_from_ts_code(self, ts_code):
        """
        将tushare格式代码转换为6位代码
        
        Args:
            ts_code: tushare格式代码（如：000001.SZ）
            
        Returns:
            str: 6位股票代码
        """
        if '.' in ts_code:
            return ts_code.split('.')[0]
        return ts_code


# 全局数据源管理器实例
data_source_manager = DataSourceManager()
