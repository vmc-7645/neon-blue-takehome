# Neon Blue Take-Home

## Quick Start

Docker build
```bash
docker compose up -d --build
```

Health check
```bash
curl.exe -H "Authorization: Bearer dev-token-1" http://localhost:8000/health
```

## Example Usage

### Create an experiment
```bash
curl -X POST http://localhost:8000/experiments \
  -H "Authorization: Bearer dev-token-1" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "CTA Test",
    "description": "A/B CTA",
    "variants": [
      {"key": "control", "allocation_percent": 50},
      {"key": "treatment", "allocation_percent": 50}
    ]
  }'
```

### Get assignment (idempotent)
```bash
curl http://localhost:8000/experiments/{experiment_id}/assignment/user123 \
  -H "Authorization: Bearer dev-token-1"
```

### Record an event
```bash
curl -X POST http://localhost:8000/events \
  -H "Authorization: Bearer dev-token-1" \
  -H "Content-Type: application/json" \
  -d '{
    "experiment_id": "{experiment_id}",
    "user_id": "user123",
    "type": "click",
    "timestamp": "2025-01-01T00:00:00Z",
    "properties": {"button": "cta"}
  }'
```

### Fetch experiment results
```bash
curl "http://localhost:8000/experiments/{experiment_id}/results?event_type=click" \
  -H "Authorization: Bearer dev-token-1"
```
