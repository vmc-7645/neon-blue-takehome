# Experimentation Platform Take-Home

## 1. Overview

This project implements a simplified A/B experimentation service designed to mirror the core responsibilities of an experimentation platform engineer:

- Deterministic, idempotent user assignment
- Flexible experiment configuration and traffic allocation
- Event ingestion with temporal correctness
- Results aggregation suitable for multiple stakeholder views
- Clear operational and extension paths

The system favors clarity, correctness, and extensibility over premature optimization, while still demonstrating awareness of production-scale concerns.

## 2. High-Level Architecture

### Stack

- **API**: FastAPI (Python)
- **Server**: Uvicorn
- **Database**: PostgreSQL (via SQLAlchemy ORM)
- **Migrations**: Alembic
- **Auth**: Bearer token middleware
- **Infra**: Docker + docker-compose
- **Testing**: Pytest + FastAPI TestClient

### Core Components

- `routers/` – HTTP API endpoints
- `models/` – SQLAlchemy data models
- `services/` – Business logic (assignment, results aggregation)
- `cache/` – Lightweight in-memory assignment cache
- `db/` – Session management and migrations
- `tests/` – Behavioral tests for critical paths

The design follows a thin-controller, fat-service pattern to keep business logic testable and isolated from HTTP concerns.

## 3. Data Model & Schema Design

### Core Tables

#### Experiment
Represents a single A/B (or multivariate) experiment.

**Key fields**:
- `id`
- `name`
- `description`
- `status` (running, stopped)
- `created_at`

**Indexes**:
- `id` (primary key)
- `status` (for filtering active experiments)

#### Variant
Represents a treatment within an experiment.

**Key fields**:
- `id`
- `experiment_id`
- `key` (human-readable identifier)
- `traffic_allocation` (percentage)
- `metadata` (JSON)

**Indexes**:
- `(experiment_id, key)` unique constraint

#### Assignment
Represents a deterministic assignment of a user to a variant.

**Key fields**:
- `experiment_id`
- `user_id`
- `variant_id`
- `assigned_at`

**Indexes**:
- `(experiment_id, user_id)` unique constraint → guarantees idempotency

#### Event
Represents an interaction or conversion.

**Key fields**:
- `experiment_id`
- `user_id`
- `type`
- `timestamp`
- `properties` (JSON)

**Indexes**:
- `(experiment_id, type, timestamp)`
- `(experiment_id, user_id, timestamp)`

### Design Rationale

- Assignments are first-class entities to guarantee idempotency and temporal correctness.
- Events are append-only and immutable.
- Temporal joins enforce "events only count after assignment".

## 4. Assignment Logic

### Goals
- Idempotent per `(experiment_id, user_id)`
- Supports arbitrary traffic splits
- Deterministic and auditable

### Flow
1. Check in-memory cache for existing assignment.
2. If cache miss, query database for assignment.
3. If assignment exists, return it and populate cache.
4. If experiment is stopped, reject new assignments.
5. Otherwise:
   - Select variant based on traffic allocation weights.
   - Persist assignment transactionally.
   - Cache the result.

### In-Memory Cache
A small TTL-based cache is used to reduce repeated DB reads for hot users.

**Characteristics**:
- TTL: 5 minutes
- Key: `(experiment_id, user_id)`
- Explicit invalidation when experiment status changes

This cache is non-authoritative and safe to evict at any time.

## 5. Event Ingestion

### Guarantees
- Events must reference an existing experiment.
- Events are only accepted for users with assignments.
- Assignment timestamp is used as a lower bound for results.

This enforces correctness while keeping ingestion logic simple.

**Trade-off**: Some systems allow pre-assignment events; here, rejecting them simplifies reasoning and avoids ambiguous attribution.

## 6. Results Endpoint Design Philosophy

**Endpoint**: `GET /experiments/{id}/results`

### Supported Query Parameters
- `event_type`
- `start`, `end` (time range)
- `group_by` (currently variant; extensible)

### Aggregation Guarantees
- Only events occurring after assignment are counted.
- Joins enforce `(experiment_id, user_id)` consistency.
- Distinct-user counts prevent double-counting conversions.

### Output Structure
The response is intentionally verbose and structured:
- `query` – echoes filters for auditability
- `totals` – per-variant and overall metrics
- `exec_summary` – high-level comparison (lift, z-score, p-value)
- `definitions` – metric semantics (for non-technical consumers)
- `diagnostics` – internal visibility and debugging aids

This structure supports:
- Real-time dashboards
- Analyst deep-dives
- Executive summaries
- Programmatic consumption

## 7. Statistical Analysis

The results endpoint includes basic statistical comparisons:
- Absolute lift
- Relative lift
- Z-score
- P-value
- Significance flag (α = 0.05)

These are intentionally lightweight and illustrative rather than exhaustive.

**Future extension**:
- Bayesian methods
- Sequential testing
- Guardrail metrics
- Multiple hypothesis correction

## 8. Authentication & Security

- All endpoints require Bearer token authentication.
- Tokens are validated against a configured allowlist.
- Unauthorized requests return 401 or 403 appropriately.

This is intentionally simple but mirrors internal service-to-service auth patterns.

## 9. Testing Strategy

Tests focus on behavioral correctness, not implementation details.

**Covered paths**:
- Assignment idempotency
- Event attribution after assignment
- Experiment stop behavior
- Results aggregation correctness

Tests run inside Docker against a real PostgreSQL instance with Alembic migrations applied, ensuring parity with runtime behavior.

## 10. Infrastructure & Operations

- Docker Compose orchestrates API + DB.
- Environment variables control DB and auth.
- Alembic manages schema evolution.
- FastAPI auto-generates API documentation at `/docs` and `/redoc`.

## 11. Trade-offs & Decisions

### What was optimized for
- Correctness over throughput
- Explicitness over cleverness
- Ease of evaluation by reviewers

### What was intentionally deferred
- Distributed caching (e.g. Redis)
- Async event ingestion
- Streaming pipelines
- Feature flag unification

These are natural next steps once scale or requirements demand them.

## 12. Production Extension Plan

If evolving this into a production system, the next priorities would be:

1. Replace in-memory cache with Redis
2. Introduce async ingestion (Kafka / PubSub)
3. Add experiment lifecycle governance (guardrails, auto-stop)
4. Support multi-metric experiments
5. Expand statistical tooling
6. Add role-based access control