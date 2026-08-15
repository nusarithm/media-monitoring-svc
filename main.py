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
from app.core.config import settings
import traceback


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open the PostgreSQL pool on startup, close it on shutdown."""
    await init_pool()
    yield
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
