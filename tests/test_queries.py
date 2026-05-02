"""
tests/test_queries.py
---------------------
End-to-end query-type coverage tests.
Verifies that all required query types produce valid (non-error) responses.
Run with:  pytest tests/test_queries.py -v
Requires a live DB + .env.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from database.connection import init_pool, close_pool


@pytest_asyncio.fixture(scope="function")
async def client():
    await init_pool()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    await close_pool()


QUERY_CASES = [
    # (label, question, required_columns_hint)
    ("direct_lookup",       "Show me all customers from New York",               None),
    ("filtering",           "Which products cost more than $100?",               None),
    ("aggregation_count",   "How many sales were made in 2023?",                 None),
    ("aggregation_sum",     "What is total revenue per product category?",       "category"),
    ("aggregation_avg",     "What is the average salary per department?",        "department"),
    ("join_two_tables",     "List customer names and what products they bought", None),
    ("join_three_tables",   "Which employees sold the most Electronics items?",  None),
    ("temporal_year",       "How many sales happened last year?",                None),
    ("temporal_quarter",    "Total revenue in Q1 2023",                          None),
    ("temporal_this_year",  "How many new customers signed up this year?",       None),
    ("projects_active",     "List all active projects",                          None),
    ("projects_budget",     "What is the total budget across all projects?",     None),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("label,question,col_hint", QUERY_CASES)
async def test_query_type(client, label, question, col_hint):
    resp = await client.post("/ask", json={"question": question})
    assert resp.status_code == 200, f"[{label}] HTTP {resp.status_code}"
    data = resp.json()

    # Must not error
    assert data["error"] is None, f"[{label}] Error: {data['error']}"

    # Must have an answer
    assert data["answer"], f"[{label}] Empty answer"

    # Must have generated a query
    assert data["sql_query"], f"[{label}] No SQL generated"

    # If a column hint provided, check it appears
    if col_hint:
        cols_lower = [c.lower() for c in data["columns"]]
        assert any(col_hint in c for c in cols_lower), \
            f"[{label}] Expected column containing '{col_hint}' in {data['columns']}"
