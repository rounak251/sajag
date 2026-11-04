"""Write JSON a browser can read. Browsers reject NaN, and one NaN fails the whole file."""
import json
import math


def finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [finite(v) for v in value]
    return value


def dumps(payload, **kwargs) -> str:
    return json.dumps(finite(payload), ensure_ascii=False, allow_nan=False, **kwargs)
