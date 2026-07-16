# roadbogo-api

Roadbogo service API server.

## Stack

- Python 3.11+
- FastAPI- MariaDB 10.11
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
python3 -m venv .venvuvicorn app.main:app --reload --port 8000
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

# Database Migration

Apply the verified MVP schema, reference seed data, and views:

python -m alembic upgrade head
Compare a migrated test database with the SQL reference database:

python scripts/compare_mvp_databases.py `
  --reference roadbogo_test `
  --migration roadbogo_orm_test
The migration-managed database includes Alembic's alembic_version table in addition to the 44 MVP tables. The comparison script excludes only that table.