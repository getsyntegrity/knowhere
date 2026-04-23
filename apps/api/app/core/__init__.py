"""Unified imports for API core modules.

Configuration, Redis management, and other shared functionality should be
imported from the shared package.
"""

# Import shared infrastructure from the shared package.
from shared.core.config import app_config, redis_config_manager, redis_pool_manager
from shared.core.constants import (APIConstants, BusinessConstants,
                                   ProcessingConstants, SystemConstants)
from shared.core.database import get_db
from shared.core.logging import setup_logging
from shared.core.security import get_password_hash, verify_password

# Response helpers remain API-specific.
from .response import ResponseCode

# Backward-compatible alias.
settings = app_config

__all__ = [
    # Configuration
    "app_config",
    "settings",  # Backward-compatible alias

    # Redis
    "redis_config_manager",
    "redis_pool_manager",

    # Database
    "get_db",

    # Security
    "get_password_hash",
    "verify_password",

    # Response handling
    "ResponseCode",

    # Constants
    "SystemConstants",
    "BusinessConstants",
    "APIConstants",
    "ProcessingConstants",

    # Logging
    "setup_logging",
]
