from __future__ import annotations

import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import api_router
from app.config import settings, STATIC_DIR
from app.database import init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds essential security headers to every response."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Content Security Policy allowing local assets and safe Google fonts
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self';"
        )
        return response


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="AI Lead Intelligence & Crawler System for B2B/B2G Digital Transformation",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Add Security Headers Middleware
    app.add_middleware(SecurityHeadersMiddleware)

    # Add CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Initialize Database Tables & Start Background Scheduler
    @app.on_event("startup")
    async def on_startup():
        logger.info("Initializing local query cache...")
        init_db()
        from app.database import SessionLocal
        from app.services.google_sheets_service import google_sheets_service
        cache_db = SessionLocal()
        try:
            from app.models.lead import Lead
            local_count = cache_db.query(Lead).count()
            if google_sheets_service.configured or local_count == 0:
                imported = google_sheets_service.hydrate_sqlite(cache_db)
            else:
                imported = 0
            logger.info("Hydrated %s leads from Google Sheets.", imported)
            profile_counts = google_sheets_service.hydrate_profiles_sqlite(cache_db)
            logger.info("Hydrated round-two profiles from Google Sheets: %s", profile_counts)
            try:
                synced = google_sheets_service.sync_sqlite(cache_db)
                logger.info("Synced %s local leads to Google Sheets.", synced)
            except Exception:
                logger.exception("Google Sheets sync failed; continuing with the local cache.")
        finally:
            cache_db.close()
        try:
            from app.services.keyword_service import keyword_service
            keyword_state = keyword_service.bootstrap()
            logger.info(
                "Loaded %s keywords from %s.",
                keyword_state["total"],
                keyword_state["source"],
            )
        except Exception:
            logger.exception(
                "Google Sheets keyword sync failed; keeping the last in-memory keyword cache."
            )
        try:
            from app.services.source_service import source_service
            source_state = source_service.bootstrap()
            logger.info(
                "Loaded %s crawler sources from %s.",
                source_state["total"],
                source_state["source"],
            )
        except Exception:
            logger.exception(
                "Google Sheets source sync failed; keeping the last in-memory source cache."
            )
        logger.info("Starting configurable crawler scheduler...")
        from app.services.scheduler_service import scheduler_service
        scheduler_service.load_persisted_config()
        scheduler_service.start()
        logger.info("System initialized successfully.")

    @app.on_event("shutdown")
    async def on_shutdown():
        logger.info("Stopping automated daily background scheduler...")
        from app.services.scheduler_service import scheduler_service
        scheduler_service.stop()
        from app.services.browser_crawl_service import browser_crawl_service
        await browser_crawl_service.close()

    # Include API Routes
    app.include_router(api_router)

    # Mount Static Files (Frontend Web UI)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/health")
    def health_check():
        from app.services.google_sheets_service import google_sheets_service
        return {
            "status": "healthy",
            "app": settings.app_name,
            "version": settings.app_version,
            "storage": google_sheets_service.status(),
            "search_configured": bool(settings.xah_api_key),
        }

    @app.get("/")
    def serve_frontend():
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        return JSONResponse({
            "message": "AI Lead Intelligence & Crawler Backend Running. Static UI not found.",
            "docs": "/docs",
            "api": "/api/leads",
        })

    return app


app = create_app()
