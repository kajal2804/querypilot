"""
agents/schema_agent.py — Agent 1: Schema Agent
------------------------------------------------
Responsibilities:
  - Fetch full DB schema from PostgreSQL
  - Use Groq LLM to identify ONLY the relevant tables/fields for the question
  - Return focused schema context (not the entire schema)
"""

from groq import Groq
from database.connection import fetch_schema_info, fetch_foreign_keys
from config import GROQ_API_KEY, GROQ_MODEL

_FILTER_PROMPT = """You are a database schema analyst.
Given a full database schema and a user question, identify ONLY the tables
and columns that are needed to answer the question.

Rules:
- Output a JSON object like: {"relevant_tables": ["table1", "table2"]}
- Only include tables actually needed for the query.
- If a JOIN is needed, include all tables involved.
- Output ONLY the JSON — no explanation, no markdown.
"""


class SchemaAgent:

    def __init__(self) -> None:
        self._full_cache: dict | None = None
        self.client = Groq(api_key=GROQ_API_KEY)

    # ── full schema ───────────────────────────────────────────────────────────

    async def get_schema(self) -> dict:
        if self._full_cache is not None:
            return self._full_cache

        col_rows = await fetch_schema_info()
        fk_rows  = await fetch_foreign_keys()

        schema: dict = {}
        for row in col_rows:
            t = row["table_name"]
            if t not in schema:
                schema[t] = {"columns": [], "foreign_keys": []}
            schema[t]["columns"].append({
                "name":       row["column_name"],
                "type":       row["data_type"],
                "nullable":   row["is_nullable"] == "YES",
                "constraint": row["constraint_type"],
            })
        for row in fk_rows:
            t = row["table_name"]
            if t in schema:
                schema[t]["foreign_keys"].append(
                    f"{row['column_name']} → {row['foreign_table']}.{row['foreign_column']}"
                )

        self._full_cache = schema
        return schema

    async def get_table_names(self) -> list[str]:
        return list((await self.get_schema()).keys())

    # ── agentic: identify relevant tables via Groq ────────────────────────────

    async def identify_relevant_tables(self, question: str) -> list[str]:
        """
        Uses Groq to decide which tables are actually needed for this question.
        Falls back to all tables if LLM call fails.
        """
        schema     = await self.get_schema()
        all_tables = list(schema.keys())
        schema_summary = _build_schema_summary(schema)

        try:
            import json
            resp = self.client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": _FILTER_PROMPT},
                    {"role": "user",   "content":
                        f"Schema:\n{schema_summary}\n\nQuestion: {question}"},
                ],
                temperature=0.0,
                max_tokens=128,
            )
            raw = resp.choices[0].message.content.strip()
            # strip accidental fences
            import re
            raw = re.sub(r"```[a-zA-Z]*", "", raw).replace("```", "").strip()
            data = json.loads(raw)
            relevant = [t for t in data.get("relevant_tables", []) if t in all_tables]
            return relevant if relevant else all_tables
        except Exception:
            return all_tables

    # ── format focused schema for SQL Generator ───────────────────────────────

    async def format_for_prompt(self, question: str | None = None) -> str:
        """
        If a question is provided, returns only relevant tables.
        Otherwise returns full schema (fallback).
        """
        schema          = await self.get_schema()
        relevant_tables = (
            await self.identify_relevant_tables(question)
            if question else list(schema.keys())
        )

        lines = []
        for table in relevant_tables:
            if table not in schema:
                continue
            info = schema[table]
            lines.append(f"Table: {table}")
            for col in info["columns"]:
                c_hint  = f" [{col['constraint']}]" if col["constraint"] else ""
                nn_hint = "" if col["nullable"] else " NOT NULL"
                lines.append(f"  - {col['name']} ({col['type']}{nn_hint}{c_hint})")
            for fk in info["foreign_keys"]:
                lines.append(f"  FK: {fk}")
            lines.append("")
        return "\n".join(lines)

    def invalidate_cache(self) -> None:
        self._full_cache = None


# ── helpers ───────────────────────────────────────────────────────────────────

def _build_schema_summary(schema: dict) -> str:
    """Compact one-liner per table for the filter prompt."""
    lines = []
    for table, info in schema.items():
        cols = ", ".join(c["name"] for c in info["columns"])
        lines.append(f"{table}: {cols}")
    return "\n".join(lines)
