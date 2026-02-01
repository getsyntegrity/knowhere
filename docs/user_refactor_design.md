# Refactoring User Management: The Shadow User Pattern

## 1. Overview
The goal of this refactor is to decouple authentication/authorization from the API service and adopt the "Shadow User" (Resource Server) pattern. The API will no longer manage user credentials, profiles, or registration. Instead, it will rely on an upstream service (or Identity Provider) to authenticate requests and provide an authenticated user identity via secure headers.

## 2. Core Concepts
### 2.1 The Shadow User
- **Role**: The API maintains a lightweight `users` table solely for internal referential integrity (Foreign Keys for jobs, transactions, etc.).
- **Identifier**: The `id` (UUID) remains the internal Primary Key. A new `external_id` column maps to the upstream identity provider's subject ID.
- **Data Minimization**: The API **DOES NOT** store:
  - Passwords (hashed or otherwise)
  - Emails
  - Usernames
  - Phone numbers
  - Avatars
  - Verification status
- **Responsibility**: The upstream service handles user management. The API only knows "User X (external_id) exists and has ID Y (internal UUID)".

### 2.2 Authentication Mechanism
- **Method**: HMAC Signature Verification.
- **Trusted Upstream**: The API trusts requests that are signed with a shared secret (`API_SIGNATURE_SECRET`).
- **Headers**:
  - `X-Knowhere-User-Id`: The upstream user ID (maps to local `external_id`).
  - `X-Knowhere-Signature`: `HMAC-SHA256(secret, values)`.
  - `X-Knowhere-Timestamp`: Unix timestamp to prevent replay attacks.
- **Logic**: 
  1. Middleware/Dependency computes signature of request headers.
  2. If valid, looks up `User` by `external_id`.
  3. If found, sets `current_user`.
  4. If not found, **automatically creates** a Shadow User record (Auto-provisioning).

## 3. Implementation Details

### 3.1 Database Schema Changes (`users` table)
We will perform a non-destructive migration to adapt the existing table.

**New Columns:**
- `external_id`: String(255), Unique, Indexed, Not Null.

**Dropped Columns:**
- `hashed_password`
- `email`
- `username`
- `phone`
- `avatar_url`
- `is_verified`
- `provider_type`, `provider_id` (likely legacy OAuth columns, can be mapped to external_id if needed, or dropped).

**Preserved Columns:**
- `id` (UUID, Primary Key)
- `created_at` / `create_time`
- `updated_at`
- `credits_balance`
- `stripe_customer_id`
- `user_type` (admin/user)
- `is_active` (for banning)

### 3.2 Migration Strategy
1. **Add `external_id` (Nullable)**.
2. **Backfill**: Populate `external_id` for existing users using a deterministic fallback (e.g., `legacy_{uuid}`). This ensures existing users can still be identified if the upstream also migrates them or if we manually map them.
3. **Enforce Constraints**: Set `external_id` to NOT NULL and UNIQUE.
4. **Drop Legacy Columns**.

### 3.3 Codebase Refactor
- **Remove `fastapi-users`**:
  - Delete `UserManager`, `SQLAlchemyUserDatabase` dependencies.
  - Remove `get_current_user` logic that relies on local JWTs.
  - Remove `/auth/jwt/*` routes.
- **Update `User` Model**:
  - Inherit from standard `Base`, not `SQLAlchemyBaseUserTableUUID`.
  - Remove all removed columns from the SQLAlchemy model definition.
- **Implement `VerifySignatureDependency`**:
  - Validates `X-Knowhere-*` headers.
  - Returns `User` instance.

