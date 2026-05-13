# AKShare 与 Tushare 替代检查

检查日期：2026-05-12

当前权限假设：Tushare 账户有 2000 积分，未额外开通实时、分钟线、新闻资讯、港股日线/财报等独立权限。

## 结论

项目中并不是所有 AKShare 调用都能在当前 2000 积分权限下替换为 Tushare。当前代码里共检查到 12 个 Python 文件、43 个函数位置存在 AKShare 接口引用，按接口引用点计约 69 处。

整体状态如下：

| 状态 | 说明 | 代表模块 |
|------|------|----------|
| 2000 积分可替换 | Tushare 常规权限可覆盖，适合改成 Tushare 优先 | A 股日线/K 线、基础信息、估值、市值、财务三表、财务指标、个股资金流、北向资金、两融、指数日线、核心宏观、期货日线 |
| 有 Tushare 接口但当前权限不足 | Tushare 有对应接口，但需要 5000/6000/8000 积分或独立权限 | 涨跌停池、东财/同花顺板块、板块资金流、盘中实时、分钟线、港股日线/财务、新闻资讯 |
| 当前代码已有 fallback | AKShare 失败后会降级到 Tushare，但默认仍是 AKShare 优先，且部分字段口径需要修正 | `integrations/market_data/providers.py`、`smart_monitor/data.py`、`smart_monitor/kline.py`、`fund_flow.py` |
| 不建议直接替换 | Tushare 未找到同口径接口，或数据维度不是自然等价 | 财新 PMI、房地产宏观、个股新闻按股票聚合 |

关键判断：

1. 2000 积分下，可以推进“默认使用 Tushare 做 A 股盘后行情、基础信息、估值、财务、资金流、两融、指数日线和核心宏观”。
2. 2000 积分下，不应把盘中实时、分钟线、新闻、港股日线/财务、涨跌停池、板块/概念表现、板块资金流改成 Tushare 默认源。
3. 当前已有 Tushare fallback 的地方，多数仍是 AKShare 优先；真正切默认源需要调整调用顺序和统一适配层。
4. 后续如果积分升到 5000/6000/8000 或开通独立权限，涨跌停、板块、新闻、港股等模块可重新评估。

## 逐文件检查

### `src/aiagents_stock/integrations/market_data/providers.py`

集中数据源管理器，当前是 AKShare 优先、Tushare fallback。

| 函数 | AKShare 接口 | Tushare 对应 | 检查结论 |
|------|--------------|--------------|----------|
| `get_stock_hist_data` | `stock_zh_a_hist` | `daily` | 有 fallback，但当前代码把 `adj` 传给 `daily`，疑似不符合 Tushare Pro `daily` 用法；复权数据应考虑 `pro_bar` 或 `adj_factor` |
| `get_stock_basic_info` | `stock_individual_info_em` | `stock_basic` | 有 fallback，但 `stock_basic` 不覆盖 PE/PB、市值等实时/估值字段；需要补 `daily_basic` |
| `get_realtime_quotes` | `stock_zh_a_spot_em` | `daily`/`daily_basic` 盘后替代；实时接口需独立权限 | 2000 积分不能替换盘中实时，只能替换盘后快照 |
| `get_financial_data` | `stock_financial_report_sina` | `income`、`balancesheet`、`cashflow` | 有较清晰 fallback，适合改成 Tushare 优先 |

建议：这个文件最适合作为后续统一替换入口，但需要先把日线复权、实时行情、估值字段补齐。

### `src/aiagents_stock/features/smart_monitor/data.py`

实时监测数据模块，当前链路大致是 TDX 优先，其次 AKShare，再 Tushare。

| 函数 | AKShare 接口 | Tushare 对应 | 检查结论 |
|------|--------------|--------------|----------|
| `get_realtime_quote` | `stock_individual_info_em`、`stock_zh_a_hist_min_em`、`stock_zh_a_hist` | `stock_basic`、`daily_basic`、`daily`；分钟/实时需独立权限 | 基础信息和盘后行情可替换；2000 积分不能替换分钟/实时 |
| `get_technical_indicators` | `stock_zh_a_hist` | `daily` | 有 fallback，可改为 Tushare 优先 |
| `get_main_force_flow` | `stock_individual_fund_flow_rank` | `moneyflow` | 有 fallback，但主力资金流在综合数据里当前被注释停用 |

建议：技术指标可以优先改 Tushare；实时行情仍应保留 TDX 或 AKShare 作为实时数据补充。

### `src/aiagents_stock/features/smart_monitor/kline.py`

K 线模块当前是 TDX 优先、AKShare 次之、Tushare fallback。

| 函数 | AKShare 接口 | Tushare 对应 | 检查结论 |
|------|--------------|--------------|----------|
| `get_kline_data` | `stock_zh_a_hist` | `daily` | 有 fallback，但同样存在复权参数问题；建议改为 `pro_bar` 或统一复权计算 |

### `src/aiagents_stock/features/stock_analysis/fund_flow.py`

| 函数 | AKShare 接口 | Tushare 对应 | 检查结论 |
|------|--------------|--------------|----------|
| `_get_individual_fund_flow` | `stock_individual_fund_flow` | `moneyflow` | 有 fallback，适合改成 Tushare 优先 |

### `src/aiagents_stock/features/stock_analysis/data.py`

股票分析核心数据模块，覆盖 A 股、港股、财务、估值等。这里不是完整替代状态。

| 函数 | AKShare 接口 | Tushare 对应 | 检查结论 |
|------|--------------|--------------|----------|
| `_get_chinese_stock_info` | `stock_individual_info_em` | `stock_basic`、`daily_basic` | 部分 fallback，但只有异常路径或字段缺失时才用 Tushare；默认仍依赖 AKShare |
| `_get_chinese_stock_info` | `stock_zh_valuation_baidu` | `daily_basic` | 代码里没有 Tushare fallback；PE/PB/市值应改由 `daily_basic` 补齐 |
| `_get_chinese_stock_data` | 通过 `DataSourceManager.stock_zh_a_hist` | `daily` | 间接有 fallback，但默认仍是 AKShare |
| `_get_chinese_financial_data` | `stock_financial_abstract_ths`、`stock_financial_abstract` | `income`、`balancesheet`、`cashflow`、`fina_indicator` | 没有直接 fallback；这是 A 股财务替换的重点 |
| `_get_hk_stock_info`、`_get_hk_stock_data`、`_get_hk_financial_data` | `stock_hk_spot_em`、`stock_hk_hist`、`stock_hk_financial_indicator_em` | `hk_basic` 可替换基础列表；`hk_daily`/`hk_fina_indicator` 需独立权限或更高权限 | 2000 积分只适合替换港股基础信息，不适合替换港股行情/财务 |

建议：A 股基础信息、估值、财务可以系统性补 Tushare；港股应单独保留 AKShare/yfinance 链路。

### `src/aiagents_stock/features/stock_analysis/quarterly_report_data.py`

季报数据当前完全依赖 AKShare。

| 函数 | AKShare 接口 | Tushare 对应 | 检查结论 |
|------|--------------|--------------|----------|
| `_get_income_statement` | `stock_financial_report_sina` | `income` | 未替代 |
| `_get_balance_sheet` | `stock_financial_report_sina` | `balancesheet` | 未替代 |
| `_get_cash_flow` | `stock_financial_report_sina` | `cashflow` | 未替代 |
| `_get_financial_indicators` | `stock_financial_abstract` | `fina_indicator` | 未替代 |

建议：这里是最适合做 Tushare 优先改造的模块之一，字段映射成本可控。

### `src/aiagents_stock/features/stock_analysis/market_sentiment_data.py`

市场情绪模块是部分替代。

| 函数 | AKShare 接口 | Tushare 对应 | 检查结论 |
|------|--------------|--------------|----------|
| `_get_turnover_rate` | `stock_zh_a_spot_em` | `daily_basic` | 有 fallback |
| `_get_market_index_sentiment` | `stock_zh_index_spot_em` | `index_daily` | 指数涨跌有 fallback，但涨跌家数仍依赖 AKShare 全市场快照 |
| `_get_limit_up_down_stats` | `stock_zt_pool_em`、`stock_zt_pool_dtgc_em` | `limit_list_d`、`limit_list_ths` | Tushare 有接口，但 2000 积分不能调用；`limit_list_d` 需 5000，`limit_list_ths` 需 8000 |
| `_get_margin_trading_data` | `stock_margin_underlying_info_szse`、`stock_margin_szsh` | `margin_secs`、`margin`、`margin_detail` | 2000 积分可替换；需要对齐“标的列表”和“两融汇总/明细”的字段口径 |
| `_get_fear_greed_index` | `stock_zh_a_spot_em` | 部分可由 `daily_basic`/行情列表聚合 | 未替代 |

建议：换默认源时要把“指数行情”和“市场宽度/涨跌停/融资融券”拆开处理，不能用一个 Tushare 接口覆盖。

### `src/aiagents_stock/features/sector_strategy/data.py`

智策板块模块大部分仍依赖 AKShare。

| 函数 | AKShare 接口 | Tushare 对应 | 检查结论 |
|------|--------------|--------------|----------|
| `_get_sector_performance` | `stock_board_industry_name_em` | `dc_index`、`dc_daily`、`ths_index`、`ths_daily` | Tushare 有接口，但通常需 6000 积分；2000 积分不能替换 |
| `_get_concept_performance` | `stock_board_concept_name_em` | `dc_index`、`dc_daily`、`ths_index`、`ths_daily` | Tushare 有接口，但通常需 6000 积分；2000 积分不能替换 |
| `_get_sector_fund_flow` | `stock_sector_fund_flow_rank` | `moneyflow_ind_dc`、`moneyflow_ind_ths`、`moneyflow_cnt_ths` | Tushare 有接口，但需 6000 积分；2000 积分不能替换 |
| `_get_market_overview` | `stock_zh_a_spot_em`、`stock_zh_index_spot_em` | `daily_basic`、`index_daily` | 盘后可部分替换；盘中实时不能替换 |
| `_get_north_money_flow` | `stock_hsgt_fund_flow_summary_em` | `moneyflow_hsgt` | 已经是 Tushare 优先，AKShare fallback |
| `_get_financial_news` | `stock_news_em` | `news`、`major_news` | Tushare 新闻需独立权限，2000 积分不能替换 |

建议：北向资金已经符合目标；板块/概念/板块资金流在 2000 积分下不能替换，新闻需要独立权限。

### `src/aiagents_stock/features/macro_cycle/data.py`

宏观周期模块几乎全部是 AKShare 宏观和期货接口，没有 Tushare fallback。

| 数据类型 | AKShare 接口 | Tushare 对应 | 检查结论 |
|----------|--------------|--------------|----------|
| GDP/CPI/PPI/货币供应 | `macro_china_gdp`、`macro_china_cpi_monthly`、`macro_china_ppi_yearly`、`macro_china_money_supply` | `cn_gdp`、`cn_cpi`、`cn_ppi`、`cn_m` | 2000 积分可替换 |
| PMI/LPR | `macro_china_pmi_yearly`、`macro_china_lpr` | `cn_pmi`、`shibor_lpr` | 2000 积分可替换 |
| 财新 PMI/房地产 | `macro_china_cx_pmi_yearly`、`macro_china_real_estate` | 未找到明确同口径接口 | 不建议直接替换 |
| 指数 | `stock_zh_index_daily` | `index_daily` | 可替代但未实现 |
| 商品期货 | `futures_main_sina` | `fut_mapping` + `fut_daily` | 2000 积分可替换，但要先做主连/交易所代码映射 |
| 宏观新闻 | `stock_info_global_em` | `news`、`major_news` | 新闻需独立权限，2000 积分不能替换 |

建议：宏观数据不应一刀切改 Tushare。项目里 `macro_analysis/data.py` 已有国家统计局接口，核心宏观指标可以优先走官方接口。

### `src/aiagents_stock/features/macro_analysis/data.py`

宏观分析模块核心宏观数据主要走国家统计局接口，AKShare 只用于市场指数、新闻和股票快照补充。

| 函数 | AKShare 接口 | Tushare 对应 | 检查结论 |
|------|--------------|--------------|----------|
| `_fetch_market_indices` | `stock_zh_index_daily` | `index_daily` | 可替代但未实现 |
| `_fetch_macro_news` | `stock_info_global_em` | `news`、`major_news` | Tushare 新闻需独立权限，2000 积分不能替换 |
| `_enrich_stock_snapshot` | `stock_individual_info_em`、`stock_zh_a_hist` | `stock_basic`、`daily_basic`、`daily`/`pro_bar` | 可替代但未实现 |

### `src/aiagents_stock/features/stock_analysis/qstock_news_data.py`

新闻数据完全依赖 AKShare。

| 函数 | AKShare 接口 | Tushare 对应 | 检查结论 |
|------|--------------|--------------|----------|
| `_get_news_data` | `stock_news_em`、`stock_news_sina`、`stock_news_cls`、`stock_zh_a_spot_em` | `news`、`major_news` 可做资讯源替代；个股名需另行过滤 | 新闻需独立权限，2000 积分不能替换 |

建议：新闻不应纳入 Tushare 默认替换范围。可以保留 AKShare，或新增独立新闻源。

### `src/aiagents_stock/features/selectors/value_stock/strategy.py`

| 函数 | AKShare 接口 | Tushare 对应 | 检查结论 |
|------|--------------|--------------|----------|
| `calculate_rsi` | `stock_zh_a_hist` | `daily`/`pro_bar` | 未替代；建议复用统一数据源管理器，避免策略层直接依赖 AKShare |

## 可替换优先级

### 第一优先级：2000 积分下适合改为 Tushare 默认

| 数据类型 | 推荐 Tushare 接口 | 涉及模块 |
|----------|-------------------|----------|
| A 股日线/K 线 | `pro_bar` 或 `daily` + `adj_factor` | `providers.py`、`smart_monitor/kline.py`、`value_stock/strategy.py` |
| A 股基础信息 | `stock_basic` | `providers.py`、`stock_analysis/data.py`、`macro_analysis/data.py` |
| A 股估值/市值/换手率 | `daily_basic` | `providers.py`、`stock_analysis/data.py`、`market_sentiment_data.py` |
| 财务三表 | `income`、`balancesheet`、`cashflow` | `providers.py`、`quarterly_report_data.py`、`stock_analysis/data.py` |
| 财务指标 | `fina_indicator` | `quarterly_report_data.py`、`stock_analysis/data.py` |
| 个股资金流 | `moneyflow` | `fund_flow.py`、`smart_monitor/data.py` |
| 北向资金 | `moneyflow_hsgt` | `sector_strategy/data.py` |
| 指数日线 | `index_daily` | `macro_cycle/data.py`、`macro_analysis/data.py`、`market_sentiment_data.py` |

### 第二优先级：可部分替换，但需要保留其他源

| 数据类型 | 原因 |
|----------|------|
| 实时行情 | Tushare 日线不是严格实时；TDX/AKShare 更适合作为实时补充 |
| 市场宽度/涨跌家数 | 可通过全市场行情聚合，但 Tushare 默认不一定提供同口径实时快照 |
| 融资融券 | Tushare 可能可拼接，但字段口径需单独对齐 |
| 宏观指标 | 核心指标优先官方统计局接口，Tushare 可作为 fallback 或补充 |
| 期货主力合约 | 需要确认 Tushare 合约代码、主连口径和字段映射 |

### 不建议强行替换

| 数据类型 | 原因 |
|----------|------|
| 港股行情/财务 | Tushare 有 `hk_daily`、`hk_fina_indicator`，但需要独立权限或更高权限；2000 积分不适合作默认源 |
| 财经新闻/个股新闻/全球新闻 | Tushare 有 `news`、`major_news`，但新闻资讯是独立权限；个股聚合口径也需重做 |
| 板块/概念实时表现 | Tushare 有东财/同花顺板块接口，但通常需 6000 积分，且多为盘后数据 |
| 涨停/跌停池 | Tushare 有 `limit_list_d`/`limit_list_ths`，但当前 2000 积分不能调用；且主要是盘后数据 |

## 主要风险

1. 当前已有 fallback 不等于可以直接改默认源。部分 Tushare fallback 只是“兜底能返回数据”，字段口径、实时性和复权处理还没有统一。
2. `daily` 与复权参数的使用需要重点检查。若需要前复权/后复权，应优先使用 `pro_bar` 或用 `adj_factor` 自行计算。
3. 将 Tushare 设为默认源后，需要统一 `ts_code`、普通股票代码、港股代码、指数代码的转换逻辑。
4. 板块、概念、新闻、涨跌停这类数据源更像“特色数据”，不适合被 Tushare 作为唯一默认源覆盖。

## 基于官方文档和 2000 积分的复核

依据 Tushare 官方接口文档与权限说明复核后，需要把“有没有接口”和“当前 2000 积分能不能调用”分开看。

官方权限口径：

1. 2000 积分属于常规积分权限，可调用不少 A 股、财务、宏观、期货日线等常规接口，但频率和总量低于 5000 积分。
2. 分钟、实时、新闻资讯、公告、港美股日线/财报等属于独立权限，和 2000 积分不是一回事。
3. 涨跌停、东财/同花顺板块、板块资金流等特色接口通常要求 5000、6000 或 8000 积分；2000 积分下不能作为默认替换源。

### 2000 积分下可以优先替换的 AKShare 接口

| 当前 AKShare 接口 | 使用位置 | Tushare 替代接口 | 2000 积分可用性 | 替换判断 |
|-------------------|----------|------------------|----------------|----------|
| `stock_zh_a_hist` | A 股日线/K 线/RSI/技术指标 | `daily`，复权场景用通用行情或 `adj_factor` 方案 | 可用 | 可以替换；注意 `daily` 是未复权，不应直接传 `adj` |
| `stock_individual_info_em` | 个股基础信息、快照补充 | `stock_basic` + `daily_basic` + 最近 `daily` | 可用 | 可以替换；需把名称/行业/上市信息和估值/市值字段拆开取 |
| `stock_zh_valuation_baidu` | PE/PB 估值 | `daily_basic` | 可用 | 可以替换；`daily_basic` 覆盖 `pe`、`pe_ttm`、`pb`、`total_mv`、`circ_mv`、换手率 |
| `stock_financial_report_sina` | 利润表/资产负债表/现金流量表 | `income`、`balancesheet`、`cashflow` | 可用 | 可以替换；2000 积分按单只股票拉历史，批量季度全市场 VIP 接口需 5000 |
| `stock_financial_abstract`、`stock_financial_abstract_ths` | 财务摘要/指标 | `fina_indicator` | 可用 | 可以替换；需要做字段映射 |
| `stock_individual_fund_flow` | 个股资金流 | `moneyflow` | 可用 | 可以替换；口径为小/中/大/特大单主动买卖统计 |
| `stock_individual_fund_flow_rank` | 主力资金排行 | `moneyflow` 聚合或 `moneyflow_dc`/`moneyflow_ths` | `moneyflow` 可用，DC/THS 口径需另看权限 | 可部分替换；排名需要按日期聚合排序 |
| `stock_hsgt_fund_flow_summary_em` | 北向/南向资金 | `moneyflow_hsgt` | 可用 | 可以替换；当前代码已经是 Tushare 优先 |
| `stock_zh_index_daily` | 指数日线 | `index_daily` | 可用 | 可以替换；申万等行业指数不在 2000 权限内 |
| `stock_margin_szsh` | 两融汇总 | `margin` | 可用 | 可以替换；更适合取沪深京交易所汇总 |
| `stock_margin_underlying_info_szse` | 融资融券标的 | `margin_secs` | 可用 | 可以替换；仅标的列表，不等同两融余额 |
| 宏观 `macro_china_gdp` | GDP | `cn_gdp` | 可用 | 可以替换；字段口径需映射 |
| 宏观 `macro_china_cpi_monthly` | CPI | `cn_cpi` | 可用 | 可以替换 |
| 宏观 `macro_china_ppi_yearly` | PPI | `cn_ppi` | 可用 | 可以替换；注意 AKShare 函数名是 yearly，但 Tushare 以月度为主 |
| 宏观 `macro_china_money_supply` | 货币供应量 | `cn_m` | 可用 | 可以替换 |
| 宏观 `macro_china_pmi_yearly` | PMI | `cn_pmi` | 可用 | 可以替换 |
| 宏观 `macro_china_lpr` | LPR | `shibor_lpr` | 可用 | 可以替换 |
| `futures_main_sina` | 黄金/原油/铜主力期货 | `fut_mapping` + `fut_daily` | 可用 | 可以替换，但要先建立 `AU0`/`SC0`/`CU0` 到 Tushare 连续合约和交易所代码的映射 |

### Tushare 有接口，但 2000 积分当前不适合作为替换源

| 当前 AKShare 接口 | Tushare 相关接口 | 权限/积分 | 替换判断 |
|-------------------|------------------|-----------|----------|
| `stock_zh_a_hist_min_em` | 股票历史分钟/实时分钟 | 独立权限，不属于 2000 积分 | 不能用当前 2000 积分替换 |
| `stock_zh_a_spot_em` | 股票实时日线 | 独立权限；2000 积分只能用 `daily`/`daily_basic` 做盘后替代 | 盘中实时不能替换；盘后快照可替换 |
| `stock_zh_index_spot_em` | 指数实时日线 | 独立权限；`index_daily` 只能盘后替代 | 盘中实时不能替换；盘后指数可替换 |
| `stock_zt_pool_em`、`stock_zt_pool_dtgc_em` | `limit_list_d`、`limit_list_ths` | `limit_list_d` 需 5000，`limit_list_ths` 需 8000 | 2000 积分不能替换；升到 5000 后可用 `limit_list_d` 替换盘后涨跌停/炸板 |
| `stock_board_industry_name_em` | `dc_index`、`dc_daily`、`ths_index`、`ths_daily` | 多数需 6000 | 2000 积分不能替换；6000 后可做盘后行业/概念表现替换 |
| `stock_board_concept_name_em` | `dc_index`、`dc_daily`、`ths_index`、`ths_daily` | 多数需 6000 | 2000 积分不能替换 |
| `stock_sector_fund_flow_rank` | `moneyflow_ind_dc`、`moneyflow_ind_ths`、`moneyflow_cnt_ths` | 需 6000 | 2000 积分不能替换 |
| `stock_hk_spot_em` | `hk_basic`、港股实时日线 | `hk_basic` 2000 可用；港股实时日线独立权限 | 只能替换港股基础列表，不能替换实时行情 |
| `stock_hk_hist` | `hk_daily`、`hk_daily_adj` | 独立权限 | 2000 积分不能替换 |
| `stock_hk_financial_indicator_em` | `hk_fina_indicator` | 单独权限或 15000 积分 | 2000 积分不能替换 |
| `stock_news_em`、`stock_news_sina`、`stock_news_cls`、`stock_info_global_em` | `news`、`major_news` | 新闻资讯独立权限，和积分无关 | 2000 积分不能替换；即使开通也要按新闻源和关键词重做过滤 |

### 仍不建议直接替换的接口

| 当前 AKShare 接口 | 原因 | 建议 |
|-------------------|------|------|
| `macro_china_cx_pmi_yearly` | Tushare 有官方 PMI `cn_pmi`，但财新 PMI 口径未在当前文档中找到明确等价接口 | 保留 AKShare 或另找财新 PMI 源 |
| `macro_china_real_estate` | 当前 Tushare 文档中未找到与 AKShare 房地产宏观指标完全等价的接口 | 保留 AKShare，或改走国家统计局/其他官方源 |
| `stock_news_*` 用于个股新闻 | Tushare 新闻接口是资讯源维度，不是天然按个股聚合；且需独立权限 | 不纳入 Tushare 默认替换；作为可选新闻源单独设计 |

### 2000 积分下的实际改造范围

可以先落地的替换范围：

1. A 股盘后行情、K 线、技术指标：`daily`/复权方案。
2. A 股基础信息与估值：`stock_basic` + `daily_basic`。
3. A 股财务：`income`、`balancesheet`、`cashflow`、`fina_indicator`。
4. A 股个股资金流：`moneyflow`。
5. 北向资金：`moneyflow_hsgt`。
6. 两融：`margin`、`margin_detail`、`margin_secs`。
7. 宏观核心指标：`cn_gdp`、`cn_cpi`、`cn_ppi`、`cn_m`、`cn_pmi`、`shibor_lpr`。
8. 指数日线：`index_daily`。
9. 期货日线/主连映射：`fut_daily` + `fut_mapping`。

暂时不应纳入 2000 积分替换范围：

1. 盘中实时行情和分钟线。
2. 港股日线、港股财务、港股实时行情。
3. 新闻资讯。
4. 涨跌停池、连板、炸板。
5. 东财/同花顺板块表现、概念表现、板块资金流。

## 参考 `stock-data-store` 的改造方案

参考项目路径：`/Users/kongwei/stocks/stock-data-store`。

该项目的核心思路不是在业务代码里直接调用 Tushare，而是把 Tushare 访问、字段映射、本地缓存、增量更新、复权漂移检测拆成独立层：

| 参考模块 | 可借鉴点 | 当前项目落点 |
|----------|----------|--------------|
| `clients/tushare.py` | token 解析、`ts.pro_api` 封装、重试、限速、统计、`pro_bar` 获取复权日线 | 新增或重构 `src/aiagents_stock/integrations/market_data/tushare_client.py` |
| `services/data_manager.py` | `DataManager.from_tushare()` 门面，把 client、store、universe、bar/fundamental fetcher 组装起来 | 重构当前 `DataSourceManager`，让业务模块只依赖统一门面 |
| `services/daily_bars.py` | 日线增量更新、复权漂移检测、必要时全量刷新 | A 股 K 线、技术指标、RSI、市场情绪历史行情 |
| `services/fundamental.py` | 用 dataset spec 管理 `daily_basic`、`fina_indicator`、`income` 的字段、主键、增量合并 | 财务三表、财务指标、估值、市值、换手率 |
| `services/universe.py` | `stock_basic` 同步、过滤 ST、上市天数、交易所 | A 股基础信息、候选股票池、股票代码/名称/行业映射 |
| `stores/csv_store.py` | 本地 CSV cache、last_ts metadata、append/merge/dedup | 当前项目可新增 `data/market_data/` 或 `stock_data/` 本地缓存目录 |
| `mappers.py` | 日期、字段、OHLCV 标准化 | 当前项目统一输出 `date/open/high/low/close/volume/amount/pct_change` 等内部 schema |

### 总体原则

1. 不把 `/Users/kongwei/stocks/stock-data-store` 直接作为运行时依赖，先借鉴其分层和关键逻辑，避免两个项目耦合。
2. 2000 积分可覆盖的数据默认改为 Tushare 优先；当前权限不足的数据继续保留 AKShare/TDX/yfinance。
3. 策略层、UI 层、分析模块不再直接 import AKShare/Tushare，统一走 `DataSourceManager` 或更细的 market data service。
4. 默认链路优先读本地 cache，缺失或过期才访问远端，减少 Tushare 频率压力。
5. 保留 AKShare 作为 fallback，不在第一轮删除 AKShare 代码。

### 目标数据源顺序

| 数据能力 | 目标顺序 | 说明 |
|----------|----------|------|
| A 股日线/K 线/技术指标/RSI | 本地 cache -> Tushare `pro_bar` -> AKShare fallback | 修正当前把 `adj` 传给 `daily` 的问题 |
| A 股基础信息 | 本地 `stock_basic` cache -> Tushare `stock_basic` -> AKShare fallback | 名称、行业、市场、上市日期统一从 Tushare 来 |
| 估值/市值/换手率 | 本地 `daily_basic` cache -> Tushare `daily_basic` -> AKShare fallback | 替代 `stock_zh_valuation_baidu` 和部分实时快照字段 |
| 财务三表/季报 | 本地 fundamental cache -> Tushare `income`/`balancesheet`/`cashflow` -> AKShare fallback | 优先替换季报和股票分析财务模块 |
| 财务指标 | 本地 `fina_indicator` cache -> Tushare `fina_indicator` -> AKShare fallback | 替代 `stock_financial_abstract*` |
| 个股资金流 | Tushare `moneyflow` -> AKShare fallback | 可先不做本地全量 cache，按需拉取 |
| 北向资金 | Tushare `moneyflow_hsgt` -> AKShare fallback | 当前已基本符合目标 |
| 两融 | Tushare `margin`/`margin_detail`/`margin_secs` -> AKShare fallback | 2000 积分可替换 |
| 指数日线 | Tushare `index_daily` -> AKShare fallback | 替换宏观和市场情绪里的指数历史行情 |
| 核心宏观 | Tushare `cn_gdp`/`cn_cpi`/`cn_ppi`/`cn_m`/`cn_pmi`/`shibor_lpr` -> 官方统计局/AKShare fallback | 财新 PMI、房地产宏观不直接替换 |
| 期货主力 | Tushare `fut_mapping` + `fut_daily` -> AKShare fallback | 需要先维护 `AU0`/`SC0`/`CU0` 映射 |
| 盘中实时/分钟线 | TDX/AKShare -> 不走 Tushare 默认 | 2000 积分不覆盖 |
| 港股行情/财务 | yfinance/AKShare -> 不走 Tushare 默认 | 2000 积分只适合 `hk_basic` |
| 新闻/板块/涨跌停 | AKShare -> 不走 Tushare 默认 | 新闻需独立权限，板块/涨跌停需更高积分 |

### 分阶段实施方案

#### 阶段 0：配置与边界固化

目标：不改行为，先把默认源和权限边界配置化。

建议新增配置：

```dotenv
MARKET_DATA_PROVIDER_ORDER=tushare,akshare
TUSHARE_POINTS=2000
TUSHARE_ENABLE_PERMISSIONED=false
TUSHARE_REQUESTS_PER_SECOND=3
TUSHARE_RETRY=3
TUSHARE_RETRY_INTERVAL=1.0
STOCK_DATA_ROOT=stock_data
STOCK_DATA_ADJ=qfq
STOCK_DATA_CACHE_ENABLED=true
```

验收标准：

1. 未配置 `TUSHARE_TOKEN` 时仍能按旧逻辑运行。
2. 配置 `TUSHARE_TOKEN` 后，只启用 2000 积分可用接口。
3. 文档标注实时、分钟、新闻、港股、板块、涨跌停暂不纳入 Tushare 默认链路。

#### 阶段 1：引入 Tushare client 与本地 cache 基础设施

借鉴 `stock-data-store`：

1. 新增 `TushareClient`：封装 token、`ts.pro_api(token)`、重试、限速、API 调用统计；避免写入本地全局 token 配置。
2. 新增 `MarketDataCache`：支持日线、`stock_basic`、`daily_basic`、财务数据 CSV 存储。
3. 新增 `market_data/mappers.py`：统一 Tushare/AKShare 字段到项目内部字段。
4. 将当前 `DataSourceManager` 改为门面类，内部组合 Tushare client、AKShare fallback 和 cache。

重点修正：

1. A 股复权日线使用 `ts.pro_bar(asset="E", adj="qfq", freq="D")`，不再对 `pro.daily()` 传 `adj`。
2. 所有 Tushare 日期参数统一使用 `YYYYMMDD`，输出统一转成项目内部日期格式。
3. 统一股票代码转换：`000001` <-> `000001.SZ`，指数、港股、期货不要复用 A 股转换逻辑。

#### 阶段 2：替换 A 股日线、基础信息、估值

优先改这些位置：

| 模块 | 改造点 |
|------|--------|
| `integrations/market_data/providers.py` | `get_stock_hist_data` 改为 cache -> Tushare `pro_bar` -> AKShare；`get_stock_basic_info` 合并 `stock_basic` + `daily_basic` |
| `features/stock_analysis/data.py` | `_get_chinese_stock_info`、`_get_chinese_stock_data` 改为统一数据源，不再直接调用 `stock_zh_valuation_baidu` |
| `features/smart_monitor/kline.py` | K 线 fallback 改用统一数据源，避免自己直接写 Tushare/AKShare 顺序 |
| `features/selectors/value_stock/strategy.py` | `calculate_rsi` 改用统一日线接口，移除策略层 AKShare import |
| `features/stock_analysis/market_sentiment_data.py` | 历史指数/换手率使用 `daily_basic`/`index_daily` |

验收标准：

1. A 股日线默认 Tushare，AKShare 只作为 fallback。
2. 前复权 K 线不会混用不同复权基准；检测到历史 close 漂移时触发全量刷新。
3. PE/PB/市值/换手率来自 `daily_basic`，不再依赖百度估值接口。

#### 阶段 3：替换财务与季报

优先改这些位置：

| 模块 | 改造点 |
|------|--------|
| `features/stock_analysis/quarterly_report_data.py` | `income`、`balancesheet`、`cashflow`、`fina_indicator` 改为 Tushare 优先 |
| `features/stock_analysis/data.py` | `_get_chinese_financial_data` 改为统一 financial service |
| `integrations/market_data/providers.py` | `get_financial_data` 改为 Tushare 优先并统一字段 |

借鉴 `stock-data-store/services/fundamental.py`：

1. 为 `income`、`balancesheet`、`cashflow`、`fina_indicator` 定义 dataset spec。
2. 用 `end_date` 作为财报期主键，`ann_date` 作为修订排序字段。
3. 增量更新时回看 5 天，远端同主键覆盖本地差异，本地独有历史保留。

验收标准：

1. 最近 8 期季报可由 Tushare 返回并适配原 UI/分析结构。
2. 财务指标字段从中文行列式 AKShare 输出，迁移成明确字段映射。
3. 单只股票历史财务接口适配 2000 积分权限；不使用 5000 积分 VIP 全市场接口。

#### 阶段 4：替换资金流、两融、指数、核心宏观、期货

| 数据 | Tushare 接口 | 主要落点 |
|------|--------------|----------|
| 个股资金流 | `moneyflow` | `stock_analysis/fund_flow.py`、`smart_monitor/data.py` |
| 北向资金 | `moneyflow_hsgt` | `sector_strategy/data.py` |
| 两融 | `margin`、`margin_detail`、`margin_secs` | `market_sentiment_data.py` |
| 指数日线 | `index_daily` | `macro_analysis/data.py`、`macro_cycle/data.py`、`market_sentiment_data.py` |
| GDP/CPI/PPI/M2/PMI/LPR | `cn_gdp`、`cn_cpi`、`cn_ppi`、`cn_m`、`cn_pmi`、`shibor_lpr` | `macro_cycle/data.py` |
| 期货 | `fut_mapping`、`fut_daily` | `macro_cycle/data.py` |

注意：

1. `stock_individual_fund_flow_rank` 的排名口径不能直接等同 `moneyflow`，需要按日期聚合后排序。
2. 市场宽度、涨跌家数、恐惧贪婪指数如果需要盘中口径，仍保留 AKShare。
3. 财新 PMI、房地产宏观继续保留 AKShare 或改官方数据源。

#### 阶段 5：保留 AKShare 的权限不足数据，并隔离直接调用

这些能力暂时保留 AKShare/其他源：

1. 盘中实时行情、分钟线：TDX/AKShare。
2. 港股日线、港股财务、港股实时：yfinance/AKShare。
3. 新闻：AKShare，后续开 Tushare 新闻权限后单独设计关键词过滤。
4. 板块/概念表现、板块资金流：AKShare，后续 6000 积分后评估 Tushare `dc_*`/`ths_*`。
5. 涨跌停池、炸板、连板：AKShare，后续 5000/8000 积分后评估 `limit_list_d`/`limit_list_ths`。

代码治理目标：

1. 业务模块不直接 import AKShare，改为调用 `DataSourceManager.get_realtime_quote()`、`get_sector_performance()` 等能力接口。
2. AKShare 只集中在 `AkshareProvider` 或 legacy fallback 模块里。
3. 每个能力接口都标注 `source`、`is_realtime`、`permission_required`，便于 UI 和日志展示。

### 推荐落地顺序

1. 先迁 `TushareClient`、限速、重试、`pro_bar` 日线和 `stock_basic`。
2. 再迁本地日线 cache 和复权漂移检测，解决 K 线/RSI/技术指标的稳定性。
3. 再迁 `daily_basic`，解决估值、市值、换手率。
4. 再迁财务三表和财务指标，替换季报模块。
5. 再迁资金流、两融、指数、宏观、期货。
6. 最后清理散落的 AKShare import，只保留权限不足数据的集中 fallback。

### 本地缓存每日自动更新机制

结论：替换为 Tushare 后，应同步建设本地缓存每日自动更新机制。否则只是在查询时懒加载，无法充分发挥本地 cache 的稳定性，也无法像 `stock-data-store` 一样处理除权、分红、配股等事件导致的前复权历史价格漂移。

参考 `stock-data-store` 的实现方式：

| 能力 | 参考实现 | 当前项目建议 |
|------|----------|--------------|
| 日线增量更新 | `cli/update_daily.py` + `services/daily_bars.py` | 新增 `market_data` 缓存更新任务，按股票池逐只更新 |
| 前复权漂移检测 | 重新拉取本地最后交易日，比较远端复权 `close` 与本地 `close` | 若相对差异超过阈值，触发该股票前复权全历史刷新 |
| 进度恢复 | `daily_update_progress.json` + symbols 文件 | 更新中断后可从 `next_index` 继续，不重复全市场重跑 |
| 基本面增量 | `cli/update_fundamental.py` + dataset spec | `daily_basic` 每日更新；财务三表/指标按公告期回看更新 |
| 股票池 | `stock_basic` cache + ST/上市天数过滤 | 每周或每日盘前刷新 `stock_basic`，生成 A 股 universe |
| 限速与并发 | 全局 `requests_per_second` + `max_workers` | 2000 积分下默认保守限速，避免触发频控 |

#### 自动更新任务设计

建议新增一个独立的数据缓存调度器，例如：

```text
src/aiagents_stock/features/market_data/
  cache_store.py
  scheduler.py
  update_daily.py
  update_fundamental.py
  update_universe.py
```

也可以放在 `src/aiagents_stock/integrations/market_data/` 下，关键是保持职责边界：远端 API 在 client/provider，缓存读写在 store，自动任务在 scheduler/CLI。

每日任务建议：

| 时间 | 任务 | 数据 | 原因 |
|------|------|------|------|
| 08:30 | 刷新股票基础信息 | `stock_basic` | 盘前更新股票池、ST/上市状态、行业信息 |
| 17:10 | 更新 A 股日线 | `pro_bar(adj="qfq")` | Tushare A 股日线通常 15:00-16:00 后入库，17 点后更稳 |
| 17:30 | 更新每日指标 | `daily_basic` | 估值、市值、换手率通常 15:00-17:00 后可用 |
| 18:00 | 更新指数/两融/资金流 | `index_daily`、`margin*`、`moneyflow` | 盘后分析和持仓分析需要 |
| 20:30 | 更新财务/基本面 | `income`、`balancesheet`、`cashflow`、`fina_indicator` | 公告数据不一定盘后立即完整，晚间增量更合适 |
| 每周末 | 全量校验任务 | 日线 recent window、财务 recent window | 发现漏更、修订和前复权漂移 |

#### 日线更新规则

借鉴 `stock-data-store` 的 `update_daily.py`：

1. 从 `stock_basic` cache 构建股票池，默认只处理沪深 A 股，可配置是否包含 ST、北交所、上市未满 N 天的新股。
2. 对每只股票读取本地最后交易日 `last_ts`。
3. 正常增量：从 `last_ts + 1` 更新到今天。
4. 如果今天没有新交易日数据，但开启除权检测，则仍用 `last_ts` 到今天做一次探测。
5. 探测到远端前复权 `close` 与本地 `close` 差异超过阈值，例如 `1%`，判定发生复权基准变化。
6. 触发该股票从上市日或默认起始日开始的全量前复权刷新。
7. 每处理 N 只或每隔 N 秒保存进度，异常中断后可继续。

推荐配置：

```dotenv
STOCK_DATA_CACHE_ENABLED=true
STOCK_DATA_ROOT=stock_data
STOCK_DATA_ADJ=qfq
STOCK_DATA_UPDATE_DAILY_TIME=17:10
STOCK_DATA_UPDATE_BASIC_TIME=17:30
STOCK_DATA_UPDATE_FUNDAMENTAL_TIME=20:30
STOCK_DATA_MAX_WORKERS=2
STOCK_DATA_REQUESTS_PER_SECOND=2
STOCK_DATA_ADJUSTMENT_DETECT_ENABLED=true
STOCK_DATA_ADJUSTMENT_PRICE_TOLERANCE=0.01
STOCK_DATA_PROGRESS_SAVE_EVERY=50
STOCK_DATA_PROGRESS_SAVE_INTERVAL=15
```

2000 积分下建议默认 `max_workers=1~2`、`requests_per_second=1~3`，不要照搬过高并发。

#### 基本面更新规则

借鉴 `stock-data-store/services/fundamental.py`：

1. 每个数据集定义明确 spec：字段列表、主键、日期字段、数值字段、修订排序字段。
2. `daily_basic` 以 `trade_date` 为主键，每日盘后增量更新。
3. `income`、`balancesheet`、`cashflow`、`fina_indicator` 以 `end_date` 为主键，`ann_date` 作为修订排序字段。
4. 增量更新时从本地最新公告日向前回看 5-10 天，覆盖可能修订的数据。
5. 远端同主键数据优先，本地独有历史数据保留。
6. 2000 积分下只做“按单只股票拉历史/增量”，不调用 5000 积分的全市场 VIP 接口。

建议缓存目录：

```text
stock_data/
  daily/<ts_code>.csv
  fundamental/
    daily_basic/<ts_code>.csv
    income/<ts_code>.csv
    balancesheet/<ts_code>.csv
    cashflow/<ts_code>.csv
    fina_indicator/<ts_code>.csv
  meta/
    stock_basic.csv
    daily_last_ts/<ts_code>.txt
    daily_update_progress.json
    fundamental_update_progress.json
    scheduler_logs.csv
```

#### 调度方式

当前项目已经有多个基于 `schedule` 的业务调度器，例如智策、持仓分析、实时监测、新闻流量。因此本地缓存更新可以采用两层触发：

1. 应用内调度：新增 `MarketDataCacheScheduler`，随应用启动后按配置时间运行，提供 UI 状态、手动触发、停止调度、查看日志。
2. 命令行调度：新增类似 `python -m src.aiagents_stock...update_daily` 的 CLI，供 cron、Docker、服务器计划任务调用。

推荐两者都保留：

1. 本地桌面/Streamlit 使用应用内调度，方便手动触发和看状态。
2. 服务器部署使用 cron 或进程管理器调 CLI，更可靠，不依赖浏览器页面是否打开。

#### 与业务查询的关系

业务查询应优先读 cache：

1. 如果 cache 覆盖请求日期范围，直接返回本地数据。
2. 如果 cache 缺失且允许懒加载，则触发单只股票增量更新后返回。
3. 如果 Tushare 失败，回退 AKShare 并标注 `source=akshare_fallback`，但不要把 fallback 数据直接混入前复权 cache，除非字段和复权口径已标准化。
4. 实时、分钟、新闻、板块、涨跌停、港股等权限不足数据不写入 Tushare cache，继续走各自专用源。

#### 验收标准

1. 每天收盘后自动更新 A 股日线和 `daily_basic`。
2. 发生除权/分红/配股导致前复权历史价格变化时，自动对受影响股票全量刷新。
3. 基本面数据支持每日增量更新和修订覆盖。
4. 中断后能从进度文件恢复。
5. UI 或日志能看到最近一次更新时间、成功/失败数量、触发全量刷新数量。
6. 2000 积分权限下不会自动调用高权限或独立权限接口。

### 测试与验收清单

| 类型 | 验收项 |
|------|--------|
| 单元测试 | 股票代码转换、日期转换、Tushare 字段映射、AKShare 字段映射 |
| 缓存测试 | 首次拉取写入、本地命中、增量追加、重复日期去重 |
| 复权测试 | 本地最后一天 close 与远端复权 close 不一致时触发全量刷新 |
| fallback 测试 | Tushare 抛错/空数据时回退 AKShare；AKShare 权限不足数据不误走 Tushare |
| 权限测试 | `TUSHARE_POINTS=2000` 时禁止调用 `limit_list_d`、`dc_daily`、`news`、`hk_daily` 等接口 |
| 集成测试 | 选一只 A 股验证行情、估值、财务、资金流、两融；选一个指数验证 `index_daily`；选一个宏观指标验证 `cn_*` |

### 预期收益

1. 大部分 A 股盘后数据从 AKShare 切到 Tushare，稳定性更高。
2. 高频重复请求改为本地 cache，减少接口压力和封禁风险。
3. 复权数据不再混用，技术指标和策略结果更稳定。
4. 财务数据字段从中文表格行列式解析，改为结构化字段映射。
5. 后续升级积分或开通独立权限时，只需要扩展 provider，不需要大面积改业务代码。

## 官方文档依据

- Tushare 数据接口总览：https://tushare.pro/document/2
- Tushare 积分与频次权限说明：https://tushare.pro/document/1?doc_id=290
- 涨跌停列表 `limit_list_d`：https://tushare.pro/document/2?doc_id=298
- 东财概念和行业指数行情 `dc_daily`：https://tushare.pro/document/2?doc_id=382
- 同花顺涨跌停榜单 `limit_list_ths`：https://tushare.pro/document/2?doc_id=355
- 港股基础信息 `hk_basic`：https://tushare.pro/document/2?doc_id=191
