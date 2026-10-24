import json
from typing import Any


def jsonable(value: Any) -> Any:
    """把 UUID / datetime / Decimal / Pydantic 对象转成可写入 JSONB 的结构。"""
    if value is None:
        return None
    return json.loads(json.dumps(value, default=str, ensure_ascii=False))
