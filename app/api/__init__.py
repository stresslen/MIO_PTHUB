from fastapi import APIRouter
from app.api.leads import router as leads_router
from app.api.crawl import router as crawl_router
from app.api.sources import router as sources_router
from app.api.export import router as export_router
from app.api.scheduler import router as scheduler_router
from app.api.storage import router as storage_router
from app.api.keywords import router as keywords_router

api_router = APIRouter(prefix="/api")
api_router.include_router(leads_router)
api_router.include_router(crawl_router)
api_router.include_router(sources_router)
api_router.include_router(export_router)
api_router.include_router(scheduler_router)
api_router.include_router(storage_router)
api_router.include_router(keywords_router)

__all__ = ["api_router"]
