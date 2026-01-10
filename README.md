# Jump Backend

FastAPI backend for the Jump email app.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your credentials.

## Running

```bash
uvicorn app.main:app --reload
```

Runs on http://localhost:8000

## Database

Using PostgreSQL. Run migrations with:

```bash
alembic upgrade head
```

To create a new migration after changing models:

```bash
alembic revision --autogenerate -m "description"
```

## Tests

```bash
pytest
```
