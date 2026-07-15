# roadbogo-api

Roadbogo service API server.

## Stack

- Python 3.11+
- FastAPI
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
