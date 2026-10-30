"""决策模型分歧分析回测：历史 AI 报告 × SystemOne(intern-decision-4b) × 后验收益。

接口：TokenPlan SystemOne（Jev / TypeSafe 兼容协议）
  POST {api_base}/v1/systemone    api_base 默认 https://discovery-api.intern-ai.org.cn
  模型 intern-decision-4b；仅按输入 Token 计费（0.2 墨点/百万），输出不计费。
  限速 200 RPM（与生成模型分开计）。

一次请求提交两道判断题（协议支持 1~16 题）：
  rating  choice 题 —— 买入/持有/卖出 评级概率，与 LLM 首席决策对比
  upside  noul   题 —— P(T+20 收盘涨幅 ≥ +threshold%)，概率与实际命中率对比，
                      直接检验模型校准能力

回答三个问题（"要不要加决策模型轨"的判据）：
  1. 一致率         —— 决策模型与 LLM 首席决策的评级一致比例（决定加轨增益空间）
  2. 分歧样本正确率 —— 两者不一致时谁更准（决定分歧时的仲裁方向）
  3. ECE / 校准     —— 两者 confidence 谁更可信（决定校准价值）

用法（在 backend 目录下）：
    uv run python -m app.scripts.backtest_decision_model --api-key <TOKENPLAN_KEY>
    API Key 也可用环境变量 TOKENPLAN_API_KEY 传入；其余参数见 --help。

输出：
    控制台统计摘要 + logs/decision_backtest_samples.csv 样本明细

方法论（避免前视偏差）：
    - 决策输入 state 从 analysis_reports.report JSONB 重建（六维分数与摘要），
      即"决策时刻同源数据"，不用今日行情评判旧决策。
    - 后验收益从前复权日 K（东财）计算：基准 = 决策日【之后】第一根 K 线收盘价
      （严格晚于决策日，避免用决策后才发生的当日收盘价），T+5/T+20 为其后第 5/20 根收盘。
    - 方向标签：T+20 收益 >= +threshold（默认 5%）为"买入"，<= -threshold 为"卖出"，
      中间为"持有"。K 线拉取约 250 根（一年），--days 请勿超过 240。
"""

import argparse
import asyncio
import csv
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select

from app.db.models.analysis_report import AnalysisReport
from app.db.redis import close_redis, get_redis
from app.db.session import SessionLocal, engine
from app.providers.models import Adjust, KlinePeriod
from app.services.market_service import MarketDataService

TZ = ZoneInfo("Asia/Shanghai")
RATINGS = ("买入", "持有", "卖出")


# ---------------------------------------------------------------------------
# 1. 报告加载与 state 重建
# ---------------------------------------------------------------------------

async def load_reports(days: int, limit: int) -> list[AnalysisReport]:
    """近 N 天、report JSONB 内含首席决策的报告；同股同日只保留最新一份。"""
    async with SessionLocal() as session:
        stmt = (
            select(AnalysisReport)
            .where(AnalysisReport.created_at >= datetime.now(TZ) - timedelta(days=days))
            .order_by(AnalysisReport.created_at.desc())
        )
        rows = (await session.scalars(stmt)).all()

    picked: dict[tuple[str, str], AnalysisReport] = {}
    for row in rows:  # 已按时间倒序，先见即最新
        decision = (row.report or {}).get("decision") or {}
        if not decision.get("rating"):
            continue  # 早期版本的报告可能没有 decision 键
        key = (row.symbol, row.created_at.astimezone(TZ).date().isoformat())
        picked.setdefault(key, row)
    return list(picked.values())[:limit]


def build_state(row: AnalysisReport) -> dict:
    """从 report JSONB 重建决策输入（决策时刻同源数据）。"""
    payload = row.report or {}
    return {
        "symbol": row.symbol,
        "name": row.name,
        "price": payload.get("price"),
        "change_pct": payload.get("change_pct"),
        "decision_date": row.created_at.astimezone(TZ).date().isoformat(),
        "analysis_summary": (payload.get("analysis") or {}).get("summary", ""),
        "analysts": [
            {
                "name": item.get("name"),
                "score": item.get("score"),
                "rating": item.get("rating"),
                "summary": (item.get("summary") or "")[:120],
            }
            for item in payload.get("analysts", [])
        ],
    }


# ---------------------------------------------------------------------------
# 2. SystemOne 决策调用（choice 评级题 + noul 是非题）
# ---------------------------------------------------------------------------

def build_questions(threshold_pct: float, horizon: int) -> dict:
    """题目定义与回测标签规则对齐（±threshold%、T+horizon），保证评测语义一致。"""
    up = f"+{threshold_pct:g}%"
    down = f"-{threshold_pct:g}%"
    return {
        "rating": {
            "type": "choice",
            "instructions": f"该股未来 {horizon} 个交易日最合理的操作评级是？",
            "criteria": {
                "买入": f"六维证据偏多，预期持有期收盘涨幅达到 {up}",
                "持有": "多空证据大体平衡，预期涨幅在正负阈值之间震荡",
                "卖出": f"六维证据偏空，预期持有期收盘跌幅达到 {down}",
            },
        },
        "upside": {
            "type": "noul",
            "instructions": f"未来 {horizon} 个交易日，该股收盘价涨幅是否达到 {up}？",
            "criteria": {
                "true": f"涨幅达到或超过 {up}",
                "false": f"涨幅不足 {up}（含持平与下跌）",
            },
        },
    }


async def score_decision(
    client: httpx.AsyncClient,
    api_base: str,
    api_key: str,
    model: str,
    state: dict,
    questions: dict,
) -> dict | None:
    """调 SystemOne 接口；返回评级概率、P(涨≥阈值) 与输入 token 数，失败重试一次。"""
    body = {
        "model": model,
        "state": json.dumps(state, ensure_ascii=False),
        "questions": questions,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    for attempt in range(2):
        try:
            response = await client.post(
                f"{api_base}/v1/systemone", json=body, headers=headers, timeout=60
            )
            response.raise_for_status()
            data = response.json()
            answers = data.get("answers") or {}
            probs_raw = (answers.get("rating") or {}).get("probabilities") or {}
            values = {key: max(0.0, float(probs_raw.get(key, 0) or 0)) for key in RATINGS}
            total = sum(values.values())
            if total <= 0:
                return None
            p_up = (answers.get("upside") or {}).get("noul")
            return {
                "probs": {key: value / total for key, value in values.items()},
                "p_up": min(1.0, max(0.0, float(p_up))) if p_up is not None else None,
                "input_tokens": int((data.get("usage") or {}).get("input_tokens") or 0),
            }
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            pass
        await asyncio.sleep(1.5 * (attempt + 1))
    return None


# ---------------------------------------------------------------------------
# 3. K 线对齐与方向标签
# ---------------------------------------------------------------------------

def forward_bars(bars: list, decision_date) -> int:
    """决策日之后有多少根日 K（先按时间升序，兼容不同 provider 的返回顺序）。"""
    ordered = sorted(bars, key=lambda bar: bar.time)
    return sum(1 for bar in ordered if bar.time.astimezone(TZ).date() > decision_date)


def label_outcome(
    bars: list,
    decision_date,
    threshold_pct: float,
    horizon: int,
) -> dict | None:
    """基准 = 严格晚于决策日的第一根 K 线；不足 horizon 根返回 None（T+N 窗口未走完）。"""
    after = [
        bar
        for bar in sorted(bars, key=lambda bar: bar.time)
        if bar.time.astimezone(TZ).date() > decision_date
    ]
    if len(after) <= horizon:  # 需要 after[horizon] 存在
        return None
    base = after[0].close
    if base <= 0:
        return None
    ret5 = after[5].close / base - 1 if len(after) > 5 else None
    ret20 = after[horizon].close / base - 1
    label = "持有"
    if ret20 >= threshold_pct / 100:
        label = "买入"
    elif ret20 <= -threshold_pct / 100:
        label = "卖出"
    return {
        "ret5": ret5 * 100 if ret5 is not None else None,
        "ret20": ret20 * 100,
        "label": label,
    }


# ---------------------------------------------------------------------------
# 4. 统计
# ---------------------------------------------------------------------------

def accuracy(samples: list[dict], key: str) -> float:
    if not samples:
        return 0.0
    hits = sum(1 for s in samples if s[key] == s["label"])
    return hits / len(samples)


def ece(items: list[tuple[float, bool]]) -> float:
    """期望校准误差（10 桶）：Σ 桶样本占比 × |平均置信 - 命中率|。"""
    if not items:
        return float("nan")
    buckets: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0, 0])  # 置信和/命中和/数量
    for conf, hit in items:
        slot = buckets[min(int(conf * 10), 9)]
        slot[0] += conf
        slot[1] += 1.0 if hit else 0.0
        slot[2] += 1
    total = len(items)
    return sum(
        (slot[2] / total) * abs(slot[0] / slot[2] - slot[1] / slot[2])
        for slot in buckets.values()
    )


def calibration_rows(items: list[tuple[float, bool]]) -> list[str]:
    """P(涨≥阈值) 分桶校准表：概率区间 → 样本数 / 平均概率 / 实际命中率。"""
    rows: list[str] = []
    for low, high in ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)):
        bucket = [item for item in items if low <= item[0] < high]
        if not bucket:
            continue
        avg_prob = sum(p for p, _ in bucket) / len(bucket)
        hit_rate = sum(1 for _, hit in bucket if hit) / len(bucket)
        rows.append(
            f"    {low:.1f}–{min(high, 1.0):.1f}: n={len(bucket)} "
            f"平均概率 {avg_prob:.2f} | 实际命中 {hit_rate:.0%}"
        )
    return rows


def group_returns(samples: list[dict], key: str) -> dict[str, tuple[float, int]]:
    """按评级分组的平均 T+20 收益（检验分级单调性），按买/持/卖固定顺序输出。"""
    stats: dict[str, list[float]] = defaultdict(list)
    for s in samples:
        stats[s[key]].append(s["ret20"])
    return {
        rating: (sum(values) / len(values), len(values))
        for rating in RATINGS
        if (values := stats.get(rating))
    }


def summarize(samples: list[dict], threshold_pct: float, horizon: int, input_tokens: int) -> None:
    labeled = [s for s in samples if s["label"]]
    if samples and not labeled:
        # 没有任何一个样本能对齐后验收益——先诊断清楚是哪种情况
        counts = sorted(s["forward_bars"] for s in samples)
        latest = max(s["decision_date"] for s in samples)
        print("0 个样本可对齐后验收益，决策 API 一次也没被调用（未消耗额度）。")
        print(f"最晚决策日 {latest}；决策日之后的日 K 根数："
              f"最少 {counts[0]} / 中位 {counts[len(counts) // 2]} / 最多 {counts[-1]}")
        if counts[-1] == 0:
            print("全部样本的 K 线数据为空——检查行情接口在服务器上是否可达。")
            return
        best = counts[-1]
        print(f"\n各持有期当前能对齐的样本数（共 {len(samples)} 份报告）：")
        for h, th in ((1, 2), (3, 3), (5, 3), (10, 4), (20, 5)):
            usable = sum(1 for s in samples if s["forward_bars"] > h)
            wait = max(0, h + 1 - best)
            note = "现在就能跑" if not wait else f"约 {wait} 个交易日后可跑"
            print(f"  T+{h:<2} (±{th}%): 可对齐 {usable} 份 | {note}")
        print("\n说明：T+1/T+3 噪声较大，只适合验证调用链路；"
              "\n正式回测建议等 T+20 窗口走完，届时样本量也会自然增长。")
        return
    dm_labeled = [s for s in labeled if s["dm_ok"]]
    if not dm_labeled:
        print(f"有 {len(labeled)} 个可对齐样本，但决策模型调用全部失败——"
              "检查 API Key / 模型名 / 网络后重跑。")
        return

    disagreements = [s for s in dm_labeled if not s["agree"]]
    directional = [s for s in dm_labeled if s["label"] in ("买入", "卖出")]
    agree_rate = 1 - len(disagreements) / len(dm_labeled)
    llm_acc = accuracy(dm_labeled, "llm_rating")
    dm_acc = accuracy(dm_labeled, "dm_rating")
    llm_ece = ece([(s["llm_conf"] / 100, s["llm_rating"] == s["label"]) for s in dm_labeled])
    dm_ece = ece([(s["dm_conf"], s["dm_rating"] == s["label"]) for s in dm_labeled])

    print("\n" + "=" * 64)
    failed = len(labeled) - len(dm_labeled)
    unlabeled = len(samples) - len(labeled)
    print(f"分歧分析结果（有效样本 {len(dm_labeled)}，"
          f"决策模型失败 {failed}，缺后验标签 {unlabeled}）")
    print("=" * 64)
    print(f"一致率：{agree_rate:.1%}（分歧 {len(disagreements)} 条）")
    print(f"三分类准确率（全部样本）：LLM {llm_acc:.1%} | 决策模型 {dm_acc:.1%}")
    if directional:
        print(f"方向准确率（仅 |T+20|≥阈值的 {len(directional)} 条）："
              f"LLM {accuracy(directional, 'llm_rating'):.1%} | "
              f"决策模型 {accuracy(directional, 'dm_rating'):.1%}")
    if disagreements:
        print(f"分歧样本准确率（{len(disagreements)} 条）："
              f"LLM {accuracy(disagreements, 'llm_rating'):.1%} | "
              f"决策模型 {accuracy(disagreements, 'dm_rating'):.1%}")
    print(f"ECE（越小越可信）：LLM {llm_ece:.3f} | 决策模型 {dm_ece:.3f}")

    print("分级单调性（评级 → 平均 T+20 收益%，括号为样本数）：")
    for label, key in (("LLM", "llm_rating"), ("决策模型", "dm_rating")):
        grouped = group_returns(dm_labeled, key)
        parts = [f"{rating} {value:+.2f}%(n={count})" for rating, (value, count) in grouped.items()]
        print(f"  {label}：" + (" | ".join(parts) if parts else "无样本"))

    # noul 是非题校准：P(涨≥阈值) vs 实际命中（校准能力最直接的检验）
    upside = [
        (s["p_up"], s["ret20"] >= threshold_pct)
        for s in dm_labeled
        if s["p_up"] is not None
    ]
    if upside:
        print(f"upside 是非题校准（P(T+20 涨幅≥{threshold_pct:g}%)，ECE = {ece(upside):.3f}）：")
        for row in calibration_rows(upside):
            print(row)

    print("\n结论建议：")
    if len(dm_labeled) < 60:
        print("  样本量 < 60，统计不稳健——先只看趋势，攒够样本后再跑一次。")
    dm_gap = accuracy(disagreements, "dm_rating") - accuracy(disagreements, "llm_rating")
    if agree_rate > 0.9 and dm_gap <= 0:
        print("  一致率 >90% 且分歧样本 LLM 不差 → 不建议加轨；"
              "决策模型仅可考虑用于 confidence 校准展示。")
    elif dm_gap >= 0.10:
        print(f"  分歧样本上决策模型显著更准（+{dm_gap:.0%}）→ 值得以『先验注入式』接入起步。")
    elif dm_ece < llm_ece - 0.05:
        print("  决策模型校准显著更好 → 优先考虑仅把其概率作为报告 confidence 校准源。")
    else:
        print("  两轨差异不显著 → 维持现状；样本攒多或阈值调参后再复跑。")

    if input_tokens:
        cost = input_tokens / 1_000_000 * 0.2
        print(f"\n决策 API 共消耗输入 token {input_tokens:,}（估算 {cost:.4f} 墨点，输出不计费）")


# ---------------------------------------------------------------------------
# 5. 主流程
# ---------------------------------------------------------------------------

async def run(args: argparse.Namespace) -> None:
    if not args.api_key:
        raise SystemExit("缺少 API Key：--api-key 或环境变量 TOKENPLAN_API_KEY")

    reports = await load_reports(args.days, args.limit)
    if not reports:
        print(f"近 {args.days} 天内没有含首席决策的历史报告，"
              "先让系统正常跑一段时间再回测。")
        return
    print(f"载入历史报告 {len(reports)} 份（近 {args.days} 天，同股同日去重后）")

    # 按股拉一次前复权日 K（MarketDataService 自带缓存与限流）
    market = MarketDataService(get_redis())
    klines: dict[str, list] = {}
    delayed_symbols: set[str] = set()
    symbols = sorted({row.symbol for row in reports})
    for index, symbol in enumerate(symbols, 1):
        try:
            series = await market.get_kline(symbol, period=KlinePeriod.DAY, adjust=Adjust.QFQ)
            klines[symbol] = series.bars
            if series.delayed:
                delayed_symbols.add(symbol)
        except Exception as exc:  # noqa: BLE001 —— 单股失败不应中断整体回测
            print(f"K 线获取失败 {symbol}: {exc}")
        if index % 20 == 0:
            print(f"K 线进度 {index}/{len(symbols)}")
    if delayed_symbols:
        print(f"警告：{len(delayed_symbols)} 只股票的 K 线来自过期缓存（行情源失败自动兜底），"
              "统计可能不含最近交易日——先用 app.scripts.check_proxy 自检行情源。")

    questions = build_questions(args.threshold, args.horizon)
    semaphore = asyncio.Semaphore(args.concurrency)
    progress = 0
    input_tokens = 0
    samples: list[dict] = []

    async def run_one(client: httpx.AsyncClient, row: AnalysisReport) -> None:
        nonlocal progress, input_tokens
        decision = (row.report or {}).get("decision") or {}
        decision_date = row.created_at.astimezone(TZ).date()
        outcome = label_outcome(
            klines.get(row.symbol, []), decision_date, args.threshold, args.horizon
        )
        bars = klines.get(row.symbol, [])
        sample = {
            "symbol": row.symbol,
            "name": row.name,
            "decision_date": decision_date.isoformat(),
            "llm_rating": decision.get("rating", ""),
            "llm_conf": float(decision.get("confidence") or 0),
            "dm_probs": None,
            "dm_rating": "",
            "dm_conf": 0.0,
            "p_up": None,
            "dm_ok": False,
            "agree": False,
            "forward_bars": forward_bars(bars, decision_date),
            "ret5": outcome["ret5"] if outcome else None,
            "ret20": outcome["ret20"] if outcome else None,
            "label": outcome["label"] if outcome else "",
        }
        if outcome is not None:
            async with semaphore:
                result = await score_decision(
                    client, args.api_base, args.api_key, args.model,
                    build_state(row), questions,
                )
                await asyncio.sleep(args.interval)
            if result is not None:
                probs = result["probs"]
                sample["dm_probs"] = probs
                sample["dm_rating"] = max(probs, key=probs.get)
                sample["dm_conf"] = probs[sample["dm_rating"]]
                sample["p_up"] = result["p_up"]
                sample["dm_ok"] = True
                sample["agree"] = sample["dm_rating"] == sample["llm_rating"]
                input_tokens += result["input_tokens"]
        samples.append(sample)
        progress += 1
        if progress % 20 == 0 or progress == len(reports):
            print(f"决策评分进度 {progress}/{len(reports)}")

    async with httpx.AsyncClient() as client:
        await asyncio.gather(*(run_one(client, row) for row in reports))

    summarize(samples, args.threshold, args.horizon, input_tokens)
    write_csv(samples, Path(args.csv))

    await close_redis()
    await engine.dispose()


def write_csv(samples: list[dict], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "symbol", "name", "decision_date", "llm_rating", "llm_conf",
            "dm_buy", "dm_hold", "dm_sell", "dm_rating", "dm_conf", "p_up", "agree",
            "ret5_pct", "ret20_pct", "label",
        ])
        for s in samples:
            probs = s["dm_probs"] or {}
            writer.writerow([
                s["symbol"], s["name"], s["decision_date"], s["llm_rating"], s["llm_conf"],
                round(probs["买入"], 4) if probs else "",
                round(probs["持有"], 4) if probs else "",
                round(probs["卖出"], 4) if probs else "",
                s["dm_rating"],
                round(s["dm_conf"], 4) if s["dm_ok"] else "",
                round(s["p_up"], 4) if s["p_up"] is not None else "",
                int(s["agree"]),
                "" if s["ret5"] is None else round(s["ret5"], 2),
                "" if s["ret20"] is None else round(s["ret20"], 2),
                s["label"],
            ])
    print(f"样本明细已写入 {out_path.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="决策模型分歧分析回测（SystemOne 协议）")
    parser.add_argument("--api-key", default=os.environ.get("TOKENPLAN_API_KEY", ""),
                        help="TOKENPLAN API Key（或环境变量 TOKENPLAN_API_KEY）")
    parser.add_argument("--api-base", default="https://discovery-api.intern-ai.org.cn",
                        help="SystemOne API 根地址（不带 /v1）")
    parser.add_argument("--model", default="intern-decision-4b", help="决策模型 ID")
    parser.add_argument("--days", type=int, default=120, help="回看天数（默认 120，勿超 240）")
    parser.add_argument("--limit", type=int, default=300, help="最多样本数（默认 300）")
    parser.add_argument("--threshold", type=float, default=5.0, help="方向标签阈值%%（默认 5）")
    parser.add_argument("--horizon", type=int, default=20, help="持有期交易日数（默认 20）")
    parser.add_argument("--concurrency", type=int, default=4,
                        help="决策 API 并发（默认 4；接口限速 200 RPM）")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="每次调用间隔秒（默认 1.0；4 并发约 120 RPM，低于接口 200 RPM 限速）")
    parser.add_argument("--csv", default="logs/decision_backtest_samples.csv",
                        help="明细输出路径")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
