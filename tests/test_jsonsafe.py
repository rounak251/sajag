import json

from sajag.jsonsafe import dumps


def test_nan_becomes_null_at_any_depth():
    text = dumps({"a": [1.5, float("nan")], "b": {"c": float("inf")}})
    assert json.loads(text) == {"a": [1.5, None], "b": {"c": None}}
    assert "NaN" not in text
