"""Shared Streamlit session-state helpers."""

from __future__ import annotations

import streamlit as st


PAGE_KEYS = [
    "show_history",
    "show_monitor",
    "show_config",
    "show_main_force",
    "show_dragon_strategy",
    "show_sector_strategy",
    "show_longhubang",
    "show_portfolio",
    "show_stock_pool",
    "show_low_price_bull",
    "show_news_flow",
    "show_macro_cycle",
    "show_macro_analysis",
    "show_value_stock",
    "show_small_cap",
    "show_profit_growth",
    "show_smart_monitor",
]


def clear_pages(except_key: str | None = None) -> None:
    """Clear page flags while optionally preserving one target page."""
    for key in PAGE_KEYS:
        if key == except_key:
            continue
        st.session_state.pop(key, None)


def switch_page(page_key: str) -> None:
    """Activate one page flag and clear the rest."""
    st.session_state[page_key] = True
    clear_pages(except_key=page_key)
