"""
agents/retriever_agent.py — Agent 3: Retriever Agent
------------------------------------------------------
Responsibilities:
  - Execute the generated SQL against PostgreSQL via asyncpg
  - On failure: send error back to SQL Generator and retry once (self-healing)
  - Validate that results are non-trivially empty vs genuinely no data
  - Return structured rows + column names
"""

import asyncpg
from database.connection import get_pool

MAX_ROWS    = 200
MAX_RETRIES = 1   # one self-healing retry


class RetrieverAgent:

    async def execute(self, sql: str, question: str = "", sql_agent=None) -> dict:
        """
        Run a SELECT query. If it fails and sql_agent is provided,
        ask the SQL Generator to fix the SQL and retry once.

        Returns:
        {
            "columns":   [...],
            "rows":      [[...], ...],
            "row_count": int,
            "sql_used":  str,          # may differ from input if retry happened
            "retried":   bool,
            "error":     None | str
        }
        """
        if not sql:
            return _empty("No SQL query provided.")

        result = await self._run(sql)

        # ── retry if failed and sql_agent available ───────────────────────────
        if result["error"] and sql_agent and question:
            fixed = sql_agent.fix(question, sql, result["error"])
            if fixed["sql"]:
                retry_result = await self._run(fixed["sql"])
                retry_result["retried"]  = True
                retry_result["sql_used"] = fixed["sql"]
                return retry_result
            else:
                result["error"] = f"{result['error']} | Auto-fix also failed: {fixed['error']}"

        result.setdefault("retried",  False)
        result.setdefault("sql_used", sql)
        return result

    # ── internal run ──────────────────────────────────────────────────────────

    async def _run(self, sql: str) -> dict:
        try:
            async with get_pool().acquire() as conn:
                records = await conn.fetch(sql)

            if not records:
                return {**_empty(None), "sql_used": sql, "retried": False}

            columns = list(records[0].keys())
            rows    = _serialize([list(r.values()) for r in records[:MAX_ROWS]])

            return {
                "columns":   columns,
                "rows":      rows,
                "row_count": len(rows),
                "sql_used":  sql,
                "retried":   False,
                "error":     None,
            }

        except asyncpg.PostgresError as exc:
            return {**_empty(f"Database error: {exc}"), "sql_used": sql, "retried": False}
        except Exception as exc:
            return {**_empty(f"Unexpected error: {exc}"), "sql_used": sql, "retried": False}

    # ── utility ───────────────────────────────────────────────────────────────

    @staticmethod
    def rows_to_text(columns: list, rows: list) -> str:
        if not columns:
            return "No results."
        header = " | ".join(columns)
        lines  = [header, "-" * len(header)]
        for row in rows[:50]:
            lines.append(" | ".join(str(v) for v in row))
        if len(rows) > 50:
            lines.append(f"… and {len(rows) - 50} more rows")
        return "\n".join(lines)


# ── helpers ───────────────────────────────────────────────────────────────────

def _empty(error: str | None) -> dict:
    return {"columns": [], "rows": [], "row_count": 0, "error": error}


def _serialize(rows: list[list]) -> list[list]:
    import decimal, datetime
    out = []
    for row in rows:
        new_row = []
        for v in row:
            if isinstance(v, decimal.Decimal):
                new_row.append(float(v))
            elif isinstance(v, (datetime.date, datetime.datetime)):
                new_row.append(v.isoformat())
            else:
                new_row.append(v)
        out.append(new_row)
    return out
