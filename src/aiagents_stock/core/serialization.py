"""Serialization helpers shared by API responses and persistence layers."""

from __future__ import annotations

import math
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


def to_jsonable(value: Any) -> Any:
    """Convert project return values into JSON-safe Python objects."""
    if value is None or isinstance(value, (str, int, bool)):
        return value

    if isinstance(value, float):
        return value if math.isfinite(value) else None

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Path):
        return str(value)

    if is_dataclass(value):
        return to_jsonable(asdict(value))

    if hasattr(value, "model_dump"):
        return to_jsonable(value.model_dump())

    if hasattr(value, "dict") and value.__class__.__module__.startswith("pydantic"):
        return to_jsonable(value.dict())

    try:
        import numpy as np

        if isinstance(value, np.generic):
            return to_jsonable(value.item())
        if isinstance(value, np.ndarray):
            return to_jsonable(value.tolist())
    except Exception:
        pass

    try:
        import pandas as pd

        if isinstance(value, pd.DataFrame):
            frame = value.copy()
            frame = frame.where(pd.notnull(frame), None)
            return {
                "type": "dataframe",
                "columns": [str(column) for column in frame.columns],
                "records": to_jsonable(frame.to_dict("records")),
                "row_count": int(len(frame)),
            }
        if isinstance(value, pd.Series):
            return to_jsonable(value.to_dict())
    except Exception:
        pass

    if hasattr(value, "to_dict"):
        try:
            return to_jsonable(value.to_dict())
        except Exception:
            pass

    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]

    return str(value)
