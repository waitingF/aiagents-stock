"""Streamlit UI for stock pools."""

from __future__ import annotations

import json
import time
from datetime import date, datetime
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

from src.aiagents_stock.features.stock_pool.manager import stock_pool_manager
from src.aiagents_stock.features.stock_pool.repository import HOLDING_POOL_NAME
from src.aiagents_stock.features.stock_pool.scheduler import stock_pool_scheduler


SCOPE_OPTIONS = {
    "today_unanalysed": "今日未分析",
    "all": "全部股票",
    "custom": "自定义股票",
    "tag": "按标签筛选",
}


def display_holding_pool_manager():
    """Compatibility view for the original portfolio analysis entry."""
    holding_pool = stock_pool_manager.get_holding_pool()
    st.markdown("## 📊 持仓定时分析")
    st.markdown("---")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📝 持仓管理",
        "🔄 批量分析",
        "📅 每日复盘",
        "⏰ 定时任务",
        "📈 分析历史",
    ])
    with tab1:
        display_pool_stocks(holding_pool, holding_view=True)
    with tab2:
        display_pool_analysis(default_pool_ids=[holding_pool["id"]], holding_view=True)
    with tab3:
        display_daily_review(default_pool_id=holding_pool["id"])
    with tab4:
        display_scheduler_management(default_pool_ids=[holding_pool["id"]])
    with tab5:
        display_analysis_history(default_pool_id=holding_pool["id"])


def display_stock_pool_manager():
    """Full stock pool management UI."""
    st.markdown("## ⭐ 股票池")
    st.markdown("---")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "🗂️ 股票池管理",
        "📝 股票管理",
        "🔄 股票池分析",
        "📅 每日复盘",
        "📈 分析历史",
    ])
    with tab1:
        display_pool_management()
    with tab2:
        pool = select_pool("选择股票池", key="stock_manage_pool")
        if pool:
            display_pool_stocks(pool)
    with tab3:
        display_pool_analysis()
    with tab4:
        display_daily_review()
    with tab5:
        display_analysis_history()


def select_pool(label: str, key: str, include_all: bool = False) -> Optional[Dict]:
    pools = stock_pool_manager.list_pools()
    if not pools:
        st.warning("暂无股票池")
        return None
    options = ["全部"] + [pool["id"] for pool in pools] if include_all else [pool["id"] for pool in pools]
    if st.session_state.get(key) not in options:
        st.session_state.pop(key, None)
    selected = st.selectbox(
        label,
        options=options,
        format_func=lambda value: "全部" if value == "全部" else _pool_select_label(next(pool for pool in pools if pool["id"] == value)),
        key=key,
    )
    if selected == "全部":
        return None
    pool = next(pool for pool in pools if pool["id"] == selected)
    st.caption(f"当前股票数: {pool.get('active_count', 0)}")
    return pool


def _pool_select_label(pool: Dict) -> str:
    system = "系统" if pool.get("is_system") else "普通"
    return f"{pool['name']} ({system})"


def _pool_label(pool: Dict) -> str:
    system = "系统" if pool.get("is_system") else "普通"
    return f"{pool['name']} ({system}, {pool.get('active_count', 0)}只)"


def display_pool_management():
    st.markdown("### 🗂️ 股票池管理")
    pools = stock_pool_manager.list_pools()
    if pools:
        df = pd.DataFrame([
            {
                "名称": pool["name"],
                "类型": pool["type"],
                "系统池": "是" if pool.get("is_system") else "否",
                "股票数": pool.get("active_count", 0),
                "描述": pool.get("description") or "",
                "创建时间": str(pool.get("created_at", ""))[:19],
            }
            for pool in pools
        ])
        st.dataframe(df, width="stretch", hide_index=True)

    with st.expander("➕ 创建股票池", expanded=False):
        with st.form("create_pool_form"):
            name = st.text_input("股票池名称")
            description = st.text_area("描述", height=80)
            submitted = st.form_submit_button("创建", type="primary")
            if submitted:
                success, message, _ = stock_pool_manager.create_pool(name, description)
                _show_result(success, message)
                if success:
                    time.sleep(0.3)
                    st.rerun()

    editable_pools = [pool for pool in pools if not pool.get("is_system")]
    if editable_pools:
        with st.expander("✏️ 编辑/删除普通股票池", expanded=False):
            pool_id = st.selectbox(
                "选择普通股票池",
                options=[pool["id"] for pool in editable_pools],
                format_func=lambda value: next(pool["name"] for pool in editable_pools if pool["id"] == value),
            )
            pool = next(pool for pool in editable_pools if pool["id"] == pool_id)
            with st.form(f"edit_pool_{pool_id}"):
                new_name = st.text_input("名称", value=pool["name"])
                new_description = st.text_area("描述", value=pool.get("description") or "", height=80)
                sort_order = st.number_input("排序", value=int(pool.get("sort_order") or 100), step=1)
                col_save, col_delete = st.columns(2)
                with col_save:
                    if st.form_submit_button("保存", type="primary"):
                        success, message = stock_pool_manager.update_pool(
                            pool_id,
                            name=new_name,
                            description=new_description,
                            sort_order=sort_order,
                        )
                        _show_result(success, message)
                        if success:
                            time.sleep(0.3)
                            st.rerun()
                with col_delete:
                    if st.form_submit_button("删除"):
                        success, message = stock_pool_manager.delete_pool(pool_id)
                        _show_result(success, message)
                        if success:
                            time.sleep(0.3)
                            st.rerun()


def display_pool_stocks(pool: Dict, holding_view: bool = False):
    title = "持仓股票管理" if holding_view else f"{pool['name']} 股票管理"
    st.markdown(f"### 📝 {title}")

    with st.expander("➕ 添加股票", expanded=False):
        display_add_stock_form(pool, holding_view)

    with st.expander("📥 批量导入", expanded=False):
        stock_input = st.text_area("股票代码", placeholder="支持换行、逗号、空格分隔，如 600519.SH, 000001.SZ", height=120)
        default_tags = st.text_input("默认标签", placeholder="可选")
        if st.button("导入", type="primary", key=f"batch_import_{pool['id']}"):
            result = stock_pool_manager.batch_import_stocks(pool["id"], stock_input, default_tags=default_tags)
            st.info(f"导入完成：共 {result['total']} 只，成功 {result['added']} 只，失败 {len(result['failed'])} 只")
            if result["failed"]:
                st.dataframe(pd.DataFrame(result["failed"]), width="stretch", hide_index=True)
            time.sleep(0.3)
            st.rerun()

    stocks = stock_pool_manager.list_stocks(pool["id"])
    if not stocks:
        st.info("暂无股票，请先添加。")
        return

    display_stock_metrics(stocks, holding_view)
    for stock in stocks:
        display_stock_card(stock, holding_view)


def display_add_stock_form(pool: Dict, holding_view: bool):
    with st.form(f"add_stock_form_{pool['id']}"):
        col1, col2 = st.columns(2)
        with col1:
            code = st.text_input("股票代码*", placeholder="例如: 600519.SH 或 000001.SZ")
            name = st.text_input("股票名称", placeholder="可选，留空使用代码")
            tags = st.text_input("标签", placeholder="如 低估值,AI")
        with col2:
            cost_price = st.number_input("成本价", min_value=0.0, step=0.01)
            quantity = st.number_input("持仓数量", min_value=0, step=100)
            auto_monitor = st.checkbox("自动同步到监测", value=holding_view)

        watch_reason = st.text_area("观察理由", height=70)
        note = st.text_area("备注", height=70)
        if st.form_submit_button("添加", type="primary"):
            success, message, _ = stock_pool_manager.add_stock(
                pool_id=pool["id"],
                code=code,
                name=name or None,
                tags=tags,
                note=note,
                watch_reason=watch_reason,
                cost_price=cost_price if cost_price > 0 else None,
                quantity=quantity if quantity > 0 else None,
                auto_monitor=auto_monitor,
            )
            _show_result(success, message)
            if success:
                time.sleep(0.3)
                st.rerun()


def display_stock_metrics(stocks: List[Dict], holding_view: bool):
    col1, col2, col3 = st.columns(3)
    col1.metric("股票数", len(stocks))
    col2.metric("自动监测", sum(1 for stock in stocks if stock.get("auto_monitor")))
    if holding_view:
        total_cost = sum(
            (stock.get("cost_price") or 0) * (stock.get("quantity") or 0)
            for stock in stocks
        )
        col3.metric("总持仓成本", f"¥{total_cost:,.2f}")
    else:
        tag_count = len({tag.strip() for stock in stocks for tag in (stock.get("tags") or "").split(",") if tag.strip()})
        col3.metric("标签数", tag_count)


def display_stock_card(stock: Dict, holding_view: bool):
    with st.container():
        col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
        with col1:
            st.markdown(f"**{stock['code']}** {stock['name']}")
            if stock.get("tags"):
                st.caption(f"标签: {stock['tags']}")
            if stock.get("note"):
                st.caption(f"备注: {stock['note']}")
        with col2:
            st.caption(f"加入时间: {str(stock.get('created_at', ''))[:16]}")
            if stock.get("watch_reason"):
                st.caption(f"观察: {stock['watch_reason']}")
        with col3:
            if stock.get("cost_price") and stock.get("quantity"):
                st.write(f"成本: ¥{float(stock['cost_price']):.2f}")
                st.caption(f"数量: {stock['quantity']}股")
            else:
                st.caption("未设置持仓")
        with col4:
            edit_key = f"editing_pool_item_{stock['id']}"
            col_edit, col_remove = st.columns(2)
            with col_edit:
                if st.button("✏️", key=f"edit_item_{stock['id']}", help="编辑"):
                    st.session_state[edit_key] = True
                    st.rerun()
            with col_remove:
                if st.button("🗑️", key=f"remove_item_{stock['id']}", help="移除"):
                    success, message = stock_pool_manager.remove_stock(stock["id"])
                    _show_result(success, message)
                    time.sleep(0.3)
                    st.rerun()

        if st.session_state.get(edit_key):
            display_edit_stock_form(stock, holding_view)
        st.markdown("---")


def display_edit_stock_form(stock: Dict, holding_view: bool):
    pools = stock_pool_manager.list_pools()
    with st.form(f"edit_stock_form_{stock['id']}"):
        col1, col2 = st.columns(2)
        with col1:
            name = st.text_input("股票名称", value=stock.get("name") or "")
            tags = st.text_input("标签", value=stock.get("tags") or "")
            cost_price = st.number_input("成本价", value=float(stock.get("cost_price") or 0), min_value=0.0, step=0.01)
            quantity = st.number_input("持仓数量", value=int(stock.get("quantity") or 0), min_value=0, step=100)
        with col2:
            target_price = st.number_input("目标价", value=float(stock.get("target_price") or 0), min_value=0.0, step=0.01)
            take_profit = st.number_input("止盈", value=float(stock.get("take_profit") or 0), min_value=0.0, step=0.01)
            stop_loss = st.number_input("止损", value=float(stock.get("stop_loss") or 0), min_value=0.0, step=0.01)
            auto_monitor = st.checkbox("自动同步到监测", value=bool(stock.get("auto_monitor")))
        watch_reason = st.text_area("观察理由", value=stock.get("watch_reason") or "", height=70)
        note = st.text_area("备注", value=stock.get("note") or "", height=70)

        target_pool_id = st.selectbox(
            "复制/移动到股票池",
            options=[pool["id"] for pool in pools],
            format_func=lambda value: next(pool["name"] for pool in pools if pool["id"] == value),
            key=f"target_pool_{stock['id']}",
        )

        col_save, col_copy, col_move, col_cancel = st.columns(4)
        with col_save:
            if st.form_submit_button("保存", type="primary"):
                success, message = stock_pool_manager.update_stock(
                    stock["id"],
                    name=name,
                    tags=tags,
                    cost_price=cost_price if cost_price > 0 else None,
                    quantity=quantity if quantity > 0 else None,
                    target_price=target_price if target_price > 0 else None,
                    take_profit=take_profit if take_profit > 0 else None,
                    stop_loss=stop_loss if stop_loss > 0 else None,
                    auto_monitor=auto_monitor,
                    watch_reason=watch_reason,
                    note=note,
                )
                _show_result(success, message)
                st.session_state.pop(f"editing_pool_item_{stock['id']}", None)
                time.sleep(0.3)
                st.rerun()
        with col_copy:
            if st.form_submit_button("复制"):
                success, message, _ = stock_pool_manager.copy_stock_to_pool(stock["id"], target_pool_id)
                _show_result(success, message)
        with col_move:
            if st.form_submit_button("移动"):
                success, message, _ = stock_pool_manager.move_stock_to_pool(stock["id"], target_pool_id)
                _show_result(success, message)
                if success:
                    st.session_state.pop(f"editing_pool_item_{stock['id']}", None)
                    time.sleep(0.3)
                    st.rerun()
        with col_cancel:
            if st.form_submit_button("取消"):
                st.session_state.pop(f"editing_pool_item_{stock['id']}", None)
                st.rerun()


def display_pool_analysis(default_pool_ids: Optional[List[int]] = None, holding_view: bool = False):
    st.markdown("### 🔄 股票池分析" if not holding_view else "### 🔄 批量分析持仓股票")
    pools = stock_pool_manager.list_pools()
    if not pools:
        st.warning("暂无股票池")
        return

    if default_pool_ids:
        selected_pool_ids = default_pool_ids
        selected_pools = [pool for pool in pools if pool["id"] in selected_pool_ids]
        st.info(f"当前分析股票池：{', '.join(pool['name'] for pool in selected_pools)}")
    else:
        selected_pool_ids = st.multiselect(
            "选择股票池",
            options=[pool["id"] for pool in pools],
            default=[pool["id"] for pool in pools if pool["name"] == HOLDING_POOL_NAME][:1],
            format_func=lambda value: next(_pool_label(pool) for pool in pools if pool["id"] == value),
        )

    if not selected_pool_ids:
        st.warning("请选择至少一个股票池")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        analysis_mode = st.selectbox(
            "分析模式",
            options=["sequential", "parallel"],
            format_func=lambda value: "顺序分析" if value == "sequential" else "并行分析",
        )
    with col2:
        max_workers = st.number_input("并行线程数", min_value=2, max_value=10, value=3, disabled=analysis_mode != "parallel")
    with col3:
        scope = st.selectbox(
            "分析范围",
            options=list(SCOPE_OPTIONS.keys()),
            format_func=lambda value: SCOPE_OPTIONS[value],
        )

    selected_codes = None
    tag_filter = None
    all_items = stock_pool_manager.db.list_items_for_pools(selected_pool_ids)
    code_to_label = _build_code_labels(all_items)

    if scope == "custom":
        selected_codes = st.multiselect(
            "选择股票",
            options=list(code_to_label.keys()),
            format_func=lambda code: code_to_label[code],
        )
    elif scope == "tag":
        tag_filter = st.text_input("标签关键词")

    targets = stock_pool_manager.build_analysis_targets(
        selected_pool_ids,
        scope="all" if scope in {"all", "custom", "tag"} else scope,
        selected_codes=selected_codes,
        tag_filter=tag_filter,
    )
    st.caption(f"本次将分析 {len(targets)} 只去重后的股票，写回 {sum(len(items) for items in targets.values())} 条池内记录。")

    col_sync, col_notify = st.columns(2)
    with col_sync:
        auto_sync = st.checkbox("自动同步到监测", value=holding_view)
    with col_notify:
        send_notification = st.checkbox("发送完成通知", value=False)

    if st.button("🚀 立即开始分析", type="primary", disabled=not targets):
        progress_bar = st.progress(0)
        status_text = st.empty()

        def update_progress(current, total, code, status):
            progress_bar.progress(current / total)
            status_text.text(f"{code} {status} ({current}/{total})")

        with st.spinner("正在分析股票池..."):
            result = stock_pool_manager.batch_analyze_pools(
                pool_ids=selected_pool_ids,
                scope="all" if scope in {"all", "custom", "tag"} else scope,
                selected_codes=selected_codes,
                tag_filter=tag_filter,
                mode=analysis_mode,
                max_workers=max_workers if analysis_mode == "parallel" else 1,
                progress_callback=update_progress,
            )

        progress_bar.empty()
        status_text.empty()
        if not result.get("success"):
            st.error(result.get("error", "分析失败"))
            return

        sync_result = None
        if auto_sync:
            sync_result = stock_pool_manager.sync_results_to_monitor(result)
            st.info(f"监测同步：新增 {sync_result.get('added', 0)}，更新 {sync_result.get('updated', 0)}")
        if send_notification:
            from src.aiagents_stock.integrations.notification.service import notification_service

            notification_service.send_portfolio_analysis_notification(result, sync_result)
            st.info("已发送通知")

        display_batch_result_summary(result)


def _build_code_labels(items: List[Dict]) -> Dict[str, str]:
    grouped: Dict[str, Dict[str, List[str]]] = {}
    for item in items:
        entry = grouped.setdefault(item["code"], {"name": item.get("name") or "", "pools": []})
        entry["pools"].append(item.get("pool_name") or "")
    return {
        code: f"{code} {value['name']} - 来自: {', '.join(sorted(set(value['pools'])))}"
        for code, value in grouped.items()
    }


def display_batch_result_summary(result: Dict):
    st.success("✅ 分析完成")
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("去重股票", result.get("total", 0))
    col2.metric("成功", result.get("succeeded", 0))
    col3.metric("失败", result.get("failed", 0))
    col4.metric("写入历史", len(result.get("saved_ids", [])))
    col5.metric("耗时", f"{result.get('elapsed_time', 0):.1f}秒")

    if result.get("failed_stocks"):
        st.warning("部分股票分析失败")
        st.dataframe(pd.DataFrame(result["failed_stocks"]), width="stretch", hide_index=True)

    for item in result.get("results", []):
        display_analysis_result_card(item)


def display_analysis_result_card(item: Dict):
    code = item.get("code", "")
    result = item.get("result", {})
    final_decision = result.get("final_decision", {})
    stock_info = result.get("stock_info", {})
    rating = final_decision.get("rating", "未知")
    icon = _rating_icon(rating)
    pool_names = sorted({pool_item.get("pool_name", "") for pool_item in item.get("pool_items", [])})
    with st.expander(f"{icon} {code} {stock_info.get('name', '')} - {rating} | 写回: {', '.join(pool_names)}"):
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"目标价: {final_decision.get('target_price', 'N/A')}")
            st.write(f"进场区间: {final_decision.get('entry_range', 'N/A')}")
        with col2:
            st.write(f"止盈: {final_decision.get('take_profit', 'N/A')}")
            st.write(f"止损: {final_decision.get('stop_loss', 'N/A')}")
        advice = final_decision.get("operation_advice") or final_decision.get("advice") or final_decision.get("summary")
        if advice:
            st.info(advice)
        risk = final_decision.get("risk_warning")
        if risk:
            st.warning(risk)


def display_daily_review(default_pool_id: Optional[int] = None):
    st.markdown("### 📅 每日复盘")
    if default_pool_id:
        pool = stock_pool_manager.get_pool(default_pool_id)
    else:
        pool = select_pool("选择股票池", key="review_pool")
    if not pool:
        return
    review_date = st.date_input("复盘日期", value=date.today(), key=f"review_date_{pool['id']}")
    records = stock_pool_manager.get_daily_reviews(pool["id"], review_date.isoformat())
    if not records:
        st.info("该日期暂无复盘记录")
        return

    display_daily_review_summary(records)
    for record in records:
        display_history_record(record)


def display_daily_review_summary(records: List[Dict]):
    ratings = {}
    review_statuses = {}
    for record in records:
        ratings[record.get("rating") or "未知"] = ratings.get(record.get("rating") or "未知", 0) + 1
        status = record.get("review_status") or "未复盘"
        review_statuses[status] = review_statuses.get(status, 0) + 1

    col1, col2, col3 = st.columns(3)
    col1.metric("复盘股票", len(records))
    col2.metric("买入相关", sum(count for rating, count in ratings.items() if "买入" in rating))
    col3.metric("风险失效", review_statuses.get("失效", 0))
    st.caption(f"评级分布: {ratings} | 复盘状态: {review_statuses}")


def display_scheduler_management(default_pool_ids: Optional[List[int]] = None):
    st.markdown("### ⏰ 定时任务管理")
    is_running = stock_pool_scheduler.is_running()
    schedule_times = stock_pool_scheduler.get_schedule_times()
    col1, col2, col3 = st.columns(3)
    col1.success("运行中") if is_running else col1.error("已停止")
    col2.info(f"定时数量: {len(schedule_times)}")
    col3.info(f"下次运行: {stock_pool_scheduler.get_next_run_time() or '未设置'}")

    st.markdown("#### 已配置时间")
    st.write("、".join(schedule_times) if schedule_times else "暂无")
    with st.expander("➕ 添加定时时间"):
        new_time = st.time_input("选择时间", value=datetime.strptime("15:05", "%H:%M").time())
        if st.button("添加定时"):
            if stock_pool_scheduler.add_schedule_time(new_time.strftime("%H:%M")):
                st.success("已添加")
                st.rerun()
            else:
                st.warning("该时间已存在")

    with st.form("stock_pool_scheduler_config"):
        analysis_mode = st.selectbox(
            "分析模式",
            ["sequential", "parallel"],
            format_func=lambda value: "顺序分析" if value == "sequential" else "并行分析",
            index=0 if stock_pool_scheduler.analysis_mode == "sequential" else 1,
        )
        max_workers = st.number_input("并行线程数", min_value=2, max_value=10, value=stock_pool_scheduler.max_workers)
        scope = st.selectbox(
            "分析范围",
            ["today_unanalysed", "all"],
            format_func=lambda value: SCOPE_OPTIONS[value],
        )
        auto_sync = st.checkbox("自动同步到监测", value=stock_pool_scheduler.auto_monitor_sync)
        send_notification = st.checkbox("发送通知", value=stock_pool_scheduler.notification_enabled)
        if st.form_submit_button("保存配置", type="primary"):
            stock_pool_scheduler.update_config(
                analysis_mode=analysis_mode,
                max_workers=max_workers,
                auto_sync_monitor=auto_sync,
                send_notification=send_notification,
                scope=scope,
                pool_ids=default_pool_ids,
            )
            st.success("配置已更新")

    col_start, col_run, col_stop = st.columns(3)
    with col_start:
        if st.button("▶️ 启动调度器", disabled=is_running):
            stock_pool_scheduler.set_pool_ids(default_pool_ids)
            stock_pool_scheduler.start_scheduler()
            st.rerun()
    with col_run:
        if st.button("🚀 立即执行一次"):
            stock_pool_scheduler.set_pool_ids(default_pool_ids)
            with st.spinner("正在执行..."):
                result = stock_pool_scheduler.run_analysis_now()
            if result.get("success"):
                display_batch_result_summary(result)
            else:
                st.error(result.get("error", "执行失败"))
    with col_stop:
        if st.button("⏹️ 停止调度器", disabled=not is_running):
            stock_pool_scheduler.stop_scheduler()
            st.rerun()


def display_analysis_history(default_pool_id: Optional[int] = None):
    st.markdown("### 📈 分析历史")
    pools = stock_pool_manager.list_pools()
    if default_pool_id:
        pool_id = default_pool_id
    else:
        pool = select_pool("选择股票池", key="history_pool", include_all=True)
        pool_id = pool["id"] if pool else None
    code = st.text_input("股票代码过滤", placeholder="可选")
    use_date_filter = st.checkbox("按交易日过滤", value=False)
    trading_date = None
    if use_date_filter:
        trading_date = st.date_input("交易日", value=date.today()).isoformat()
    records = stock_pool_manager.get_analysis_history(
        pool_id=pool_id,
        code=code or None,
        trading_date=trading_date,
        limit=100,
    )
    if not records:
        st.info("暂无分析历史")
        return
    st.caption(f"共 {len(records)} 条记录")
    for record in records:
        display_history_record(record)


def display_history_record(record: Dict):
    rating = record.get("rating", "未知")
    icon = _rating_icon(rating)
    pool_name = record.get("pool_name", "")
    with st.expander(
        f"{icon} {record.get('code', '')} {record.get('name', '')} - {rating} | {pool_name} | {record.get('analysis_time', '')}",
        expanded=False,
    ):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            _write_price("当时价格", record.get("current_price"))
            _write_price("目标价", record.get("target_price"))
        with col2:
            if record.get("entry_min") and record.get("entry_max"):
                st.write(f"进场: ¥{record['entry_min']:.2f} ~ ¥{record['entry_max']:.2f}")
        with col3:
            _write_price("止盈", record.get("take_profit"))
            _write_price("止损", record.get("stop_loss"))
        with col4:
            st.write(f"信心度: {record.get('confidence', 'N/A')}/10")
            if record.get("review_status"):
                st.write(f"复盘: {record['review_status']}")

        if record.get("operation_advice") or record.get("summary"):
            st.info(record.get("operation_advice") or record.get("summary"))
        if record.get("risk_warning"):
            st.warning(record["risk_warning"])
        review = parse_review_json(record)
        if review:
            display_review_section(review)


def display_review_section(review: Dict):
    status = review.get("review_status", "待验证")
    st.markdown(f"**复盘信息** {_review_icon(status)} {status}")
    if review.get("review_summary"):
        st.info(review["review_summary"])
    col1, col2 = st.columns(2)
    with col1:
        if review.get("plan_check"):
            st.write(f"计划检查: {review['plan_check']}")
        if review.get("price_review"):
            st.write(f"价格复盘: {review['price_review']}")
    with col2:
        if review.get("logic_change"):
            st.write(f"逻辑变化: {review['logic_change']}")
        if review.get("action_adjustment"):
            st.write(f"本次调整: {review['action_adjustment']}")
    watchpoints = review.get("next_watchpoints") or []
    if watchpoints:
        st.markdown("**下次关注点**")
        for point in watchpoints:
            st.write(f"- {point}")


def parse_review_json(record: Dict) -> Dict:
    review_json = record.get("review_json")
    if not review_json:
        return {}
    if isinstance(review_json, dict):
        return review_json
    try:
        parsed = json.loads(review_json)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _write_price(label: str, value):
    if value is not None:
        try:
            st.write(f"{label}: ¥{float(value):.2f}")
        except (TypeError, ValueError):
            st.write(f"{label}: {value}")


def _rating_icon(rating: str) -> str:
    if "买入" in (rating or ""):
        return "🟢"
    if "卖出" in (rating or ""):
        return "🔴"
    return "🟡"


def _review_icon(status: str) -> str:
    return {
        "兑现": "🟢",
        "部分兑现": "🟡",
        "失效": "🔴",
        "待验证": "⚪",
        "首次分析": "🔵",
    }.get(status or "", "⚪")


def _show_result(success: bool, message: str):
    if success:
        st.success(message)
    else:
        st.error(message)
