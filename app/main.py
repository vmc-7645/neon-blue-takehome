from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse
from fastapi import status
from app.auth import require_bearer_token
from app.routers.experiments import router as experiments_router


app = FastAPI(title="Experimentation API", version="0.1.0")

# Include experiment api routers
app.include_router(experiments_router)

# Global auth: every request must include Bearer token
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Let docs load without auth if you want; otherwise remove this block.
    if request.url.path in ("/docs", "/openapi.json", "/redoc", "/health"):
        return await call_next(request)

    auth = request.headers.get("Authorization")
    # reuse the same validation logic
    try:
        require_bearer_token(auth)
    except Exception as e:
        # FastAPI middleware can't directly raise HTTPException reliably in all setups
        detail = getattr(e, "detail", "Unauthorized")
        code = getattr(e, "status_code", status.HTTP_401_UNAUTHORIZED)
        return JSONResponse(status_code=code, content={"detail": detail})

    return await call_next(request)


@app.get("/health")
def health():
    return {"ok": True}
