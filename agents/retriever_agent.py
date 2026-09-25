"""
agents/retriever_agent.py — Agent 3: Retriever Agent
------------------------------------------------------
Responsibilities:
  - Validate generated SQL before database execution
  - Execute the generated SQL against PostgreSQL via asyncpg
  - On database failure: send error back to SQL Generator and retry once
  - Prevent unsafe SQL from reaching the database
  - Return structured rows + column names
"""

import asyncpg

from database.connection import get_pool
from agents.sql_validator import validate_sql


MAX_ROWS = 200
MAX_RETRIES = 1   # one self-healing retry


class RetrieverAgent:

    async def execute(
        self,
        sql: str,
        question: str = "",
        sql_agent=None
    ) -> dict:
        """
        Run a SELECT query.

        If the query fails and sql_agent is provided,
        ask the SQL Generator to fix the SQL and retry once.

        Returns:
        {
            "columns":   [...],
            "rows":      [[...], ...],
            "row_count": int,
            "sql_used":  str,
            "retried":   bool,
            "error":     None | str
        }
        """

        if not sql:
            return _empty("No SQL query provided.")

        # First execution
        result = await self._run(sql)

        # Do not attempt AI auto-fix if the query failed
        # because it was rejected by the SQL safety validator.
        if (
            result["error"]
            and result.get("validation_error") is not True
            and sql_agent
            and question
        ):
            fixed = sql_agent.fix(
                question,
                sql,
                result["error"]
            )

            if fixed["sql"]:
                retry_result = await self._run(fixed["sql"])

                retry_result["retried"] = True
                retry_result["sql_used"] = fixed["sql"]

                return retry_result

            else:
                result["error"] = (
                    f"{result['error']} | "
                    f"Auto-fix also failed: {fixed['error']}"
                )

        result.setdefault("retried", False)
        result.setdefault("sql_used", sql)

        return result

    async def _run(self, sql: str) -> dict:
        """
        Validate and execute SQL against PostgreSQL.
        """

        # ---------------------------------------------------------
        # SQL SAFETY VALIDATION
        # ---------------------------------------------------------
        #
        # This is a second safety layer immediately before the
        # query reaches PostgreSQL.
        #
        is_valid, validation_error = validate_sql(sql)

        if not is_valid:
            return {
                **_empty(
                    f"SQL validation failed: {validation_error}"
                ),
                "sql_used": sql,
                "retried": False,
                "validation_error": True,
            }

        # ---------------------------------------------------------
        # DATABASE EXECUTION
        # ---------------------------------------------------------

        try:
            async with get_pool().acquire() as conn:

                records = await conn.fetch(sql)

            # Query executed successfully but returned no rows
            if not records:
                return {
                    **_empty(None),
                    "sql_used": sql,
                    "retried": False,
                    "validation_error": False,
                }

            # Get column names
            columns = list(records[0].keys())

            # Limit returned rows to MAX_ROWS
            rows = _serialize(
                [
                    list(record.values())
                    for record in records[:MAX_ROWS]
                ]
            )

            return {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "sql_used": sql,
                "retried": False,
                "error": None,
                "validation_error": False,
            }

        except asyncpg.PostgresError as exc:
            return {
                **_empty(f"Database error: {exc}"),
                "sql_used": sql,
                "retried": False,
                "validation_error": False,
            }

        except Exception as exc:
            return {
                **_empty(f"Unexpected error: {exc}"),
                "sql_used": sql,
                "retried": False,
                "validation_error": False,
            }

    @staticmethod
    def rows_to_text(columns: list, rows: list) -> str:
        """
        Convert query results into readable text.
        """

        if not columns:
            return "No results."

        header = " | ".join(columns)

        lines = [
            header,
            "-" * len(header)
        ]

        for row in rows[:50]:
            lines.append(
                " | ".join(str(value) for value in row)
            )

        if len(rows) > 50:
            lines.append(
                f"… and {len(rows) - 50} more rows"
            )

        return "\n".join(lines)


def _empty(error: str | None) -> dict:
    """
    Return a standard empty result structure.
    """

    return {
        "columns": [],
        "rows": [],
        "row_count": 0,
        "error": error
    }


def _serialize(rows: list[list]) -> list[list]:
    """
    Convert PostgreSQL values into JSON-friendly values.
    """

    import decimal
    import datetime

    out = []

    for row in rows:

        new_row = []

        for value in row:

            if isinstance(value, decimal.Decimal):
                new_row.append(float(value))

            elif isinstance(
                value,
                (datetime.date, datetime.datetime)
            ):
                new_row.append(value.isoformat())

            else:
                new_row.append(value)

        out.append(new_row)

    return out