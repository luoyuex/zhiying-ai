"""主力选股：排行解析、过滤规则与接口。"""

import uuid
from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.deps import get_current_user
from app.db.models.user import User
from app.llm.client import LLMRequestError, LLMResponseError
from app.main import app
from app.providers.base import ProviderUnavailable, now_shanghai
from app.providers.fund_flow_rank import SinaFundFlowRankProvider
from app.providers.models import Quote
from app.providers.performance import EastmoneyPerformanceProvider
from app.schemas.screener import (
    FundFlowRankItem,
    LowPriceBullAnalysisRequest,
    LowPriceBullItem,
    LowPriceBullRequest,
    LowPriceBullResponse,
    MainForceAnalysisRequest,
    MainForceAnalysisResponse,
    MainForceRecommendation,
    MainForceScreenRequest,
    MainForceScreenResponse,
    PerformanceRow,
    ProfitGrowthAnalysisRequest,
    ProfitGrowthItem,
    SmallCapAnalysisRequest,
    SmallCapItem,
    SmallCapRequest,
    SmallCapResponse,
)
from app.services import main_force_analysis_service, screener_service
from app.services.screener_service import (
    LowPriceCandidateSet,
    ProfitGrowthCandidateSet,
    SmallCapCandidateSet,
)


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str | int] = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value

    async def incr(self, key: str) -> int:
        value = int(self.store.get(key, 0)) + 1
        self.store[key] = value
        return value

    async def expire(self, key: str, seconds: int) -> None:
        return None


ROWS = [
    {
        "symbol": "sh511360",
        "name": "短融ETF海富通",
        "trade": "114.0770",
        "changeratio": "0.00007",
        "r0_net": "5829699867.3",
        "r0_ratio": "0.0852256",
        "amount": "68403143939.0",
    },
    {
        "symbol": "sh603236",
        "name": "移远通信",
        "trade": "50.00",
        "changeratio": "0.03",
        "r0_net": "1320237099.64",
        "r0_ratio": "0.085",
        "amount": "1000000000",
    },
    {
        "symbol": "sz300394",
        "name": "天孚通信",
        "trade": "100.00",
        "changeratio": "0.05",
        "r0_net": "1098295551.69",
        "r0_ratio": "0.07",
        "amount": "800000000",
    },
    {
        "symbol": "sh688111",
        "name": "金山办公",
        "trade": "300.00",
        "changeratio": "0.02",
        "r0_net": "500000000",
        "r0_ratio": "0.05",
        "amount": "600000000",
    },
    {
        "symbol": "sh600000",
        "name": "ST浦发",
        "trade": "10.00",
        "changeratio": "0.01",
        "r0_net": "400000000",
        "r0_ratio": "0.04",
        "amount": "500000000",
    },
    {
        "symbol": "sz000001",
        "name": "平安银行",
        "trade": "12.00",
        "changeratio": "0.05",
        "r0_net": "300000000",
        "r0_ratio": "0.03",
        "amount": "400000000",
    },
]


def parse_rows():
    return [
        item
        for row in ROWS
        if (item := SinaFundFlowRankProvider.parse_row(row)) is not None
    ]


def test_parse_row_filters_non_stocks():
    items = parse_rows()

    assert [item.symbol for item in items] == [
        "603236",
        "300394",
        "688111",
        "600000",
        "000001",
    ]
    assert items[0].change_pct == 3.0
    assert items[0].main_net_pct == 8.5


def test_filter_main_force_rules():
    request = MainForceScreenRequest(top_n=10, max_change_pct=7.0)
    filtered = screener_service.filter_main_force(parse_rows(), request)

    assert [item.symbol for item in filtered] == ["603236", "000001"]


async def test_screen_main_force(monkeypatch):
    async def fake_fetch(self, limit: int = 300):
        return parse_rows()

    monkeypatch.setattr(SinaFundFlowRankProvider, "fetch", fake_fetch)

    response = await screener_service.screen_main_force(
        FakeRedis(),
        MainForceScreenRequest(top_n=5, max_change_pct=7.0),
    )

    assert response.strategy == "main_force"
    assert response.scanned_count == 5
    assert response.candidate_count == 2
    assert [item.symbol for item in response.items] == ["603236", "000001"]
    assert response.filters["exclude_gem"] is True


async def test_strategies_api():
    user = User(id=uuid.uuid4(), email="screener@example.com", nickname="Screener")
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/v1/screener/strategies")
            assert response.status_code == 200, response.text
            body = response.json()
            assert body[0]["id"] == "main_force"
            assert body[0]["status"] == "available"
    finally:
        app.dependency_overrides.clear()


async def test_main_force_api(monkeypatch):
    user = User(id=uuid.uuid4(), email="screener2@example.com", nickname="Screener")

    async def fake_screen(_redis, _request):
        return MainForceScreenResponse(
            items=[],
            scanned_count=0,
            candidate_count=0,
            fetched_at=datetime.now(),
            filters={},
        )

    monkeypatch.setattr("app.api.v1.screener.screen_main_force", fake_screen)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post("/api/v1/screener/main-force", json={"top_n": 5})
            assert response.status_code == 200, response.text
            assert response.json()["strategy"] == "main_force"
    finally:
        app.dependency_overrides.clear()


async def test_main_force_api_maps_market_error(monkeypatch):
    user = User(id=uuid.uuid4(), email="screener3@example.com", nickname="Screener")

    async def broken(_redis, _request):
        raise ProviderUnavailable("mock unavailable")

    monkeypatch.setattr("app.api.v1.screener.screen_main_force", broken)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post("/api/v1/screener/main-force", json={"top_n": 5})
            assert response.status_code == 503
            assert response.json()["code"] == "MARKET_UNAVAILABLE"
    finally:
        app.dependency_overrides.clear()


def test_performance_parse_rows():
    payload = {
        "result": {
            "data": [
                {
                    "SECURITY_CODE": "600798",
                    "SECURITY_NAME_ABBR": "宁波海运",
                    "REPORTDATE": "2026-09-30 00:00:00",
                    "SJLTZ": 135.4,
                    "YSTZ": 56.2,
                },
                {
                    "SECURITY_CODE": "511360",
                    "SECURITY_NAME_ABBR": "短融ETF",
                    "REPORTDATE": "2026-09-30 00:00:00",
                    "SJLTZ": 10,
                    "YSTZ": 5,
                },
            ]
        }
    }

    rows = EastmoneyPerformanceProvider.parse_rows(payload)

    assert len(rows) == 1
    assert rows[0].symbol == "600798"
    assert rows[0].profit_growth == 135.4
    assert rows[0].report_date == "2026-09-30"


class FakePerformanceProvider:
    async def fetch(self, _min_growth: float, _min_revenue: float = 0.0):
        return "2026-09-30", [
            PerformanceRow(
                symbol="600798",
                name="宁波海运",
                report_date="2026-09-30",
                profit_growth=135.4,
                revenue_growth=56.2,
            ),
            PerformanceRow(
                symbol="002148",
                name="北纬科技",
                report_date="2026-09-30",
                profit_growth=2246.4,
                revenue_growth=0.7,
            ),
            PerformanceRow(
                symbol="301118",
                name="恒光股份",
                report_date="2026-09-30",
                profit_growth=4845.1,
            ),
            PerformanceRow(
                symbol="688779",
                name="五矿新能",
                report_date="2026-09-30",
                profit_growth=2396.7,
            ),
            PerformanceRow(
                symbol="600001",
                name="ST测试",
                report_date="2026-09-30",
                profit_growth=300.0,
            ),
            PerformanceRow(
                symbol="830799",
                name="北交所测试",
                report_date="2026-09-30",
                profit_growth=200.0,
            ),
        ]


def make_quote(
    symbol: str,
    price: float,
    amount: float,
    market_cap: float | None = None,
) -> Quote:
    return Quote(
        symbol=symbol,
        name=f"测试{symbol}",
        price=price,
        change_pct=1.0,
        amount=amount,
        total_market_cap=market_cap,
        source="test",
        fetched_at=now_shanghai(),
    )


async def test_low_price_bull_screen(monkeypatch):
    async def fake_fetch_quotes(_symbols):
        return {
            "600798": make_quote("600798", 3.29, 52_436_307),
            "002148": make_quote("002148", 6.27, 59_388_524),
        }

    monkeypatch.setattr(screener_service, "fetch_quotes", fake_fetch_quotes)

    response = await screener_service.screen_low_price_bull(
        LowPriceBullRequest(top_n=5, max_price=10, min_profit_growth=100),
        provider=FakePerformanceProvider(),
    )

    assert response.scanned_count == 6
    assert response.candidate_count == 2
    assert [item.symbol for item in response.items] == ["600798", "002148"]
    assert response.items[0].price == 3.29
    assert response.items[0].profit_growth == 135.4
    assert response.filters["report_date"] == "2026-09-30"


async def test_low_price_bull_api(monkeypatch):
    user = User(id=uuid.uuid4(), email="lowbull@example.com", nickname="LowBull")

    async def fake_screen(_request):
        return LowPriceBullResponse(
            items=[],
            scanned_count=0,
            candidate_count=0,
            fetched_at=datetime.now(),
            filters={},
        )

    monkeypatch.setattr("app.api.v1.screener.screen_low_price_bull", fake_screen)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/v1/screener/low-price-bull", json={"top_n": 5}
            )
            assert response.status_code == 200, response.text
            assert response.json()["strategy"] == "low_price_bull"
    finally:
        app.dependency_overrides.clear()


async def test_low_price_bull_api_maps_market_error(monkeypatch):
    user = User(id=uuid.uuid4(), email="lowbull2@example.com", nickname="LowBull")

    async def broken(_request):
        raise ProviderUnavailable("mock unavailable")

    monkeypatch.setattr("app.api.v1.screener.screen_low_price_bull", broken)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/v1/screener/low-price-bull", json={"top_n": 5}
            )
            assert response.status_code == 503
            assert response.json()["code"] == "MARKET_UNAVAILABLE"
    finally:
        app.dependency_overrides.clear()


class FakeSmallCapProvider:
    async def fetch(self, _min_profit: float, _min_revenue: float = 0.0):
        return "2026-09-30", [
            PerformanceRow(
                symbol="600798",
                name="宁波海运",
                report_date="2026-09-30",
                profit_growth=135.4,
                revenue_growth=56.2,
            ),
            PerformanceRow(
                symbol="002083",
                name="孚日股份",
                report_date="2026-09-30",
                profit_growth=135.1,
                revenue_growth=23.8,
            ),
            PerformanceRow(
                symbol="002353",
                name="杰瑞股份",
                report_date="2026-09-30",
                profit_growth=500.0,
                revenue_growth=20.0,
            ),
            PerformanceRow(
                symbol="301118",
                name="恒光股份",
                report_date="2026-09-30",
                profit_growth=4845.1,
                revenue_growth=30.0,
            ),
            PerformanceRow(
                symbol="688779",
                name="五矿新能",
                report_date="2026-09-30",
                profit_growth=2396.7,
                revenue_growth=40.0,
            ),
            PerformanceRow(
                symbol="600001",
                name="ST测试",
                report_date="2026-09-30",
                profit_growth=300.0,
                revenue_growth=50.0,
            ),
            PerformanceRow(
                symbol="830799",
                name="北交所测试",
                report_date="2026-09-30",
                profit_growth=200.0,
                revenue_growth=20.0,
            ),
        ]


async def test_small_cap_screen(monkeypatch):
    async def fake_fetch_quotes(_symbols):
        return {
            "600798": make_quote("600798", 3.29, 52_436_307, 40e8),
            "002083": make_quote("002083", 9.28, 45_240_099, 60e8),
            "002353": make_quote("002353", 91.0, 66_488_017, 30e8),
        }

    monkeypatch.setattr(screener_service, "fetch_quotes", fake_fetch_quotes)

    response = await screener_service.screen_small_cap(
        SmallCapRequest(
            top_n=5,
            max_market_cap=50,
            min_profit_growth=100,
            min_revenue_growth=10,
        ),
        provider=FakeSmallCapProvider(),
    )

    assert response.scanned_count == 7
    assert response.candidate_count == 2
    assert [item.symbol for item in response.items] == ["002353", "600798"]
    assert response.items[0].total_market_cap == 30e8
    assert response.items[0].profit_growth == 500.0
    assert response.filters["report_date"] == "2026-09-30"


async def test_small_cap_api(monkeypatch):
    user = User(id=uuid.uuid4(), email="smallcap@example.com", nickname="SmallCap")

    async def fake_screen(_request):
        return SmallCapResponse(
            items=[],
            scanned_count=0,
            candidate_count=0,
            fetched_at=datetime.now(),
            filters={},
        )

    monkeypatch.setattr("app.api.v1.screener.screen_small_cap", fake_screen)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post("/api/v1/screener/small-cap", json={"top_n": 5})
            assert response.status_code == 200, response.text
            assert response.json()["strategy"] == "small_cap"
    finally:
        app.dependency_overrides.clear()


ANALYSIS_ITEMS = [
    FundFlowRankItem(
        symbol="002463",
        name="沪电股份",
        price=114.97,
        change_pct=3.57,
        main_net=2_000_000_000,
        main_net_pct=17.5,
        amount=1_000_000_000,
    ),
    FundFlowRankItem(
        symbol="601899",
        name="紫金矿业",
        price=28.87,
        change_pct=-0.65,
        main_net=1_500_000_000,
        main_net_pct=18.4,
        amount=2_000_000_000,
    ),
    FundFlowRankItem(
        symbol="600798",
        name="宁波海运",
        price=3.29,
        change_pct=1.0,
        main_net=1_000_000_000,
        main_net_pct=10.0,
        amount=50_000_000,
    ),
]


class FakeAnalysisLLM:
    def __init__(self, final_payload: dict) -> None:
        self.final_payload = final_payload
        self.text_calls: list[tuple[str, str]] = []
        self.json_calls: list[tuple[str, str]] = []

    async def generate_text(
        self,
        system: str,
        user: str,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ):
        self.text_calls.append((system, user))
        return f"分析报告 {len(self.text_calls)}"

    async def generate_json(
        self,
        system: str,
        user: str,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> dict:
        self.json_calls.append((system, user))
        return self.final_payload


class FakeAnalysisPerformanceProvider:
    async def fetch_latest_by_codes(self, codes: list[str]):
        return {
            code: PerformanceRow(
                symbol=code,
                name="",
                report_date="2026-09-30",
                profit_growth=100.0,
                revenue_growth=20.0,
                industry="测试行业",
            )
            for code in codes
        }


async def test_main_force_analysis(monkeypatch):
    async def fake_load(_redis):
        return ANALYSIS_ITEMS

    async def fake_quotes(symbols):
        return {
            "002463": make_quote("002463", 114.97, 1_000_000_000, 80e8),
            "601899": make_quote("601899", 28.87, 2_000_000_000, 50e8),
            "600798": make_quote("600798", 3.29, 50_000_000, 40e8),
        }

    monkeypatch.setattr(
        main_force_analysis_service, "load_fund_flow_rank", fake_load
    )
    monkeypatch.setattr(main_force_analysis_service, "fetch_quotes", fake_quotes)

    llm = FakeAnalysisLLM(
        {
            "recommendations": [
                {
                    "rank": 1,
                    "symbol": "002463",
                    "name": "错误名称",
                    "reasons": ["资金面强", "行业景气", "基本面稳健"],
                    "highlights": "主力资金持续流入",
                    "risks": "注意板块波动",
                    "position": "20-30%",
                    "investment_period": "中期",
                },
                {
                    "rank": 2,
                    "symbol": "999999",
                    "name": "模型编造",
                    "reasons": [],
                },
            ]
        }
    )
    redis = FakeRedis()
    phases: list[str] = []

    async def on_phase(phase: str) -> None:
        phases.append(phase)

    response = await main_force_analysis_service.analyze_main_force(
        redis,
        uuid.uuid4(),
        5,
        MainForceAnalysisRequest(top_n=10, final_n=3, max_change_pct=7),
        llm_client=llm,
        performance_provider=FakeAnalysisPerformanceProvider(),
        on_phase=on_phase,
    )

    assert phases == [
        "获取主力资金排行",
        "补充行情与业绩数据",
        "三位分析师整体分析中",
        "资深研究员精选中",
    ]

    assert response.analyzed_count == 3
    assert len(response.recommendations) == 1
    assert response.recommendations[0].symbol == "002463"
    assert response.recommendations[0].name == "沪电股份"
    assert response.recommendations[0].rank == 1
    assert len(llm.text_calls) == 3
    assert response.quota_used == 1
    assert "测试行业" in llm.text_calls[0][1]


def test_normalize_recommendations_does_not_pad_with_rule_picks():
    rows = [
        {"symbol": "002463", "name": "沪电股份"},
        {"symbol": "601899", "name": "紫金矿业"},
        {"symbol": "600798", "name": "宁波海运"},
    ]
    recommendations = main_force_analysis_service.normalize_recommendations(
        {"recommendations": [{"symbol": "002463", "reasons": ["资金面强"]}]},
        rows,
        3,
    )

    assert [item.symbol for item in recommendations] == ["002463"]


async def test_main_force_analysis_empty(monkeypatch):
    async def fake_load(_redis):
        return []

    monkeypatch.setattr(
        main_force_analysis_service, "load_fund_flow_rank", fake_load
    )

    with pytest.raises(main_force_analysis_service.MainForceEmptyError):
        await main_force_analysis_service.analyze_main_force(
            FakeRedis(),
            uuid.uuid4(),
            5,
            MainForceAnalysisRequest(top_n=10, final_n=3),
            llm_client=FakeAnalysisLLM({"recommendations": []}),
            performance_provider=FakeAnalysisPerformanceProvider(),
        )


async def test_main_force_analysis_api(monkeypatch):
    user = User(id=uuid.uuid4(), email="mfai@example.com", nickname="MF-AI")
    record_id = uuid.uuid4()

    async def fake_analyze(_redis, _user_id, _quota, _request):
        return MainForceAnalysisResponse(
            fund_flow="资金面报告",
            industry="行业报告",
            fundamental="基本面报告",
            recommendations=[
                MainForceRecommendation(
                    rank=1,
                    symbol="002463",
                    name="沪电股份",
                    reasons=["资金面强"],
                )
            ],
            generated_at=datetime.now(),
            model="test-model",
        )

    async def fake_save(_user_id, _strategy, _filters, _response):
        return record_id

    monkeypatch.setattr("app.api.v1.screener.analyze_main_force", fake_analyze)
    monkeypatch.setattr("app.api.v1.screener.save_screener_record", fake_save)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/v1/screener/main-force/analysis",
                json={"top_n": 10, "final_n": 3},
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["fund_flow"] == "资金面报告"
            assert body["recommendations"][0]["symbol"] == "002463"
            assert body["record_id"] == str(record_id)
    finally:
        app.dependency_overrides.clear()


class FlakyFinalLLM:
    def __init__(self, failures: int = 1) -> None:
        self.failures = failures
        self.calls = 0

    async def generate_json(self, *_args, **_kwargs) -> dict:
        self.calls += 1
        if self.calls <= self.failures:
            raise LLMRequestError("mock timeout")
        return {"recommendations": [{"symbol": "002463", "rank": 1}]}


async def test_final_selection_retries_once(monkeypatch):
    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(main_force_analysis_service.asyncio, "sleep", no_sleep)
    llm = FlakyFinalLLM()

    data = await main_force_analysis_service._generate_final(llm, "prompt")

    assert llm.calls == 2
    assert data["recommendations"][0]["symbol"] == "002463"


async def test_final_selection_stops_after_retry(monkeypatch):
    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(main_force_analysis_service.asyncio, "sleep", no_sleep)
    llm = FlakyFinalLLM(failures=2)

    with pytest.raises(LLMRequestError):
        await main_force_analysis_service._generate_final(llm, "prompt")

    assert llm.calls == 2


async def test_final_selection_retries_on_invalid_json(monkeypatch):
    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(main_force_analysis_service.asyncio, "sleep", no_sleep)

    class FlakyJsonLLM:
        def __init__(self) -> None:
            self.calls = 0

        async def generate_json(self, *_args, **_kwargs) -> dict:
            self.calls += 1
            if self.calls == 1:
                raise LLMResponseError("bad json")
            return {"recommendations": [{"symbol": "002463", "rank": 1}]}

    llm = FlakyJsonLLM()
    data = await main_force_analysis_service._generate_final(llm, "prompt")

    assert llm.calls == 2
    assert data["recommendations"][0]["symbol"] == "002463"


def make_growth_performance(symbol: str, name: str) -> PerformanceRow:
    return PerformanceRow(
        symbol=symbol,
        name=name,
        report_date="2026-09-30",
        profit_growth=150.0,
        revenue_growth=20.0,
        industry="电子",
    )


async def test_analyze_low_price_bull(monkeypatch):
    item = LowPriceBullItem(
        symbol="002463",
        name="沪电股份",
        price=9.5,
        change_pct=1.0,
        amount=50_000_000,
        profit_growth=150.0,
        revenue_growth=20.0,
        report_date="2026-09-30",
    )
    candidates = LowPriceCandidateSet(
        items=[item],
        quotes={"002463": make_quote("002463", 9.5, 50_000_000, 80e8)},
        performance={"002463": make_growth_performance("002463", "沪电股份")},
        report_date="2026-09-30",
        scanned_count=10,
        candidate_count=1,
    )

    async def fake_collect(*_args, **_kwargs):
        return candidates

    monkeypatch.setattr(
        main_force_analysis_service, "collect_low_price_candidates", fake_collect
    )
    llm = FakeAnalysisLLM(
        {
            "recommendations": [
                {
                    "rank": 1,
                    "symbol": "002463",
                    "name": "错误名称",
                    "reasons": ["资金与流动性匹配"],
                    "highlights": "低估高增",
                    "risks": "流动性风险",
                    "position": "10-20%",
                    "investment_period": "中期",
                }
            ]
        }
    )
    phases: list[str] = []

    async def on_phase(phase: str) -> None:
        phases.append(phase)

    response = await main_force_analysis_service.analyze_low_price_bull(
        FakeRedis(),
        uuid.uuid4(),
        5,
        LowPriceBullAnalysisRequest(final_n=3),
        llm_client=llm,
        on_phase=on_phase,
    )

    assert response.strategy == "low_price_bull"
    assert response.analyzed_count == 1
    assert response.recommendations[0].symbol == "002463"
    assert response.recommendations[0].name == "沪电股份"
    assert phases == [
        "读取最新业绩报表与行情",
        "三位分析师整体分析中",
        "资深研究员精选中",
    ]


async def test_analyze_small_cap(monkeypatch):
    item = SmallCapItem(
        symbol="002463",
        name="沪电股份",
        price=9.5,
        change_pct=1.0,
        total_market_cap=40e8,
        profit_growth=150.0,
        revenue_growth=20.0,
        report_date="2026-09-30",
    )
    candidates = SmallCapCandidateSet(
        items=[item],
        quotes={"002463": make_quote("002463", 9.5, 50_000_000, 40e8)},
        performance={"002463": make_growth_performance("002463", "沪电股份")},
        report_date="2026-09-30",
        scanned_count=10,
        candidate_count=1,
    )

    async def fake_collect(*_args, **_kwargs):
        return candidates

    monkeypatch.setattr(
        main_force_analysis_service, "collect_small_cap_candidates", fake_collect
    )
    llm = FakeAnalysisLLM(
        {
            "recommendations": [
                {
                    "rank": 1,
                    "symbol": "002463",
                    "reasons": ["小市值高成长"],
                }
            ]
        }
    )

    response = await main_force_analysis_service.analyze_small_cap(
        FakeRedis(),
        uuid.uuid4(),
        5,
        SmallCapAnalysisRequest(final_n=3),
        llm_client=llm,
    )

    assert response.strategy == "small_cap"
    assert response.recommendations[0].symbol == "002463"
    assert response.recommendations[0].name == "沪电股份"


async def test_collect_profit_growth_candidates(monkeypatch):
    async def fake_fetch_quotes(_symbols):
        return {
            "600798": make_quote("600798", 3.29, 52_436_307),
            "002148": make_quote("002148", 6.27, 59_388_524),
        }

    monkeypatch.setattr(screener_service, "fetch_quotes", fake_fetch_quotes)

    candidates = await screener_service.collect_profit_growth_candidates(
        ProfitGrowthAnalysisRequest(final_n=3, min_profit_growth=10),
        provider=FakePerformanceProvider(),
        limit=40,
    )

    assert candidates.scanned_count == 6
    assert candidates.candidate_count == 2
    assert [item.symbol for item in candidates.items] == ["600798", "002148"]
    assert candidates.items[0].profit_growth == 135.4


async def test_analyze_profit_growth(monkeypatch):
    item = ProfitGrowthItem(
        symbol="600798",
        name="宁波海运",
        price=3.29,
        change_pct=1.0,
        amount=52_436_307,
        profit_growth=135.4,
        revenue_growth=56.2,
        report_date="2026-09-30",
    )
    candidates = ProfitGrowthCandidateSet(
        items=[item],
        quotes={"600798": make_quote("600798", 3.29, 52_436_307, 40e8)},
        performance={"600798": make_growth_performance("600798", "宁波海运")},
        report_date="2026-09-30",
        scanned_count=6,
        candidate_count=1,
    )

    async def fake_collect(*_args, **_kwargs):
        return candidates

    monkeypatch.setattr(
        main_force_analysis_service, "collect_profit_growth_candidates", fake_collect
    )
    llm = FakeAnalysisLLM(
        {
            "recommendations": [
                {
                    "rank": 1,
                    "symbol": "600798",
                    "reasons": ["净利增长质量较好"],
                }
            ]
        }
    )
    phases: list[str] = []

    async def on_phase(phase: str) -> None:
        phases.append(phase)

    response = await main_force_analysis_service.analyze_profit_growth(
        FakeRedis(),
        uuid.uuid4(),
        5,
        ProfitGrowthAnalysisRequest(final_n=3, min_profit_growth=10),
        llm_client=llm,
        on_phase=on_phase,
    )

    assert response.strategy == "profit_growth"
    assert response.recommendations[0].symbol == "600798"
    assert response.recommendations[0].name == "宁波海运"
    assert phases == [
        "读取最新业绩报表与行情",
        "三位分析师整体分析中",
        "资深研究员精选中",
    ]
