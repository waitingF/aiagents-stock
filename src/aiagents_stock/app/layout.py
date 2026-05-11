"""Shared Streamlit layout helpers."""

from __future__ import annotations

import streamlit as st

from src.aiagents_stock.core import config


def configure_page() -> None:
    """Apply the Streamlit page configuration."""
    st.set_page_config(
        page_title="复合多AI智能体股票团队分析系统",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )


def render_header() -> None:
    """Render the application header."""
    st.markdown(
        """
        <div class="top-nav">
            <h1 class="nav-title">📈 复合多AI智能体股票团队分析系统</h1>
            <p class="nav-subtitle">基于AI的专业量化投资分析平台 | Multi-Agent Stock Analysis System</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_current_model_info() -> None:
    """Show the active model in the sidebar."""
    st.sidebar.markdown("---")
    st.sidebar.subheader("🤖 AI模型")
    st.sidebar.info(f"当前模型: **{config.DEFAULT_MODEL_NAME}**")
    st.sidebar.caption("可在「环境配置」中修改模型名称")
