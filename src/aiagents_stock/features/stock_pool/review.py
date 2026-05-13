"""Review helpers for stock pools."""

from __future__ import annotations

from typing import Dict, List, Optional

from src.aiagents_stock.features.portfolio import review as portfolio_review


extract_first_price_range = portfolio_review.extract_first_price_range
extract_first_price = portfolio_review.extract_first_price
safe_float = portfolio_review.safe_float


def build_pool_review(previous_record: Optional[Dict], current_record: Dict, pool_item: Dict, final_decision: Dict) -> Dict:
    """Build a per-pool review using the existing portfolio review rules."""
    stock = {
        "code": pool_item.get("code", ""),
        "name": pool_item.get("name", ""),
    }
    return portfolio_review.build_portfolio_review(previous_record, current_record, stock, final_decision)


def build_next_watchpoints(current_record: Dict, final_decision: Dict) -> List[str]:
    return portfolio_review.build_next_watchpoints(current_record, final_decision)

