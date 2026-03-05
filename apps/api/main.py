import asyncio
import os
from pathlib import Path
import httpx
import uvicorn
from fastapi import FastAPI
from sqlalchemy import text
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

# Import custom OpenAPI function
from custom_openapi import custom_openapi

# Import from shared packages
from shared.core.config import redis_pool_manager, settings
from shared.core.database import engine, Base, safe_dispose_engine
from shared.core.logging import setup_logging

# Import from local API project
from loguru import logger
from contextlib import asynccontextmanager
from app.api.api_router import api_router
from app.core.middleware import setup_cors, LoggingMiddleware
from app.core.image_cli import ImageCli
from app.middleware.moesif_middleware import MoesifMiddleware
from app.core.exception_handlers import setup_exception_handlers
from app.services.rate_limit.rule_loader import load_rules

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle management
    """
    # Run database migrations
    import subprocess
    import sys
    
    try:
        logger.info("start running database migration...")
        result = subprocess.run([
            sys.executable, "-m", "alembic", "upgrade", "heads"
        ], cwd=str(Path(__file__).parent), capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("database migration completed")
        else:
            logger.error(f"database migration failed: {result.stderr}")
            raise Exception(f"database migration failed: {result.stderr}")
    except Exception as e:
        logger.error(f"running database migration failed: {e}")
        raise

    from shared.core.database import prewarm_connection_pool
    await prewarm_connection_pool()
    logger.info("database connection pool warmed up.")
    
    await redis_pool_manager.init_pool()
    logger.info("Redis connection pool created.")

    ImageCli.http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    # Initialize rate limiter rules from DB and start Pub/Sub listener.
    # Fail fast on init errors so we don't serve with partially enforced limits.
    from app.services.rate_limit.config import RateLimitConfig
    from shared.core.database import AsyncSessionFactory

    redis_url = redis_pool_manager.config.get_connection_url()
    RateLimitConfig.get_instance(redis_url)
    async with AsyncSessionFactory() as session:
        await load_rules(session)

    async def _rate_limit_rule_sync_loop():
        sync_interval = 60
        while True:
            try:
                await asyncio.sleep(sync_interval)
                async with AsyncSessionFactory() as session:
                    await load_rules(session)
                logger.debug("rate limit rules periodic DB sync finished")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"rate limit rules periodic DB sync failed: {e}")

    app.state.rate_limit_rule_sync_task = asyncio.create_task(
        _rate_limit_rule_sync_loop(),
        name="rate_limit_rule_sync",
    )

    try:
        from app.services.messaging_service import messaging_service
        await messaging_service.start()
    except Exception as e:
        logger.error(f"message consumer start failed: {e}")
    
    logger.info("knowledge library API service started!")
    yield

    # Stop rate limiter sync task
    if hasattr(app.state, "rate_limit_rule_sync_task"):
        app.state.rate_limit_rule_sync_task.cancel()
        try:
            await app.state.rate_limit_rule_sync_task
        except asyncio.CancelledError:
            pass

    try:
        from app.services.messaging_service import messaging_service
        await messaging_service.stop()
    except Exception as e:
        logger.error(f"message consumer stop failed: {e}")
    
    logger.info("knowledge library API service stopped!")
    await safe_dispose_engine(engine)
    logger.info("database engine connection pool disposed.")
    logger.info("service stopped.")

def create_app() -> FastAPI:
    # Setup structured logging BEFORE creating FastAPI app
    # This ensures all logs (including lifespan) use structured format
    # Note: We pass app=None initially, then instrument FastAPI after app creation
    setup_logging(service_name="knowhere-api")

    app = FastAPI(
        title=settings.APP_TITLE,
        version=settings.APP_VERSION,
        description=settings.APP_DESCRIPTION,
        lifespan=lifespan,  # Bind lifecycle manager
        docs_url="/docs",
        openapi_version="3.1.0",
        root_path="/api"
    )

    # Now instrument FastAPI with Logfire (if enabled)
    from shared.core.config import settings as config_settings
    if config_settings.LOGFIRE_TOKEN:
        try:
            import logfire
            logfire.instrument_fastapi(app)
        except ImportError:
            pass

    # Setup middleware
    setup_cors(app)
    app.add_middleware(LoggingMiddleware)

    # Moesif API monitoring middleware — disabled (broken SDK client, adds latency + log noise)
    # app.add_middleware(MoesifMiddleware)

    # Add API Key authentication middleware
    # app.add_middleware(api_key_auth_middleware)

    @app.get("/", tags=["Root"])
    async def read_root():
        return {"message": f"Welcome to {app.title} - Knowledge Base API Service!"}

    @app.api_route("/health", methods=["GET", "HEAD"], tags=["Health"])
    async def health_check():
        """Simple health check endpoint, supports GET and HEAD methods"""
        version = os.getenv("APP_VERSION", settings.APP_VERSION)
        return {
            "status": "healthy",
            "service": "knowhere-api",
            "version": version
        }
    
    # Register other API routes
    app.include_router(api_router)

    # Setup global exception handlers
    setup_exception_handlers(app)
    
    # Set up custom OpenAPI schema (flattens $ref references)
    app.openapi = lambda: custom_openapi(app)
    
    return app

# Worker settings removed as DsTasks.py was deleted
app = create_app()

if __name__ == "__main__":
    logger.info("Knowledge Base API service starting...")
    port = 5005
    reload = False  # Enable hot reload
    host = "0.0.0.0"
    uvicorn.run(app, host=host, port=port, reload=reload, log_level="debug")
