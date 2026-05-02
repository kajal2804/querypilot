"""
database/connection.py
----------------------
asyncpg connection pool + schema creation + query helpers.
The pool is initialised once at FastAPI lifespan startup and shared
across all requests.
"""

import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/ragdb"
)

# Module-level pool reference — set by init_pool() at startup
_pool: asyncpg.Pool | None = None


# ── lifecycle ─────────────────────────────────────────────────────────────────

async def init_pool() -> None:
    """Create the connection pool.  Call once at app startup."""
    global _pool
    _pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )
    await _create_schema()


async def close_pool() -> None:
    """Gracefully close the pool.  Call at app shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialised. Call init_pool() first.")
    return _pool


# ── schema ────────────────────────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id   SERIAL PRIMARY KEY,
    first_name    VARCHAR(50)   NOT NULL,
    last_name     VARCHAR(50)   NOT NULL,
    email         VARCHAR(100)  UNIQUE NOT NULL,
    city          VARCHAR(50),
    country       VARCHAR(50),
    signup_date   DATE          NOT NULL
);

CREATE TABLE IF NOT EXISTS employees (
    employee_id   SERIAL PRIMARY KEY,
    first_name    VARCHAR(50)   NOT NULL,
    last_name     VARCHAR(50)   NOT NULL,
    department    VARCHAR(50)   NOT NULL,
    job_title     VARCHAR(80)   NOT NULL,
    hire_date     DATE          NOT NULL,
    salary        NUMERIC(10,2) NOT NULL
);

CREATE TABLE IF NOT EXISTS products (
    product_id    SERIAL PRIMARY KEY,
    name          VARCHAR(100)  NOT NULL,
    category      VARCHAR(50)   NOT NULL,
    unit_price    NUMERIC(10,2) NOT NULL,
    stock_qty     INT           NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sales (
    sale_id       SERIAL PRIMARY KEY,
    customer_id   INT           NOT NULL REFERENCES customers(customer_id),
    employee_id   INT           NOT NULL REFERENCES employees(employee_id),
    product_id    INT           NOT NULL REFERENCES products(product_id),
    quantity      INT           NOT NULL CHECK (quantity > 0),
    total_amount  NUMERIC(12,2) NOT NULL,
    sale_date     DATE          NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    project_id    SERIAL PRIMARY KEY,
    name          VARCHAR(120)  NOT NULL,
    department    VARCHAR(50)   NOT NULL,
    lead_employee_id INT        REFERENCES employees(employee_id),
    status        VARCHAR(30)   NOT NULL DEFAULT 'active',
    budget        NUMERIC(12,2) NOT NULL,
    start_date    DATE          NOT NULL,
    end_date      DATE
);

CREATE INDEX IF NOT EXISTS idx_sales_date        ON sales(sale_date);
CREATE INDEX IF NOT EXISTS idx_sales_customer    ON sales(customer_id);
CREATE INDEX IF NOT EXISTS idx_sales_employee    ON sales(employee_id);
CREATE INDEX IF NOT EXISTS idx_sales_product     ON sales(product_id);
CREATE INDEX IF NOT EXISTS idx_projects_dept     ON projects(department);
CREATE INDEX IF NOT EXISTS idx_projects_status   ON projects(status);
"""


async def _create_schema() -> None:
    async with get_pool().acquire() as conn:
        await conn.execute(_SCHEMA_SQL)


# ── query helpers ─────────────────────────────────────────────────────────────

async def execute_query(sql: str, *args) -> list[dict]:
    """
    Run a SELECT and return rows as a list of dicts.
    Raises asyncpg.PostgresError on failure.
    """
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(sql, *args)
        return [dict(r) for r in rows]


async def execute_write(sql: str, *args) -> str:
    """
    Run INSERT / UPDATE / DELETE and return the status string.
    (Used by seed.py only — agents never write.)
    """
    async with get_pool().acquire() as conn:
        return await conn.execute(sql, *args)


async def fetch_schema_info() -> list[dict]:
    """
    Return raw schema rows from information_schema (columns + FK constraints).
    Used by SchemaAgent.
    """
    sql = """
        SELECT
            c.table_name,
            c.column_name,
            c.data_type,
            c.is_nullable,
            tc.constraint_type
        FROM information_schema.columns c
        LEFT JOIN information_schema.key_column_usage kcu
            ON  c.table_name   = kcu.table_name
            AND c.column_name  = kcu.column_name
            AND c.table_schema = kcu.table_schema
        LEFT JOIN information_schema.table_constraints tc
            ON  kcu.constraint_name = tc.constraint_name
            AND kcu.table_schema    = tc.table_schema
        WHERE c.table_schema = 'public'
        ORDER BY c.table_name, c.ordinal_position
    """
    return await execute_query(sql)


async def fetch_foreign_keys() -> list[dict]:
    """Return FK relationships for SchemaAgent."""
    sql = """
        SELECT
            kcu.table_name,
            kcu.column_name,
            ccu.table_name  AS foreign_table,
            ccu.column_name AS foreign_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
           AND tc.table_schema    = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
           AND ccu.table_schema    = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema    = 'public'
    """
    return await execute_query(sql)
