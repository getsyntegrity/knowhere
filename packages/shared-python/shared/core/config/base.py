"""Base application configuration."""

import os

from loguru import logger
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseConfig(BaseSettings):
    """Base application configuration."""

    # Environment configuration.
    ENVIRONMENT: str = Field(default="production", description="Runtime environment")
    APP_ENV: str = Field(
        default="",
        description="Deploy environment (<empty>|development|staging|production)",
    )
    DEBUG: bool = Field(default=False, description="Debug mode")
    LOG_LEVEL: str = Field(default="INFO", description="Log level")

    # Application metadata.
    APP_TITLE: str = Field(default="Knowhere API", description="Application title")
    APP_VERSION: str = Field(
        default_factory=lambda: os.getenv("APP_VERSION", "1.0.0"),
        description="Application version read from the APP_VERSION environment variable",
    )
    APP_DESCRIPTION: str = Field(
        default="AI-powered document parsing, retrieval, and knowledge access backend",
        description="Application description",
    )

    # Logging configuration
    LOGFIRE_TOKEN: str = Field(
        default="", description="Logfire API token for distributed tracing"
    )

    # Security configuration.
    SECRET_KEY: str = Field(..., description="JWT secret key")
    ALGORITHM: str = Field(default="HS256", description="JWT signing algorithm")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=10080, description="Access-token expiration in minutes"
    )
    WEBHOOK_MASTER_KEY: str = Field(
        default="", description="Webhook encryption master key"
    )
    INTERNAL_DASHBOARD_ENDPOINT: str = Field(
        default="http://localhost:3000", description="Internal Dashboard endpoint"
    )

    # Local path configuration.
    TMP_PATH: str = Field(..., description="Temporary-file path")
    FONT_PATH: str = Field(..., description="Font-file path")
    CHROMEDRIVER_PATH: str = Field(..., description="ChromeDriver path")

    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v):
        """Validate the runtime environment."""
        if v not in ["development", "staging", "production"]:
            raise ValueError("ENVIRONMENT must be development, staging, or production")
        return v

    @field_validator("APP_ENV")
    @classmethod
    def validate_app_env(cls, v):
        app_env = v.strip().lower()
        if app_env and app_env not in ["development", "staging", "production"]:
            raise ValueError("APP_ENV must be empty, staging, or production")
        return app_env

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v):
        """Validate the log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}")
        return v.upper()

    def validate_file_paths(self) -> bool:
        """Validate required local file paths."""
        paths_to_check = {
            "TMP_PATH": self.TMP_PATH,
            "FONT_PATH": self.FONT_PATH,
            "CHROMEDRIVER_PATH": self.CHROMEDRIVER_PATH,
        }

        for name, path in paths_to_check.items():
            if not os.path.exists(path):
                logger.warning(f"Path does not exist: {name} = {path}")
                return False

        logger.info("File-path validation succeeded")
        return True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore unrelated environment variables.
    )
