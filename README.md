# Bulk Certificate Generator

A backend API built with **FastAPI**, **PostgreSQL**, **Celery**, and
**ReportLab** that accepts certificate generation requests for a list of
recipients and generates PDF certificates using a predefined template.

---

## Features

- **Bulk processing** — submit hundreds of recipients in a single API request
- **Background generation** — Celery workers generate PDFs asynchronously
- **Real-time tracking** — poll the batch status to see progress as each
  certificate is generated
- **Failure isolation** — one certificate's failure doesn't block the rest
- **PDF download** — retrieve individual certificates as PDF files
- **Input validation** — email format, date format, required fields

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| API framework | FastAPI |
| Database | PostgreSQL 15 |
| Background tasks | Celery 5 + Redis 7 |
| PDF generation | ReportLab |
| ORM | SQLAlchemy 2.0 (async) |
| Validation | Pydantic v2 |
| Testing | pytest + httpx |

---

## Project Structure

```
├── app/
│   ├── main.py                         # FastAPI entry point
│   ├── config.py                       # Environment-based settings
│   ├── database.py                     # Async engine & session
│   ├── models.py                       # BatchRequest, Certificate models
│   ├── schemas.py                      # Pydantic schemas
│   ├── worker.py                       # Celery app instance
│   ├── routers/
│   │   └── certificates.py            # API endpoints
│   └── services/
│       ├── certificate_generator.py   # PDF generation logic
│       └── batch_processor.py         # Celery background task
├── certificates/                       # Generated PDFs (auto-created)
├── tests/
│   ├── conftest.py                     # Test fixtures
│   └── test_api.py                     # Test suite
├── docker-compose.yml                  # PostgreSQL + Redis
├── requirements.txt
├── .env                                # Environment variables
└── README.md
```

---

## Setup

### Prerequisites

- Python 3.10+
- Docker & Docker Compose (for PostgreSQL and Redis)

### 1. Start infrastructure services

```bash
docker-compose up -d
```

This starts PostgreSQL (port 5432) and Redis (port 6379).

### 2. Create a virtual environment and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment (optional)

The `.env` file contains sensible defaults. Edit it if your database
credentials differ.

---

## Running the Application

### Start the API server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API is available at **http://localhost:8000**.
Interactive docs at **http://localhost:8000/docs**.

### Start the Celery worker

Open a **second terminal** (with the venv activated):

```bash
celery -A app.worker:celery_app worker --loglevel=info
```

> **Both the API server and the Celery worker must be running** for
> certificates to be generated.

---

## Running Tests

### 1. Create the test database

```bash
docker exec -it cert_generator_postgres psql -U postgres -c "CREATE DATABASE test_certificates_db;"
```

### 2. Run the test suite

```bash
pytest tests/ -v
```

The tests mock Celery (no Redis required for testing) and use an isolated
test database.

---

## API Endpoints

### Submit a certificate generation request

```
POST /api/batch-requests
```

**Request body:**
```json
{
  "course_name": "Advanced Python Programming",
  "issue_date": "2026-10-08",
  "recipients": [
    {"name": "Alice Johnson", "email": "alice@example.com"},
    {"name": "Bob Smith", "email": "bob@example.com"},
    {"name": "Charlie Lee", "email": "charlie@example.com"}
  ]
}
```

**Response (201):**
```json
{
  "id": "a1b2c3d4-...",
  "status": "pending",
  "total_recipients": 3,
  "successful_count": 0,
  "failed_count": 0,
  "course_name": "Advanced Python Programming",
  "issue_date": "2026-10-08",
  "created_at": "2026-10-08T00:00:00Z",
  "updated_at": "2026-10-08T00:00:00Z"
}
```

### Check batch status and progress

```
GET /api/batch-requests/{batch_id}
```

Returns the batch summary plus all individual certificate statuses.

### List all batch requests

```
GET /api/batch-requests?skip=0&limit=20
```

### List certificates for a batch

```
GET /api/batch-requests/{batch_id}/certificates
GET /api/batch-requests/{batch_id}/certificates?status=success
```

### Download a generated certificate

```
GET /api/certificates/{certificate_id}/download
```

Returns the PDF file. Only available when the certificate status is `success`.

### Health check

```
GET /health
```

---

## Example Workflow with curl

```bash
# 1. Submit a batch
curl -X POST http://localhost:8000/api/batch-requests \
  -H "Content-Type: application/json" \
  -d '{
    "course_name": "Machine Learning Fundamentals",
    "issue_date": "2026-10-08",
    "recipients": [
      {"name": "Alice Johnson", "email": "alice@example.com"},
      {"name": "Bob Smith", "email": "bob@example.com"}
    ]
  }'

# 2. Check status (replace BATCH_ID with the id from step 1)
curl http://localhost:8000/api/batch-requests/BATCH_ID

# 3. Download a certificate (replace CERT_ID)
curl -o certificate.pdf http://localhost:8000/api/certificates/CERT_ID/download
```

---

## Design Decisions

### Why background processing (Celery)?

Generating PDFs for hundreds of recipients synchronously would block the
API server. Celery processes the batch in a separate worker, keeping the
API responsive. The client receives an immediate response and can poll
for progress.

### Why per-certificate commits?

Each certificate is committed to the database individually so that:
- Progress is visible in real time.
- A crash doesn't lose already-completed work.
- Failed certificates are recorded without rolling back successful ones.

### Why separate async/sync database sessions?

FastAPI runs on an async event loop (asyncpg), while Celery workers are
synchronous (psycopg2). Using the correct driver for each context avoids
blocking the event loop or adding unnecessary async overhead.

### Why UUID primary keys?

UUIDs are safe to expose externally (no information leakage), don't require
central coordination, and are natively supported by PostgreSQL.

---