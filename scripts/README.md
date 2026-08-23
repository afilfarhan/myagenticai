# SentinelChain Scripts

| Script | Purpose | Requires |
|---|---|---|
| `seed.py` | Populate the DB with 50 dummy suppliers via `POST /api/v1/seed` | Running backend (`python scripts/seed.py --url http://localhost:8000`) |
| `run_evals.py` | Run the W&B Weave evaluation suite on the golden set | Full backend requirements + W&B credentials, run from repo root |

## Database migrations (Alembic)

Schema is managed by Alembic from `backend/migrations`:

```powershell
cd backend
.venv\Scripts\alembic upgrade head                      # apply migrations
.venv\Scripts\alembic revision --autogenerate -m "..."  # after model changes
```

Notes:
- The URL comes from `DATABASE__URL` env or `backend/config.yaml`.
- Dev/test convenience still auto-creates tables via `create_all`; use
  migrations for any real environment so schema changes are tracked.


## Typical dev flow

```powershell
# terminal 1 - backend (Python 3.11 or 3.12; crewai requires <3.13)
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\uvicorn app.main:app --reload

# terminal 2 - frontend
cd frontend
npm install
npm run dev

# seed sample data
python scripts/seed.py
```
