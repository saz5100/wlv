"""
Database connection and schema setup for the WLV CS learning platform.
Consolidated to PostgreSQL + pgvector (VM database).
"""
import os
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager
import psycopg2.extras
import asyncio

# Retrieve DSN from env variables or fallback to dev VM DSN
PG_DSN = os.environ.get(
    "WLV_PG_DSN", 
    "dbname=wlv_kb user=wlv_app password=wlv_kb_2026 host=db port=5432 client_encoding=utf8"
)

# Initialize connection pool: minimum 2, maximum 20 connections
pool = ThreadedConnectionPool(2, 20, dsn=PG_DSN)

def get_db():
    """Get a raw database connection from the pool."""
    return pool.getconn()

def release_db(conn):
    """Release a database connection back to the pool."""
    pool.putconn(conn)

@contextmanager
def get_db_cursor():
    """Context manager for obtaining a database cursor with auto-commit."""
    conn = pool.getconn()
    conn.autocommit = True
    try:
        yield conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    finally:
        pool.putconn(conn)

def query(sql_str, params=None):
    """Execute a query and return all results as dicts."""
    with get_db_cursor() as cur:
        cur.execute(sql_str, params or ())
        return list(cur.fetchall())

def query_one(sql_str, params=None):
    """Execute a query and return the first result or None."""
    rows = query(sql_str, params)
    return rows[0] if rows else None

def execute(sql_str, params=None):
    """Execute a write query and return rowcount."""
    with get_db_cursor() as cur:
        cur.execute(sql_str, params or ())
        return cur.rowcount

# Async wrappers — run sync DB calls in thread pool to avoid blocking event loop
async def query_async(sql_str, params=None):
    return await asyncio.to_thread(query, sql_str, params)

async def query_one_async(sql_str, params=None):
    return await asyncio.to_thread(query_one, sql_str, params)

async def execute_async(sql_str, params=None):
    return await asyncio.to_thread(execute, sql_str, params)

# Schema versioning compatibility no-ops
SCHEMA_VERSION = 9

def init_db():
    """Schema is managed centrally in PostgreSQL, this is a no-op."""
    print("✅ Database schema initialised (PostgreSQL)")

def ensure_default_user():
    """Create default user if not exists."""
    execute(
        "INSERT INTO users (username, display_name) VALUES (%s, %s) ON CONFLICT(username) DO NOTHING",
        ("shazad", "Shazad")
    )

def check_schema():
    """Check schema version (no-op placeholder)."""
    return SCHEMA_VERSION


# ═══════════════════════════════════════════════════════════════════════
# Shared embedding utility — used by RAG, wiki search, exam marking
# ═══════════════════════════════════════════════════════════════════════

OLLAMA_EMBED_URL = "http://ollama.lan:11434/api/embed"
EMBED_MODEL = "all-minilm"

def get_embedding(text: str):
    """Get embedding vector from Ollama all-minilm (384d)."""
    import httpx
    try:
        resp = httpx.post(OLLAMA_EMBED_URL, json={"model": EMBED_MODEL, "input": text[:8000]}, timeout=30)
        return resp.json()["embeddings"][0]
    except Exception:
        return None
