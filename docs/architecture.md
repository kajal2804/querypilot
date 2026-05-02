# QueryPilot — System Architecture

## Overview

QueryPilot is a **multi-agent RAG system** that converts natural-language questions into PostgreSQL queries and returns human-readable answers through a sequential 4-agent pipeline.

## Pipeline

```
User Question (HTTP POST /ask)
         │
         ▼
┌─────────────────┐
│  Schema Agent   │  Reads live DB schema from information_schema.
│  (Agent 1)      │  Caches tables, columns, types, FKs.
│                 │  → Produces: schema_text (prompt context)
└────────┬────────┘
         │
         ▼
┌──────────────────────┐
│ SQL Generator Agent  │  Calls Groq LLM (llama3-70b-8192).
│ (Agent 2)            │  System prompt: SELECT-only, temporal helpers.
│                      │  → Produces: validated PostgreSQL SELECT query
└────────┬─────────────┘
         │
         ▼
┌──────────────────┐
│ Retriever Agent  │  Executes SQL via asyncpg connection pool.
│ (Agent 3)        │  Caps at 200 rows. Serialises Decimal/date types.
│                  │  → Produces: columns[], rows[][]
└────────┬─────────┘
         │
         ▼
┌────────────────────┐
│ Synthesizer Agent  │  Calls Groq LLM with question + results table.
│ (Agent 4)          │  System prompt: direct, factual, 4 sentences max.
│                    │  → Produces: natural-language answer string
└────────┬───────────┘
         │
         ▼
    JSON Response
    {answer, sql_query, columns, rows, row_count, error}
```

## Component Map

```
querypilot/
├── app/main.py              FastAPI — routes, lifespan, agent orchestration
├── agents/
│   ├── schema_agent.py      Agent 1 — schema introspection + caching
│   ├── sql_generator_agent.py  Agent 2 — NL→SQL via Groq
│   ├── retriever_agent.py   Agent 3 — SQL execution via asyncpg
│   └── synthesizer_agent.py Agent 4 — rows→NL via Groq
├── database/
│   ├── connection.py        asyncpg pool, schema DDL, query helpers
│   └── seed.py              synthetic data generator (770 rows)
└── frontend/
    ├── index.html           Single-page UI
    ├── styles.css           Dark-theme styling
    └── app.js               fetch('/ask') + DOM rendering
```

## Database Schema (5 Tables)

```
customers          employees           products
───────────        ──────────          ────────
customer_id PK     employee_id PK      product_id PK
first_name         first_name          name
last_name          last_name           category
email              department          unit_price
city               job_title           stock_qty
country            hire_date
signup_date        salary

sales                           projects
─────                           ────────
sale_id PK                      project_id PK
customer_id FK→customers        name
employee_id FK→employees        department
product_id  FK→products         lead_employee_id FK→employees
quantity                        status
total_amount                    budget
sale_date                       start_date
                                end_date
```

## Design Decisions

**Why asyncpg?** asyncpg is the fastest PostgreSQL driver for Python and integrates naturally with FastAPI's async event loop. A connection pool (min=2, max=10) is created at startup via lifespan and shared across requests.

**Why cache the schema?** The schema is static at runtime. Caching after the first fetch eliminates an extra DB round-trip on every request. The cache can be invalidated manually via `SchemaAgent.invalidate_cache()`.

**Why cap rows at 200 / pass only 50 to LLM?** Returning unlimited rows would risk both memory issues and blowing the LLM context window. The Synthesizer only needs a representative sample to produce an accurate answer.

**Safety gate on SQL.** The SQL Generator checks that the query starts with SELECT or WITH before execution. Any other statement is blocked with an error — preventing prompt-injection-style attacks that try to generate DELETE/DROP.
