# roadbogo-api

Roadbogo 서비스 API 서버입니다.

## Stack

- Python 3.11+
- FastAPI
- Uvicorn

## Getting Started

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

API 문서는 `http://localhost:8000/docs` 에서 확인할 수 있습니다.
