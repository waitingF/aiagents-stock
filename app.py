"""Compatibility entrypoint. Prefer running aiagents_stock.app.main."""

from src.aiagents_stock.features.stock_analysis.service import analyze_single_stock_for_batch

__all__ = ["main", "analyze_single_stock_for_batch"]


def main():
    from src.aiagents_stock.app.main import main as streamlit_main

    return streamlit_main()


if __name__ == "__main__":
    main()
