# Neon Blue Take-Home

Docker build
```bash
docker compose up -d --build
```

Health check
```bash
curl.exe -H "Authorization: Bearer dev-token-1" http://localhost:8000/health
```



$exp="00010002000300040001000200030004"
curl.exe -s -H "Authorization: Bearer dev-token-1" http://localhost:8000/experiments/$exp/assignment/user123
curl.exe -s -H "Authorization: Bearer dev-token-1" http://localhost:8000/experiments/$exp/assignment/user123
