"""
tests/test_api.py
-----------------
Full response validation tests for all endpoints.
Run with:  pytest tests/test_api.py -v
"""

import time
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from database.connection import init_pool, close_pool

EXPECTED_TABLES = {"customers", "employees", "products", "sales", "projects"}


@pytest_asyncio.fixture(scope="function")
async def client():
    await init_pool()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    await close_pool()


# ── GET /health ───────────────────────────────────────────────────────────────

class TestHealth:

    async def test_status_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_all_tables_present(self, client):
        data = resp = await client.get("/health")
        tables = set(resp.json()["tables"])
        assert EXPECTED_TABLES.issubset(tables), f"Missing tables: {EXPECTED_TABLES - tables}"

    async def test_response_time(self, client):
        start = time.perf_counter()
        await client.get("/health")
        assert time.perf_counter() - start < 2.0, "Health check took > 2s"


# ── GET /schema ───────────────────────────────────────────────────────────────

class TestSchema:

    async def test_status_ok(self, client):
        resp = await client.get("/schema")
        assert resp.status_code == 200

    async def test_all_tables_present(self, client):
        schema = (await client.get("/schema")).json()["schema"]
        assert EXPECTED_TABLES.issubset(set(schema.keys()))

    async def test_table_has_required_keys(self, client):
        schema = (await client.get("/schema")).json()["schema"]
        for table in EXPECTED_TABLES:
            assert "columns"      in schema[table], f"{table} missing 'columns'"
            assert "foreign_keys" in schema[table], f"{table} missing 'foreign_keys'"

    async def test_columns_have_required_fields(self, client):
        schema = (await client.get("/schema")).json()["schema"]
        for table in EXPECTED_TABLES:
            for col in schema[table]["columns"]:
                for field in ("name", "type", "nullable", "constraint"):
                    assert field in col, f"{table}.{col} missing field '{field}'"

    async def test_foreign_keys_are_list(self, client):
        schema = (await client.get("/schema")).json()["schema"]
        for table in EXPECTED_TABLES:
            assert isinstance(schema[table]["foreign_keys"], list)

    async def test_sales_has_foreign_keys(self, client):
        schema = (await client.get("/schema")).json()["schema"]
        fks = schema["sales"]["foreign_keys"]
        assert len(fks) >= 3, "sales table should have at least 3 FKs"


# ── GET / (frontend) ─────────────────────────────────────────────────────────

class TestFrontend:

    async def test_serves_html(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    async def test_html_contains_ui_elements(self, client):
        html = (await client.get("/")).text
        assert "QueryPilot"  in html
        assert "askQuestion" in html
        assert "question"    in html


# ── POST /ask ─────────────────────────────────────────────────────────────────

class TestAsk:

    # ── structure validation ──────────────────────────────────────────────────

    async def test_empty_question_returns_400(self, client):
        resp = await client.post("/ask", json={"question": ""})
        assert resp.status_code == 400

    async def test_missing_question_field_returns_422(self, client):
        resp = await client.post("/ask", json={})
        assert resp.status_code == 422

    async def test_response_has_all_fields(self, client):
        data = (await client.post("/ask", json={"question": "How many customers are there?"})).json()
        for field in ("question", "answer", "sql_query", "columns", "rows",
                      "row_count", "relevant_tables", "error", "retried"):
            assert field in data, f"Missing field: '{field}'"

    async def test_question_echoed_back(self, client):
        q    = "How many customers are there?"
        data = (await client.post("/ask", json={"question": q})).json()
        assert data["question"] == q

    # ── success response ──────────────────────────────────────────────────────

    async def test_no_error_on_valid_question(self, client):
        data = (await client.post("/ask", json={"question": "How many customers are there?"})).json()
        assert data["error"] is None

    async def test_answer_is_non_empty_string(self, client):
        data = (await client.post("/ask", json={"question": "How many customers are there?"})).json()
        assert isinstance(data["answer"], str)
        assert len(data["answer"]) > 0

    async def test_sql_starts_with_select_or_with(self, client):
        data = (await client.post("/ask", json={"question": "How many customers are there?"})).json()
        first_word = (data["sql_query"] or "").strip().split()[0].upper()
        assert first_word in ("SELECT", "WITH"), f"SQL starts with: {first_word}"

    async def test_columns_is_list(self, client):
        data = (await client.post("/ask", json={"question": "How many customers are there?"})).json()
        assert isinstance(data["columns"], list)

    async def test_rows_is_list(self, client):
        data = (await client.post("/ask", json={"question": "How many customers are there?"})).json()
        assert isinstance(data["rows"], list)

    async def test_row_count_matches_rows_length(self, client):
        data = (await client.post("/ask", json={"question": "How many customers are there?"})).json()
        assert data["row_count"] == len(data["rows"])

    async def test_relevant_tables_non_empty(self, client):
        data = (await client.post("/ask", json={"question": "How many customers are there?"})).json()
        assert isinstance(data["relevant_tables"], list)
        assert len(data["relevant_tables"]) > 0

    async def test_relevant_tables_are_valid(self, client):
        data = (await client.post("/ask", json={"question": "How many customers are there?"})).json()
        all_tables = EXPECTED_TABLES
        for t in data["relevant_tables"]:
            assert t in all_tables, f"Unknown table in relevant_tables: {t}"

    async def test_retried_is_bool(self, client):
        data = (await client.post("/ask", json={"question": "How many customers are there?"})).json()
        assert isinstance(data["retried"], bool)

    # ── query type validation ─────────────────────────────────────────────────

    async def test_aggregation_returns_rows(self, client):
        data = (await client.post("/ask", json={"question": "Total revenue by product category"})).json()
        assert data["error"] is None
        assert data["row_count"] >= 1

    async def test_aggregation_has_category_column(self, client):
        data = (await client.post("/ask", json={"question": "Total revenue by product category"})).json()
        cols_lower = [c.lower() for c in data["columns"]]
        assert any("category" in c for c in cols_lower)

    async def test_join_query(self, client):
        data = (await client.post("/ask", json={"question": "Which customers bought Electronics products?"})).json()
        assert data["error"] is None
        assert data["row_count"] >= 1

    async def test_temporal_query(self, client):
        data = (await client.post("/ask", json={"question": "How many sales were made in 2023?"})).json()
        assert data["error"] is None
        assert data["sql_query"] is not None

    async def test_projects_query(self, client):
        data = (await client.post("/ask", json={"question": "List all active projects"})).json()
        assert data["error"] is None
        assert data["row_count"] >= 1

    async def test_top_customers_returns_5_rows(self, client):
        data = (await client.post("/ask", json={"question": "Top 5 customers by total spending"})).json()
        assert data["error"] is None
        assert data["row_count"] == 5

    async def test_average_salary_has_numeric_values(self, client):
        data = (await client.post("/ask", json={"question": "Average salary per department"})).json()
        assert data["error"] is None
        for row in data["rows"]:
            assert any(isinstance(v, (int, float)) for v in row), "Expected numeric salary values"

    # ── response time ─────────────────────────────────────────────────────────

    async def test_response_time_under_15s(self, client):
        start = time.perf_counter()
        await client.post("/ask", json={"question": "How many employees are there?"})
        elapsed = time.perf_counter() - start
        assert elapsed < 15.0, f"Response took {elapsed:.1f}s — too slow"
