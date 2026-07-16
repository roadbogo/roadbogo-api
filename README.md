# roadbogo-api

Roadbogo service API server.

## Stack

- Python 3.11+
- FastAPI
- MariaDB 10.11
- SQLAlchemy 2.x
- Alembic
- Uvicorn
- Pydantic Settings

## Getting Started

### Windows PowerShell

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
pytest -q
```

### WSL/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
pytest -q
```

API documents are available at `http://localhost:8000/docs`.

Phone numbers are encrypted before storage. Generate a dedicated Fernet key and set
`AUTH_PHONE_ENCRYPTION_KEY` in `.env` (do not reuse the JWT secret):

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Health check:

```bash
curl http://localhost:8000/api/v1/health
```

## Authentication API

`GET /api/v1/auth/me` and `PATCH /api/v1/auth/me` both return `data.user` with
the same fields as the login response: `public_id`, `email`, `user_name`,
`phone`, `account_status`, `organization`, `roles`, `permissions`, and
`last_login_at`. `PATCH` accepts only `user_name` and `phone`. A phone write
requires `AUTH_PHONE_ENCRYPTION_KEY`; configuration failures use the
`AUTH_PHONE_ENCRYPTION_UNAVAILABLE` error code without exposing key details.

Password reset uses `POST /api/v1/auth/password-reset/request` followed by
`POST /api/v1/auth/password-reset/confirm`. The request endpoint deliberately
returns the same public acknowledgement for known and unknown accounts. In
`APP_ENV=local` or `test`, `AUTH_PASSWORD_RESET_DEBUG_RESPONSE=true` may include
a same-origin `${FRONTEND_BASE_URL}/reset-password?token=...` URL. Settings
validation rejects that debug option in every other environment. Production
delivery therefore requires SMTP configuration. Confirmation can return
`AUTH_PASSWORD_RESET_TOKEN_INVALID`, `AUTH_PASSWORD_RESET_TOKEN_EXPIRED`,
`AUTH_ACCOUNT_UNAVAILABLE`, or `USER_PASSWORD_POLICY_VIOLATION`.

## Database Migration

Apply the verified MVP schema, reference seed data, and views:

```powershell
python -m alembic upgrade head
```

Compare a migrated test database with the SQL reference database:

```powershell
python scripts/compare_mvp_databases.py `
  --reference roadbogo_test `
  --migration roadbogo_orm_test
```

The migration-managed database includes Alembic's `alembic_version` table in
addition to the 44 MVP tables. The comparison script excludes only that table.
