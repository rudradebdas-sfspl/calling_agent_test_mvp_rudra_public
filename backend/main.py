"""FastAPI application entrypoint."""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import agents, kb, policy, providers, sessions, troubleshooting
from backend.services.redis.cache import close_cache, get_cache
import backend.models.kb  # noqa: F401 — ensures kb_chunks table is registered with Base

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    ok = await get_cache().ping()
    log.info("Redis ping: %s", "ok" if ok else "FAILED")
    yield
    await close_cache()


app = FastAPI(title="Customizable Voice Agent Platform", lifespan=lifespan)

# Comma-separated origins, for example:
# CORS_ORIGINS=http://203.0.113.10:5173,http://localhost:5173
cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents.router)
app.include_router(providers.router)
app.include_router(sessions.router)
app.include_router(kb.router)
app.include_router(troubleshooting.router)
app.include_router(policy.router)


@app.get("/health")
def health():
    return {"status": "ok"}