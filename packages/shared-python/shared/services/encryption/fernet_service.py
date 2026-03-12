"""
Encryption Service - Fernet-based symmetric encryption for secrets.

Uses the cryptography library's Fernet implementation which provides:
- AES-128-CBC encryption
- HMAC-SHA256 for authentication
- Automatic IV/salt handling
"""
import secrets
import threading
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from loguru import logger
from shared.core.config import settings
from shared.core.exceptions.domain_exceptions import (
    SystemSettingInvalidException,
    SystemSettingMissingException
)


class FernetService:
    """
    Service for encrypting and decrypting secrets using Fernet.
    
    The master key is loaded from environment variables and used to
    create a Fernet instance for all encryption operations.
    """
    
    def __init__(self, master_key: str):
        """
        Initialize FernetService with a master key.
        
        Args:
            master_key: URL-safe base64-encoded 32-byte key.
                       Generate with: Fernet.generate_key().decode()
        
        Raises:
            SystemSettingMissingException: If master_key is empty.
            SystemSettingInvalidException: If master_key is invalid.
        """
        if not master_key:
            raise SystemSettingMissingException(internal_message="WEBHOOK_MASTER_KEY is required for encryption")
        
        try:
            self._fernet = Fernet(master_key.encode())
        except Exception as error:
            logger.error(f"Invalid master key format: {error}")
            raise SystemSettingInvalidException(
                internal_message=f"WEBHOOK_MASTER_KEY must be a valid Fernet key. Error: {error}"
            ) from error
    
    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a plaintext string.
        
        Args:
            plaintext: The string to encrypt.
            
        Returns:
            URL-safe base64-encoded ciphertext.
        """
        token = self._fernet.encrypt(plaintext.encode())
        return token.decode()
    
    def decrypt(self, ciphertext: str) -> Optional[str]:
        """
        Decrypt a ciphertext string.
        
        Args:
            ciphertext: URL-safe base64-encoded ciphertext.
            
        Returns:
            Decrypted plaintext, or None if decryption fails.
        """
        try:
            plaintext = self._fernet.decrypt(ciphertext.encode())
            return plaintext.decode()
        except InvalidToken:
            logger.warning("Failed to decrypt: Invalid token or wrong key")
            return None
        except Exception as error:
            logger.error(f"Decryption error: {error}")
            return None
    
    @staticmethod
    def generate_webhook_secret() -> str:
        """
        Generate a new webhook secret with 'whsec_' prefix.
        
        Returns:
            A new secret in format 'whsec_<64 hex chars>'.
        """
        return f"whsec_{secrets.token_hex(32)}"
    
    @staticmethod
    def generate_master_key() -> str:
        """
        Generate a new Fernet master key for configuration.
        
        Returns:
            URL-safe base64-encoded 32-byte key.
        """
        return Fernet.generate_key().decode()


# Singleton instance (lazy loaded)
_fernet_service: Optional[FernetService] = None
_fernet_service_lock = threading.Lock()


def get_fernet_service() -> FernetService:
    """
    Get the singleton FernetService instance.

    Loads the master key from environment on first call.

    Returns:
        FernetService instance.

    Raises:
        SystemSettingMissingException: If WEBHOOK_MASTER_KEY is not configured.
    """
    global _fernet_service

    if _fernet_service is None:
        with _fernet_service_lock:
            if _fernet_service is None:
                import os

                master_key = settings.WEBHOOK_MASTER_KEY
                if not master_key:
                    raise SystemSettingMissingException(internal_message="WEBHOOK_MASTER_KEY must be set in environment")

                _fernet_service = FernetService(master_key)

    return _fernet_service
