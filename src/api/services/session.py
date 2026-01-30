"""
Session Management Service for BenchGoblin.

Handles session creation, validation, expiration, and credential storage.
"""

import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import Session, SessionCredential


class SessionService:
    """Service for managing user sessions and encrypted credentials."""

    # Configuration defaults
    DEFAULT_EXPIRY_DAYS = 30
    MAX_EXPIRY_DAYS = 90
    INACTIVE_EXPIRY_DAYS = 7
    TOKEN_BYTES = 32  # 256 bits

    def __init__(self):
        self._encryption_key: bytes | None = None

    @property
    def encryption_key(self) -> bytes:
        """Get the master encryption key from environment."""
        if self._encryption_key is None:
            key_b64 = os.getenv("SESSION_ENCRYPTION_KEY")
            if key_b64:
                import base64

                self._encryption_key = base64.b64decode(key_b64)
            else:
                # For development only - generate a temporary key
                # In production, this should fail or use a secure key management system
                self._encryption_key = secrets.token_bytes(32)
        return self._encryption_key

    def generate_token(self) -> str:
        """Generate a cryptographically secure session token."""
        return secrets.token_urlsafe(self.TOKEN_BYTES)

    def _derive_key(self, session_id: str) -> bytes:
        """Derive a session-specific encryption key."""
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=session_id.encode(),
            info=b"gamespace-credentials",
        )
        return hkdf.derive(self.encryption_key)

    def _encrypt_data(self, data: dict[str, Any], session_id: str) -> tuple[bytes, bytes]:
        """Encrypt credential data using AES-256-GCM."""
        key = self._derive_key(session_id)
        aesgcm = AESGCM(key)
        iv = os.urandom(12)  # 96-bit IV for GCM
        plaintext = json.dumps(data).encode()
        ciphertext = aesgcm.encrypt(iv, plaintext, None)
        return ciphertext, iv

    def _decrypt_data(self, ciphertext: bytes, iv: bytes, session_id: str) -> dict[str, Any]:
        """Decrypt credential data."""
        key = self._derive_key(session_id)
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(iv, ciphertext, None)
        return json.loads(plaintext.decode())

    async def create_session(
        self,
        db: AsyncSession,
        platform: str,
        device_id: str | None = None,
        device_name: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        user_id: str | None = None,
    ) -> Session:
        """Create a new session."""
        now = datetime.now(UTC)
        expiry_days = int(os.getenv("SESSION_DEFAULT_EXPIRY_DAYS", self.DEFAULT_EXPIRY_DAYS))

        session = Session(
            session_token=self.generate_token(),
            platform=platform,
            device_id=device_id,
            device_name=device_name,
            ip_address=ip_address,
            user_agent=user_agent,
            user_id=user_id,
            status="active",
            created_at=now,
            last_active_at=now,
            expires_at=now + timedelta(days=expiry_days),
        )

        db.add(session)
        await db.flush()
        return session

    async def get_session_by_token(
        self,
        db: AsyncSession,
        token: str,
        update_activity: bool = True,
    ) -> Session | None:
        """Get a session by its token, optionally updating last activity."""
        result = await db.execute(select(Session).where(Session.session_token == token))
        session = result.scalar_one_or_none()

        if session and update_activity:
            session.last_active_at = datetime.now(UTC)

        return session

    async def get_session_by_id(self, db: AsyncSession, session_id: UUID) -> Session | None:
        """Get a session by its UUID."""
        result = await db.execute(select(Session).where(Session.id == session_id))
        return result.scalar_one_or_none()

    async def validate_session(
        self,
        db: AsyncSession,
        token: str,
        update_activity: bool = True,
    ) -> tuple[bool, Session | None, str | None]:
        """
        Validate a session token.

        Returns:
            Tuple of (is_valid, session, error_message)
        """
        session = await self.get_session_by_token(db, token, update_activity=False)

        if not session:
            return False, None, "Session not found"

        now = datetime.now(UTC)

        # Check status
        if session.status == "revoked":
            return False, session, "Session has been revoked"

        if session.status == "expired":
            return False, session, "Session has expired"

        # Check expiration
        if session.expires_at < now:
            session.status = "expired"
            return False, session, "Session has expired"

        # Check inactivity
        inactive_days = int(os.getenv("SESSION_INACTIVE_EXPIRY_DAYS", self.INACTIVE_EXPIRY_DAYS))
        if session.last_active_at < now - timedelta(days=inactive_days):
            session.status = "expired"
            return False, session, "Session expired due to inactivity"

        # Session is valid - update activity
        if update_activity:
            session.last_active_at = now

        return True, session, None

    async def refresh_session(
        self,
        db: AsyncSession,
        session: Session,
        extend_days: int | None = None,
    ) -> Session:
        """Extend a session's expiration time."""
        max_days = int(os.getenv("SESSION_MAX_EXPIRY_DAYS", self.MAX_EXPIRY_DAYS))
        extend_days = extend_days or int(
            os.getenv("SESSION_DEFAULT_EXPIRY_DAYS", self.DEFAULT_EXPIRY_DAYS)
        )

        # Cap extension at max
        extend_days = min(extend_days, max_days)

        now = datetime.now(UTC)
        session.expires_at = now + timedelta(days=extend_days)
        session.last_active_at = now

        return session

    async def revoke_session(self, db: AsyncSession, session: Session) -> None:
        """Revoke a session."""
        session.status = "revoked"

    async def revoke_all_sessions(self, db: AsyncSession, user_id: str) -> int:
        """Revoke all sessions for a user. Returns count of revoked sessions."""
        result = await db.execute(
            update(Session)
            .where(Session.user_id == user_id)
            .where(Session.status == "active")
            .values(status="revoked")
        )
        return result.rowcount

    async def get_user_sessions(
        self,
        db: AsyncSession,
        user_id: str,
        active_only: bool = True,
    ) -> list[Session]:
        """Get all sessions for a user."""
        query = select(Session).where(Session.user_id == user_id)

        if active_only:
            query = query.where(Session.status == "active")

        query = query.order_by(Session.last_active_at.desc())
        result = await db.execute(query)
        return list(result.scalars().all())

    async def cleanup_expired_sessions(
        self,
        db: AsyncSession,
        delete_after_days: int = 30,
    ) -> tuple[int, int]:
        """
        Clean up expired sessions.

        Returns:
            Tuple of (marked_expired_count, deleted_count)
        """
        now = datetime.now(UTC)

        # Mark expired sessions
        mark_result = await db.execute(
            update(Session)
            .where(Session.status == "active")
            .where(Session.expires_at < now)
            .values(status="expired")
        )
        marked_count = mark_result.rowcount

        # Delete old expired sessions
        delete_cutoff = now - timedelta(days=delete_after_days)
        delete_result = await db.execute(
            delete(Session)
            .where(Session.status.in_(["expired", "revoked"]))
            .where(Session.expires_at < delete_cutoff)
        )
        deleted_count = delete_result.rowcount

        return marked_count, deleted_count

    # -------------------------------------------------------------------------
    # Credential Management
    # -------------------------------------------------------------------------

    async def store_credential(
        self,
        db: AsyncSession,
        session: Session,
        provider: str,
        data: dict[str, Any],
        expires_at: datetime | None = None,
    ) -> SessionCredential:
        """Store encrypted credentials for a provider."""
        session_id_str = str(session.id)
        encrypted_data, iv = self._encrypt_data(data, session_id_str)

        # Check for existing credential
        result = await db.execute(
            select(SessionCredential)
            .where(SessionCredential.session_id == session.id)
            .where(SessionCredential.provider == provider)
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing
            existing.encrypted_data = encrypted_data
            existing.encryption_iv = iv
            existing.expires_at = expires_at
            existing.updated_at = datetime.now(UTC)
            return existing

        # Create new
        credential = SessionCredential(
            session_id=session.id,
            provider=provider,
            encrypted_data=encrypted_data,
            encryption_iv=iv,
            expires_at=expires_at,
        )
        db.add(credential)
        await db.flush()
        return credential

    async def get_credential(
        self,
        db: AsyncSession,
        session: Session,
        provider: str,
    ) -> dict[str, Any] | None:
        """Get decrypted credentials for a provider."""
        result = await db.execute(
            select(SessionCredential)
            .where(SessionCredential.session_id == session.id)
            .where(SessionCredential.provider == provider)
        )
        credential = result.scalar_one_or_none()

        if not credential:
            return None

        # Check expiration
        if credential.expires_at and credential.expires_at < datetime.now(UTC):
            return None

        return self._decrypt_data(
            credential.encrypted_data,
            credential.encryption_iv,
            str(session.id),
        )

    async def delete_credential(
        self,
        db: AsyncSession,
        session: Session,
        provider: str,
    ) -> bool:
        """Delete credentials for a provider. Returns True if deleted."""
        result = await db.execute(
            delete(SessionCredential)
            .where(SessionCredential.session_id == session.id)
            .where(SessionCredential.provider == provider)
        )
        return result.rowcount > 0

    async def get_credential_status(
        self,
        db: AsyncSession,
        session: Session,
    ) -> dict[str, dict[str, Any]]:
        """Get status of all credentials for a session."""
        result = await db.execute(
            select(SessionCredential).where(SessionCredential.session_id == session.id)
        )
        credentials = result.scalars().all()

        now = datetime.now(UTC)
        status = {}

        for cred in credentials:
            is_expired = cred.expires_at and cred.expires_at < now
            status[cred.provider] = {
                "connected": not is_expired,
                "expires_at": cred.expires_at.isoformat() if cred.expires_at else None,
                "expired": is_expired,
                "updated_at": cred.updated_at.isoformat() if cred.updated_at else None,
            }

        return status


# Singleton instance
session_service = SessionService()
