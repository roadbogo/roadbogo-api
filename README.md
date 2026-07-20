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

Health check:

```bash
curl http://localhost:8000/api/v1/health
```

### Local controller account

After applying migrations, create an idempotent controller account for local integration tests:

```powershell
$env:DEV_CONTROLLER_PASSWORD="<local-development-password>"
python scripts/bootstrap_dev_controller.py
Remove-Item Env:DEV_CONTROLLER_PASSWORD
```

The command refuses to run unless `APP_ENV` is `local` or `test`. It uses the
seeded `CONTROLLER` role, its existing permissions, and the first active
`CONTROL_CENTER` organization. If no such organization exists, it creates the
idempotent `LOCAL_CONTROL_CENTER` development organization. Set
`DEV_CONTROLLER_EMAIL` only when a different local email is needed.

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
