# Experimentation API

A lightweight experimentation (A/B testing) API built with FastAPI, PostgreSQL, and SQLAlchemy, designed to demonstrate core experimentation concepts: experiment lifecycle management, idempotent user assignment, event attribution, and results analysis.

## Quick Start

### Prerequisites
- Docker
- Docker Compose

### Start the service
```bash
docker compose up -d --build
```

### Verify health
```bash
curl.exe -H "Authorization: Bearer dev-token-1" http://localhost:8000/health
```

## Example Usage

You can explore the API in your browser via:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Demo Scripts

This repository includes scripts that demonstrate all required behaviors:
- Create an experiment with variants
- Get idempotent user assignments
- Record events with proper attribution
- Fetch and analyze results

#### PowerShell (Windows)

```powershell
# Run the demo script
powershell -ExecutionPolicy Bypass -File .\scripts\demo.ps1

# Optional overrides
$env:BASE_URL="http://localhost:8000"
$env:API_TOKEN="dev-token-1"
powershell -ExecutionPolicy Bypass -File .\scripts\demo.ps1
```

#### Bash (Linux/Mac/WSL)

```bash
# Make script executable and run
chmod +x scripts/demo.sh
./scripts/demo.sh

# Optional overrides
BASE_URL="http://localhost:8000" API_TOKEN="dev-token-1" ./scripts/demo.sh
```

## Features

- **Idempotent assignment**: A user will always receive the same variant for a given experiment
- **Traffic allocation support**: Variants support configurable percentage-based allocation
- **Event attribution correctness**: Only events occurring after a user's assignment timestamp are counted
- **Experiment lifecycle management**: Experiments can be stopped to freeze new assignments while preserving existing ones
- **Lightweight caching**: A small in-memory TTL cache reduces repeat database reads for assignments
- **Production-friendly schema**: Indexed PostgreSQL schema with Alembic migrations

### Documentation

This service uses FastAPI, which automatically generates interactive API documentation from type hints and request/response models.

Once the service is running, documentation is available at:

- Swagger UI: http://localhost:8000/docs
- ReDoc (read-only): http://localhost:8000/redoc

These pages act as the primary API reference, showing:
- Endpoint descriptions
- Required authentication
- Request and response schemas
- Example payloads

## API Endpoints

### Create Experiment
`POST /experiments`

Creates a new experiment with variants.

**Request**
```bash
curl -X POST http://localhost:8000/experiments \
  -H "Authorization: Bearer dev-token-1" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "CTA Test",
    "description": "Homepage CTA experiment",
    "variants": [
      {"key": "control", "allocation_percent": 50, "metadata": {}},
      {"key": "treatment", "allocation_percent": 50, "metadata": {}}
    ]
  }'
```

**Response**: `201 Created`

### Get User Assignment
`GET /experiments/{id}/assignment/{user_id}`

- Idempotent
- Deterministic once assigned
- Respects experiment status

**Example**:
```bash
curl "http://localhost:8000/experiments/{experiment_id}/assignment/user123" \
  -H "Authorization: Bearer dev-token-1"
```

### Record Event
`POST /events`

Records an event for a user.

**Request**
```bash
curl -X POST http://localhost:8000/events \
  -H "Authorization: Bearer dev-token-1" \
  -H "Content-Type: application/json" \
  -d '{
    "experiment_id": "<uuid>",
    "user_id": "user123",
    "type": "click",
    "timestamp": "2025-01-01T00:00:00Z",
    "properties": {
      "button": "cta"
    }
  }'
```

### Get Experiment Results
`GET /experiments/{id}/results`

**Query Parameters**:
- `event_type` (optional)
- `start` / `end` (optional ISO timestamps)
- `group_by` (variant, day — extensible)

**Example**:
```bash
curl "http://localhost:8000/experiments/{experiment_id}/results?event_type=click" \
  -H "Authorization: Bearer dev-token-1"
```

### Stop Experiment
`POST /experiments/{id}/status`

Stops an experiment and freezes new assignments.

**Request**
```bash
curl -X POST http://localhost:8000/experiments/{id}/status \
  -H "Authorization: Bearer dev-token-1" \
  -H "Content-Type: application/json" \
  -d '{"status": "stopped"}'
```

**Behavior**:
- Existing assignments remain valid
- New assignments are rejected with `409 Conflict`

## Architecture

```
FastAPI
 ├── Routers (experiments, events)
 ├── Services
 │   ├── assignment logic
 │   ├── results aggregation
 │   └── assignment cache
 ├── SQLAlchemy ORM
 ├── PostgreSQL
 └── Alembic migrations
```

- FastAPI for clear, typed API boundaries
- SQLAlchemy ORM for explicit query control
- Alembic for schema migrations
- Docker Compose for reproducible local setup

## Data Model

Core tables:
- experiments
- variants
- assignments
- events

Key properties:
- Composite uniqueness on (experiment_id, user_id) for assignments
- Time-based indexing for event queries
- All attribution joins enforce event.timestamp >= assignment.assigned_at

## Authentication

All endpoints require Bearer token authentication.

Tokens are configured via environment variable:
```
API_TOKENS=dev-token-1,dev-token-2
```

Invalid or missing tokens return `401 Unauthorized`.

## Testing

Tests are written with pytest and FastAPI's TestClient.

Covered behaviors:
- Assignment idempotency
- Event attribution only after assignment
- Experiment stop freezes new assignments

Run tests:
```bash
docker compose exec api pytest -q
```

## Design Decisions & Tradeoffs

- **Events require assignment**: Prevents orphan events and simplifies attribution logic
- **Post-assignment filtering in results**: Attribution is enforced even if events are backfilled
- **In-memory TTL cache**: Reduces DB load while keeping correctness via invalidation on experiment stop
- **Explicit stop behavior**: Experiment lifecycle is a first-class concept, not an afterthought

## Future Improvements

- Add more sophisticated statistical analysis (p-values, confidence intervals)
- Implement experiment analysis UI
- Add support for feature flags
- Add rate limiting and request validation
- Implement more granular permissions system
