"""
Unit tests for FernetService.
"""

from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from shared.core.exceptions.domain_exceptions import (
    SystemSettingInvalidException,
    SystemSettingMissingException,
)
from shared.services.encryption.fernet_service import FernetService, get_fernet_service


# Helper to generate a valid key
def generate_key():
    return Fernet.generate_key().decode()


class TestFernetService:

    def test_init_raises_if_no_key(self):
        """Test initialization fails without master key."""
        with pytest.raises(
            SystemSettingMissingException, match="WEBHOOK_MASTER_KEY is required"
        ):
            FernetService(master_key="")

    def test_init_raises_if_invalid_key(self):
        """Test initialization fails with invalid key."""
        with pytest.raises(
            SystemSettingInvalidException,
            match="WEBHOOK_MASTER_KEY must be a valid Fernet key",
        ):
            FernetService(master_key="invalid-key-format")

    def test_encrypt_decrypt_cycle(self):
        """Test full encryption/decryption cycle."""
        key = generate_key()
        service = FernetService(master_key=key)

        original_text = "secret_message_123"
        encrypted = service.encrypt(original_text)

        assert encrypted != original_text
        assert service.decrypt(encrypted) == original_text

    def test_generate_webhook_secret(self):
        """Test secret generation."""
        key = generate_key()
        service = FernetService(master_key=key)

        secret = service.generate_webhook_secret()
        assert len(secret) == 70  # whsec_ + 64 hex chars

    def test_factory_function_loads_env(self):
        """Test get_fernet_service loads from env."""
        key = generate_key()
        with patch(
            "shared.services.encryption.fernet_service.settings.WEBHOOK_MASTER_KEY", key
        ):
            # Reset singleton if exists
            import shared.services.encryption.fernet_service as module

            old_instance = module._fernet_service
            module._fernet_service = None

            try:
                service = get_fernet_service()
                assert isinstance(service, FernetService)
                # Verify it works
                assert service.decrypt(service.encrypt("foo")) == "foo"
            finally:
                # Restore
                module._fernet_service = old_instance

    def test_decrypt_invalid_token(self):
        """Test decryption of invalid token returns None (or raises depending on implementation)."""
        # Review implementation: currently it calls fernet.decrypt which raises InvalidToken
        # But my Repository wrapper catches exception. Service itself does NOT catch it.
        # Let's check service code (I viewed it earlier).
        # Service just wraps fernet.decrypt. So it should raise.
        key = generate_key()
        service = FernetService(master_key=key)

        result = service.decrypt("invalid_token")
        assert result is None
