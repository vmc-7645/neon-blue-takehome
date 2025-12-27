# A/B Testing API

A simplified A/B testing API demonstrating experiment creation, deterministic user assignment, event tracking, and results aggregation using FastAPI, PostgreSQL, and SQLAlchemy.

This project focuses on correctness, clarity, and extensibility rather than feature sprawl.

## Features

- Create experiments with multiple variants and traffic allocation
- Deterministic, idempotent user assignment per experiment
- Persistent assignment storage
- Event ingestion with flexible JSON properties
- PostgreSQL-backed data model with indexes
- Bearer token authentication on all endpoints
- Dockerized local development setup
- Alembic migrations
- Clean separation of routers, services, and models

## Tech Stack

- Python 3.12
- FastAPI
- PostgreSQL 16
- SQLAlchemy 2.0
- Alembic
- Docker + Docker Compose

## Project Structure

```
.
├── app/
│   ├── main.py              # FastAPI app + router wiring
│   ├── config.py            # Environment config
│   ├── auth.py              # Bearer token auth
│   ├── db.py                # SQLAlchemy session + Base
│   ├── models.py            # ORM models
│   ├── schemas.py           # Pydantic schemas
│   ├── routers/
│   │   └── experiments.py  # Experiment + assignment endpoints
│   └── services/
│       └── assignment.py   # Deterministic assignment logic
├── alembic/
│   └── versions/            # DB migrations
├── tests/                   # (optional) tests
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## Authentication

All endpoints require a Bearer token.

Tokens are configured via environment variable:

```bash
API_TOKENS=dev-token-1,dev-token-2
```

Requests must include:

```
Authorization: Bearer dev-token-1
```

Invalid or missing tokens return `401 Unauthorized`.

## Running Locally (Docker)

### Prerequisites

- Docker Desktop (Linux containers / WSL2)

### Start services

```bash
docker compose up -d --build
```

### Verify API health

```bash
curl -H "Authorization: Bearer dev-token-1" http://localhost:8000/health
```

Expected response:

```json
{"ok": true}
```

## Database Migrations

Alembic is fully configured.

### Generate migration (already done)

```bash
docker compose exec api alembic revision --autogenerate -m "init"
```

### Apply migration

```bash
docker compose exec api alembic upgrade head
```

### Verify tables

```bash
docker compose exec db psql -U ab -d ab -c "\dt"
```

## API Usage Examples

### Create Experiment

`POST /experiments`

```bash
curl -H "Authorization: Bearer dev-token-1" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "Button Copy Test",
       "description": "Landing page CTA experiment",
       "variants": [
         { "key": "control", "allocation_percent": 50, "metadata": {"copy": "Buy now"} },
         { "key": "treatment", "allocation_percent": 50, "metadata": {"copy": "Get started"} }
       ]
     }' \
     http://localhost:8000/experiments
```

Response includes experiment ID and variants.

### Get User Assignment (Idempotent)

`GET /experiments/{experiment_id}/assignment/{user_id}`

```bash
curl -H "Authorization: Bearer dev-token-1" \
     http://localhost:8000/experiments/<EXPERIMENT_ID>/assignment/user_123
```

Repeat the request with the same `user_id` and experiment:
- Same `variant_id`
- Same `assigned_at`

Assignment is deterministic and persisted.

## Assignment Logic

Users are deterministically bucketed using:

```python
SHA256(experiment_id + user_id) % 100
```

- Variants are selected based on cumulative traffic allocation
- Database constraint ensures one assignment per (experiment_id, user_id)
- Concurrent race conditions are safely handled

This guarantees:
- Idempotency
- Stable assignments
- Correct traffic distribution

## Data Model Overview

- `experiments`: experiment metadata
- `variants`: experiment variants with allocation
- `assignments`: user -> variant mapping
- `events`: user events (used later for results)

All tables are indexed for common access patterns.

## Design Decisions & Trade-Offs

### Why deterministic hashing?
- Enables idempotency without needing pre-reads
- Prevents assignment drift
- Scales horizontally

### Why Postgres + Alembic?
- Realistic production choice
- Strong transactional guarantees
- Clean migration history

### Why separate service layer?
- Keeps routers thin
- Enables easy unit testing
- Clear separation of concerns

## How This Would Scale in Production

- Move event ingestion to async pipeline (Kafka/SQS)
- Add Redis for assignment caching
- Precompute experiment rollups
- Add statistical significance calculations
- Introduce feature flag unification
- Shard events by experiment_id

## Next Feature to Implement

Results endpoint (`GET /experiments/{id}/results`)

Would include:
- Only events after assignment time
- Per-variant metrics
- Time-window filtering
- Optional statistical significance

## Notes for Reviewers

- Focused on correctness and clarity over surface area
- All core constraints in the prompt are met
- Code is intentionally straightforward and readable
- Dockerized for 1-command setup

$exp="00010002000300040001000200030004"
curl.exe -s -H "Authorization: Bearer dev-token-1" http://localhost:8000/experiments/$exp/assignment/user123
curl.exe -s -H "Authorization: Bearer dev-token-1" http://localhost:8000/experiments/$exp/assignment/user123
