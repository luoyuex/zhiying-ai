from fastapi import APIRouter

from app.api.v1 import admin, ai, auth, automation, reports, screener, stocks, watchlist

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(admin.router)
api_router.include_router(auth.router)
api_router.include_router(stocks.router)
api_router.include_router(screener.router)
api_router.include_router(watchlist.router)
api_router.include_router(ai.router)
api_router.include_router(reports.router)
api_router.include_router(automation.router)
