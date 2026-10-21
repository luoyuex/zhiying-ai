"""股票基础库：拼音生成、全量同步、搜索与接口。"""

import uuid

from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, insert, select

from app.core.deps import get_current_user
from app.db.models.stock import Stock
from app.db.models.user import User
from app.db.session import SessionLocal
from app.main import app
from app.providers.models import StockBasic
from app.providers.stock_directory import EastmoneyStockDirectory
from app.services.stock_directory_service import (
    build_pinyin,
    search_stocks,
    sync_stocks,
)

SAMPLE = [
    StockBasic(code="600519", name="贵州茅台", exchange="SH"),
    StockBasic(code="600903", name="贵州燃气", exchange="SH"),
    StockBasic(code="300750", name="宁德时代", exchange="SZ"),
    StockBasic(code="920296", name="N文峰", exchange="BJ"),
]
CODES = [item.code for item in SAMPLE]
_FIELDS = ("code", "name", "exchange", "pinyin", "abbr", "is_active")


async def snapshot() -> list[dict]:
    """测试库可能已有种子数据，先留存，跑完原样写回。"""
    async with SessionLocal() as session:
        rows = (await session.scalars(select(Stock).where(Stock.code.in_(CODES)))).all()
    return [{field: getattr(row, field) for field in _FIELDS} for row in rows]


async def restore(saved: list[dict]) -> None:
    async with SessionLocal() as session:
        await session.execute(delete(Stock).where(Stock.code.in_(CODES)))
        if saved:
            await session.execute(insert(Stock).values(saved))
        await session.commit()


def test_build_pinyin():
    assert build_pinyin("贵州茅台") == ("guizhoumaotai", "gzmt")
    assert build_pinyin("*ST海航") == ("haihang", "hh")
    assert build_pinyin("N文峰") == ("wenfeng", "wf")
    assert build_pinyin("") == ("", "")


def test_directory_normalize():
    items = EastmoneyStockDirectory.normalize(
        [
            {"f12": "600519", "f14": "贵州茅台"},
            {"f12": "300750", "f14": "宁德时代"},
            {"f12": "920296", "f14": "N文峰"},
            {"f12": "600519", "f14": "贵州茅台"},
            {"f12": "XX0001", "f14": "坏数据"},
            {"f12": "000001", "f14": ""},
        ]
    )
    assert [item.code for item in items] == ["600519", "300750", "920296"]
    assert items[2].exchange == "BJ"


async def test_sync_and_search():
    saved = await snapshot()
    try:
        result = await sync_stocks(SAMPLE, deactivate_missing=False)
        assert result["synced"] == len(SAMPLE)

        by_name = await search_stocks("茅台")
        assert by_name[0].code == "600519"
        assert by_name[0].name == "贵州茅台"

        assert (await search_stocks("gzmt"))[0].code == "600519"
        assert {"600519", "600903"} <= {item.code for item in await search_stocks("guizhou")}
        assert (await search_stocks("600519"))[0].code == "600519"
        assert (await search_stocks("宁德"))[0].code == "300750"
        assert await search_stocks("") == []
        assert await search_stocks("  ") == []
        assert await search_stocks("%_") == []
        assert len(await search_stocks("600", limit=1)) == 1
    finally:
        await restore(saved)


async def test_search_api():
    saved = await snapshot()
    user = User(id=uuid.uuid4(), email="search@example.com", nickname="Search")
    await sync_stocks(SAMPLE, deactivate_missing=False)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/v1/stocks/search", params={"q": "gzmt"})
            assert response.status_code == 200, response.text
            body = response.json()
            assert body[0] == {"code": "600519", "name": "贵州茅台", "exchange": "SH"}

            response = await client.get("/api/v1/stocks/search", params={"q": "600519"})
            assert response.status_code == 200
            assert response.json()[0]["code"] == "600519"

            response = await client.get(
                "/api/v1/stocks/search", params={"q": "600", "limit": 2}
            )
            assert response.status_code == 200
            assert len(response.json()) == 2

            response = await client.get("/api/v1/stocks/search", params={"q": ""})
            assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()
        await restore(saved)
