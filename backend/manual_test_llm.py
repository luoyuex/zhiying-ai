"""用真实 LLM Key 验证推理型模型的 JSON 输出链路（不落库、不走 HTTP）。"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.llm.client import LLMClient  # noqa: E402
from app.llm.prompts import SYSTEM_PROMPT  # noqa: E402

QUOTE = {
    "symbol": "600519",
    "name": "贵州茅台",
    "price": 1523.0,
    "change_pct": 1.24,
    "pe_ttm": 22.8,
    "pb": 7.9,
    "market_cap": 191300000000,
}
INDICATORS = {
    "ma5": 1510.2,
    "ma10": 1495.6,
    "ma20": 1478.3,
    "ma60": 1452.1,
    "rsi14": 61.5,
    "macd": 3.8,
    "macd_signal": 2.9,
    "boll_upper": 1560.0,
    "boll_lower": 1435.0,
    "support": 1480.0,
    "resistance": 1560.0,
    "atr14": 28.5,
}
USER_PROMPT = (
    "请基于以下数据输出 JSON（不要输出多余文字）：\n"
    f"行情：{json.dumps(QUOTE, ensure_ascii=False)}\n"
    f"指标：{json.dumps(INDICATORS, ensure_ascii=False)}\n"
    "字段要求：rating(买入/持有/卖出 之一)、confidence(1-10 整数)、"
    "summary(100字内)、key_points(数组，3条)、risks(数组，2条)"
)


async def main() -> None:
    client = LLMClient()
    result = await client.generate_json(SYSTEM_PROMPT, USER_PROMPT)
    print("=== 解析成功 ===")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:800])


if __name__ == "__main__":
    asyncio.run(main())
