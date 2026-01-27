"""Tests for session management service (non-DB parts)."""

import pytest

from services.session import SessionService


@pytest.fixture
def svc():
    return SessionService()


class TestGenerateToken:
    def test_generates_string(self, svc):
        token = svc.generate_token()
        assert isinstance(token, str)
        assert len(token) > 20

    def test_unique(self, svc):
        tokens = {svc.generate_token() for _ in range(100)}
        assert len(tokens) == 100


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self, svc):
        data = {"access_token": "secret123", "refresh_token": "refresh456"}
        session_id = "test-session-id"
        ciphertext, iv = svc._encrypt_data(data, session_id)
        result = svc._decrypt_data(ciphertext, iv, session_id)
        assert result == data

    def test_different_sessions_different_ciphertext(self, svc):
        data = {"key": "value"}
        ct1, iv1 = svc._encrypt_data(data, "session-1")
        ct2, iv2 = svc._encrypt_data(data, "session-2")
        assert ct1 != ct2

    def test_wrong_session_id_fails(self, svc):
        data = {"key": "value"}
        ciphertext, iv = svc._encrypt_data(data, "session-1")
        with pytest.raises(Exception):
            svc._decrypt_data(ciphertext, iv, "session-2")

    def test_complex_data(self, svc):
        data = {
            "token": "abc",
            "nested": {"list": [1, 2, 3]},
            "number": 42,
            "null_val": None,
        }
        session_id = "test"
        ct, iv = svc._encrypt_data(data, session_id)
        result = svc._decrypt_data(ct, iv, session_id)
        assert result == data


class TestDeriveKey:
    def test_deterministic(self, svc):
        k1 = svc._derive_key("session-1")
        k2 = svc._derive_key("session-1")
        assert k1 == k2

    def test_different_sessions_different_keys(self, svc):
        k1 = svc._derive_key("session-1")
        k2 = svc._derive_key("session-2")
        assert k1 != k2

    def test_key_length(self, svc):
        key = svc._derive_key("test")
        assert len(key) == 32  # 256 bits


class TestEncryptionKeyProperty:
    def test_generates_key_without_env(self, svc):
        key = svc.encryption_key
        assert isinstance(key, bytes)
        assert len(key) == 32

    def test_caches_key(self, svc):
        k1 = svc.encryption_key
        k2 = svc.encryption_key
        assert k1 is k2
