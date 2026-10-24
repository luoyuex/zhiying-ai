from fastapi import APIRouter, Depends

from app.api.v1.admin import audit, automation, content, costs, jobs, overview, users
from app.core.deps import require_admin

router = APIRouter(
    prefix="/admin",
    tags=["后台管理"],
    dependencies=[Depends(require_admin)],
)
router.include_router(overview.router)
router.include_router(users.router)
router.include_router(costs.router)
router.include_router(jobs.router)
router.include_router(automation.router)
router.include_router(content.router)
router.include_router(audit.router)
