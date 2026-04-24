"""
Version information API endpoints.
"""

import os
from datetime import datetime

from fastapi import APIRouter

from shared.core.config import app_config

router = APIRouter()


@router.get("/version", summary="Get application version information")
async def get_version():
    """
    Return version information for the current deployment.

    Response shape:
    {
        "version": "v1.0.0",
        "commit": "abc1234",
        "build_time": "2024-01-01T00:00:00Z",
        "environment": "production"
    }
    """
    # Read version metadata from the environment when available.
    version = os.getenv("APP_VERSION", app_config.APP_VERSION)
    commit = os.getenv("GIT_COMMIT", "")
    build_time = os.getenv("BUILD_TIME", "")
    environment = os.getenv("ENVIRONMENT", "development")

    return {
        "version": version,
        "commit": commit,
        "build_time": build_time,
        "environment": environment,
        "service": "knowhere-api",
    }


@router.get("/", summary="Root version information")
async def root_version():
    """Return version information from the root path."""
    return await get_version()
