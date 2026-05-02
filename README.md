# QueryPilot — Multi-Agent RAG SQL Assistant

A **multi-agent RAG system** that interprets natural-language questions, queries a PostgreSQL database through a 4-agent pipeline, and returns human-readable answers via a REST API and web UI.

Built as part of an AI Internship Assignment — demonstrates multi-agent orchestration, vector-based RAG fallback, and document-augmented synthesis.

---

## Live Demo

> Run locally — see [Setup](#setup) below.  
> Web UI: `http://localhost:8000`  
> API Docs: `http://localhost:8000/docs`

---

## Architecture

```
User Question (POST /ask)
        │
        ▼
┌─────────────────┐
│  Schema Agent   │  Groq LLM — identifies relevant tables from live DB schema
└────────┬────────┘
         │
         ▼
┌─────────────────┐     Rate limited?
│ SQL Generator   │ ──────────────────► Vector Cache (ChromaDB)
│     Agent       │                     re-run cached SQL on Postgres
└────────┬────────┘                     return answer without Groq
         │
         ▼
┌─────────────────┐
│ Retriever Agent │  Executes SQL · auto-retries on failure
└────────┬────────┘
         │                  ┌────────────────────┐
         ├──────────────────► Doc Store (ChromaDB)│  searches uploaded docs
         │                  └────────┬───────────┘  adds context if relevant
         ▼                           │
┌─────────────────┐ ◄────────────────┘
│  Synthesizer    │  Groq LLM — rows + doc context → natural language answer
│     Agent       │  Rate limited? → plain template answer (no Groq needed)
└────────┬────────┘
         │
         ▼
  JSON Response + Web UI
```

---

## Tech Stack

| Layer       | Technology                                  |
|-------------|---------------------------------------------|
| Backend     | Python 3.11+, FastAPI, asyncpg              |
| LLM         | Groq API (`llama-3.3-70b-versatile`)        |
| Database    | PostgreSQL 15+                              |
| Vector DB   | ChromaDB (local, no server needed)          |
| Embeddings  | sentence-transformers `all-MiniLM-L6-v2`    |
| Frontend    | HTML, CSS, vanilla JavaScript               |
| Tests       | pytest, pytest-asyncio, httpx               |

---

## Project Structure

```
querypilot/
├── app/
│   └── main.py                  FastAPI app — all endpoints
├── agents/
│   ├── schema_agent.py          Agent 1 — schema introspection via Groq
│   ├── sql_generator_agent.py   Agent 2 — NL → SQL via Groq
│   ├── retriever_agent.py       Agent 3 — SQL execution + auto-retry
│   ├── synthesizer_agent.py     Agent 4 — rows → NL answer via Groq
│   ├── vector_store.py          ChromaDB query cache (RAG fallback)
│   └── doc_store.py             ChromaDB document knowledge base
├── database/
│   ├── connection.py            asyncpg pool, DDL, query helpers
│   ├── seed.py                  synthetic data (500 rows across 5 tables)
│   └── seed_cache.py            pre-seeds vector cache with common Q&A pairs
├── frontend/
│   ├── index.html               3-tab UI (Ask / Documents / Tests)
│   ├── styles.css               dark theme
│   └── app.js                   pipeline visualizer + fetch logic
├── tests/
│   ├── test_api.py              27 integration tests
│   └── test_queries.py          12 query-type coverage tests
├── config.py                    Groq key + model config
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 15+ running locally (port 5432)
- Free [Groq API key](https://console.groq.com/)

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/querypilot.git
cd querypilot
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

> **Windows / Python 3.13 note:** if you see a C++ compiler error for numpy, run:
> ```bash
> pip install "numpy>=2.0" sentence-transformers chromadb
> ```

### 3. Create the PostgreSQL database

```sql
-- Run in psql or pgAdmin:
CREATE USER raguser WITH PASSWORD 'ragpass';
CREATE DATABASE ragdb OWNER raguser;

-- Grant permissions (required):
\c ragdb
GRANT ALL ON SCHEMA public TO raguser;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO raguser;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO raguser;
```

### 4. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
GROQ_API_KEY=gsk_your_key_here
DATABASE_URL=postgresql://raguser:ragpass@localhost:5432/ragdb
```

### 5. Seed the database

```bash
python -m database.seed
```

Inserts: **200 customers · 50 employees · 20 products · 500 sales · 15 projects**

### 6. Pre-seed the vector cache (optional but recommended)

This loads 14 common Q&A pairs into ChromaDB so the fallback works immediately, even before any live queries have been made.

```bash
python -m database.seed_cache
```

### 7. Start the server

```bash
uvicorn app.main:app --reload
```

Open **http://localhost:8000** — the web UI loads automatically.

---

## Agent Descriptions

### 1. Schema Agent
Connects to PostgreSQL and reads `information_schema` to extract table names, columns, data types, primary keys, and foreign keys. Then calls Groq to identify which tables are relevant to the user's question, so the SQL Generator only sees the schema it needs. Schema is cached after first fetch.

### 2. SQL Generator Agent
Receives the question and the filtered schema, calls Groq (`llama-3.3-70b-versatile`) with a strict system prompt: SELECT-only, valid PostgreSQL syntax, correct date functions for temporal references (`last year`, `Q1 2023`, etc.). If Groq returns a 429 rate-limit error, sets a `rate_limited` flag so the pipeline can fall back to the vector cache.

### 3. Retriever Agent
Executes the generated SQL against PostgreSQL using the shared asyncpg connection pool. If execution fails (syntax error, unknown column, etc.), it calls `SQLGeneratorAgent.fix()` to auto-correct the SQL and retries once. Returns columns, rows, and a `retried` flag. Serialises Decimal and date types for JSON output.

### 4. Synthesizer Agent
Takes the original question and the retrieved rows (formatted as a plain-text table), optionally adds relevant document context from the Doc Store, and calls Groq to produce a concise 3–5 sentence natural-language answer. If Groq is rate-limited at this stage, generates a plain template-based answer from the rows directly — no LLM needed.

---

## RAG Fallback System

QueryPilot has **two separate ChromaDB collections**:

| Collection | Purpose | Triggered when |
|---|---|---|
| `query_cache` | Stores past Q&A pairs with their SQL | Groq hits 429 during SQL generation |
| `documents` | Stores uploaded PDF/TXT chunks | Every query — enriches synthesis |

**When rate-limited (SQL generation):**
1. Vector cache searched for most similar past question (threshold: 0.92 cosine similarity)
2. Cached SQL re-executed against Postgres for fresh rows
3. Cached answer returned — Groq not called at all
4. UI shows `⚡ answered from cache` badge

**When rate-limited (synthesis):**
1. Rows already retrieved from DB
2. Plain template answer built directly from row data
3. Full data table still shown in UI

---

## API Reference

### `POST /ask`

```json
// Request
{ "question": "What is the average salary per department?" }

// Response
{
  "question":        "What is the average salary per department?",
  "answer":          "The Engineering department has the highest average salary at $95,200...",
  "sql_query":       "SELECT department, ROUND(AVG(salary)::numeric,2) FROM employees GROUP BY department ORDER BY avg_salary DESC",
  "columns":         ["department", "avg_salary"],
  "rows":            [["Engineering", 95200.0], ["Finance", 88400.0]],
  "row_count":       5,
  "relevant_tables": ["employees"],
  "retried":         false,
  "from_cache":      false,
  "doc_context":     [],
  "error":           null
}
```

### `GET /health`
```json
{ "status": "ok", "tables": ["customers", "employees", "products", "sales", "projects"] }
```

### `GET /schema`
Returns full DB schema as JSON.

### `POST /upload-doc`
Upload a `.txt` or `.md` file to the document knowledge base.

### `GET /docs-list`
Returns list of ingested documents and total chunk count.

### `GET /run-tests`
Runs the test suite and returns structured pass/fail results (used by the Tests tab in the UI).

---

## Supported Query Types

| Type | Example |
|---|---|
| Direct lookup | `Show all customers from New York` |
| Filtering | `Products that cost more than $100` |
| Aggregation COUNT | `How many sales were made in 2024?` |
| Aggregation SUM/AVG | `Total revenue by product category` |
| Multi-table join | `Which employees made the most sales?` |
| Temporal — quarter | `Sales in Q1 2023` |
| Temporal — year | `Total revenue last year` |
| Project queries | `List all active projects and their budgets` |

---

## Running Tests

```bash
# From inside querypilot/
pytest tests/ -v
```

Or use the **🧪 Tests** tab in the web UI to run and view results live.

---

## Known Limitations & Future Work

- **Document chunking (future work):** Due to time constraints during development, the document chunking and embedding pipeline is partially implemented. The architecture is in place (`doc_store.py`, ChromaDB `documents` collection, upload endpoint) but text chunking produces inconsistent results for small or non-standard formatted files. The majority of development effort was focused on the core SQL pipeline and Groq API integration, which is where the system performs well. A proper chunking strategy using `langchain.text_splitter` or `tiktoken`-based splitting is the recommended next step.
- **PDF extraction:** pypdf has font-encoding compatibility issues with certain PDF generators. Plain `.txt` and `.md` files ingest correctly. Future fix: replace with `pdfplumber` or `pymupdf` for more reliable extraction.
- **Groq free tier:** 100,000 tokens/day limit. The vector cache fallback handles this gracefully — the system re-executes cached SQL directly against Postgres and returns real rows without calling Groq.
- **Row cap:** Retriever limits results to 200 rows; only 50 rows are passed to the LLM context window.
- **Production database:** The `DATABASE_URL` fallback in `connection.py` is a local dev default only. Always set a proper `DATABASE_URL` in `.env` for any real deployment.

---

## Database Schema

```
customers   — customer_id, first_name, last_name, email, city, state, created_at
employees   — employee_id, first_name, last_name, department, salary, hire_date
products    — product_id, name, category, unit_price, stock_quantity
sales       — sale_id, customer_id, employee_id, product_id, quantity, total_amount, sale_date
projects    — project_id, name, department, status, budget, start_date, end_date
```

---

*Built with FastAPI · Groq · PostgreSQL · ChromaDB*
