# Session Requirements Specification

## Overview

This document defines the session management requirements for BenchGoblins, a fantasy sports decision engine. Sessions provide secure, stateful interactions between the mobile app and backend API, managing user credentials for ESPN, Yahoo, and other fantasy platform integrations.

## Current State

### Problems with Current Implementation

1. **In-Memory Credential Storage**: ESPN and Yahoo credentials stored in Python dictionaries (`_espn_credentials`, `_yahoo_tokens`) are lost on server restart
2. **No Session Lifecycle**: Sessions default to `"default"` with no creation, expiration, or validation
3. **No Security**: Credentials stored in plaintext with no encryption
4. **No Multi-Device Support**: Single "default" session doesn't support multiple devices
5. **No Audit Trail**: No logging of credential access or session events

### Current Usage

```python
# In-memory storage (main.py:842-843, 1203-1204)
_espn_credentials: dict[str, ESPNCredentials] = {}
_yahoo_tokens: dict[str, dict] = {}

# Default session fallback
session_id: str = Query(default="default")
```

## Requirements

### 1. Session Model

#### Database Schema

```sql
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Session identification
    session_token VARCHAR(64) UNIQUE NOT NULL,  -- Secure random token
    device_id VARCHAR(100),                      -- Client device identifier
    device_name VARCHAR(100),                    -- Human-readable device name
    platform VARCHAR(20) NOT NULL,               -- 'ios', 'android', 'web'

    -- Lifecycle
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- 'active', 'expired', 'revoked'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_active_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,

    -- Security
    ip_address INET,
    user_agent TEXT,

    -- Future: User association
    user_id VARCHAR(100)  -- For future auth integration
);
```

#### Session States

| Status | Description |
|--------|-------------|
| `active` | Session is valid and can be used |
| `expired` | Session has passed its expiration time |
| `revoked` | Session was manually invalidated |

#### Session Token

- 256-bit cryptographically secure random token
- Base64URL encoded (43 characters)
- Generated using `secrets.token_urlsafe(32)`

### 2. Credential Storage

#### Encrypted Credentials Table

```sql
CREATE TABLE session_credentials (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,

    -- Credential identification
    provider VARCHAR(20) NOT NULL,  -- 'espn', 'yahoo', 'sleeper'

    -- Encrypted data (AES-256-GCM)
    encrypted_data BYTEA NOT NULL,
    encryption_iv BYTEA NOT NULL,    -- Initialization vector

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,          -- For OAuth tokens

    UNIQUE (session_id, provider)
);
```

#### Encryption Strategy

- **Algorithm**: AES-256-GCM (authenticated encryption)
- **Key Management**:
  - Master key from `SESSION_ENCRYPTION_KEY` environment variable
  - Key derivation using HKDF with session-specific salt
- **Data Format**: JSON serialized credentials before encryption

### 3. Session Lifecycle

#### Creation Flow

```
1. Client requests new session → POST /sessions
2. Server generates secure session token
3. Server creates session record with expiration
4. Server returns session token to client
5. Client stores token securely (Keychain/Keystore)
```

#### Validation Flow

```
1. Client includes session token in request header
2. Server validates token exists and is active
3. Server checks expiration time
4. Server updates last_active_at timestamp
5. Request proceeds or returns 401
```

#### Expiration Policy

| Scenario | Expiration |
|----------|------------|
| Default session | 30 days from creation |
| After credential connection | Extended to 90 days |
| Inactive session | Expires after 7 days of inactivity |

#### Cleanup

- Background job runs daily to:
  - Mark expired sessions as `status = 'expired'`
  - Delete sessions expired > 30 days
  - Clear associated credentials

### 4. API Changes

#### New Endpoints

```
POST   /sessions              Create new session
GET    /sessions/current      Get current session info
POST   /sessions/refresh      Extend session expiration
DELETE /sessions/current      Revoke current session
GET    /sessions              List all sessions (for user)
DELETE /sessions/{id}         Revoke specific session
```

#### Request Header

All authenticated requests must include:

```
X-Session-Token: <session_token>
```

Or query parameter for backwards compatibility:

```
?session_id=<session_token>
```

#### Response Models

```python
class SessionResponse(BaseModel):
    session_id: str
    session_token: str  # Only returned on creation
    platform: str
    device_name: str | None
    created_at: datetime
    expires_at: datetime
    last_active_at: datetime
    credentials: dict[str, CredentialStatus]

class CredentialStatus(BaseModel):
    provider: str
    connected: bool
    expires_at: datetime | None  # For OAuth tokens
```

### 5. Mobile Integration

#### Session Store (Zustand)

```typescript
interface SessionState {
  // Session data
  sessionId: string | null;
  sessionToken: string | null;
  expiresAt: Date | null;

  // Credential status
  espnConnected: boolean;
  yahooConnected: boolean;
  sleeperUsername: string | null;

  // Actions
  initSession: () => Promise<void>;
  refreshSession: () => Promise<void>;
  clearSession: () => Promise<void>;

  // Credential actions
  setESPNConnected: (connected: boolean) => void;
  setYahooConnected: (connected: boolean) => void;
  setSleeperUsername: (username: string | null) => void;
}
```

#### Secure Storage

- **iOS**: Keychain Services via `expo-secure-store`
- **Android**: EncryptedSharedPreferences via `expo-secure-store`
- **Storage Key**: `benchgoblins_session_token`

#### Session Initialization

```typescript
async function initSession() {
  // 1. Check for stored token
  const storedToken = await SecureStore.getItemAsync('benchgoblins_session_token');

  if (storedToken) {
    // 2. Validate with server
    const session = await api.validateSession(storedToken);
    if (session.valid) {
      return session;
    }
  }

  // 3. Create new session
  const newSession = await api.createSession({
    platform: Platform.OS,
    deviceId: await getDeviceId(),
    deviceName: await getDeviceName(),
  });

  // 4. Store token securely
  await SecureStore.setItemAsync('benchgoblins_session_token', newSession.token);

  return newSession;
}
```

### 6. Security Requirements

#### Rate Limiting

| Endpoint | Limit |
|----------|-------|
| `POST /sessions` | 10/hour per IP |
| `POST /sessions/refresh` | 60/hour per session |
| Credential endpoints | 30/minute per session |

#### Audit Logging

Log the following events:

- Session created
- Session expired/revoked
- Credential connected/disconnected
- Failed authentication attempts
- Suspicious activity (multiple IPs, rapid requests)

#### Security Headers

```python
# Required for all session endpoints
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
```

### 7. Migration Plan

#### Phase 1: Database Schema (This PR)

- Add `sessions` table
- Add `session_credentials` table
- Add Session ORM models
- Create SessionService

#### Phase 2: API Integration

- Add session middleware
- Update existing endpoints to use SessionService
- Maintain backward compatibility with `session_id` query param

#### Phase 3: Credential Migration

- Implement credential encryption
- Migrate from in-memory to database storage
- Add cleanup jobs

#### Phase 4: Mobile Integration

- Create sessionStore
- Implement secure token storage
- Update API service to include session headers

### 8. Environment Variables

```bash
# Required
SESSION_ENCRYPTION_KEY=<base64-encoded-32-byte-key>

# Optional
SESSION_DEFAULT_EXPIRY_DAYS=30
SESSION_MAX_EXPIRY_DAYS=90
SESSION_INACTIVE_EXPIRY_DAYS=7
```

### 9. Testing Requirements

- Unit tests for SessionService
- Integration tests for session endpoints
- Security tests for token generation
- Load tests for session validation performance

## Appendix

### A. Session Token Generation

```python
import secrets
import hashlib

def generate_session_token() -> str:
    """Generate a cryptographically secure session token."""
    return secrets.token_urlsafe(32)  # 256 bits, 43 chars

def hash_token_for_storage(token: str) -> str:
    """Hash token for database storage (optional additional security)."""
    return hashlib.sha256(token.encode()).hexdigest()
```

### B. Credential Encryption

```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
import os
import json

def encrypt_credentials(data: dict, master_key: bytes, session_id: str) -> tuple[bytes, bytes]:
    """Encrypt credentials using AES-256-GCM."""
    # Derive session-specific key
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=session_id.encode(),
        info=b"benchgoblins-credentials",
    )
    key = hkdf.derive(master_key)

    # Encrypt
    aesgcm = AESGCM(key)
    iv = os.urandom(12)
    plaintext = json.dumps(data).encode()
    ciphertext = aesgcm.encrypt(iv, plaintext, None)

    return ciphertext, iv
```

### C. Related Files

| File | Purpose |
|------|---------|
| `data/schema.sql` | Database schema |
| `src/api/models/database.py` | SQLAlchemy ORM models |
| `src/api/services/session.py` | Session management service |
| `src/api/main.py` | API endpoints |
| `src/mobile/src/stores/sessionStore.ts` | Mobile session state |
