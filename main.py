import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.database import init_pool, close_pool
from app.api.auth import router as auth_router
from app.api.news import router as news_router
from app.api.keywords import router as keywords_router
from app.api.analytics import router as analytics_router
from app.api.analytics_v2 import router as analytics_v2_router
from app.api.settings import router as settings_router
from app.api.subscription import router as subscription_router
from app.api.email import router as email_router
from app.api.payment import router as payment_router, webhook_router
from app.api.reports import router as reports_router
from app.api.topics import router as topics_router
from app.api.entities import router as entities_router
from app.api.alerts import router as alerts_router
from app.core.config import settings
import traceback


async def _alert_loop():
    """Evaluate alert rules on an interval.

    In-process rather than cron: the service runs from a tmux shell with no
    systemd unit, so a crontab entry would be a second piece of state to
    remember. This restarts with the app.

    Single-process assumption: running several uvicorn workers would sweep
    once per worker. The rule cooldown limits the damage to duplicate
    evaluation, not duplicate mail, but move this to a real scheduler before
    scaling out.
    """
    from app.services.alert_service import sweep

    interval = settings.ALERT_SWEEP_MINUTES * 60
    while True:
        await asyncio.sleep(interval)
        try:
            fired = [r for r in await sweep(send_email=True) if r["triggered"] and not r["cooldown"]]
            if fired:
                print(f"[alerts] {len(fired)} rule(s) fired")
        except Exception as e:
            # A failed sweep must not kill the loop - the next one may work.
            print(f"[alerts] sweep failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the PostgreSQL pool on startup, close it on shutdown."""
    await init_pool()

    task = None
    if settings.ALERT_SWEEP_MINUTES > 0:
        task = asyncio.create_task(_alert_loop())
        print(f"[alerts] sweep every {settings.ALERT_SWEEP_MINUTES} min")

    yield

    if task:
        task.cancel()
    await close_pool()


# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="API untuk sistem authentication dengan PostgreSQL",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS middleware - exact origins, since allow_credentials rules out "*"
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    if settings.DEBUG:
        return JSONResponse(
            status_code=500,
            content={
                "detail": str(exc),
                "traceback": traceback.format_exc()
            }
        )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# Health check endpoint
@app.get("/", tags=["Health"])
async def root():
    """Root endpoint - Health check"""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION
    }


# Include routers
app.include_router(auth_router)
app.include_router(news_router)
app.include_router(keywords_router)
app.include_router(analytics_router)
app.include_router(analytics_v2_router)
app.include_router(reports_router)
app.include_router(topics_router)
app.include_router(entities_router)
app.include_router(alerts_router)
app.include_router(settings_router)
app.include_router(subscription_router)
app.include_router(email_router)
app.include_router(payment_router, prefix="/api/payment")
app.include_router(webhook_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8989,
        reload=settings.DEBUG,
        # Runs behind the Cloudflare tunnel, so trust its forwarded headers
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1"
    )
