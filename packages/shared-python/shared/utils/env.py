from shared.core.config import settings

def is_development() -> bool:
    return settings.ENVIRONMENT == "development"
