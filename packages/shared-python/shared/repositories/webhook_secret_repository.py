"""
Webhook Secret Repository Layer

Provides database operations for webhook secrets management.
"""

from typing import List, Optional

from loguru import logger
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.database.webhook_secret import WebhookSecret, WebhookSecretStatus
from shared.services.encryption import get_fernet_service


class WebhookSecretRepository:
    """Repository for webhook secret operations."""

    async def create_secret(
        self,
        db: AsyncSession,
        user_id: str,
        endpoint: Optional[str] = None,
    ) -> WebhookSecret:
        """
        Create a new webhook secret for a user.

        Args:
            db: Database session
            user_id: User ID
            endpoint: Optional endpoint-specific URL (None = default account secret)

        Returns:
            Created WebhookSecret with decrypted secret available via _raw_secret
        """
        fernet = get_fernet_service()

        # Generate raw secret
        raw_secret = fernet.generate_webhook_secret()

        # Encrypt for storage
        encrypted_secret = fernet.encrypt(raw_secret)

        secret = WebhookSecret(
            user_id=user_id,
            endpoint=endpoint,
            secret_encrypted=encrypted_secret,
            status=WebhookSecretStatus.ACTIVE,
        )

        db.add(secret)
        await db.commit()
        await db.refresh(secret)

        # Attach raw secret for one-time display (not persisted)
        secret._raw_secret = raw_secret  # type: ignore

        logger.info(
            f"Created webhook secret: id={secret.id}, user_id={user_id}, endpoint={endpoint}"
        )
        return secret

    async def get_active_secret(
        self,
        db: AsyncSession,
        user_id: str,
        endpoint: Optional[str] = None,
    ) -> Optional[WebhookSecret]:
        """
        Get the active secret for a user/endpoint combination.

        Resolution order:
        1. Exact match: user_id + endpoint
        2. Fallback: user_id + endpoint=NULL (default account secret)

        Args:
            db: Database session
            user_id: User ID
            endpoint: Target endpoint URL (optional)

        Returns:
            WebhookSecret if found, None otherwise
        """
        # 1. Try exact match first
        if endpoint:
            result = await db.execute(
                select(WebhookSecret).where(
                    and_(
                        WebhookSecret.user_id == user_id,
                        WebhookSecret.endpoint == endpoint,
                        WebhookSecret.status == WebhookSecretStatus.ACTIVE,
                    )
                )
            )
            secret = result.scalar_one_or_none()
            if secret:
                return secret

        # 2. Fallback to default account secret
        result = await db.execute(
            select(WebhookSecret).where(
                and_(
                    WebhookSecret.user_id == user_id,
                    WebhookSecret.endpoint.is_(None),
                    WebhookSecret.status == WebhookSecretStatus.ACTIVE,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create_secret(
        self,
        db: AsyncSession,
        user_id: str,
        endpoint: Optional[str] = None,
    ) -> WebhookSecret:
        """
        Get existing active secret or create a new one (lazy creation).

        Args:
            db: Database session
            user_id: User ID
            endpoint: Target endpoint URL (optional)

        Returns:
            WebhookSecret (existing or newly created)
        """
        existing = await self.get_active_secret(db, user_id, endpoint)
        if existing:
            return existing

        # Create new secret
        return await self.create_secret(db, user_id, endpoint)

    async def list_secrets(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> List[WebhookSecret]:
        """
        List all secrets for a user (active and revoked).

        Args:
            db: Database session
            user_id: User ID

        Returns:
            List of WebhookSecret entries
        """
        result = await db.execute(
            select(WebhookSecret)
            .where(WebhookSecret.user_id == user_id)
            .order_by(WebhookSecret.created_at.desc())
        )
        return list(result.scalars().all())

    async def revoke_secret(
        self,
        db: AsyncSession,
        secret_id: str,
        user_id: str,
    ) -> bool:
        """
        Revoke a secret by ID (only if owned by user).

        Args:
            db: Database session
            secret_id: Secret ID to revoke
            user_id: User ID (for ownership check)

        Returns:
            True if revoked, False if not found or not owned
        """
        result = await db.execute(
            select(WebhookSecret).where(
                and_(
                    WebhookSecret.id == secret_id,
                    WebhookSecret.user_id == user_id,
                )
            )
        )
        secret = result.scalar_one_or_none()

        if not secret:
            return False

        if secret.status == WebhookSecretStatus.REVOKED:
            return True  # Already revoked

        secret.status = WebhookSecretStatus.REVOKED
        await db.commit()

        logger.info(f"Revoked webhook secret: id={secret_id}, user_id={user_id}")
        return True

    def decrypt_secret(self, secret: WebhookSecret) -> Optional[str]:
        """
        Decrypt a secret's encrypted value.

        Args:
            secret: WebhookSecret with encrypted value

        Returns:
            Decrypted secret string, or None if decryption fails
        """
        try:
            fernet = get_fernet_service()
            return fernet.decrypt(secret.secret_encrypted)
        except Exception as e:
            logger.error(f"Failed to decrypt secret {secret.id}: {e}")
            return None
