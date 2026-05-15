"""Streamlit UI for dragon strategy workflows."""

from __future__ import annotations

from datetime import date as date_cls
from io import StringIO

import pandas as pd
import streamlit as st

from src.aiagents_stock.features.selectors.dragon_strategy.engine import DragonStrategyEngine


ENGINE_SESSION_VERSION = "no-proxy-provider-v3-sector-diagnostics"


def _engine() -> DragonStrategyEngine:
    if (
        "dragon_strategy_engine" not in st.session_state
        or st.session_state.get("dragon_strategy_engine_version") != ENGINE_SESSION_VERSION
    ):
        st.session_state.dragon_strategy_engine = DragonStrategyEngine()
        st.session_state.dragon_strategy_engine_version = ENGINE_SESSION_VERSION
    return st.session_state.dragon_strategy_engine


def _date_text(value: date_cls) -> str:
    return value.strftime("%Y%m%d")


def _leaders_frame(report) -> pd.DataFrame:
    rows = []
    for item in report.leaders:
        plan = item.trade_plan.to_dict() if item.trade_plan else {}
        rows.append(
            {
                "代码": item.code,
                "名称": item.name,
                "板块": item.sector,
                "连板": item.lianban_count,
                "级别": item.level,
                "分数": item.score,
                "价格": item.price,
                "止损": plan.get("stop_loss"),
                "目标": ",".join(str(v) for v in plan.get("targets", [])),
            }
        )
    return pd.DataFrame(rows)


def _sectors_frame(signals) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "板块": item.name,
                "排名": item.rank,
                "涨跌幅": item.pct_chg,
                "涨停数": item.limit_up_count,
                "连续主线天数": item.consecutive_days,
                "阶段": item.stage,
                "评级": item.rating,
                "动作": item.action,
                "状态": item.status,
            }
            for item in signals
        ]
    )


def _trends_frame(candidates) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "代码": item.code,
                "名称": item.name,
                "板块": item.sector,
                "收盘": item.close,
                "涨跌幅": item.pct_chg,
                "趋势分": item.trend_score,
                "量比": item.volume_ratio,
                "20日斜率": item.ma20_slope,
                "支撑": item.support,
                "压力": item.resistance,
            }
            for item in candidates
        ]
    )


def display_dragon_strategy() -> None:
    st.title("🐉 龙头战法")
    engine = _engine()
    selected_date = st.date_input("交易日期", value=date_cls.today(), key="dragon_strategy_date")
    trade_date = _date_text(selected_date)

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["龙头MVP", "主线板块", "趋势跟踪", "日报/回测", "历史"])

    with tab1:
        if st.button("运行龙头MVP", use_container_width=True, key="run_dragon_mvp"):
            with st.spinner("正在计算龙头战法 MVP..."):
                st.session_state.dragon_mvp_report = engine.run_dragon_mvp(date=trade_date, persist=True)
        report = st.session_state.get("dragon_mvp_report")
        if report:
            cols = st.columns(4)
            cols[0].metric("情绪分", report.market.score)
            cols[1].metric("涨停", report.market.limit_up_count)
            cols[2].metric("跌停", report.market.limit_down_count)
            cols[3].metric("最高连板", report.market.max_lianban)
            st.caption(report.market.message)
            frame = _leaders_frame(report)
            st.dataframe(frame, use_container_width=True, height=320) if not frame.empty else st.info("暂无符合条件的龙头候选")

    with tab2:
        sector_top_n = st.slider("显示板块数", min_value=20, max_value=100, value=50, step=10, key="dragon_sector_top_n")
        if st.button("更新主线板块", use_container_width=True, key="run_dragon_sectors"):
            with st.spinner("正在跟踪主线板块状态..."):
                st.session_state.dragon_sector_signals = engine.track_main_sectors(
                    date=trade_date,
                    persist=True,
                    top_n=sector_top_n,
                )
                st.session_state.dragon_sector_diagnostics = engine.last_sector_diagnostics
        diagnostics = st.session_state.get("dragon_sector_diagnostics", {})
        if diagnostics:
            st.caption(
                "数据源：{source}；行业排行原始 {raw_rank_rows} 条，标准化 {normalized_rank_rows} 条；"
                "涨停池 {limit_up_rows} 条；输出 {output_rows} 条；无排名 {missing_rank_rows} 条。".format(
                    **diagnostics
                )
            )
        signals = st.session_state.get("dragon_sector_signals", [])
        frame = _sectors_frame(signals)
        st.dataframe(frame, use_container_width=True, height=420) if not frame.empty else st.info("暂无板块信号")

        history = engine.repository.get_recent_sector_history(limit_days=20)
        if history:
            st.subheader("历史状态")
            st.dataframe(pd.DataFrame(history), use_container_width=True, height=280)

    with tab3:
        top_n = st.slider("候选数量", min_value=5, max_value=50, value=20, step=5)
        if st.button("扫描趋势跟踪", use_container_width=True, key="run_dragon_trends"):
            with st.spinner("正在扫描趋势候选..."):
                st.session_state.dragon_trend_candidates = engine.scan_trends(date=trade_date, top_n=top_n)
        candidates = st.session_state.get("dragon_trend_candidates", [])
        frame = _trends_frame(candidates)
        st.dataframe(frame, use_container_width=True, height=420) if not frame.empty else st.info("暂无趋势候选")

    with tab4:
        if st.button("生成定时日报内容", use_container_width=True, key="run_dragon_daily_report"):
            with st.spinner("正在生成日报..."):
                st.session_state.dragon_daily_report = engine.generate_daily_report(date=trade_date, persist=True)
        daily_report = st.session_state.get("dragon_daily_report")
        if daily_report:
            st.markdown(daily_report.markdown)
            st.download_button(
                "下载Markdown日报",
                data=daily_report.markdown.encode("utf-8"),
                file_name=f"dragon_strategy_{daily_report.report_date}.md",
                mime="text/markdown",
                use_container_width=True,
            )

        st.subheader("固定持有回测")
        signals_text = st.text_area(
            "信号CSV",
            value="code,name,signal_date\n",
            height=120,
            help="列名：code,name,signal_date；signal_date格式为YYYYMMDD",
        )
        holding_days = st.number_input("持有天数", min_value=1, max_value=30, value=5)
        stop_loss_pct = st.number_input("止损比例", min_value=0.01, max_value=0.30, value=0.05, step=0.01)
        take_profit_pct = st.number_input("止盈比例", min_value=0.00, max_value=1.00, value=0.00, step=0.01)
        if st.button("运行回测", use_container_width=True, key="run_dragon_backtest"):
            signals_df = pd.read_csv(StringIO(signals_text))
            daily_by_code = {
                str(row["code"]): engine.provider.get_stock_daily(str(row["code"]), trade_date)
                for _, row in signals_df.iterrows()
                if str(row.get("code", "")).strip()
            }
            result = engine.run_backtest(
                signals=signals_df.to_dict("records"),
                daily_by_code=daily_by_code,
                holding_days=int(holding_days),
                stop_loss_pct=float(stop_loss_pct),
                take_profit_pct=float(take_profit_pct) if take_profit_pct else None,
            )
            st.session_state.dragon_backtest_result = result.to_dict()
        backtest_result = st.session_state.get("dragon_backtest_result")
        if backtest_result:
            st.json(backtest_result["summary"])
            st.dataframe(pd.DataFrame(backtest_result["trades"]), use_container_width=True, height=320)

    with tab5:
        report_type = st.selectbox("报告类型", ["全部", "dragon_mvp", "daily_report"], index=0)
        reports = engine.repository.list_reports(
            limit=30,
            report_type=None if report_type == "全部" else report_type,
        )
        if reports:
            report_frame = pd.DataFrame(reports)
            st.dataframe(report_frame[["id", "report_date", "report_type", "created_at"]], use_container_width=True)
            selected_id = st.number_input("报告ID", min_value=1, value=int(report_frame["id"].iloc[0]))
            item = engine.repository.get_report(int(selected_id))
            if item and item.get("markdown"):
                st.markdown(item["markdown"])
        else:
            st.info("暂无历史报告")
