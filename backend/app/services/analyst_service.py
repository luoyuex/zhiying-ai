"""六分析师报告：全部由代码基于真实数据生成，不额外消耗 LLM。"""

from app.providers.models import Quote
from app.schemas.analysis import TechnicalAnalysis
from app.schemas.analyst import AnalystReport
from app.schemas.company import FinancialData, FundFlowData, SentimentData
from app.schemas.search import WebSearchResult

POSITIVE_WORDS = (
    "增长", "预增", "中标", "回购", "增持", "分红", "获批", "突破",
    "涨价", "签订", "合作", "扭亏", "创新高", "利好",
)
NEGATIVE_WORDS = (
    "减持", "亏损", "预亏", "处罚", "立案", "违规", "解禁", "下调",
    "终止", "诉讼", "风险", "退市", "利空", "暴跌",
)
FUNDAMENTAL_WORDS = (
    "业绩", "中报", "年报", "季报", "预告", "快报", "回购", "分红",
    "中标", "订单", "合同", "签约", "扩产", "获批", "营收", "净利",
)
RISK_EVENT_WORDS = (
    "减持", "解禁", "处罚", "立案", "诉讼", "仲裁", "违规", "质押",
    "冻结", "监管函", "警示函", "问询", "调查", "退市",
)


def _clamp(value: float) -> int:
    return max(0, min(100, round(value)))


def _rating(score: int) -> str:
    if score >= 65:
        return "乐观"
    if score >= 45:
        return "中性"
    return "谨慎"


def _web_pages(web: WebSearchResult | None) -> list:
    if web is None or not web.success or not web.pages:
        return []
    return list(web.pages)


def _match_pages(pages: list, words: tuple[str, ...]) -> list[tuple[str, object]]:
    """每个网页按命中的第一个关键词归类，供分析师提取事件线索。"""
    matches: list[tuple[str, object]] = []
    for page in pages:
        text = f"{getattr(page, 'title', '')} {getattr(page, 'summary', '')}"
        for word in words:
            if word in text:
                matches.append((word, page))
                break
    return matches


def _page_meta(page: object) -> str:
    site = str(getattr(page, "site", "") or "")
    date = str(getattr(page, "date", "") or "")
    meta = " ".join(part for part in (site, date) if part)
    return f"（{meta}）" if meta else ""


def _big(value: float | None) -> str:
    if value is None:
        return "—"
    if abs(value) >= 1e8:
        return f"{value / 1e8:.2f} 亿"
    if abs(value) >= 1e4:
        return f"{value / 1e4:.2f} 万"
    return f"{value:.0f}"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}%"


def _technical_analyst(technical: TechnicalAnalysis) -> AnalystReport:
    points = [
        f"{signal.name}：{signal.detail}"
        for signal in technical.signals
        if signal.direction.value == "bullish"
    ][:4]
    risks = [
        f"{signal.name}：{signal.detail}"
        for signal in technical.signals
        if signal.direction.value == "bearish"
    ][:4]
    if not points:
        points = ["技术信号整体中性，未出现明确多头信号"]
    if not risks:
        risks = ["技术面未出现明显空头信号，但仍需关注大盘系统性风险"]
    return AnalystReport(
        key="technical",
        name="技术面",
        score=technical.score,
        rating=_rating(technical.score),
        summary=technical.summary,
        points=points,
        risks=risks,
        data_sources=[technical.source],
        missing=[],
    )


def _fundamental_analyst(
    quote: Quote,
    financial: FinancialData | None,
    web: WebSearchResult | None = None,
) -> AnalystReport:
    if financial is None or not financial.periods:
        pages = _web_pages(web)
        company_news = _match_pages(pages, FUNDAMENTAL_WORDS)
        web_points = [
            f"公开信息提及「{word}」等公司动态{_page_meta(page)}"
            for word, page in company_news[:1]
        ]
        return AnalystReport(
            key="fundamental",
            name="基本面",
            score=50,
            rating="中性",
            summary="未获取到财务/季报数据，基本面维度按中性处理。",
            points=web_points,
            risks=["财务/季报数据缺失，最终结论置信度应下调"],
            data_sources=["元宝搜索"] if company_news else [],
            missing=["财务/季报"],
        )

    latest = financial.periods[0]
    score = 50.0
    points: list[str] = []
    risks: list[str] = []

    if latest.roe is not None:
        if latest.roe >= 15:
            score += 10
            points.append(f"ROE {latest.roe:.2f}%，盈利质量较强")
        elif latest.roe >= 10:
            score += 5
            points.append(f"ROE {latest.roe:.2f}%，盈利能力中等")
        elif latest.roe < 5:
            score -= 5
            risks.append(f"ROE {latest.roe:.2f}%，盈利能力偏弱")

    if latest.revenue_growth_pct is not None:
        if latest.revenue_growth_pct >= 10:
            score += 8
            points.append(f"营收同比 +{latest.revenue_growth_pct:.2f}%")
        elif latest.revenue_growth_pct >= 0:
            score += 3
            points.append(f"营收同比 {latest.revenue_growth_pct:.2f}%")
        else:
            score -= 8
            risks.append(f"营收同比 {latest.revenue_growth_pct:.2f}%")

    if latest.profit_growth_pct is not None:
        if latest.profit_growth_pct >= 10:
            score += 8
            points.append(f"归母净利同比 +{latest.profit_growth_pct:.2f}%")
        elif latest.profit_growth_pct >= 0:
            score += 3
            points.append(f"归母净利同比 {latest.profit_growth_pct:.2f}%")
        else:
            score -= 8
            risks.append(f"归母净利同比 {latest.profit_growth_pct:.2f}%")

    if latest.gross_margin_pct is not None and latest.gross_margin_pct >= 30:
        score += 5
        points.append(f"毛利率 {latest.gross_margin_pct:.2f}%")
    if latest.net_margin_pct is not None and latest.net_margin_pct >= 15:
        score += 4
        points.append(f"净利率 {latest.net_margin_pct:.2f}%")
    if latest.debt_ratio_pct is not None:
        if latest.debt_ratio_pct <= 40:
            score += 5
            points.append(f"资产负债率 {latest.debt_ratio_pct:.2f}%，杠杆较低")
        elif latest.debt_ratio_pct >= 70:
            score -= 8
            risks.append(f"资产负债率 {latest.debt_ratio_pct:.2f}%，杠杆偏高")
        elif latest.debt_ratio_pct >= 60:
            score -= 4
            risks.append(f"资产负债率 {latest.debt_ratio_pct:.2f}%")
    if latest.current_ratio is not None:
        if latest.current_ratio >= 1.5:
            score += 3
        elif latest.current_ratio < 1:
            score -= 4
            risks.append(f"流动比率 {latest.current_ratio:.2f}，短期偿债偏紧")

    if quote.pe is not None and quote.pe > 60:
        score -= 3
        risks.append(f"动态市盈率 {quote.pe:.2f}，估值偏高")
    if quote.pb is not None and quote.pb > 10:
        score -= 2
        risks.append(f"市净率 {quote.pb:.2f}，估值偏高")

    risks.append("仅基于最新报告期与当前估值，未做行业横向对比")
    score = _clamp(score)

    pages = _web_pages(web)
    company_news = _match_pages(pages, FUNDAMENTAL_WORDS)
    web_points: list[str] = []
    if company_news:
        word, page = company_news[0]
        web_points.append(f"公开信息提及「{word}」等公司动态{_page_meta(page)}")
    summary = (
        f"{latest.report_name or latest.report_date}：营收 {_big(latest.revenue)}"
        f"（同比 {_pct(latest.revenue_growth_pct)}），"
        f"归母净利 {_big(latest.net_profit)}（同比 {_pct(latest.profit_growth_pct)}），"
        f"ROE {_pct(latest.roe)}，毛利率 {_pct(latest.gross_margin_pct)}，"
        f"资产负债率 {_pct(latest.debt_ratio_pct)}。"
    )
    return AnalystReport(
        key="fundamental",
        name="基本面",
        score=score,
        rating=_rating(score),
        summary=summary,
        points=(web_points + points)[:4],
        risks=risks[:4],
        data_sources=[financial.source] + (["元宝搜索"] if company_news else []),
        missing=[],
    )


def _fund_flow_analyst(
    fund_flow: FundFlowData | None,
    quote: Quote,
) -> AnalystReport:
    if fund_flow is None or not fund_flow.days:
        return AnalystReport(
            key="fund_flow",
            name="资金面",
            score=50,
            rating="中性",
            summary="未获取到资金流数据，资金面维度按中性处理。",
            points=[],
            risks=["资金流数据缺失，无法判断主力行为"],
            data_sources=[],
            missing=["资金流"],
        )

    days = fund_flow.days
    main_5 = sum(day.main_net or 0 for day in days[-5:])
    main_20 = sum(day.main_net or 0 for day in days[-20:])
    positive_20 = sum(1 for day in days[-20:] if (day.main_net or 0) > 0)
    latest = days[-1]
    score = 50.0
    points: list[str] = []
    risks: list[str] = []

    if main_5 > 0:
        score += 8
        points.append(f"近 5 日主力净流入 {_big(main_5)}")
    else:
        score -= 8
        risks.append(f"近 5 日主力净流出 {_big(abs(main_5))}")
    if main_20 > 0:
        score += 6
        points.append(f"近 20 日主力累计净流入 {_big(main_20)}")
    else:
        score -= 6
        risks.append(f"近 20 日主力累计净流出 {_big(abs(main_20))}")
    if positive_20 >= 12:
        score += 5
        points.append(f"近 20 日有 {positive_20} 天主力净流入")
    elif positive_20 <= 8:
        score -= 5
        risks.append(f"近 20 日仅 {positive_20} 天主力净流入")
    if latest.main_pct is not None and latest.main_pct < -3:
        score -= 3
        risks.append(f"最新交易日主力净占比 {latest.main_pct:.2f}%")

    score = _clamp(score)
    summary = (
        f"近 5 日主力净流入 {_big(main_5)}，近 20 日 {_big(main_20)}，"
        f"20 日中 {positive_20} 天净流入；最新 {latest.date} 主力净占比 {_pct(latest.main_pct)}。"
    )
    return AnalystReport(
        key="fund_flow",
        name="资金面",
        score=score,
        rating=_rating(score),
        summary=summary,
        points=points[:4] or ["资金面多空力量接近平衡"],
        risks=risks[:4],
        data_sources=[fund_flow.source],
        missing=[],
    )


def _sentiment_analyst(
    sentiment: SentimentData | None,
    quote: Quote,
    web: WebSearchResult | None = None,
) -> AnalystReport:
    if sentiment is None:
        pages = _web_pages(web)
        web_points: list[str] = []
        score = 50.0
        if pages:
            text = " ".join(f"{page.title} {page.summary}" for page in pages)
            positive = sum(text.count(word) for word in POSITIVE_WORDS)
            negative = sum(text.count(word) for word in NEGATIVE_WORDS)
            if positive or negative:
                web_points.append(
                    f"公开信息情绪：正面 {positive} / 负面 {negative} 关键词"
                    f"（元宝搜索 {len(pages)} 条）"
                )
                score = 50.0 + min(6, positive * 2) - min(6, negative * 2)
        return AnalystReport(
            key="sentiment",
            name="情绪面",
            score=_clamp(score),
            rating=_rating(_clamp(score)),
            summary="未获取到市场情绪数据，情绪面按中性处理。",
            points=web_points,
            risks=["情绪数据缺失"],
            data_sources=["元宝搜索"] if pages else [],
            missing=["情绪"],
        )

    score = 50.0
    points: list[str] = []
    risks: list[str] = []

    if sentiment.ar is not None:
        points.append(f"AR {sentiment.ar:.1f}")
        if sentiment.ar >= 120:
            score -= 5
            risks.append(f"AR {sentiment.ar:.1f}，短线偏热")
        elif sentiment.ar <= 70:
            score += 3
            risks.append(f"AR {sentiment.ar:.1f}，情绪偏冷")
    if sentiment.br is not None:
        points.append(f"BR {sentiment.br:.1f}")
        if sentiment.br >= 150:
            score -= 5
            risks.append(f"BR {sentiment.br:.1f}，情绪过热")
        elif sentiment.br <= 70:
            score += 3
            risks.append(f"BR {sentiment.br:.1f}，情绪偏冷")
    if sentiment.turnover_pct is not None:
        points.append(f"换手率 {sentiment.turnover_pct:.2f}%")
        if sentiment.turnover_pct >= 15:
            score -= 4
            risks.append("换手率过高，短线分歧较大")
        elif sentiment.turnover_pct <= 1:
            score -= 2
            risks.append("换手率偏低，市场关注度不足")
    if sentiment.rsi14 is not None:
        points.append(f"RSI14 {sentiment.rsi14:.1f}")
        if sentiment.rsi14 >= 75:
            score -= 3
        elif 50 <= sentiment.rsi14 < 70:
            score += 3
    if sentiment.index_changes:
        average = sum(sentiment.index_changes.values()) / len(sentiment.index_changes)
        index_text = "、".join(
            f"{name} {value:+.2f}%" for name, value in sentiment.index_changes.items()
        )
        points.append(f"大盘：{index_text}")
        if average >= 0.5:
            score += 5
        elif average <= -0.5:
            score -= 5
            risks.append("主要指数当日走弱")
    if quote.change_pct is not None and quote.change_pct < -3:
        score -= 3
        risks.append(f"当日跌幅 {quote.change_pct:.2f}%，情绪承压")

    pages = _web_pages(web)
    web_points: list[str] = []
    if pages:
        text = " ".join(f"{page.title} {page.summary}" for page in pages)
        positive = sum(text.count(word) for word in POSITIVE_WORDS)
        negative = sum(text.count(word) for word in NEGATIVE_WORDS)
        if positive or negative:
            web_points.append(
                f"公开信息情绪：正面 {positive} / 负面 {negative} 关键词"
                f"（元宝搜索 {len(pages)} 条）"
            )
            score += min(6, positive * 2) - min(6, negative * 2)
            if negative >= 2:
                risks.append("公开信息出现多条负面关键词，情绪承压")

    score = _clamp(score)
    summary = (
        f"AR {sentiment.ar if sentiment.ar is not None else '—'} / "
        f"BR {sentiment.br if sentiment.br is not None else '—'}，"
        f"换手率 {_pct(sentiment.turnover_pct)}，RSI14 "
        f"{sentiment.rsi14 if sentiment.rsi14 is not None else '—'}；"
        + ("公开信息情绪一并参考元宝搜索。" if pages else "大盘情绪参考主要指数当日表现。")
    )
    return AnalystReport(
        key="sentiment",
        name="情绪面",
        score=score,
        rating=_rating(score),
        summary=summary,
        points=(web_points + points)[:4],
        risks=risks[:4],
        data_sources=[sentiment.source] + (["元宝搜索"] if pages else []),
        missing=[],
    )


def _risk_analyst(
    quote: Quote,
    technical: TechnicalAnalysis,
    bars: list,
    web: WebSearchResult | None = None,
) -> AnalystReport:
    score = 70.0
    points: list[str] = []
    risks: list[str] = []

    atr = technical.indicators.atr14
    atr_pct = atr / quote.price * 100 if atr and quote.price else None
    if atr_pct is not None:
        points.append(f"ATR14 {atr:.2f}（约占现价 {atr_pct:.2f}%）")
        if atr_pct >= 4:
            score -= 15
            risks.append(f"ATR 波动率 {atr_pct:.2f}%，波动偏高")
        elif atr_pct >= 2.5:
            score -= 8
            risks.append(f"ATR 波动率 {atr_pct:.2f}%，波动中等偏高")
        else:
            score += 5

    if len(bars) >= 20:
        recent_high = max(bar.high for bar in bars[-60:])
        drawdown = (recent_high - quote.price) / recent_high * 100 if recent_high else None
        if drawdown is not None:
            points.append(f"距 60 日高点回撤 {drawdown:.2f}%")
            if drawdown >= 20:
                score -= 15
                risks.append("距 60 日高点回撤超过 20%，趋势破坏风险")
            elif drawdown >= 10:
                score -= 8
                risks.append("距 60 日高点回撤超过 10%")
            else:
                score += 5

    rsi = technical.indicators.rsi14
    if rsi is not None:
        if rsi >= 75:
            score -= 8
            risks.append("RSI 超买，短线回调风险")
        elif rsi <= 30:
            score -= 5
            risks.append("RSI 超卖，波动风险偏高")
    if quote.turnover_pct is not None and quote.turnover_pct >= 15:
        score -= 5
        risks.append("换手率过高，交易拥挤")

    pages = _web_pages(web)
    event_news = _match_pages(pages, RISK_EVENT_WORDS)
    web_points: list[str] = []
    if event_news:
        word, page = event_news[0]
        web_points.append(f"公开信息提及「{word}」等事件线索{_page_meta(page)}")
        risks.insert(0, f"公开信息出现 {len(event_news)} 条风险类报道，需以正式公告核实")
        score -= min(9, len(event_news) * 3)
    else:
        risks.append("公告级风险事件（减持/解禁/处罚）未接入，仅覆盖技术风险")

    score = _clamp(score)
    summary = (
        f"ATR 波动率 {_pct(atr_pct)}，"
        f"距 60 日高点回撤 {_pct(drawdown if len(bars) >= 20 else None)}，"
        f"RSI14 {rsi if rsi is not None else '—'}；"
        + (
            f"公开信息提供 {len(event_news)} 条事件线索，以正式公告为准。"
            if event_news
            else "事件级风险数据未接入。"
        )
    )
    return AnalystReport(
        key="risk",
        name="风险",
        score=score,
        rating="低风险" if score >= 70 else "中等风险" if score >= 45 else "高风险",
        summary=summary,
        points=(web_points + points)[:4],
        risks=risks[:4],
        data_sources=["computed_technical"] + (["元宝搜索"] if event_news else []),
        missing=[] if event_news else ["公告级风险事件"],
    )


def _news_analyst(web: WebSearchResult | None) -> AnalystReport:
    if web is None or not web.success or not web.pages:
        return AnalystReport(
            key="news",
            name="新闻",
            score=50,
            rating="中性",
            summary="未获取到公开网页信息，新闻维度按中性处理。",
            points=[],
            risks=["新闻/公告数据缺失，无法评估事件影响"],
            data_sources=[],
            missing=["新闻/公告"],
        )

    text = " ".join(f"{page.title} {page.summary}" for page in web.pages)
    positive = sum(text.count(word) for word in POSITIVE_WORDS)
    negative = sum(text.count(word) for word in NEGATIVE_WORDS)
    score = _clamp(50 + positive * 4 - negative * 4)
    points = [
        f"{page.title}（{page.site or '未知站点'} {page.date or '日期未知'}）"
        for page in web.pages[:3]
    ]
    risks = ["公开网页信息未经官方公告核验，需核对发布日期"]
    if negative:
        risks.append(f"检索结果中出现 {negative} 个偏负面关键词")
    summary = (
        f"元宝检索到 {len(web.pages)} 条公开信息，"
        f"正面关键词 {positive} 个、负面关键词 {negative} 个；仅作事件背景。"
    )
    return AnalystReport(
        key="news",
        name="新闻",
        score=score,
        rating=_rating(score),
        summary=summary,
        points=points,
        risks=risks,
        data_sources=["元宝搜索"],
        missing=[],
    )


def build_analysts(
    quote: Quote,
    technical: TechnicalAnalysis,
    financial: FinancialData | None,
    fund_flow: FundFlowData | None,
    sentiment: SentimentData | None,
    web: WebSearchResult | None,
    bars: list,
) -> list[AnalystReport]:
    return [
        _technical_analyst(technical),
        _fundamental_analyst(quote, financial, web),
        _fund_flow_analyst(fund_flow, quote),
        _risk_analyst(quote, technical, bars, web),
        _sentiment_analyst(sentiment, quote, web),
        _news_analyst(web),
    ]
