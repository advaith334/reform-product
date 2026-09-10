"""FastAPI application factory.

Run it with::

    uv run uvicorn reform.api.app:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .. import db
from ..config import CORS_ORIGINS, UPLOADS_DIR, database_url
from .routes import router

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Own the connection pool and make sure the schema is in place.

    ``dict_row`` matches what ``db.connect()`` uses, so the queries in db.py work
    against a pooled connection unchanged.
    """
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    pool = ConnectionPool(
        database_url(),
        min_size=1,
        max_size=10,
        kwargs={"row_factory": dict_row},
        open=True,
    )
    pool.wait(timeout=30)

    with pool.connection() as conn:
        db.init_schema(conn)

    app.state.pool = pool
    try:
        yield
    finally:
        pool.close()


app = FastAPI(
    title="Reform",
    description="Extract structured fields from trade documents with Mistral OCR.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
