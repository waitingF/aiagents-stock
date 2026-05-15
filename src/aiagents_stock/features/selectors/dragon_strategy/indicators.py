"""Technical indicator helpers used by dragon and trend strategies."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


def to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None or pd.isna(value):
            return default
    except TypeError:
        pass
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def latest_ma(frame: pd.DataFrame, window: int, column: str = "close") -> Optional[float]:
    if frame is None or frame.empty or column not in frame or len(frame) < window:
        return None
    return float(frame[column].rolling(window).mean().iloc[-1])


def previous_ma(frame: pd.DataFrame, window: int, column: str = "close") -> Optional[float]:
    if frame is None or frame.empty or column not in frame or len(frame) < window + 1:
        return None
    return float(frame[column].rolling(window).mean().iloc[-2])


def calculate_volume_ratio(frame: pd.DataFrame, window: int = 5) -> float:
    if frame is None or frame.empty or "volume" not in frame or len(frame) < window + 1:
        return 0.0
    latest = to_float(frame["volume"].iloc[-1], 0.0) or 0.0
    avg = frame["volume"].iloc[-window - 1 : -1].mean()
    return round(float(latest / avg), 2) if avg else 0.0


def check_volume_and_trend(
    frame: pd.DataFrame,
    turnover_min: float,
    turnover_max: float,
    volume_ratio_min: float = 1.5,
    volume_growth_min: float = 1.3,
) -> Dict[str, Any]:
    """Return volume/trend checks used by the strict dragon MVP filter."""
    result = {
        "has_enough_data": frame is not None and len(frame) >= 20,
        "turnover": None,
        "volume_ratio": 0.0,
        "volume_growth": 0.0,
        "ma5": None,
        "ma5_prev": None,
        "ma20": None,
        "close": None,
        "volume_pass": False,
        "trend_pass": False,
    }
    if frame is None or frame.empty:
        return result

    result["close"] = to_float(frame["close"].iloc[-1], None) if "close" in frame else None
    result["turnover"] = to_float(frame["turnover"].iloc[-1], None) if "turnover" in frame else None
    if result["turnover"] is None:
        result["turnover"] = turnover_min
    if "volume_ratio" in frame and not pd.isna(frame["volume_ratio"].iloc[-1]):
        result["volume_ratio"] = to_float(frame["volume_ratio"].iloc[-1], 0.0) or 0.0
    else:
        result["volume_ratio"] = calculate_volume_ratio(frame)
    if "volume" in frame and len(frame) >= 2:
        prev = to_float(frame["volume"].iloc[-2], 0.0) or 0.0
        latest = to_float(frame["volume"].iloc[-1], 0.0) or 0.0
        result["volume_growth"] = round(latest / prev, 2) if prev else 0.0

    result["ma5"] = latest_ma(frame, 5)
    result["ma5_prev"] = previous_ma(frame, 5)
    result["ma20"] = latest_ma(frame, 20)
    result["volume_pass"] = (
        result["has_enough_data"]
        and turnover_min <= float(result["turnover"]) <= turnover_max
        and result["volume_ratio"] >= volume_ratio_min
        and result["volume_growth"] >= volume_growth_min
    )
    result["trend_pass"] = (
        result["has_enough_data"]
        and result["close"] is not None
        and result["ma5"] is not None
        and result["ma5_prev"] is not None
        and result["ma20"] is not None
        and result["close"] >= result["ma5"]
        and result["ma5"] > result["ma5_prev"]
        and result["close"] >= result["ma20"]
    )
    return result


def check_ma_alignment(frame: pd.DataFrame, mas: tuple[int, ...] = (5, 10, 20, 60)) -> tuple[bool, Dict[str, float]]:
    if frame is None or frame.empty or "close" not in frame or len(frame) < max(mas):
        return False, {}
    detail = {}
    values = []
    for ma in mas:
        col = f"ma{ma}"
        if col not in frame:
            frame = frame.copy()
            frame[col] = frame["close"].rolling(ma).mean()
        value = to_float(frame[col].iloc[-1], None)
        if value is None:
            return False, detail
        detail[col] = value
        values.append(value)
    return all(values[idx] > values[idx + 1] for idx in range(len(values) - 1)), detail


def check_macd(frame: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[Optional[pd.Series], Optional[pd.Series], Optional[pd.Series], bool, bool]:
    if frame is None or frame.empty or "close" not in frame or len(frame) < slow + signal:
        return None, None, None, False, False
    close = frame["close"].astype(float)
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    hist = 2 * (dif - dea)
    golden = dif.iloc[-2] <= dea.iloc[-2] and dif.iloc[-1] > dea.iloc[-1]
    dead = dif.iloc[-2] >= dea.iloc[-2] and dif.iloc[-1] < dea.iloc[-1]
    return dif, dea, hist, bool(golden), bool(dead)


def check_rsi(frame: pd.DataFrame, period: int = 14) -> tuple[Optional[float], str]:
    if frame is None or frame.empty or "close" not in frame or len(frame) < period + 1:
        return None, ""
    delta = frame["close"].astype(float).diff()
    gain = delta.clip(lower=0).rolling(period).mean().iloc[-1]
    loss = (-delta.clip(upper=0)).rolling(period).mean().iloc[-1]
    if loss == 0:
        return 100.0, "overbought"
    rs = gain / loss
    rsi = round(float(100 - (100 / (1 + rs))), 1)
    if 50 <= rsi < 70:
        zone = "strong"
    elif rsi >= 70:
        zone = "overbought"
    elif rsi >= 30:
        zone = "neutral"
    else:
        zone = "oversold"
    return rsi, zone


def ma20_slope(frame: pd.DataFrame) -> float:
    if frame is None or frame.empty or "close" not in frame or len(frame) < 25:
        return 0.0
    ma20 = frame["close"].rolling(20).mean()
    if len(ma20.dropna()) < 6:
        return 0.0
    return round(float((ma20.iloc[-1] - ma20.iloc[-6]) / 5), 4)


def trend_score(frame: pd.DataFrame) -> Dict[str, Any]:
    score = 0
    details: List[str] = []
    if frame is None or frame.empty:
        return {"score": 0, "details": [], "ma_aligned": False, "volume_ratio": 0.0, "rsi_zone": ""}

    aligned, _ = check_ma_alignment(frame)
    if aligned:
        score += 30
        details.append("均线多头 +30")

    dif, _, hist, golden, dead = check_macd(frame)
    if golden and not dead:
        score += 25
        details.append("MACD金叉 +25")
    elif not dead and dif is not None and hist is not None and dif.iloc[-1] > 0 and hist.iloc[-1] > 0:
        score += 15
        details.append("MACD水上 +15")

    _, zone = check_rsi(frame)
    if zone == "strong":
        score += 20
        details.append("RSI强势 +20")
    elif zone == "neutral":
        score += 10
        details.append("RSI中性 +10")

    vol_ratio = calculate_volume_ratio(frame)
    if vol_ratio >= 1.2:
        score += 15
        details.append(f"放量{vol_ratio:.1f}x +15")

    slope = ma20_slope(frame)
    if slope > 0:
        score += 10
        details.append("20日线上行 +10")

    return {
        "score": min(score, 100),
        "details": details,
        "ma_aligned": aligned,
        "volume_ratio": vol_ratio,
        "rsi_zone": zone,
        "ma20_slope": slope,
    }


def support_resistance(frame: pd.DataFrame, current_price: float) -> Dict[str, Any]:
    if frame is None or frame.empty or len(frame) < 20:
        return {
            "supports": [round(current_price * 0.95, 2), round(current_price * 0.90, 2)],
            "targets": [round(current_price * 1.05, 2), round(current_price * 1.10, 2), round(current_price * 1.15, 2)],
        }
    recent = frame.tail(20)
    ma10 = recent["close"].tail(10).mean()
    ma20 = recent["close"].mean()
    low = recent["low"].min() if "low" in recent else recent["close"].min()
    high = recent["high"].max() if "high" in recent else recent["close"].max()
    supports = sorted({round(v, 2) for v in [ma10, ma20, low, current_price * 0.95] if v < current_price})
    targets = sorted({round(v, 2) for v in [high, current_price * 1.05, current_price * 1.10, current_price * 1.15] if v > current_price})
    if len(targets) < 3:
        targets.extend([round(current_price * factor, 2) for factor in (1.05, 1.10, 1.15)])
    return {"supports": supports[:2] or [round(current_price * 0.95, 2)], "targets": targets[:3]}
