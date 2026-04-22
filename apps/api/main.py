import os
from pathlib import Path
import httpx
import uvicorn
from fastapi import FastAPI
from sqlalchemy import text
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Route

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
from app.mcp import create_retrieval_mcp_server
from app.services.local_dev import LocalDevelopmentBootstrapService
from app.services.rate_limit.rule_loader import load_rules


async def _ensure_local_development_prerequisites() -> None:
    """Make local-only auth prerequisites exist before migrations run."""
    if settings.ENVIRONMENT != "development":
        return

    service = LocalDevelopmentBootstrapService()
    await service.ensure_user_table_exists()
    logger.info("local development user table is ready")


async def _seed_local_development_identity() -> None:
    """Create or refresh the deterministic local developer account."""
    if settings.ENVIRONMENT != "development":
        return

    from shared.core.database import AsyncSessionFactory

    service = LocalDevelopmentBootstrapService()
    async with AsyncSessionFactory() as session:
        await service.seed_local_developer(session)
        await session.commit()

    logger.info(
        "local development seed is ready: user_id={}",
        LocalDevelopmentBootstrapService.LOCAL_DEV_USER_ID,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle management
    """
    # Run database migrations
    import subprocess
    import sys
    
    try:
        await _ensure_local_development_prerequisites()
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

    await _seed_local_development_identity()
    
    await redis_pool_manager.init_pool()
    logger.info("Redis connection pool created.")

    ImageCli.http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    # Initialize rate limiter rules from DB.
    # Changes now require a pod restart to take effect.
    from app.services.rate_limit.config import RateLimitConfig
    from shared.core.database import AsyncSessionFactory

    redis_url = redis_pool_manager.config.get_connection_url()
    RateLimitConfig.get_instance(redis_url)
    async with AsyncSessionFactory() as session:
        await load_rules(session)
    logger.info("rate limit rules loaded at startup; restart the pod to apply changes")

    mcp_server = getattr(app.state, "retrieval_mcp_server", None)
    mcp_session_manager = getattr(mcp_server, "session_manager", None)

    logger.info("knowledge library API service started!")
    if mcp_session_manager is not None:
        async with mcp_session_manager.run():
            yield
    else:
        yield

    try:
        from shared.utils.http_clients import close_async_client
        await close_async_client()
    except Exception as e:
        logger.error(f"async HTTP client close failed: {e}")

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
            logfire.instrument_fastapi(app, excluded_urls="/$,/health,/api/health,/database/*")
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

    retrieval_mcp_server = create_retrieval_mcp_server(
        streamable_http_path="/mcp",
    )
    retrieval_mcp_app = retrieval_mcp_server.streamable_http_app()
    app.state.retrieval_mcp_server = retrieval_mcp_server
    for route in retrieval_mcp_app.routes:
        if isinstance(route, Route) and route.path == "/mcp":
            app.router.routes.append(route)
            break
    else:  # pragma: no cover - guards against upstream FastMCP route changes
        raise RuntimeError(
            "FastMCP streamable HTTP app did not expose the expected /mcp route"
        )

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
