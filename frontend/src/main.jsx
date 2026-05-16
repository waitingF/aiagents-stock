import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  BrowserRouter,
  NavLink,
  Route,
  Routes,
  useNavigate,
} from "react-router-dom";
import {
  Activity,
  BarChart3,
  Bot,
  BriefcaseBusiness,
  CalendarClock,
  CheckSquare,
  Database,
  Eraser,
  Gauge,
  History,
  LayoutDashboard,
  ListChecks,
  Newspaper,
  Play,
  Plus,
  RefreshCw,
  Save,
  Search,
  Settings,
  Trash2,
} from "lucide-react";
import "./styles.css";

const API = "/api";

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `请求失败（${response.status}）`);
  }
  return payload;
}

function useAsync(fn, deps = []) {
  const [state, setState] = useState({ loading: true, error: "", data: null });
  const load = async () => {
    setState((prev) => ({ ...prev, loading: true, error: "" }));
    try {
      setState({ loading: false, error: "", data: await fn() });
    } catch (error) {
      setState({ loading: false, error: error.message, data: null });
    }
  };
  useEffect(() => {
    load();
  }, deps);
  return { ...state, reload: load };
}

const iconByKey = {
  dashboard: LayoutDashboard,
  "stock-analysis": BarChart3,
  history: History,
  "main-force": Search,
  "low-price-bull": Gauge,
  "small-cap": Database,
  "profit-growth": Activity,
  "value-stock": ListChecks,
  "sector-strategy": BarChart3,
  "dragon-strategy": Activity,
  longhubang: Database,
  "news-flow": Newspaper,
  "macro-analysis": Gauge,
  "macro-cycle": CalendarClock,
  portfolio: BriefcaseBusiness,
  "stock-pool": Database,
  "smart-monitor": Bot,
  "realtime-monitor": Activity,
  settings: Settings,
};

function App() {
  const { data } = useAsync(() => request("/pages"), []);
  const pages = data?.pages || [];
  const groups = useMemo(() => {
    return pages.reduce((acc, page) => {
      acc[page.group] ||= [];
      acc[page.group].push(page);
      return acc;
    }, {});
  }, [pages]);

  return (
    <BrowserRouter>
      <div className="app-shell">
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-mark">智</div>
            <div>
              <strong>智策股票</strong>
              <span>前后端分离版</span>
            </div>
          </div>
          <nav>
            {Object.entries(groups).map(([group, items]) => (
              <section key={group} className="nav-group">
                <div className="nav-group-title">{group}</div>
                {items.map((page) => {
                  const Icon = iconByKey[page.key] || LayoutDashboard;
                  return (
                    <NavLink key={page.key} to={page.path} className="nav-link">
                      <Icon size={17} />
                      <span>{page.title}</span>
                    </NavLink>
                  );
                })}
              </section>
            ))}
          </nav>
        </aside>
        <main className="content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/stock-analysis" element={<StockAnalysisPage />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route path="/main-force" element={<SelectorPage key="main-force" selectorKey="main-force" title="主力选股" />} />
            <Route path="/low-price-bull" element={<SelectorPage key="low-price-bull" selectorKey="low-price-bull" title="低价擒牛" monitorPath="/selectors/low-price-bull/monitor" />} />
            <Route path="/small-cap" element={<SelectorPage key="small-cap" selectorKey="small-cap" title="小市值策略" />} />
            <Route path="/profit-growth" element={<SelectorPage key="profit-growth" selectorKey="profit-growth" title="净利增长" monitorPath="/selectors/profit-growth/monitor" />} />
            <Route path="/value-stock" element={<SelectorPage key="value-stock" selectorKey="value-stock" title="低估值策略" defaultTopN={10} />} />
            <Route path="/sector-strategy" element={<ReportJobPage title="智策板块" runPath="/sector-strategy/run" reportsPath="/sector-strategy/reports" jobKey="strategy:sector-strategy" strategyKey="sector-strategy" />} />
            <Route path="/dragon-strategy" element={<DragonStrategyPage />} />
            <Route path="/longhubang" element={<LonghubangPage />} />
            <Route path="/news-flow" element={<NewsFlowPage />} />
            <Route path="/macro-analysis" element={<ReportJobPage title="宏观分析" runPath="/macro-analysis/run" reportsPath="/macro-analysis/reports" jobKey="strategy:macro-analysis" strategyKey="macro-analysis" />} />
            <Route path="/macro-cycle" element={<ReportJobPage title="宏观周期" runPath="/macro-cycle/run" reportsPath="/macro-cycle/reports" jobKey="strategy:macro-cycle" strategyKey="macro-cycle" />} />
            <Route path="/portfolio" element={<PortfolioPage />} />
            <Route path="/stock-pool" element={<StockPoolPage />} />
            <Route path="/smart-monitor" element={<SmartMonitorPage />} />
            <Route path="/realtime-monitor" element={<RealtimeMonitorPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

function Page({ title, subtitle, actions, children }) {
  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>{title}</h1>
          {subtitle ? <p>{subtitle}</p> : null}
        </div>
        {actions ? <div className="header-actions">{actions}</div> : null}
      </header>
      {children}
    </div>
  );
}

function Button({ children, icon: Icon, variant = "primary", ...props }) {
  return (
    <button className={`btn ${variant}`} {...props}>
      {Icon ? <Icon size={16} /> : null}
      {children}
    </button>
  );
}

function Field({ label, children }) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}

function DataView({ value }) {
  if (value === null || value === undefined) return <p className="muted">暂无数据</p>;
  if (value?.type === "dataframe") return <Table rows={value.records} columns={value.columns} />;
  if (Array.isArray(value)) return <Table rows={value} />;
  if (typeof value === "object") {
    const keys = Object.keys(value);
    const dataframeKey = keys.find((key) => value[key]?.type === "dataframe");
    if (dataframeKey) {
      return (
        <div className="stack">
          <h3>{titleize(dataframeKey)}</h3>
          <DataView value={value[dataframeKey]} />
          <JsonBlock value={{ ...value, [dataframeKey]: undefined }} />
        </div>
      );
    }
    return <ObjectView value={value} />;
  }
  return <pre className="json-block">{String(value)}</pre>;
}

const HIDDEN_TABLE_COLUMNS = new Set(["raw", "raw_json", "metadata_json", "leaders_json", "sectors_json"]);

const TABLE_PRESETS = {
  板块信号: ["name", "rank", "pct_chg", "amount", "stock_count", "up_stocks", "limit_up_count", "consecutive_days", "stage", "rating", "action", "status"],
};

const FIELD_ALIASES = {
  name: ["名称", "板块", "板块名称", "行业名称", "industry", "sector"],
  rank: ["排名", "排行", "序号"],
  pct_chg: ["涨跌幅", "涨幅", "change_pct", "pct_change"],
  amount: ["成交额", "总成交额", "成交金额", "turnover_amount"],
  stock_count: ["股票数", "股票家数", "成份股数", "成分股数", "股票数量", "个股数量", "成分股", "total_stocks"],
  up_stocks: ["上涨家数", "上涨数", "up_count", "rise_count", "rising_count"],
  down_stocks: ["下跌家数", "下跌数", "down_count", "fall_count", "falling_count"],
  flat_stocks: ["平盘家数", "平盘数", "flat_count", "unchanged_count"],
  limit_up_count: ["涨停数"],
  consecutive_days: ["连续天数", "连续主线天数"],
  action: ["动作", "操作建议"],
};

function Table({ rows, columns, preset }) {
  const data = Array.isArray(rows) ? rows : [];
  const presetColumns = TABLE_PRESETS[preset];
  const detectedColumns = Array.from(new Set(data.flatMap((row) => Object.keys(row || {}))));
  const cols = (columns || (presetColumns && hasAnyPresetValue(data, presetColumns) ? presetColumns : detectedColumns))
    .filter((col) => !HIDDEN_TABLE_COLUMNS.has(String(col)))
    .slice(0, 12);
  if (!data.length) return <p className="muted">暂无记录</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>{cols.map((col) => <th key={col}>{titleize(col)}</th>)}</tr>
        </thead>
        <tbody>
          {data.slice(0, 200).map((row, index) => (
            <tr key={index}>
              {cols.map((col) => (
                <td key={col}>{formatCell(tableCellValue(row, col))}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {data.length > 200 ? <p className="muted">仅展示前 200 条，共 {data.length} 条</p> : null}
    </div>
  );
}

function stockRowCode(row) {
  return String(row?.code || row?.symbol || row?.stock_code || "").trim().toUpperCase();
}

function StockPoolSelectionTable({ rows, selectedCodes, onToggleCode, onSelectAll }) {
  const data = Array.isArray(rows) ? rows : [];
  if (!data.length) return <p className="muted">暂无记录</p>;

  const selectedSet = new Set(selectedCodes);
  const codes = Array.from(new Set(data.map(stockRowCode).filter(Boolean)));
  const allSelected = codes.length > 0 && codes.every((code) => selectedSet.has(code));
  const displayColumns = ["code", "name", "tags", "status", "created_at"].filter((col) => (
    col === "code" || data.some((row) => hasDisplayValue(tableCellValue(row, col)))
  ));

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th className="select-column">
              <input
                aria-label="选择全部股票"
                type="checkbox"
                checked={allSelected}
                onChange={() => onSelectAll(allSelected ? [] : codes)}
              />
            </th>
            {displayColumns.map((col) => <th key={col}>{titleize(col)}</th>)}
          </tr>
        </thead>
        <tbody>
          {data.slice(0, 200).map((row, index) => {
            const code = stockRowCode(row);
            const isSelected = Boolean(code && selectedSet.has(code));
            return (
              <tr key={row.id || code || index} className={isSelected ? "selected-row" : ""}>
                <td className="select-column">
                  <input
                    aria-label={`选择 ${code || index + 1}`}
                    type="checkbox"
                    disabled={!code}
                    checked={isSelected}
                    onChange={() => code && onToggleCode(code)}
                  />
                </td>
                {displayColumns.map((col) => (
                  <td key={col}>{formatCell(tableCellValue(row, col))}</td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
      {data.length > 200 ? <p className="muted">仅展示前 200 条，共 {data.length} 条</p> : null}
    </div>
  );
}

const FIELD_LABELS = {
  id: "编号",
  success: "状态",
  status: "状态",
  timestamp: "时间",
  created_at: "创建时间",
  updated_at: "更新时间",
  finished_at: "完成时间",
  started_at: "开始时间",
  report_id: "报告编号",
  snapshot_id: "快照编号",
  report_date: "报告日期",
  report_type: "报告类型",
  analysis_type: "分析类型",
  analysis_date: "分析日期",
  title: "标题",
  report_title: "报告标题",
  summary: "摘要",
  content: "正文",
  markdown: "报告正文",
  metadata: "元信息",
  model: "模型",
  framework: "框架",
  api_configured: "接口配置",
  monitor_running: "监测服务",
  analysis_records: "分析记录",
  monitored_stocks: "监测股票",
  pending_notifications: "待处理通知",
  name: "名称",
  code: "代码",
  symbol: "代码",
  stock_code: "股票代码",
  stock_name: "股票名称",
  rank: "排名",
  pct_chg: "涨跌幅",
  change_pct: "涨跌幅",
  amount: "成交额",
  turnover: "成交额",
  close: "收盘价",
  price: "股价",
  current_price: "当前价",
  sector: "所属板块",
  industry: "所属行业",
  limit_up_count: "涨停数",
  limit_down_count: "跌停数",
  max_lianban: "最高连板",
  lianban_count: "连板数",
  consecutive_days: "连续天数",
  stage: "阶段",
  rating: "评级",
  action: "操作建议",
  stock_count: "股票数",
  up_stocks: "上涨家数",
  board_type: "板型",
  first_limit_time: "首封时间",
  seal_amount: "封单金额",
  circ_market_cap: "流通市值",
  score: "得分",
  level: "级别",
  score_detail: "评分明细",
  trade_plan: "交易计划",
  reasons: "理由",
  risks: "风险",
  trend_score: "趋势分",
  ma_aligned: "均线多头",
  ma20_slope: "MA20斜率",
  rsi_zone: "RSI区间",
  volume_ratio: "量比",
  support: "支撑位",
  resistance: "压力位",
  details: "明细",
  stop_loss: "止损位",
  targets: "目标价",
  support_levels: "支撑位",
  risk_reward: "盈亏比",
  position_advice: "仓位建议",
  position: "建议仓位",
  investment_period: "投资周期",
  highlights: "投资亮点",
  date: "日期",
  trade_date: "交易日",
  is_trade_day: "是否交易日",
  passed: "是否通过",
  message: "说明",
  explode_rate: "炸板率",
  index_day_change: "指数日涨跌幅",
  index_5day_gain: "指数5日涨幅",
  assist_pass_count: "辅助条件通过数",
  core_conditions: "核心条件",
  assist_conditions: "辅助条件",
  metrics: "指标",
  risk_level: "风险等级",
  confidence: "置信度",
  confidence_score: "置信度",
  market_outlook: "市场展望",
  investment_horizon: "投资周期",
  total_records: "记录数",
  total_stocks: "股票数",
  filtered_stocks: "筛选后数量",
  total_youzi: "席位数",
  total_net_inflow: "净流入合计",
  final_recommendations: "最终推荐",
  recommended_stocks_count: "推荐数",
  fetch_time: "抓取时间",
  duration: "耗时",
  final_predictions: "最终研判",
  comprehensive_report: "综合报告",
  agents_analysis: "分析师观点",
  data_info: "数据信息",
  final_report: "最终报告",
  recommended_stocks: "推荐股票",
  scoring_ranking: "智能评分排行",
  flow_data: "流量数据",
  model_data: "模型数据",
  sentiment_data: "情绪数据",
  ai_analysis: "智能分析",
  trading_signals: "交易信号",
  stock_news: "个股新闻",
  hot_topics: "热门话题",
  platforms_data: "平台数据",
  market: "市场环境",
  leaders: "龙头候选",
  sectors: "板块信号",
  trend_rotation: "趋势轮动",
  trend_tracking: "趋势跟踪",
  report: "报告",
  signals: "信号",
  candidates: "候选列表",
  params: "参数",
  stock_data: "股票数据",
  pool_id: "股票池编号",
  pool_type: "股票池类型",
  cost_price: "成本价",
  target_price: "目标价",
  take_profit: "止盈",
  entry_min: "进场下限",
  entry_max: "进场上限",
  check_interval: "检查间隔",
  notification_enabled: "通知开关",
  trading_hours_only: "仅交易时段",
  source: "数据来源",
};

const VALUE_LABELS = {
  true: "是",
  false: "否",
  queued: "排队中",
  running: "运行中",
  completed: "已完成",
  failed: "失败",
  active: "活跃",
  watch: "观察",
  fading: "退潮",
  daily_report: "日报",
  "fastapi-react": "前后端分离版",
  dragon_mvp: "龙头评分",
  mvp: "龙头评分",
  sectors: "主线板块",
  trends: "趋势跟踪",
  backtest: "回测",
  sector: "板块",
  longhubang: "智瞰龙虎",
  quick: "快速分析",
  full: "完整分析",
  alerts: "预警检查",
};

const CONFIG_LABELS = {
  DEEPSEEK_API_KEY: "DeepSeek 接口密钥",
  DEEPSEEK_BASE_URL: "DeepSeek 接口地址",
  DEFAULT_MODEL_NAME: "智能模型名称",
  TUSHARE_TOKEN: "Tushare 数据令牌",
  MINIQMT_ENABLED: "启用 MiniQMT 交易",
  MINIQMT_ACCOUNT_ID: "MiniQMT 账户编号",
  MINIQMT_HOST: "MiniQMT 服务地址",
  MINIQMT_PORT: "MiniQMT 服务端口",
  EMAIL_ENABLED: "启用邮件通知",
  SMTP_SERVER: "SMTP 服务地址",
  SMTP_PORT: "SMTP 服务端口",
  EMAIL_FROM: "发件邮箱",
  EMAIL_PASSWORD: "邮箱授权码",
  EMAIL_TO: "收件邮箱",
  WEBHOOK_ENABLED: "启用通知回调",
  WEBHOOK_TYPE: "通知回调类型",
  WEBHOOK_URL: "通知回调地址",
  WEBHOOK_KEYWORD: "通知回调关键词",
};

const OPTION_LABELS = {
  dingtalk: "钉钉",
  feishu: "飞书",
  true: "启用",
  false: "停用",
};

function formatCell(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "是" : "否";
  if (Array.isArray(value)) return value.map((item) => formatCell(item)).join("、");
  if (typeof value === "object") return compactText(JSON.stringify(value), 120);
  const text = String(value);
  return VALUE_LABELS[text] || text;
}

function ObjectView({ value }) {
  const entries = Object.entries(value || {}).filter(([, item]) => item !== undefined);
  if (!entries.length) return <p className="muted">暂无数据</p>;
  return (
    <div className="kv-grid">
      {entries.map(([key, item]) => (
        <div key={key} className="kv-row">
          <span>{titleize(key)}</span>
          <div>{isPlainObject(item) || Array.isArray(item) ? <DataView value={item} /> : formatCell(item)}</div>
        </div>
      ))}
    </div>
  );
}

function JsonBlock({ value }) {
  return <pre className="json-block">{JSON.stringify(value, null, 2)}</pre>;
}

function isPlainObject(value) {
  return value && typeof value === "object" && !Array.isArray(value);
}

function titleize(key) {
  const text = String(key);
  return FIELD_LABELS[text] || (/[\u4e00-\u9fff]/.test(text) ? text : text.replace(/_/g, " "));
}

function hasAnyPresetValue(rows, cols) {
  return rows.some((row) => cols.some((col) => tableCellValue(row, col) !== undefined && tableCellValue(row, col) !== null));
}

function configLabel(key, item) {
  return CONFIG_LABELS[key] || item?.description || titleize(key);
}

function optionLabel(option) {
  const text = String(option);
  return OPTION_LABELS[text] || formatCell(text);
}

function tableCellValue(row, col) {
  if (!row || typeof row !== "object") return undefined;
  const key = String(col);
  if (Object.prototype.hasOwnProperty.call(row, key)) return row[key];

  for (const alias of FIELD_ALIASES[key] || []) {
    if (Object.prototype.hasOwnProperty.call(row, alias)) return row[alias];
  }

  if (key === "stock_count") {
    const countParts = ["up_stocks", "down_stocks", "flat_stocks"]
      .map((countKey) => numericTableValue(row, countKey))
      .filter((value) => Number.isFinite(value));
    if (countParts.length) return countParts.reduce((sum, value) => sum + value, 0);
  }

  const translated = FIELD_LABELS[key];
  if (translated && Object.prototype.hasOwnProperty.call(row, translated)) {
    return row[translated];
  }

  for (const [sourceKey, label] of Object.entries(FIELD_LABELS)) {
    if (label === key && Object.prototype.hasOwnProperty.call(row, sourceKey)) {
      return row[sourceKey];
    }
    if (label === key) {
      for (const alias of FIELD_ALIASES[sourceKey] || []) {
        if (Object.prototype.hasOwnProperty.call(row, alias)) return row[alias];
      }
    }
  }

  const match = Object.keys(row).find((rowKey) => titleize(rowKey) === key);
  return match ? row[match] : undefined;
}

function numericTableValue(row, key) {
  const value = tableCellValue(row, key);
  if (value === null || value === undefined || value === "") return undefined;
  const number = Number(String(value).replace(/,/g, ""));
  return Number.isFinite(number) ? number : undefined;
}

function compactText(value, limit = 180) {
  if (value === null || value === undefined) return "";
  const text = String(value).replace(/\s+/g, " ").trim();
  return text.length > limit ? `${text.slice(0, limit)}...` : text;
}

function getByPath(value, path) {
  return path.split(".").reduce((acc, key) => (acc == null ? undefined : acc[key]), value);
}

function firstValue(value, paths) {
  for (const path of paths) {
    const item = getByPath(value, path);
    if (item !== undefined && item !== null && item !== "") return item;
  }
  return undefined;
}

function hasDisplayValue(value) {
  if (value === null || value === undefined) return false;
  if (typeof value === "number") return Number.isFinite(value);
  const text = String(value).trim();
  return Boolean(text) && !["N/A", "NA", "None", "null", "undefined", "-"].includes(text);
}

function findAliasValue(sources, aliases) {
  const sourceList = (Array.isArray(sources) ? sources : [sources]).filter(isPlainObject);
  for (const source of sourceList) {
    for (const alias of aliases) {
      if (Object.prototype.hasOwnProperty.call(source, alias) && hasDisplayValue(source[alias])) {
        return source[alias];
      }
    }
  }
  for (const source of sourceList) {
    const match = Object.entries(source).find(([key, item]) => (
      hasDisplayValue(item) && aliases.some((alias) => String(key).includes(alias))
    ));
    if (match) return match[1];
  }
  return undefined;
}

function formatNumber(value, digits = 2) {
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return Number.isInteger(number) ? String(number) : number.toFixed(digits).replace(/\.?0+$/, "");
}

function formatMoneyValue(value) {
  if (!hasDisplayValue(value)) return "";
  if (typeof value === "string" && /[万亿元]/.test(value)) return value;
  const number = Number(String(value).replace(/,/g, ""));
  if (!Number.isFinite(number)) return String(value);
  const abs = Math.abs(number);
  if (abs >= 100000000) return `${formatNumber(number / 100000000)}亿`;
  if (abs >= 10000) return `${formatNumber(number / 10000)}万`;
  return formatNumber(number);
}

function formatPercentValue(value) {
  if (!hasDisplayValue(value)) return "";
  if (typeof value === "string" && value.includes("%")) return value;
  const number = Number(String(value).replace(/,/g, ""));
  return Number.isFinite(number) ? `${formatNumber(number)}%` : String(value);
}

function normalizeTextList(value) {
  if (Array.isArray(value)) return value.map((item) => compactText(item, 220)).filter(Boolean);
  if (!hasDisplayValue(value)) return [];
  return String(value)
    .split(/\r?\n|[；;]/)
    .map((item) => compactText(item.replace(/^[-*•]\s+/, "").replace(/^\d+[.)、]\s+/, ""), 220))
    .filter(Boolean);
}

function MarkdownBlock({ text }) {
  const lines = String(text || "").split(/\r?\n/);
  const blocks = [];
  let listItems = [];
  const flushList = () => {
    if (listItems.length) {
      blocks.push(<ul key={`list-${blocks.length}`} className="report-list">{listItems}</ul>);
      listItems = [];
    }
  };

  lines.forEach((raw, index) => {
    const line = raw.trim();
    if (!line) {
      flushList();
      return;
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushList();
      const level = Math.min(heading[1].length + 2, 4);
      const Tag = `h${level}`;
      blocks.push(<Tag key={`h-${index}`}>{heading[2]}</Tag>);
      return;
    }
    const bullet = line.match(/^[-*•]\s+(.+)$/) || line.match(/^\d+[.)]\s+(.+)$/);
    if (bullet) {
      listItems.push(<li key={`li-${index}`}>{bullet[1]}</li>);
      return;
    }
    flushList();
    blocks.push(<p key={`p-${index}`}>{line}</p>);
  });
  flushList();

  return <div className="markdown-report">{blocks}</div>;
}

function MetricStrip({ items }) {
  const visible = items.filter((item) => item.value !== undefined && item.value !== null && item.value !== "");
  if (!visible.length) return null;
  return (
    <div className="report-metrics">
      {visible.map((item) => (
        <div key={item.label} className="report-metric">
          <span>{item.label}</span>
          <strong>{String(item.value)}</strong>
        </div>
      ))}
    </div>
  );
}

function findReportText(value) {
  const direct = firstValue(value, [
    "markdown",
    "summary",
    "content",
    "report.markdown",
    "report.content",
    "report.summary",
    "comprehensive_report",
    "final_report.summary",
    "ai_analysis.investment_advice.summary",
    "agents_analysis.chief.analysis",
  ]);
  if (typeof direct === "string" && direct.trim()) return direct;
  if (isPlainObject(value?.final_report)) {
    const pieces = Object.entries(value.final_report)
      .filter(([, item]) => typeof item === "string" && item.trim())
      .map(([key, item]) => `### ${titleize(key)}\n${item}`);
    if (pieces.length) return pieces.join("\n\n");
  }
  return "";
}

function collectReportTables(value) {
  const candidates = [
    ["推荐股票", value?.recommended_stocks],
    ["智能评分排行", value?.scoring_ranking],
    ["龙头候选", value?.report?.leaders || value?.leaders],
    ["板块信号", value?.signals || value?.report?.sectors || value?.sectors],
    ["趋势候选", value?.candidates || value?.report?.trend_tracking || value?.trend_tracking],
    ["热门话题", value?.hot_topics],
    ["个股新闻", value?.stock_news],
    ["看多板块", value?.sector_view?.bullish_sectors],
    ["看空板块", value?.sector_view?.bearish_sectors],
    ["推荐标的", value?.stock_view?.recommended_stocks],
    ["观察名单", value?.stock_view?.watchlist],
    ["交易信号", value?.trading_signals?.signals],
  ];
  return candidates.filter(([, rows]) => Array.isArray(rows) && rows.length);
}

function AgentAnalysisView({ agents }) {
  if (!isPlainObject(agents)) return null;
  const entries = Object.entries(agents)
    .map(([key, item]) => [key, typeof item === "string" ? item : item?.analysis || item?.summary || ""])
    .filter(([, text]) => text);
  if (!entries.length) return null;
  return (
    <section className="report-section">
      <h3>分析师观点</h3>
      <div className="agent-grid">
        {entries.map(([key, text]) => (
          <article key={key} className="agent-card">
            <h4>{AGENT_LABELS[key] || titleize(key)}</h4>
            <MarkdownBlock text={text} />
          </article>
        ))}
      </div>
    </section>
  );
}

const AGENT_LABELS = {
  technical: "技术分析师",
  fundamental: "基本面分析师",
  fund_flow: "资金面分析师",
  risk_management: "风险管理师",
  market_sentiment: "市场情绪分析师",
  news: "新闻分析师",
  macro: "宏观策略师",
  sector: "板块诊断师",
  fund: "资金流向分析师",
  sentiment: "市场情绪解码员",
  youzi: "游资行为分析师",
  stock: "个股潜力分析师",
  theme: "题材追踪分析师",
  risk: "风险控制专家",
  chief: "首席策略师",
  policy: "政策流动性分析师",
  kondratieff: "康波周期分析师",
  merrill: "美林时钟分析师",
};

function textFromAnalysis(value) {
  if (!value) return "";
  if (typeof value === "string") return value;
  if (isPlainObject(value)) {
    const direct = firstValue(value, ["analysis", "summary", "decision_text", "content", "report", "message"]);
    if (typeof direct === "string" && direct.trim()) return direct;
  }
  return "";
}

function HistoryDetailView({ detail }) {
  if (!detail) return <p className="muted">请选择左侧历史记录查看详情</p>;
  const stockInfo = detail.stock_info || {};
  const finalDecision = detail.final_decision || {};
  const agents = detail.agents_results || {};
  const stockName = detail.stock_name || stockInfo.name || "-";
  const symbol = detail.symbol || stockInfo.symbol || "-";
  const decisionText = textFromAnalysis(finalDecision);
  const discussionText = textFromAnalysis(detail.discussion_result);
  const decisionMetrics = [
    { label: "投资评级", value: finalDecision.rating },
    { label: "信心度", value: finalDecision.confidence_level || finalDecision.confidence },
    { label: "当前价", value: stockInfo.current_price },
    { label: "目标价", value: finalDecision.target_price },
    { label: "分析周期", value: detail.period },
    { label: "分析日期", value: detail.analysis_date || detail.created_at },
  ];
  const tradeMetrics = [
    { label: "进场区间", value: finalDecision.entry_range },
    { label: "止盈位", value: finalDecision.take_profit },
    { label: "止损位", value: finalDecision.stop_loss },
    { label: "持有周期", value: finalDecision.holding_period },
    { label: "建议仓位", value: finalDecision.position_size },
    { label: "行业", value: stockInfo.industry || stockInfo.sector },
  ];
  const agentEntries = Object.entries(agents)
    .map(([key, value]) => [key, textFromAnalysis(value), value])
    .filter(([, text]) => text);

  return (
    <div className="history-detail">
      <section className="report-section">
        <div className="history-title">
          <div>
            <h3>{stockName}</h3>
            <p>{symbol} · {detail.created_at || detail.analysis_date || ""}</p>
          </div>
          {finalDecision.rating ? <span className="badge strategy-badge">{finalDecision.rating}</span> : null}
        </div>
        <MetricStrip items={decisionMetrics} />
      </section>

      <section className="report-section">
        <h3>最终决策</h3>
        <MetricStrip items={tradeMetrics} />
        {finalDecision.operation_advice ? (
          <div className="decision-note">
            <strong>操作建议</strong>
            <p>{finalDecision.operation_advice}</p>
          </div>
        ) : null}
        {finalDecision.risk_warning ? (
          <div className="decision-note warning">
            <strong>风险提示</strong>
            <p>{finalDecision.risk_warning}</p>
          </div>
        ) : null}
        {decisionText ? <MarkdownBlock text={decisionText} /> : null}
        {!decisionText && !finalDecision.operation_advice && !finalDecision.risk_warning ? <DataView value={finalDecision} /> : null}
      </section>

      {discussionText ? (
        <section className="report-section">
          <h3>团队讨论</h3>
          <MarkdownBlock text={discussionText} />
        </section>
      ) : null}

      {agentEntries.length ? (
        <section className="report-section">
          <h3>分析师观点</h3>
          <div className="agent-grid">
            {agentEntries.map(([key, text]) => (
              <article key={key} className="agent-card">
                <h4>{AGENT_LABELS[key] || titleize(key)}</h4>
                <MarkdownBlock text={text} />
              </article>
            ))}
          </div>
        </section>
      ) : null}

      <details className="raw-details">
        <summary>查看原始数据</summary>
        <JsonBlock value={detail} />
      </details>
    </div>
  );
}

function formatElapsedSeconds(value) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds)) return "";
  if (seconds >= 60) return `${Math.floor(seconds / 60)}分${Math.round(seconds % 60)}秒`;
  return `${formatNumber(seconds, 1)}秒`;
}

function normalizeStockPoolAnalysisItem(item, index) {
  const result = item?.result || {};
  const stockInfo = result.stock_info || {};
  const finalDecision = result.final_decision || {};
  const poolItems = Array.isArray(item?.pool_items) ? item.pool_items : [];
  const primaryPoolItem = poolItems[0] || {};
  const symbol = result.symbol || stockInfo.symbol || item?.code || primaryPoolItem.code || "";
  const stockName = stockInfo.name || primaryPoolItem.name || "";
  const rating = finalDecision.rating || (result.success === false ? "失败" : "完成");
  const key = `${symbol || "stock"}-${index}`;
  return {
    key,
    symbol,
    stockName,
    rating,
    poolNames: poolItems.map((poolItem) => poolItem.pool_name).filter(Boolean),
    currentPrice: stockInfo.current_price,
    detail: {
      ...result,
      symbol,
      stock_name: stockName,
      pool_items: poolItems,
    },
  };
}

function StockPoolAnalysisResultView({ value }) {
  const items = useMemo(
    () => (value?.results || []).map((item, index) => normalizeStockPoolAnalysisItem(item, index)),
    [value],
  );
  const [selectedKey, setSelectedKey] = useState("");
  if (!value) return <p className="muted">暂无分析结果</p>;
  const selectedItem = items.find((item) => item.key === selectedKey) || items[0];
  const failures = Array.isArray(value.failed_stocks) ? value.failed_stocks : [];
  const metrics = [
    { label: "分析模式", value: value.mode === "parallel" ? "并发" : "顺序" },
    { label: "总数", value: value.total },
    { label: "成功", value: value.succeeded },
    { label: "失败", value: value.failed },
    { label: "耗时", value: formatElapsedSeconds(value.elapsed_time) },
    { label: "监测同步", value: value.sync_result ? `新增 ${value.sync_result.added || 0}，更新 ${value.sync_result.updated || 0}` : "" },
  ];

  return (
    <div className="stock-pool-result-view">
      {value.error ? <p className="error-text">{value.error}</p> : null}
      <MetricStrip items={metrics} />
      {items.length ? (
        <div className="stock-pool-result-grid">
          <div className="record-list">
            {items.map((item) => (
              <button
                key={item.key}
                className={selectedItem?.key === item.key ? "active" : ""}
                onClick={() => setSelectedKey(item.key)}
              >
                <strong>{item.symbol} {item.stockName}</strong>
                <span>
                  {item.rating}
                  {item.currentPrice ? ` · 当前价 ${item.currentPrice}` : ""}
                  {item.poolNames.length ? ` · ${item.poolNames.join("、")}` : ""}
                </span>
              </button>
            ))}
          </div>
          <HistoryDetailView detail={selectedItem?.detail} />
        </div>
      ) : (
        <p className="muted">暂无成功分析结果</p>
      )}
      {failures.length ? (
        <section className="report-section">
          <h3>失败股票</h3>
          <div className="stock-pool-failures">
            {failures.map((item, index) => (
              <div key={`${item.code || item.symbol || index}-${index}`}>
                <strong>{item.code || item.symbol || `#${index + 1}`}</strong>
                <span>{item.error || item.message || "分析失败"}</span>
              </div>
            ))}
          </div>
        </section>
      ) : null}
      <details className="raw-details">
        <summary>查看原始批量结果</summary>
        <JsonBlock value={value} />
      </details>
    </div>
  );
}

function StrategyReportView({ value }) {
  if (!value) return <p className="muted">暂无报告</p>;
  if (typeof value === "string") return <MarkdownBlock text={value} />;
  if (!isPlainObject(value)) return <DataView value={value} />;

  const reportObject = isPlainObject(value.report) ? value.report : value;
  const reportText = findReportText(value);
  const tables = collectReportTables(value);
  const metrics = [
    { label: "状态", value: value.success === false ? "失败" : "完成" },
    { label: "时间", value: firstValue(value, ["timestamp", "fetch_time", "report.report_date"]) },
    { label: "报告编号", value: firstValue(value, ["report_id", "saved_report.id", "report.id"]) },
    { label: "风险等级", value: firstValue(value, ["final_predictions.risk_level", "risk_level", "ai_analysis.risk_assess.risk_level"]) },
    { label: "市场展望", value: firstValue(value, ["final_predictions.market_outlook", "market_outlook", "sector_view.market_view"]) },
    { label: "置信度", value: firstValue(value, ["final_predictions.confidence_score", "confidence_score", "ai_analysis.investment_advice.confidence"]) },
  ];

  return (
    <div className="report-view">
      {value.error ? <p className="error-text">{value.error}</p> : null}
      <MetricStrip items={metrics} />
      {reportText ? (
        <section className="report-section">
          <h3>核心报告</h3>
          <MarkdownBlock text={reportText} />
        </section>
      ) : null}
      {isPlainObject(value.final_predictions) ? (
        <section className="report-section">
          <h3>最终研判</h3>
          <DataView value={value.final_predictions} />
        </section>
      ) : null}
      {tables.map(([title, rows]) => (
        <section key={title} className="report-section">
          <h3>{title}</h3>
          <Table rows={rows} preset={title} />
        </section>
      ))}
      <AgentAnalysisView agents={value.agents_analysis || reportObject.agents_analysis} />
      <details className="raw-details">
        <summary>查看原始数据</summary>
        <JsonBlock value={value} />
      </details>
    </div>
  );
}

function ReportArchive({ value }) {
  const reports = Array.isArray(value) ? value : (Array.isArray(value?.records) ? value.records : []);
  if (!reports.length) return <p className="muted">暂无历史报告</p>;
  return (
    <div className="report-archive">
      {reports.slice(0, 20).map((report, index) => {
        const detail = normalizeStoredReportDetail(report);
        const title = firstValue(report, ["title", "report_title", "report_type", "analysis_type", "data_date_range"]) || `报告 ${index + 1}`;
        const date = firstValue(report, ["report_date", "analysis_date", "created_at", "timestamp", "date"]);
        const summary = firstValue(report, ["summary", "market_outlook", "content", "comprehensive_report", "markdown"]);
        const metrics = [
          { label: "编号", value: report.id || report.report_id },
          { label: "日期", value: date },
          { label: "风险", value: report.risk_level },
          { label: "置信度", value: report.confidence_score || report.confidence },
        ];
        return (
          <article key={report.id || report.report_id || index} className="report-card">
            <div className="report-card-head">
              <h3>{formatCell(title)}</h3>
              {date ? <span>{String(date)}</span> : null}
            </div>
            <MetricStrip items={metrics} />
            {summary ? <p>{compactText(summary, 260)}</p> : null}
            <details className="raw-details">
              <summary>查看详情</summary>
              <StrategyReportView value={detail} />
            </details>
          </article>
        );
      })}
    </div>
  );
}

function normalizeStoredReportDetail(report) {
  const parsed = isPlainObject(report?.analysis_content_parsed) ? report.analysis_content_parsed : null;
  if (!parsed) return report;
  return {
    ...parsed,
    report_id: report.id || report.report_id || parsed.report_id,
    saved_report: report,
    summary: parsed.summary || report.summary,
    risk_level: parsed.risk_level || report.risk_level,
    confidence_score: parsed.confidence_score || report.confidence_score,
    market_outlook: parsed.market_outlook || report.market_outlook,
    recommended_stocks: parsed.recommended_stocks || report.recommended_stocks,
    recommended_sectors: parsed.recommended_sectors || report.recommended_sectors_parsed,
  };
}

const MAIN_FORCE_METRIC_FIELDS = [
  { label: "所属行业", aliases: ["industry", "所属同花顺行业", "所属行业", "行业", "sector"], type: "text" },
  { label: "主力净流入", aliases: ["main_fund_inflow", "区间主力资金流向", "区间主力资金净流入", "主力资金流向", "主力资金净流入", "主力净流入"], type: "money" },
  { label: "区间涨跌幅", aliases: ["range_change", "区间涨跌幅:前复权", "区间涨跌幅", "涨跌幅:前复权", "涨跌幅"], type: "percent" },
  { label: "总市值", aliases: ["market_cap", "总市值", "市值", "流通市值"], type: "marketCap" },
  { label: "市盈率", aliases: ["pe_ratio", "市盈率", "PE", "pe"], type: "number" },
  { label: "市净率", aliases: ["pb_ratio", "市净率", "PB", "pb"], type: "number" },
];

function formatMainForceMetricValue(value, type) {
  if (!hasDisplayValue(value)) return "";
  if (type === "money") return formatMoneyValue(value);
  if (type === "marketCap") {
    if (typeof value === "string" && /[万亿元]/.test(value)) return value;
    const number = Number(String(value).replace(/,/g, ""));
    if (!Number.isFinite(number)) return String(value);
    return number >= 100000000 ? `${formatNumber(number / 100000000)}亿` : `${formatNumber(number)}亿`;
  }
  if (type === "percent") return formatPercentValue(value);
  if (type === "number") {
    const number = Number(String(value).replace(/,/g, ""));
    return Number.isFinite(number) ? formatNumber(number) : String(value);
  }
  return formatCell(value);
}

function mainForceSources(rec) {
  const stockData = isPlainObject(rec?.stock_data) ? rec.stock_data : {};
  return [rec, stockData, stockData.raw_data].filter(isPlainObject);
}

function mainForceStockTitle(rec) {
  const sources = mainForceSources(rec);
  const symbol = rec?.symbol || findAliasValue(sources, ["symbol", "股票代码", "代码", "stock_code"]);
  const name = rec?.name || findAliasValue(sources, ["name", "股票简称", "股票名称", "stock_name"]);
  if (name && symbol) return `${name}（${symbol}）`;
  return name || symbol || "未命名标的";
}

function mainForceMetrics(rec) {
  const sources = mainForceSources(rec);
  return MAIN_FORCE_METRIC_FIELDS.map((field) => {
    const value = findAliasValue(sources, field.aliases);
    return { label: field.label, value: formatMainForceMetricValue(value, field.type) };
  }).filter((item) => hasDisplayValue(item.value));
}

function MainForceResultView({ value }) {
  if (!value) return <p className="muted">暂无结果</p>;
  if (!isPlainObject(value)) return <DataView value={value} />;
  const recommendations = Array.isArray(value.final_recommendations) ? value.final_recommendations : [];
  const params = isPlainObject(value.params) ? value.params : {};
  const totalStocks = Number(value.total_stocks);
  const filteredStocks = Number(value.filtered_stocks);
  const passRate = Number.isFinite(totalStocks) && totalStocks > 0 && Number.isFinite(filteredStocks)
    ? `${formatNumber((filteredStocks / totalStocks) * 100, 1)}%`
    : undefined;
  const overview = [
    { label: "运行状态", value: value.success === false ? "失败" : "已完成" },
    { label: "获取股票", value: Number.isFinite(totalStocks) ? `${totalStocks} 只` : value.total_stocks },
    { label: "筛选通过", value: Number.isFinite(filteredStocks) ? `${filteredStocks} 只` : value.filtered_stocks },
    { label: "通过率", value: passRate },
    { label: "最终推荐", value: `${recommendations.length} 只` },
  ];
  const runParams = [
    { label: "回看天数", value: hasDisplayValue(params.days_ago) ? `${params.days_ago} 天` : undefined },
    { label: "起始日期", value: params.start_date },
    { label: "推荐数量", value: params.final_n },
    { label: "最大涨跌幅", value: hasDisplayValue(params.max_range_change) ? `${params.max_range_change}%` : undefined },
    { label: "最小市值", value: hasDisplayValue(params.min_market_cap) ? `${params.min_market_cap} 亿` : undefined },
    { label: "最大市值", value: hasDisplayValue(params.max_market_cap) ? `${params.max_market_cap} 亿` : undefined },
  ];

  return (
    <div className="main-force-report">
      {value.error ? <p className="error-text">{value.error}</p> : null}

      <section className="report-section">
        <h3>筛选概览</h3>
        <MetricStrip items={overview} />
      </section>

      <section className="report-section">
        <h3>最终推荐</h3>
        {recommendations.length ? (
          <div className="main-force-cards">
            {recommendations.map((rec, index) => {
              const rank = rec.rank || index + 1;
              const metrics = mainForceMetrics(rec);
              const reasons = normalizeTextList(rec.reasons || rec.reason || rec.analysis_reason);
              const highlights = compactText(rec.highlights || rec.highlight || "", 360);
              const risks = compactText(rec.risks || rec.risk || rec.risk_warning || "", 360);
              const period = rec.investment_period || rec.investment_horizon;
              return (
                <article key={`${rec.symbol || rec.name || index}-${rank}`} className="main-force-card">
                  <div className="main-force-card-head">
                    <div>
                      <span className="main-force-rank">第 {rank} 名</span>
                      <h4>{mainForceStockTitle(rec)}</h4>
                    </div>
                    {rec.position ? <span className="badge strategy-badge">{rec.position}</span> : null}
                  </div>

                  {metrics.length ? (
                    <div className="main-force-metrics">
                      {metrics.map((item) => (
                        <div key={item.label} className="main-force-metric">
                          <span>{item.label}</span>
                          <strong>{item.value}</strong>
                        </div>
                      ))}
                    </div>
                  ) : null}

                  {reasons.length ? (
                    <div className="main-force-reasons">
                      <h5>核心理由</h5>
                      <ul>
                        {reasons.map((item) => <li key={item}>{item}</li>)}
                      </ul>
                    </div>
                  ) : null}

                  {(highlights || risks) ? (
                    <div className="main-force-notes">
                      {highlights ? (
                        <div className="decision-note">
                          <strong>投资亮点</strong>
                          <p>{highlights}</p>
                        </div>
                      ) : null}
                      {risks ? (
                        <div className="decision-note warning">
                          <strong>风险提示</strong>
                          <p>{risks}</p>
                        </div>
                      ) : null}
                    </div>
                  ) : null}

                  {(period || rec.position) ? (
                    <div className="main-force-tags">
                      {period ? <span>投资周期：{period}</span> : null}
                      {rec.position ? <span>建议仓位：{rec.position}</span> : null}
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        ) : (
          <p className="muted">暂无推荐结果，请放宽筛选条件后重新运行。</p>
        )}
      </section>

      <section className="report-section">
        <h3>运行参数</h3>
        <MetricStrip items={runParams} />
      </section>

      <details className="raw-details">
        <summary>查看原始数据</summary>
        <JsonBlock value={value} />
      </details>
    </div>
  );
}

function JobPanel({ job, onClear, renderResult, title = "任务状态" }) {
  if (!job) return null;
  const Result = renderResult;
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>{title}</h2>
        <span className={`badge ${job.status}`}>{formatCell(job.status)}</span>
      </div>
      <div className="progress">
        <div style={{ width: `${job.progress || 0}%` }} />
      </div>
      <p className="muted">{job.message}</p>
      {job.error ? <p className="error-text">{job.error}</p> : null}
      {job.result ? (Result ? <Result value={job.result} /> : <DataView value={job.result} />) : null}
      {onClear ? <Button variant="secondary" onClick={onClear}>清除结果</Button> : null}
    </section>
  );
}

function jobStorageKey(key) {
  return key ? `aiagents-stock:job:${key}` : null;
}

function readStoredJobId(key) {
  const storageKey = jobStorageKey(key);
  if (!storageKey) return null;
  try {
    return window.localStorage.getItem(storageKey);
  } catch {
    return null;
  }
}

function writeStoredJobId(key, jobId) {
  const storageKey = jobStorageKey(key);
  if (!storageKey) return;
  try {
    if (jobId) {
      window.localStorage.setItem(storageKey, jobId);
    } else {
      window.localStorage.removeItem(storageKey);
    }
  } catch {
    // Local storage can be unavailable in private or restricted browser modes.
  }
}

function useJob(storageKey) {
  const [jobState, setJobState] = useState({ storageKey, job: null });
  const job = jobState.storageKey === storageKey ? jobState.job : null;
  useEffect(() => {
    const storedJobId = readStoredJobId(storageKey);
    if (!storedJobId) {
      setJobState({ storageKey, job: null });
      return undefined;
    }
    let active = true;
    setJobState({ storageKey, job: null });
    request(`/jobs/${storedJobId}`)
      .then((snapshot) => {
        if (active && readStoredJobId(storageKey) === storedJobId) setJobState({ storageKey, job: snapshot });
      })
      .catch(() => {
        writeStoredJobId(storageKey, null);
        if (active) setJobState({ storageKey, job: null });
      });
    return () => {
      active = false;
    };
  }, [storageKey]);
  const start = async (path, payload = {}) => {
    const response = await request(path, { method: "POST", body: JSON.stringify(payload) });
    setJobState({ storageKey, job: response.job });
    writeStoredJobId(storageKey, response.job_id || response.job?.id);
    return response.job_id;
  };
  useEffect(() => {
    if (!job?.id || ["completed", "failed"].includes(job.status)) return;
    const timer = setInterval(async () => {
      try {
        const snapshot = await request(`/jobs/${job.id}`);
        setJobState((prev) => (prev.storageKey === storageKey ? { storageKey, job: snapshot } : prev));
      } catch (error) {
        setJobState((prev) => (
          prev.storageKey === storageKey && prev.job
            ? { storageKey, job: { ...prev.job, status: "failed", error: error.message } }
            : prev
        ));
      }
    }, 1500);
    return () => clearInterval(timer);
  }, [job?.id, job?.status, storageKey]);
  const clear = () => {
    writeStoredJobId(storageKey, null);
    setJobState({ storageKey, job: null });
  };
  return { job, start, clear };
}

function Dashboard() {
  const { loading, error, data, reload } = useAsync(() => request("/system/status"), []);
  const status = data || {};
  return (
    <Page title="系统总览" subtitle="后端任务、数据存储和监测服务状态">
      <section className="metric-grid">
        <Metric label="当前模型" value={status.model || "-"} />
        <Metric label="接口配置" value={status.api_configured ? "已配置" : "未配置"} />
        <Metric label="监测服务" value={status.monitor_running ? "运行中" : "已停止"} />
        <Metric label="分析记录" value={status.analysis_records ?? "-"} />
        <Metric label="监测股票" value={status.monitored_stocks ?? "-"} />
        <Metric label="待处理通知" value={status.pending_notifications ?? "-"} />
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>健康检查</h2>
          <Button icon={RefreshCw} variant="secondary" onClick={reload}>刷新</Button>
        </div>
        {loading ? <p className="muted">加载中...</p> : error ? <p className="error-text">{error}</p> : <DataView value={status} />}
      </section>
    </Page>
  );
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StockAnalysisPage() {
  const { job, start, clear } = useJob();
  const [mode, setMode] = useState("single");
  const [form, setForm] = useState({
    symbol: "600519",
    input: "600519\n000001",
    period: "1y",
    max_workers: 3,
    analysts: {
      technical: true,
      fundamental: true,
      fund_flow: true,
      risk: true,
      sentiment: false,
      news: false,
    },
  });
  const updateAnalyst = (key) =>
    setForm((prev) => ({ ...prev, analysts: { ...prev.analysts, [key]: !prev.analysts[key] } }));
  const submit = () => start(mode === "single" ? "/stock-analysis/analyze" : "/stock-analysis/batch", form);
  return (
    <Page title="股票分析" subtitle="单股深度分析与批量并行分析">
      <section className="panel">
        <div className="segmented">
          <button className={mode === "single" ? "active" : ""} onClick={() => setMode("single")}>单股分析</button>
          <button className={mode === "batch" ? "active" : ""} onClick={() => setMode("batch")}>批量分析</button>
        </div>
        <div className="form-grid">
          {mode === "single" ? (
            <Field label="股票代码">
              <input value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })} />
            </Field>
          ) : (
            <Field label="股票代码列表">
              <textarea value={form.input} onChange={(e) => setForm({ ...form, input: e.target.value })} />
            </Field>
          )}
          <Field label="周期">
            <select value={form.period} onChange={(e) => setForm({ ...form, period: e.target.value })}>
              <option value="1mo">1个月</option>
              <option value="3mo">3个月</option>
              <option value="6mo">6个月</option>
              <option value="1y">1年</option>
              <option value="2y">2年</option>
            </select>
          </Field>
          {mode === "batch" ? (
            <Field label="并行线程">
              <input type="number" min="1" max="10" value={form.max_workers} onChange={(e) => setForm({ ...form, max_workers: Number(e.target.value) })} />
            </Field>
          ) : null}
        </div>
        <div className="check-grid">
          {Object.entries({
            technical: "技术分析师",
            fundamental: "基本面分析师",
            fund_flow: "资金面分析师",
            risk: "风险管理师",
            sentiment: "市场情绪分析师",
            news: "新闻分析师",
          }).map(([key, label]) => (
            <label key={key} className="check">
              <input type="checkbox" checked={form.analysts[key]} onChange={() => updateAnalyst(key)} />
              {label}
            </label>
          ))}
        </div>
        <Button icon={Play} onClick={submit}>{mode === "single" ? "开始分析" : "开始批量分析"}</Button>
      </section>
      <JobPanel job={job} onClear={clear} />
    </Page>
  );
}

function HistoryPage() {
  const { loading, data, reload } = useAsync(() => request("/history"), []);
  const [detail, setDetail] = useState(null);
  const records = data?.records || [];
  const loadDetail = async (id) => setDetail(await request(`/history/${id}`));
  const remove = async (id) => {
    await request(`/history/${id}`, { method: "DELETE" });
    setDetail(null);
    reload();
  };
  const addMonitor = async (id) => {
    const response = await request(`/history/${id}/monitor`, { method: "POST", body: JSON.stringify({}) });
    alert(response.success ? "已加入监测" : response.error || "加入失败");
  };
  return (
    <Page title="历史记录" subtitle="查看、删除历史分析，并从历史决策加入监测">
      <section className="split">
        <div className="panel">
          <div className="panel-heading">
            <h2>记录列表</h2>
            <Button icon={RefreshCw} variant="secondary" onClick={reload}>刷新</Button>
          </div>
          {loading ? <p className="muted">加载中...</p> : (
            <div className="record-list">
              {records.map((record) => (
                <button key={record.id} className={detail?.id === record.id ? "active" : ""} onClick={() => loadDetail(record.id)}>
                  <strong>{record.symbol} {record.stock_name}</strong>
                  <span>{record.rating} · {record.analysis_date}</span>
                </button>
              ))}
              {!records.length ? <p className="muted">暂无历史记录</p> : null}
            </div>
          )}
        </div>
        <div className="panel">
          <div className="panel-heading">
            <h2>详情</h2>
            {detail ? (
              <div className="inline-actions">
                <Button icon={Plus} variant="secondary" onClick={() => addMonitor(detail.id)}>加入监测</Button>
                <Button icon={Trash2} variant="danger" onClick={() => remove(detail.id)}>删除</Button>
              </div>
            ) : null}
          </div>
          <HistoryDetailView detail={detail} />
        </div>
      </section>
    </Page>
  );
}

const SELECTOR_SPECS = {
  "main-force": {
    subtitle: "主力资金、资金流向和风险过滤的综合选股",
    summary: "按近阶段主力强度、区间波动和市值区间筛选，输出最终推荐列表。",
    quantity: { label: "最终推荐数量", min: 1, max: 30, hint: "用于最终推荐列表数量，同时保留 top_n 兼容后端任务。" },
    button: "运行主力选股",
    conditions: ["主力资金净流入", "区间涨跌幅不过热", "市值在指定区间内", "结合智能复核输出推荐"],
  },
  "low-price-bull": {
    subtitle: "低价高成长股票筛选",
    summary: "股价低于 10 元，净利润增长率较高，按成交额由小至大寻找低价弹性标的。",
    quantity: { label: "筛选数量", min: 3, max: 10, hint: "将筛选成交额最小的前 N 只股票。" },
    button: "开始低价擒牛选股",
    conditions: ["股价 < 10 元", "净利润增长率 >= 100%", "非 ST、非创业板、非科创板", "沪深 A 股", "按成交额由小至大排名"],
    tradeRules: ["初始资金 100 万元", "持股周期 5 天", "单股最大仓位 40%", "MA5 下穿 MA20 或持股满 5 天卖出"],
  },
  "small-cap": {
    subtitle: "小盘高成长股票筛选",
    summary: "聚焦总市值较小、营收和净利润高速增长的股票，按总市值由小至大排名。",
    quantity: { label: "筛选数量", min: 3, max: 10, hint: "将筛选市值最小的前 N 只股票。" },
    button: "开始小市值策略选股",
    conditions: ["总市值 <= 50 亿", "营收增长率 >= 10%", "净利润增长率 >= 100%", "非 ST、非创业板、非科创板", "按总市值由小至大排名"],
    tradeRules: ["初始资金 10 万元", "持股周期 5 天", "单股最大仓位 30%", "MA5 下穿 MA20 或持股满 5 天卖出"],
  },
  "profit-growth": {
    subtitle: "稳健成长股票筛选",
    summary: "筛选净利润持续增长的深圳 A 股，按成交额由小到大排序。",
    quantity: { label: "筛选数量", min: 3, max: 10, hint: "将筛选成交额最小的前 N 只股票。" },
    button: "开始净利增长选股",
    conditions: ["净利润增长率 >= 10%", "深圳 A 股", "非 ST、非创业板、非科创板", "按成交额由小到大排名"],
    tradeRules: ["初始资金 5 万元", "持股周期 5 天", "单日最多买入 1 只", "KDJ 死叉或持股满 5 天卖出"],
    note: "当前监控服务沿用 MA5 下穿 MA20 作为卖出提醒，后续可再升级 KDJ 指标。",
  },
  "value-stock": {
    defaultTopN: 10,
    subtitle: "价值投资低估值股票筛选",
    summary: "低 PE、低 PB、高股息、低负债，按流通市值由小到大寻找被低估标的。",
    quantity: { label: "筛选数量", min: 5, max: 20, hint: "将筛选流通市值最小的前 N 只低估值股票。" },
    button: "开始低估值选股",
    conditions: ["市盈率 PE <= 20", "市净率 PB <= 1.5", "股息率 >= 1%", "资产负债率 <= 30%", "非 ST、非创业板、非科创板"],
    tradeRules: ["初始资金 100 万元", "单股最大仓位 30%", "最多持股 4 只", "持股满 30 天或 RSI > 70 卖出"],
  },
};

function getSelectorInitialForm(selectorKey, topN) {
  const base = { top_n: topN, final_n: topN };
  if (selectorKey !== "main-force") return base;
  return {
    ...base,
    days_ago: 90,
    max_range_change: 30,
    min_market_cap: 50,
    max_market_cap: 5000,
  };
}

function SelectorPage({ selectorKey, title, defaultTopN, monitorPath }) {
  const spec = SELECTOR_SPECS[selectorKey] || {};
  const effectiveTopN = defaultTopN ?? spec.defaultTopN ?? 5;
  const quantity = spec.quantity || {};
  const ResultView = selectorKey === "main-force" ? MainForceResultView : undefined;
  const { job, start, clear } = useJob(`selector:${selectorKey}`);
  const [form, setForm] = useState(() => getSelectorInitialForm(selectorKey, effectiveTopN));
  useEffect(() => {
    setForm(getSelectorInitialForm(selectorKey, effectiveTopN));
  }, [selectorKey, effectiveTopN]);
  const monitor = useAsync(() => (monitorPath ? request(monitorPath) : Promise.resolve(null)), [monitorPath]);
  const history = useAsync(() => request(`/selectors/${selectorKey}/history`), [selectorKey]);
  useEffect(() => {
    if (job?.status === "completed") history.reload();
  }, [job?.id, job?.status]);
  const updateTopN = (value) => {
    const next = Number(value) || effectiveTopN;
    setForm({ ...form, top_n: next, final_n: next });
  };
  return (
    <Page title={title} subtitle={spec.subtitle || "保留原策略筛选条件，结果通过接口任务异步返回"}>
      <section className="panel">
        <div className="selector-brief">
          <div>
            <h2>{title}配置</h2>
            <p>{spec.summary || "运行当前选股策略并异步返回结果。"}</p>
          </div>
          <span className="badge strategy-badge">{title}</span>
        </div>
        {spec.conditions?.length ? (
          <div className="strategy-grid">
            <div>
              <h3>筛选条件</h3>
              <ul>
                {spec.conditions.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>
            {spec.tradeRules?.length ? (
              <div>
                <h3>交易规则</h3>
                <ul>
                  {spec.tradeRules.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
        {spec.note ? <p className="muted">{spec.note}</p> : null}
        <div className="form-grid">
          <Field label={quantity.label || "返回数量"}>
            <input
              type="number"
              min={quantity.min ?? 1}
              max={quantity.max ?? 100}
              value={form.top_n}
              onChange={(e) => updateTopN(e.target.value)}
            />
            {quantity.hint ? <small className="field-help">{quantity.hint}</small> : null}
          </Field>
          {selectorKey === "main-force" ? (
            <>
              <Field label="距今天数">
                <input type="number" min="1" value={form.days_ago ?? ""} onChange={(e) => setForm({ ...form, days_ago: Number(e.target.value) || "" })} />
              </Field>
              <Field label="最大涨跌幅">
                <input type="number" min="5" max="200" value={form.max_range_change ?? ""} onChange={(e) => setForm({ ...form, max_range_change: Number(e.target.value) || "" })} />
              </Field>
              <Field label="最小市值(亿)">
                <input type="number" min="10" value={form.min_market_cap ?? ""} onChange={(e) => setForm({ ...form, min_market_cap: Number(e.target.value) || "" })} />
              </Field>
              <Field label="最大市值(亿)">
                <input type="number" min="50" value={form.max_market_cap ?? ""} onChange={(e) => setForm({ ...form, max_market_cap: Number(e.target.value) || "" })} />
              </Field>
            </>
          ) : null}
        </div>
        <Button icon={Play} onClick={() => start(`/selectors/${selectorKey}/run`, form)}>{spec.button || "运行策略"}</Button>
      </section>
      <JobPanel job={job} onClear={clear} renderResult={ResultView} />
      <section className="panel">
        <div className="panel-heading">
          <h2>历史结果</h2>
          <Button icon={RefreshCw} variant="secondary" onClick={history.reload}>刷新</Button>
        </div>
        <ReportArchive value={history.data?.reports} />
      </section>
      {monitorPath ? (
        <section className="panel">
          <div className="panel-heading">
            <h2>策略监控</h2>
            <Button icon={RefreshCw} variant="secondary" onClick={monitor.reload}>刷新</Button>
          </div>
          <DataView value={monitor.data} />
        </section>
      ) : null}
    </Page>
  );
}

const STRATEGY_RESEARCH_SPECS = {
  "sector-strategy": {
    badge: "智策板块",
    subtitle: "板块轮动、资金热度和产业主线的综合研判",
    summary: "从板块涨跌、资金强度、成交活跃度和政策催化中识别当前市场主线，判断板块延续性与风险位置。",
    sections: [
      { title: "策略目标", items: ["识别当前最强势或正在形成趋势的板块", "区分短线脉冲、持续主线和高位退潮板块", "为后续龙头战法和个股筛选提供板块方向"] },
      { title: "核心逻辑", items: ["比较板块涨幅、成交额、资金净流入和市场关注度", "结合政策、新闻和产业事件判断催化是否真实", "关注板块内部扩散程度，避免只由少数个股拉动"] },
      { title: "输出结果", items: ["主线板块候选、风险提示和优先级排序", "板块强度、趋势状态和操作节奏建议", "历史报告用于复盘板块强弱切换"] },
    ],
  },
  "dragon-strategy": {
    badge: "龙头战法",
    subtitle: "围绕市场龙头、主线板块和趋势候选的短线研判",
    summary: "用情绪、强度、板块地位和趋势结构识别市场核心标的，重点服务短线主线跟踪和龙头候选复盘。",
    sections: [
      { title: "策略目标", items: ["找到当前市场最有辨识度的龙头候选", "跟踪主线板块内的强势标的和补涨梯队", "形成每日可复盘的龙头观察清单"] },
      { title: "核心逻辑", items: ["综合涨停强度、连板结构、成交活跃度和板块归属", "区分龙头、跟风、补涨和趋势中军的不同角色", "结合情绪周期判断加速、分歧、修复和退潮阶段"] },
      { title: "输出结果", items: ["龙头评分、主线板块和趋势候选列表", "可按交易日回看日报和候选变化", "用于短线策略的情绪与主线参考"] },
    ],
  },
  longhubang: {
    badge: "智瞰龙虎",
    subtitle: "龙虎榜席位、游资行为和异动个股的资金画像",
    summary: "解析龙虎榜上榜股票、营业部席位、买卖净额和历史活跃度，识别资金参与质量和可能的持续性。",
    sections: [
      { title: "策略目标", items: ["判断上榜个股背后的资金性质和参与强度", "识别活跃游资、机构席位和异常买卖行为", "辅助判断短线资金是否集中在某些题材或个股"] },
      { title: "核心逻辑", items: ["统计买入席位、卖出席位、净买额和席位历史表现", "结合个股涨跌、成交额和题材归属评估资金意图", "区分机构推动、游资接力和高位兑现风险"] },
      { title: "输出结果", items: ["龙虎榜智能评分、推荐关注股票和席位解读", "游资排行、个股排行和历史统计", "为短线复盘提供资金侧证据"] },
    ],
  },
  "news-flow": {
    badge: "新闻流量",
    subtitle: "热点新闻、主题催化和市场情绪的流量监测",
    summary: "从新闻热度、传播速度、主题聚类和情绪倾向中捕捉正在发酵的市场线索，判断信息催化对行情的影响。",
    sections: [
      { title: "策略目标", items: ["识别正在升温的政策、产业和事件主题", "发现可能驱动板块或个股异动的新闻源", "对热点持续性和情绪风险做快速判断"] },
      { title: "核心逻辑", items: ["抓取多平台新闻并按主题、分类和情绪聚合", "比较热度变化、重复传播和新增催化强度", "结合市场语境过滤低质量噪声和滞后消息"] },
      { title: "输出结果", items: ["快速分析、完整智能分析和预警检查结果", "新闻流量仪表盘、趋势变化和重点主题", "用于盘前、盘中和复盘的信息面辅助"] },
    ],
  },
  "macro-analysis": {
    badge: "宏观分析",
    subtitle: "宏观环境、政策变量和资产风险偏好的综合分析",
    summary: "从增长、通胀、利率、汇率、流动性和政策方向评估市场所处宏观背景，解释指数和行业风格的底层约束。",
    sections: [
      { title: "策略目标", items: ["判断当前市场是偏宽松、偏收缩还是政策观察期", "解释大盘风险偏好和资金风格变化的宏观原因", "为行业配置、仓位节奏和风险控制提供背景"] },
      { title: "核心逻辑", items: ["跟踪经济数据、货币政策、财政政策和海外变量", "分析利率、汇率、商品和资金面之间的联动", "把宏观变化映射到成长、周期、消费和金融等风格"] },
      { title: "输出结果", items: ["宏观环境判断、主要矛盾和风险点", "政策与流动性变化对 A 股的影响", "适合作为中期策略和组合管理输入"] },
    ],
  },
  "macro-cycle": {
    badge: "宏观周期",
    subtitle: "经济周期、行业景气和市场风格轮动判断",
    summary: "用周期位置、景气变化和政策方向判断市场处于复苏、过热、滞胀或衰退的哪一段，并推导可能受益的行业风格。",
    sections: [
      { title: "策略目标", items: ["识别宏观周期阶段和下一阶段可能的切换方向", "判断哪些行业或资产风格更可能占优", "帮助把短期热点放到中期周期框架中验证"] },
      { title: "核心逻辑", items: ["观察增长、通胀、库存、利润和信用扩张状态", "比较周期、成长、消费、防御等风格的相对环境", "结合政策节奏判断周期拐点是否得到确认"] },
      { title: "输出结果", items: ["周期阶段判断、风格配置倾向和观察指标", "行业景气线索与风险提示", "用于中期仓位和板块轮动决策"] },
    ],
  },
};

const DRAGON_ACTION_SPECS = {
  daily_report: {
    title: "生成日报",
    pageTitle: "龙头战法 - 生成日报",
    subtitle: "汇总市场情绪、龙头评分、主线板块、趋势候选和仓位建议",
    badge: "日报",
    summary: "生成完整的龙头战法日报，适合盘后复盘和次日交易计划准备。",
    button: "生成日报",
    showHistory: true,
    sections: [
      { title: "页面目标", items: ["查看市场情绪是否支持龙头战法", "同时复盘龙头候选、主线板块和趋势跟踪", "沉淀可回看的日报记录"] },
      { title: "输出内容", items: ["市场环境、情绪评分和仓位建议", "龙头评分结果、主线板块和趋势候选", "完整文字报告和历史日报"] },
      { title: "适用场景", items: ["盘后总结", "次日计划", "阶段性复盘"] },
    ],
  },
  mvp: {
    title: "龙头评分",
    pageTitle: "龙头战法 - 龙头评分",
    subtitle: "只运行龙头候选评分，聚焦连板强度、封单质量和板块地位",
    badge: "评分",
    summary: "筛选并评分当前龙头候选，适合快速查看市场核心标的。",
    button: "运行龙头评分",
    sections: [
      { title: "页面目标", items: ["识别当前最有辨识度的龙头候选", "按连板、封板时间、封单和板块地位打分", "区分总龙头、主线龙头、板块龙头和补涨候选"] },
      { title: "输出内容", items: ["龙头候选表", "评分明细", "交易计划和风险提示"] },
      { title: "适用场景", items: ["短线核心标的筛选", "涨停梯队复盘", "龙头候选对比"] },
    ],
  },
  sectors: {
    title: "主线板块",
    pageTitle: "龙头战法 - 主线板块",
    subtitle: "只运行主线板块跟踪，聚焦板块排名、涨跌幅、成交额、上涨家数和连续性",
    badge: "板块",
    summary: "跟踪当前市场主线板块和观察板块，判断板块是否具备持续发酵条件。",
    button: "更新主线板块",
    useTopN: true,
    quantityLabel: "板块数量",
    sections: [
      { title: "页面目标", items: ["确认当前资金最集中的主线板块", "观察板块涨幅排名、涨停数和连续主线天数", "识别启动、发酵、高潮、观察和退潮状态"] },
      { title: "输出内容", items: ["板块名称、排名、涨跌幅和成交额", "股票数、上涨家数、涨停数和连续天数", "阶段、评级和操作建议"] },
      { title: "适用场景", items: ["先定板块再选龙头", "判断题材持续性", "避免追逐退潮板块"] },
    ],
  },
  trends: {
    title: "趋势跟踪",
    pageTitle: "龙头战法 - 趋势跟踪",
    subtitle: "只运行趋势候选扫描，聚焦均线结构、量比、趋势分和支撑压力",
    badge: "趋势",
    summary: "扫描未必涨停但趋势结构较好的候选，作为龙头战法之外的趋势补充。",
    button: "扫描趋势候选",
    useTopN: true,
    quantityLabel: "候选数量",
    sections: [
      { title: "页面目标", items: ["寻找趋势延续且没有过热的候选个股", "查看均线多头、斜率、量比和 RSI 状态", "为主线板块提供趋势中军或补充标的"] },
      { title: "输出内容", items: ["趋势候选列表", "趋势分和技术结构", "支撑位、压力位和明细说明"] },
      { title: "适用场景", items: ["趋势股跟踪", "主线板块扩散观察", "非涨停标的补充"] },
    ],
  },
};

function StrategyIntro({ title, spec }) {
  if (!spec) return null;
  return (
    <section className="panel">
      <div className="selector-brief">
        <div>
          <h2>{title}策略说明</h2>
          <p>{spec.summary}</p>
        </div>
        <span className="badge strategy-badge">{spec.badge}</span>
      </div>
      <div className="strategy-grid detailed">
        {(spec.sections || []).map((section) => (
          <div key={section.title}>
            <h3>{section.title}</h3>
            <ul>
              {section.items.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}

function SimpleJobPage({ title, runPath, jobKey, strategyKey }) {
  const spec = STRATEGY_RESEARCH_SPECS[strategyKey];
  const { job, start, clear } = useJob(jobKey);
  return (
    <Page title={title} subtitle={spec?.subtitle || "智能分析会作为后台任务执行，切换页面不会中断"}>
      <StrategyIntro title={title} spec={spec} />
      <section className="panel">
        <Button icon={Play} onClick={() => start(runPath, {})}>开始分析</Button>
      </section>
      <JobPanel job={job} onClear={clear} renderResult={StrategyReportView} />
    </Page>
  );
}

function ReportJobPage({ title, runPath, reportsPath, jobKey, strategyKey }) {
  const spec = STRATEGY_RESEARCH_SPECS[strategyKey];
  const { job, start, clear } = useJob(jobKey);
  const reports = useAsync(() => request(reportsPath), [reportsPath]);
  useEffect(() => {
    if (job?.status === "completed") reports.reload();
  }, [job?.id, job?.status]);
  return (
    <Page title={title} subtitle={spec?.subtitle || "分析、历史报告和详情查看"}>
      <StrategyIntro title={title} spec={spec} />
      <section className="panel">
        <Button icon={Play} onClick={() => start(runPath, {})}>开始分析</Button>
      </section>
      <JobPanel job={job} onClear={clear} renderResult={StrategyReportView} />
      <section className="panel">
        <div className="panel-heading">
          <h2>历史报告</h2>
          <Button icon={RefreshCw} variant="secondary" onClick={reports.reload}>刷新</Button>
        </div>
        <ReportArchive value={reports.data?.reports} />
      </section>
    </Page>
  );
}

function DragonStrategyPage() {
  const [form, setForm] = useState({ action: "daily_report", top_n: 20 });
  const action = form.action || "daily_report";
  const actionSpec = DRAGON_ACTION_SPECS[action] || DRAGON_ACTION_SPECS.daily_report;
  const { job, start, clear } = useJob(`strategy:dragon-strategy:${action}`);
  const reports = useAsync(() => request("/dragon-strategy/reports"), []);
  return (
    <Page title={actionSpec.pageTitle} subtitle={actionSpec.subtitle}>
      <StrategyIntro key={action} title={actionSpec.title} spec={actionSpec} />
      <section className="panel">
        <div className="panel-heading">
          <h2>{actionSpec.title}参数</h2>
        </div>
        <div className="form-grid">
          <Field label="动作">
            <select value={action} onChange={(e) => setForm((prev) => ({ ...prev, action: e.target.value }))}>
              <option value="daily_report">生成日报</option>
              <option value="mvp">龙头评分</option>
              <option value="sectors">主线板块</option>
              <option value="trends">趋势跟踪</option>
            </select>
          </Field>
          <Field label="交易日期">
            <input placeholder="YYYYMMDD，可空" value={form.date || ""} onChange={(e) => setForm({ ...form, date: e.target.value })} />
          </Field>
          {actionSpec.useTopN ? (
            <Field label={actionSpec.quantityLabel || "返回数量"}>
              <input type="number" min="1" value={form.top_n} onChange={(e) => setForm({ ...form, top_n: Number(e.target.value) })} />
            </Field>
          ) : null}
        </div>
        <Button icon={Play} onClick={() => start("/dragon-strategy/run", { ...form, action })}>{actionSpec.button}</Button>
      </section>
      <JobPanel job={job} onClear={clear} renderResult={StrategyReportView} title={`${actionSpec.title}任务状态`} />
      {actionSpec.showHistory ? (
        <section className="panel">
          <div className="panel-heading">
            <h2>历史日报</h2>
            <Button icon={RefreshCw} variant="secondary" onClick={reports.reload}>刷新</Button>
          </div>
          <ReportArchive value={reports.data?.reports} />
        </section>
      ) : null}
    </Page>
  );
}

function LonghubangPage() {
  const spec = STRATEGY_RESEARCH_SPECS.longhubang;
  const { job, start, clear } = useJob("strategy:longhubang");
  const [form, setForm] = useState({ days: 1 });
  const reports = useAsync(() => request("/longhubang/reports"), []);
  const stats = useAsync(() => request("/longhubang/statistics"), []);
  useEffect(() => {
    if (job?.status === "completed") {
      reports.reload();
      stats.reload();
    }
  }, [job?.id, job?.status]);
  return (
    <Page title="智瞰龙虎" subtitle={spec.subtitle}>
      <StrategyIntro title="智瞰龙虎" spec={spec} />
      <section className="panel">
        <div className="form-grid">
          <Field label="指定日期">
            <input placeholder="YYYY-MM-DD，可空" value={form.date || ""} onChange={(e) => setForm({ ...form, date: e.target.value })} />
          </Field>
          <Field label="最近天数">
            <input type="number" min="1" max="10" value={form.days} onChange={(e) => setForm({ ...form, days: Number(e.target.value) })} />
          </Field>
        </div>
        <Button icon={Play} onClick={() => start("/longhubang/run", form)}>开始分析</Button>
      </section>
      <JobPanel job={job} onClear={clear} renderResult={StrategyReportView} />
      <section className="grid-two">
        <div className="panel">
          <div className="panel-heading">
            <h2>历史报告</h2>
            <Button icon={RefreshCw} variant="secondary" onClick={reports.reload}>刷新</Button>
          </div>
          <ReportArchive value={reports.data?.reports} />
        </div>
        <div className="panel">
          <div className="panel-heading">
            <h2>统计排行</h2>
            <Button icon={RefreshCw} variant="secondary" onClick={stats.reload}>刷新</Button>
          </div>
          <DataView value={stats.data} />
        </div>
      </section>
    </Page>
  );
}

function NewsFlowPage() {
  const spec = STRATEGY_RESEARCH_SPECS["news-flow"];
  const { job, start, clear } = useJob("strategy:news-flow");
  const [form, setForm] = useState({ mode: "quick", category: "" });
  const dashboard = useAsync(() => request("/news-flow/dashboard"), []);
  return (
    <Page title="新闻流量" subtitle={spec.subtitle}>
      <StrategyIntro title="新闻流量" spec={spec} />
      <section className="panel">
        <div className="form-grid">
          <Field label="模式">
            <select value={form.mode} onChange={(e) => setForm({ ...form, mode: e.target.value })}>
              <option value="quick">快速分析</option>
              <option value="full">智能完整分析</option>
              <option value="alerts">预警检查</option>
            </select>
          </Field>
          <Field label="分类">
            <input placeholder="可空" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
          </Field>
        </div>
        <Button icon={Play} onClick={() => start("/news-flow/run", form)}>运行</Button>
      </section>
      <JobPanel job={job} onClear={clear} renderResult={StrategyReportView} />
      <section className="panel">
        <div className="panel-heading">
          <h2>仪表盘</h2>
          <Button icon={RefreshCw} variant="secondary" onClick={dashboard.reload}>刷新</Button>
        </div>
        <DataView value={dashboard.data} />
      </section>
    </Page>
  );
}

function PortfolioPage() {
  const { loading, data, reload } = useAsync(() => request("/portfolio"), []);
  const navigate = useNavigate();
  return (
    <Page title="持仓分析" subtitle="持仓池是股票池的系统持仓视图">
      <section className="panel">
        <div className="panel-heading">
          <h2>{data?.pool?.name || "持仓池"}</h2>
          <div className="inline-actions">
            <Button icon={RefreshCw} variant="secondary" onClick={reload}>刷新</Button>
            <Button icon={Play} onClick={() => navigate("/stock-pool")}>批量分析</Button>
          </div>
        </div>
        {loading ? <p className="muted">加载中...</p> : <DataView value={data?.stocks} />}
      </section>
    </Page>
  );
}

function StockPoolPage() {
  const pools = useAsync(() => request("/stock-pools"), []);
  const { job, start, clear } = useJob("investment:stock-pool");
  const [selectedPoolId, setSelectedPoolId] = useState("");
  const [stockForm, setStockForm] = useState({ code: "", name: "", tags: "" });
  const [poolForm, setPoolForm] = useState({ name: "", description: "" });
  const [importText, setImportText] = useState("");
  const [selectedStockCodes, setSelectedStockCodes] = useState([]);
  const [analysisMode, setAnalysisMode] = useState("sequential");
  const [maxWorkers, setMaxWorkers] = useState(3);
  const stocks = useAsync(
    () => (selectedPoolId ? request(`/stock-pools/${selectedPoolId}/stocks`) : Promise.resolve({ stocks: [] })),
    [selectedPoolId],
  );
  const poolStocks = Array.isArray(stocks.data?.stocks) ? stocks.data.stocks : [];
  const availableStockCodes = useMemo(() => (
    Array.from(new Set((stocks.data?.stocks || []).map(stockRowCode).filter(Boolean)))
  ), [stocks.data]);
  useEffect(() => {
    if (!selectedPoolId && pools.data?.pools?.length) {
      setSelectedPoolId(String(pools.data.pools[0].id));
    }
  }, [pools.data, selectedPoolId]);
  useEffect(() => {
    setSelectedStockCodes([]);
  }, [selectedPoolId]);
  useEffect(() => {
    setSelectedStockCodes((prev) => prev.filter((code) => availableStockCodes.includes(code)));
  }, [availableStockCodes]);
  const createPool = async () => {
    await request("/stock-pools", { method: "POST", body: JSON.stringify(poolForm) });
    setPoolForm({ name: "", description: "" });
    pools.reload();
  };
  const addStock = async () => {
    await request(`/stock-pools/${selectedPoolId}/stocks`, { method: "POST", body: JSON.stringify(stockForm) });
    setStockForm({ code: "", name: "", tags: "" });
    stocks.reload();
  };
  const batchImport = async () => {
    await request(`/stock-pools/${selectedPoolId}/batch-import`, { method: "POST", body: JSON.stringify({ input: importText }) });
    setImportText("");
    stocks.reload();
  };
  const toggleStockSelection = (code) => {
    setSelectedStockCodes((prev) => (
      prev.includes(code) ? prev.filter((item) => item !== code) : [...prev, code]
    ));
  };
  const startPoolAnalysis = () => {
    const selectedCodes = selectedStockCodes.filter((code) => availableStockCodes.includes(code));
    const workerCount = Math.max(1, Math.min(10, Number(maxWorkers) || 3));
    start("/stock-pools/analyze", {
      pool_ids: [Number(selectedPoolId)],
      selected_codes: selectedCodes,
      scope: "all",
      mode: analysisMode,
      max_workers: workerCount,
      auto_sync_monitor: true,
    });
  };
  return (
    <Page title="股票池" subtitle="股票池管理、批量导入、池内分析和历史复盘">
      <section className="grid-two">
        <div className="panel">
          <h2>股票池</h2>
          <div className="form-grid">
            <Field label="选择股票池">
              <select value={selectedPoolId} onChange={(e) => setSelectedPoolId(e.target.value)}>
                {(pools.data?.pools || []).map((pool) => <option key={pool.id} value={pool.id}>{pool.name}</option>)}
              </select>
            </Field>
            <Field label="新建名称">
              <input value={poolForm.name} onChange={(e) => setPoolForm({ ...poolForm, name: e.target.value })} />
            </Field>
            <Field label="说明">
              <input value={poolForm.description} onChange={(e) => setPoolForm({ ...poolForm, description: e.target.value })} />
            </Field>
          </div>
          <Button icon={Plus} onClick={createPool}>新建股票池</Button>
        </div>
        <div className="panel">
          <h2>添加股票</h2>
          <div className="form-grid">
            <Field label="代码"><input value={stockForm.code} onChange={(e) => setStockForm({ ...stockForm, code: e.target.value })} /></Field>
            <Field label="名称"><input value={stockForm.name} onChange={(e) => setStockForm({ ...stockForm, name: e.target.value })} /></Field>
            <Field label="标签"><input value={stockForm.tags} onChange={(e) => setStockForm({ ...stockForm, tags: e.target.value })} /></Field>
          </div>
          <Button icon={Plus} onClick={addStock} disabled={!selectedPoolId}>添加</Button>
        </div>
      </section>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>池内股票</h2>
            <p className="muted compact-text">已选 {selectedStockCodes.length} / {availableStockCodes.length}</p>
          </div>
          <div className="inline-actions">
            <Button icon={CheckSquare} variant="secondary" onClick={() => setSelectedStockCodes(availableStockCodes)} disabled={!availableStockCodes.length}>全选</Button>
            <Button icon={Eraser} variant="secondary" onClick={() => setSelectedStockCodes([])} disabled={!selectedStockCodes.length}>清空</Button>
            <Button icon={RefreshCw} variant="secondary" onClick={stocks.reload}>刷新</Button>
          </div>
        </div>
        <StockPoolSelectionTable
          rows={poolStocks}
          selectedCodes={selectedStockCodes}
          onToggleCode={toggleStockSelection}
          onSelectAll={setSelectedStockCodes}
        />
      </section>
      <section className="grid-two">
        <div className="panel">
          <h2>批量导入</h2>
          <textarea value={importText} onChange={(e) => setImportText(e.target.value)} placeholder="支持换行、逗号、空格分隔" />
          <Button icon={Plus} onClick={batchImport} disabled={!selectedPoolId}>导入</Button>
        </div>
        <div className="panel">
          <h2>池内分析</h2>
          <div className="analysis-controls">
            <div className="field">
              <span>分析模式</span>
              <div className="segmented compact-segmented">
                <button type="button" className={analysisMode === "sequential" ? "active" : ""} onClick={() => setAnalysisMode("sequential")}>顺序</button>
                <button type="button" className={analysisMode === "parallel" ? "active" : ""} onClick={() => setAnalysisMode("parallel")}>并发</button>
              </div>
            </div>
            <Field label="并发数">
              <input
                type="number"
                min="1"
                max="10"
                value={maxWorkers}
                disabled={analysisMode !== "parallel"}
                onChange={(e) => setMaxWorkers(Math.max(1, Math.min(10, Number(e.target.value) || 1)))}
              />
            </Field>
          </div>
          <Button icon={Play} onClick={startPoolAnalysis} disabled={!selectedPoolId || selectedStockCodes.length === 0}>分析选中股票</Button>
        </div>
      </section>
      <JobPanel job={job} onClear={clear} renderResult={StockPoolAnalysisResultView} title="股票池分析结果" />
    </Page>
  );
}

function SmartMonitorPage() {
  const { job, start, clear } = useJob("investment:smart-monitor");
  const [form, setForm] = useState({ stock_code: "600519", notify: true, trading_hours_only: true });
  return (
    <Page title="智能盯盘" subtitle="DeepSeek 决策、持仓上下文、模拟或 MiniQMT 执行">
      <section className="panel">
        <div className="form-grid">
          <Field label="股票代码"><input value={form.stock_code} onChange={(e) => setForm({ ...form, stock_code: e.target.value })} /></Field>
          <Field label="持仓成本"><input type="number" value={form.position_cost || ""} onChange={(e) => setForm({ ...form, position_cost: e.target.value })} /></Field>
          <Field label="持仓数量"><input type="number" value={form.position_quantity || ""} onChange={(e) => setForm({ ...form, position_quantity: e.target.value })} /></Field>
        </div>
        <div className="check-grid">
          {["has_position", "auto_trade", "notify", "trading_hours_only"].map((key) => (
            <label key={key} className="check">
              <input type="checkbox" checked={Boolean(form[key])} onChange={() => setForm({ ...form, [key]: !form[key] })} />
              {({ has_position: "已有持仓", auto_trade: "自动交易", notify: "发送通知", trading_hours_only: "仅交易时段" })[key]}
            </label>
          ))}
        </div>
        <Button icon={Bot} onClick={() => start("/smart-monitor/analyze", form)}>开始智能盯盘分析</Button>
      </section>
      <JobPanel job={job} onClear={clear} />
    </Page>
  );
}

function RealtimeMonitorPage() {
  const overview = useAsync(() => request("/monitor"), []);
  const [form, setForm] = useState({ symbol: "", name: "", rating: "持有", entry_min: "", entry_max: "", take_profit: "", stop_loss: "", check_interval: 30 });
  const add = async () => {
    await request("/monitor/stocks", { method: "POST", body: JSON.stringify(form) });
    setForm({ symbol: "", name: "", rating: "持有", entry_min: "", entry_max: "", take_profit: "", stop_loss: "", check_interval: 30 });
    overview.reload();
  };
  const startStop = async (action) => {
    await request(`/monitor/${action}`, { method: "POST", body: JSON.stringify({}) });
    overview.reload();
  };
  const remove = async (id) => {
    await request(`/monitor/stocks/${id}`, { method: "DELETE" });
    overview.reload();
  };
  return (
    <Page title="实时监测" subtitle="价格监控、触发提醒、通知管理和后台监测服务">
      <section className="panel">
        <div className="panel-heading">
          <h2>监测服务</h2>
          <div className="inline-actions">
            <Button icon={Play} onClick={() => startStop("start")}>启动</Button>
            <Button variant="secondary" onClick={() => startStop("stop")}>停止</Button>
            <Button icon={RefreshCw} variant="secondary" onClick={overview.reload}>刷新</Button>
          </div>
        </div>
        <p className="muted">当前状态：{overview.data?.running ? "运行中" : "已停止"}</p>
      </section>
      <section className="panel">
        <h2>添加监测</h2>
        <div className="form-grid">
          {[
            ["symbol", "股票代码"],
            ["name", "名称"],
            ["rating", "评级"],
            ["entry_min", "进场下限"],
            ["entry_max", "进场上限"],
            ["take_profit", "止盈"],
            ["stop_loss", "止损"],
            ["check_interval", "检查间隔(分钟)"],
          ].map(([key, label]) => (
            <Field key={key} label={label}>
              <input value={form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
            </Field>
          ))}
        </div>
        <Button icon={Plus} onClick={add}>添加</Button>
      </section>
      <section className="panel">
        <h2>监测股票</h2>
        <div className="table-wrap">
          <table>
            <thead><tr><th>代码</th><th>名称</th><th>评级</th><th>当前价</th><th>操作</th></tr></thead>
            <tbody>
              {(overview.data?.stocks || []).map((stock) => (
                <tr key={stock.id}>
                  <td>{stock.symbol}</td><td>{stock.name}</td><td>{stock.rating}</td><td>{stock.current_price || ""}</td>
                  <td><Button icon={Trash2} variant="danger" onClick={() => remove(stock.id)}>删除</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="grid-two">
        <div className="panel"><h2>待处理通知</h2><DataView value={overview.data?.pending_notifications} /></div>
        <div className="panel"><h2>最近通知</h2><DataView value={overview.data?.recent_notifications} /></div>
      </section>
    </Page>
  );
}

function SettingsPage() {
  const settings = useAsync(() => request("/settings"), []);
  const [values, setValues] = useState({});
  useEffect(() => {
    if (settings.data?.config) {
      const next = {};
      Object.entries(settings.data.config).forEach(([key, item]) => { next[key] = item.value || ""; });
      setValues(next);
    }
  }, [settings.data]);
  const save = async () => {
    const response = await request("/settings", { method: "POST", body: JSON.stringify({ config: values }) });
    alert(response.message);
  };
  const testNotification = async (kind) => {
    const response = await request("/settings/test-notification", { method: "POST", body: JSON.stringify({ kind }) });
    alert(response.message);
  };
  return (
    <Page title="环境配置" subtitle="接口密钥、数据源、MiniQMT、邮件和通知回调配置">
      <section className="panel">
        <div className="config-grid">
          {Object.entries(settings.data?.config || {}).map(([key, item]) => (
            <Field key={key} label={configLabel(key, item)}>
              {item.type === "select" ? (
                <select value={values[key] || ""} onChange={(e) => setValues({ ...values, [key]: e.target.value })}>
                  {(item.options || []).map((option) => <option key={option} value={option}>{optionLabel(option)}</option>)}
                </select>
              ) : item.type === "boolean" ? (
                <select value={values[key] || "false"} onChange={(e) => setValues({ ...values, [key]: e.target.value })}>
                  <option value="true">启用</option>
                  <option value="false">停用</option>
                </select>
              ) : (
                <input type={item.type === "password" ? "password" : "text"} value={values[key] || ""} onChange={(e) => setValues({ ...values, [key]: e.target.value })} />
              )}
            </Field>
          ))}
        </div>
        <div className="inline-actions">
          <Button icon={Save} onClick={save}>保存配置</Button>
          <Button variant="secondary" onClick={() => testNotification("webhook")}>测试通知回调</Button>
          <Button variant="secondary" onClick={() => testNotification("email")}>测试邮件</Button>
        </div>
      </section>
    </Page>
  );
}

createRoot(document.getElementById("root")).render(<App />);
