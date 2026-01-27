"""Extended tests for session service — DB-dependent async methods with mocked DB."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.session import SessionService


@pytest.fixture
def svc():
    return SessionService()


def make_session(**overrides):
    """Create a mock Session object."""
    now = datetime.now(UTC)
    defaults = {
        "id": uuid.uuid4(),
        "session_token": "test-token",
        "platform": "web",
        "device_id": None,
        "device_name": None,
        "ip_address": None,
        "user_agent": None,
        "user_id": "user-1",
        "status": "active",
        "created_at": now,
        "last_active_at": now,
        "expires_at": now + timedelta(days=30),
    }
    defaults.update(overrides)
    session = MagicMock()
    for k, v in defaults.items():
        setattr(session, k, v)
    return session


def make_credential(**overrides):
    """Create a mock SessionCredential object."""
    defaults = {
        "id": uuid.uuid4(),
        "session_id": uuid.uuid4(),
        "provider": "espn",
        "encrypted_data": b"enc",
        "encryption_iv": b"iv",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "expires_at": None,
    }
    defaults.update(overrides)
    cred = MagicMock()
    for k, v in defaults.items():
        setattr(cred, k, v)
    return cred


def mock_db_result(value):
    """Create a mock DB execute result."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalars.return_value.all.return_value = [value] if value else []
    result.rowcount = 1
    return result


# =========================================================================
# create_session
# =========================================================================


class TestCreateSession:
    @pytest.mark.asyncio
    async def test_creates_session(self, svc):
        db = AsyncMock()
        db.flush = AsyncMock()

        await svc.create_session(
            db,
            platform="web",
            device_id="d1",
            device_name="Chrome",
            ip_address="1.2.3.4",
            user_agent="Mozilla",
        )

        db.add.assert_called_once()
        db.flush.assert_called_once()
        added = db.add.call_args[0][0]
        assert added.platform == "web"
        assert added.status == "active"
        assert added.session_token is not None

    @pytest.mark.asyncio
    async def test_with_user_id(self, svc):
        db = AsyncMock()
        db.flush = AsyncMock()

        await svc.create_session(db, platform="ios", user_id="user-123")
        added = db.add.call_args[0][0]
        assert added.user_id == "user-123"

    @pytest.mark.asyncio
    async def test_custom_expiry_env(self, svc):
        db = AsyncMock()
        db.flush = AsyncMock()

        with patch.dict("os.environ", {"SESSION_DEFAULT_EXPIRY_DAYS": "7"}):
            await svc.create_session(db, platform="web")
            added = db.add.call_args[0][0]
            delta = added.expires_at - added.created_at
            assert 6 < delta.days <= 7


# =========================================================================
# get_session_by_token
# =========================================================================


class TestGetSessionByToken:
    @pytest.mark.asyncio
    async def test_found(self, svc):
        session = make_session()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_db_result(session))

        result = await svc.get_session_by_token(db, "test-token")
        assert result is session

    @pytest.mark.asyncio
    async def test_not_found(self, svc):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_db_result(None))

        result = await svc.get_session_by_token(db, "bad-token")
        assert result is None

    @pytest.mark.asyncio
    async def test_updates_activity(self, svc):
        session = make_session(last_active_at=datetime(2020, 1, 1, tzinfo=UTC))
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_db_result(session))

        result = await svc.get_session_by_token(db, "test-token", update_activity=True)
        assert result.last_active_at.year >= 2024

    @pytest.mark.asyncio
    async def test_no_update_activity(self, svc):
        old_time = datetime(2020, 1, 1, tzinfo=UTC)
        session = make_session(last_active_at=old_time)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_db_result(session))

        result = await svc.get_session_by_token(db, "test-token", update_activity=False)
        # last_active_at not updated
        assert result.last_active_at == old_time


# =========================================================================
# get_session_by_id
# =========================================================================


class TestGetSessionById:
    @pytest.mark.asyncio
    async def test_found(self, svc):
        sid = uuid.uuid4()
        session = make_session(id=sid)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_db_result(session))

        result = await svc.get_session_by_id(db, sid)
        assert result is session

    @pytest.mark.asyncio
    async def test_not_found(self, svc):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_db_result(None))

        result = await svc.get_session_by_id(db, uuid.uuid4())
        assert result is None


# =========================================================================
# validate_session
# =========================================================================


class TestValidateSession:
    @pytest.mark.asyncio
    async def test_valid(self, svc):
        session = make_session()
        db = AsyncMock()

        with patch.object(
            svc, "get_session_by_token", new_callable=AsyncMock, return_value=session
        ):
            valid, sess, err = await svc.validate_session(db, "test-token")
            assert valid is True
            assert sess is session
            assert err is None

    @pytest.mark.asyncio
    async def test_not_found(self, svc):
        db = AsyncMock()

        with patch.object(
            svc, "get_session_by_token", new_callable=AsyncMock, return_value=None
        ):
            valid, sess, err = await svc.validate_session(db, "bad")
            assert valid is False
            assert "not found" in err

    @pytest.mark.asyncio
    async def test_revoked(self, svc):
        session = make_session(status="revoked")
        db = AsyncMock()

        with patch.object(
            svc, "get_session_by_token", new_callable=AsyncMock, return_value=session
        ):
            valid, sess, err = await svc.validate_session(db, "test")
            assert valid is False
            assert "revoked" in err

    @pytest.mark.asyncio
    async def test_expired_status(self, svc):
        session = make_session(status="expired")
        db = AsyncMock()

        with patch.object(
            svc, "get_session_by_token", new_callable=AsyncMock, return_value=session
        ):
            valid, sess, err = await svc.validate_session(db, "test")
            assert valid is False
            assert "expired" in err

    @pytest.mark.asyncio
    async def test_expired_by_time(self, svc):
        session = make_session(expires_at=datetime(2020, 1, 1, tzinfo=UTC))
        db = AsyncMock()

        with patch.object(
            svc, "get_session_by_token", new_callable=AsyncMock, return_value=session
        ):
            valid, sess, err = await svc.validate_session(db, "test")
            assert valid is False
            assert "expired" in err
            assert session.status == "expired"

    @pytest.mark.asyncio
    async def test_expired_by_inactivity(self, svc):
        session = make_session(last_active_at=datetime(2020, 1, 1, tzinfo=UTC))
        db = AsyncMock()

        with patch.object(
            svc, "get_session_by_token", new_callable=AsyncMock, return_value=session
        ):
            valid, sess, err = await svc.validate_session(db, "test")
            assert valid is False
            assert "inactivity" in err

    @pytest.mark.asyncio
    async def test_updates_activity(self, svc):
        session = make_session()
        db = AsyncMock()

        with patch.object(
            svc, "get_session_by_token", new_callable=AsyncMock, return_value=session
        ):
            valid, sess, err = await svc.validate_session(
                db, "test", update_activity=True
            )
            assert valid is True

    @pytest.mark.asyncio
    async def test_no_update_activity(self, svc):
        old_time = datetime.now(UTC) - timedelta(minutes=5)
        session = make_session(last_active_at=old_time)
        db = AsyncMock()

        with patch.object(
            svc, "get_session_by_token", new_callable=AsyncMock, return_value=session
        ):
            valid, sess, err = await svc.validate_session(
                db, "test", update_activity=False
            )
            assert valid is True


# =========================================================================
# refresh_session
# =========================================================================


class TestRefreshSession:
    @pytest.mark.asyncio
    async def test_default_extension(self, svc):
        session = make_session()
        db = AsyncMock()
        result = await svc.refresh_session(db, session)
        assert result.expires_at > datetime.now(UTC)

    @pytest.mark.asyncio
    async def test_custom_extension(self, svc):
        session = make_session()
        db = AsyncMock()
        result = await svc.refresh_session(db, session, extend_days=7)
        delta = result.expires_at - datetime.now(UTC)
        assert 6 <= delta.days <= 7

    @pytest.mark.asyncio
    async def test_capped_at_max(self, svc):
        session = make_session()
        db = AsyncMock()
        with patch.dict("os.environ", {"SESSION_MAX_EXPIRY_DAYS": "10"}):
            result = await svc.refresh_session(db, session, extend_days=999)
            delta = result.expires_at - datetime.now(UTC)
            assert delta.days <= 10


# =========================================================================
# revoke_session
# =========================================================================


class TestRevokeSession:
    @pytest.mark.asyncio
    async def test_revoke(self, svc):
        session = make_session()
        db = AsyncMock()
        await svc.revoke_session(db, session)
        assert session.status == "revoked"


# =========================================================================
# revoke_all_sessions
# =========================================================================


class TestRevokeAllSessions:
    @pytest.mark.asyncio
    async def test_revoke_all(self, svc):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.rowcount = 3
        db.execute = AsyncMock(return_value=result_mock)

        count = await svc.revoke_all_sessions(db, "user-1")
        assert count == 3


# =========================================================================
# get_user_sessions
# =========================================================================


class TestGetUserSessions:
    @pytest.mark.asyncio
    async def test_active_only(self, svc):
        session = make_session()
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [session]
        db.execute = AsyncMock(return_value=result_mock)

        result = await svc.get_user_sessions(db, "user-1")
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_all_sessions(self, svc):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        result = await svc.get_user_sessions(db, "user-1", active_only=False)
        assert result == []


# =========================================================================
# cleanup_expired_sessions
# =========================================================================


class TestCleanupExpiredSessions:
    @pytest.mark.asyncio
    async def test_cleanup(self, svc):
        db = AsyncMock()
        mark_result = MagicMock()
        mark_result.rowcount = 5
        delete_result = MagicMock()
        delete_result.rowcount = 2
        db.execute = AsyncMock(side_effect=[mark_result, delete_result])

        marked, deleted = await svc.cleanup_expired_sessions(db)
        assert marked == 5
        assert deleted == 2


# =========================================================================
# store_credential
# =========================================================================


class TestStoreCredential:
    @pytest.mark.asyncio
    async def test_new_credential(self, svc):
        session = make_session()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_db_result(None))  # No existing
        db.flush = AsyncMock()

        await svc.store_credential(db, session, "espn", {"token": "abc"})
        db.add.assert_called_once()
        db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_existing(self, svc):
        session = make_session()
        existing_cred = make_credential(session_id=session.id)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_db_result(existing_cred))

        result = await svc.store_credential(db, session, "espn", {"token": "new"})
        assert result is existing_cred
        # encrypted_data should be updated
        assert existing_cred.encrypted_data != b"enc"

    @pytest.mark.asyncio
    async def test_with_expiry(self, svc):
        session = make_session()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_db_result(None))
        db.flush = AsyncMock()

        expiry = datetime.now(UTC) + timedelta(hours=1)
        await svc.store_credential(db, session, "yahoo", {"t": "x"}, expires_at=expiry)
        added = db.add.call_args[0][0]
        assert added.expires_at == expiry


# =========================================================================
# get_credential
# =========================================================================


class TestGetCredential:
    @pytest.mark.asyncio
    async def test_found(self, svc):
        session = make_session()
        sid = str(session.id)
        data = {"token": "secret"}
        ct, iv = svc._encrypt_data(data, sid)
        cred = make_credential(
            session_id=session.id,
            encrypted_data=ct,
            encryption_iv=iv,
            expires_at=None,
        )

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_db_result(cred))

        result = await svc.get_credential(db, session, "espn")
        assert result == data

    @pytest.mark.asyncio
    async def test_not_found(self, svc):
        session = make_session()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_db_result(None))

        result = await svc.get_credential(db, session, "espn")
        assert result is None

    @pytest.mark.asyncio
    async def test_expired(self, svc):
        session = make_session()
        cred = make_credential(
            expires_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_db_result(cred))

        result = await svc.get_credential(db, session, "espn")
        assert result is None


# =========================================================================
# delete_credential
# =========================================================================


class TestDeleteCredential:
    @pytest.mark.asyncio
    async def test_deleted(self, svc):
        session = make_session()
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.rowcount = 1
        db.execute = AsyncMock(return_value=result_mock)

        result = await svc.delete_credential(db, session, "espn")
        assert result is True

    @pytest.mark.asyncio
    async def test_not_found(self, svc):
        session = make_session()
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.rowcount = 0
        db.execute = AsyncMock(return_value=result_mock)

        result = await svc.delete_credential(db, session, "espn")
        assert result is False


# =========================================================================
# get_credential_status
# =========================================================================


class TestGetCredentialStatus:
    @pytest.mark.asyncio
    async def test_with_credentials(self, svc):
        session = make_session()
        now = datetime.now(UTC)
        cred1 = make_credential(
            provider="espn", expires_at=now + timedelta(hours=1), updated_at=now
        )
        cred2 = make_credential(
            provider="yahoo", expires_at=now - timedelta(hours=1), updated_at=now
        )

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [cred1, cred2]
        db.execute = AsyncMock(return_value=result_mock)

        status = await svc.get_credential_status(db, session)
        assert "espn" in status
        assert status["espn"]["connected"] is True
        assert status["yahoo"]["connected"] is False
        assert status["yahoo"]["expired"] is True

    @pytest.mark.asyncio
    async def test_no_credentials(self, svc):
        session = make_session()
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result_mock)

        status = await svc.get_credential_status(db, session)
        assert status == {}

    @pytest.mark.asyncio
    async def test_no_expiry(self, svc):
        session = make_session()
        cred = make_credential(provider="sleeper", expires_at=None, updated_at=None)

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [cred]
        db.execute = AsyncMock(return_value=result_mock)

        status = await svc.get_credential_status(db, session)
        assert status["sleeper"]["connected"] is True
        assert status["sleeper"]["expires_at"] is None


# =========================================================================
# encryption_key from env
# =========================================================================


class TestEncryptionKeyFromEnv:
    def test_from_env_var(self):
        import base64

        key = base64.b64encode(b"x" * 32).decode()
        svc = SessionService()
        with patch.dict("os.environ", {"SESSION_ENCRYPTION_KEY": key}):
            result = svc.encryption_key
            assert result == b"x" * 32
