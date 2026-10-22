"""东方财富个股公告与新闻 Provider。

两个数据源均免密钥：
1. 公告：np-anotice-stock.eastmoney.com，按股票代码查询
2. 新闻：search-api-web.eastmoney.com JSONP，按股票名称检索

Provider 只做取数与解析；缓存和降级由 company_news_service 统一处理。
"""

import html
import json
import re

from app.providers.base import DataNotFound, ProviderSchemaDrift
from app.providers.http import fetch, provider_slot
from app.providers.symbols import parse_symbol
from app.schemas.news import NewsItem

_TAG_RE = re.compile(r"</?em>", re.IGNORECASE)


def _clean(value: object) -> str:
    text = _TAG_RE.sub("", str(value or ""))
    return html.unescape(text).strip()


def _dedupe(items: list[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    result: list[NewsItem] = []
    for item in items:
        key = item.url or item.title
        if not item.title or not item.url or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


class EastmoneyAnnouncementProvider:
    name = "eastmoney_announcement"
    URL = "https://np-anotice-stock.eastmoney.com/api/security/ann"
    _HEADERS = {"Referer": "https://data.eastmoney.com/"}

    async def fetch(self, symbol: str, limit: int = 20) -> list[NewsItem]:
        parsed = parse_symbol(symbol)
        params = {
            "sr": -1,
            "page_size": max(1, min(limit, 50)),
            "page_index": 1,
            "ann_type": "A",
            "client_source": "web",
            "stock_list": parsed.code,
            "f_node": 0,
            "s_node": 0,
        }
        async with provider_slot():
            response = await fetch(self.URL, params=params, headers=self._HEADERS)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderSchemaDrift("东财公告返回非 JSON") from exc

        items = self.parse(payload, parsed.code)
        if not items:
            raise DataNotFound(f"东财无 {parsed.code} 公告数据")
        return items

    @staticmethod
    def parse(payload: object, code: str) -> list[NewsItem]:
        if not isinstance(payload, dict):
            return []
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        rows = data.get("list") or []
        if not isinstance(rows, list):
            return []

        items: list[NewsItem] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            art_code = _clean(row.get("art_code"))
            title = _clean(row.get("title") or row.get("title_ch"))
            if not art_code or not title:
                continue
            columns = row.get("columns") or []
            category = ""
            if isinstance(columns, list) and columns:
                first = columns[0]
                if isinstance(first, dict):
                    category = _clean(first.get("column_name"))
            published = _clean(row.get("notice_date") or row.get("display_time"))
            items.append(
                NewsItem(
                    id=art_code,
                    kind="announcement",
                    title=title,
                    summary=category,
                    url=(
                        "https://data.eastmoney.com/notices/detail/"
                        f"{code}/{art_code}.html"
                    ),
                    source="东方财富·公告",
                    published_at=published[:19],
                )
            )
        return _dedupe(items)


class EastmoneyNewsSearchProvider:
    name = "eastmoney_news"
    URL = "https://search-api-web.eastmoney.com/search/jsonp"
    _HEADERS = {"Referer": "https://so.eastmoney.com/"}
    _CALLBACK = "cb"

    async def fetch(self, symbol: str, name: str = "", limit: int = 20) -> list[NewsItem]:
        parsed = parse_symbol(symbol)
        keyword = name.strip() or parsed.code
        param = {
            "uid": "",
            "keyword": keyword,
            "type": ["cmsArticleWebOld"],
            "client": "web",
            "clientType": "web",
            "clientVersion": "curr",
            "param": {
                "cmsArticleWebOld": {
                    "searchScope": "default",
                    "sort": "default",
                    "pageIndex": 1,
                    "pageSize": max(1, min(limit, 50)),
                    "preTag": "<em>",
                    "postTag": "</em>",
                }
            },
        }
        params = {
            "cb": self._CALLBACK,
            "param": json.dumps(param, ensure_ascii=False),
        }
        async with provider_slot():
            response = await fetch(self.URL, params=params, headers=self._HEADERS)

        items = self.parse(response.text)
        if not items:
            raise DataNotFound(f"东财无 {parsed.code} 新闻数据")
        return items

    @classmethod
    def parse(cls, text: str) -> list[NewsItem]:
        payload = cls._strip_callback(text)
        if not isinstance(payload, dict):
            return []
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        rows = result.get("cmsArticleWebOld") or []
        if not isinstance(rows, list):
            return []

        items: list[NewsItem] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = _clean(row.get("title"))
            url = _clean(row.get("url"))
            if not title or not url:
                continue
            items.append(
                NewsItem(
                    id=_clean(row.get("code")) or url,
                    kind="article",
                    title=title,
                    summary=_clean(row.get("content"))[:200],
                    url=url,
                    source=_clean(row.get("mediaName")) or "东方财富·资讯",
                    published_at=_clean(row.get("date"))[:19],
                )
            )
        return _dedupe(items)

    @classmethod
    def _strip_callback(cls, text: str) -> object:
        body = (text or "").strip()
        start = body.find("(")
        end = body.rfind(")")
        if start >= 0 and end > start:
            body = body[start + 1 : end]
        try:
            return json.loads(body)
        except ValueError:
            return None
