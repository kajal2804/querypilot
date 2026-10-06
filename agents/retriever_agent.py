"""
agents/retriever_agent.py — Agent 3: Retriever Agent
------------------------------------------------------
Responsibilities:
  - Validate generated SQL before database execution
  - Execute the generated SQL against PostgreSQL via asyncpg
  - On database failure: send error back to SQL Generator and retry once
  - Prevent unsafe SQL from reaching the database
  - Return paginated database results
  - Return pagination metadata (plus column names)
"""

import asyncpg

from database.connection import get_pool
from agents.sql_validator import validate_sql


# Kept for backward compatibility with any module that imports it.
# Row limiting is now handled by pagination (see MAX_PAGE_SIZE).
MAX_ROWS = 200
MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50
MAX_RETRIES = 1   # one self-healing retry


class RetrieverAgent:

    async def execute(
        self,
        sql: str,
        question: str = "",
        sql_agent=None,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> dict:
        """
        Run a SELECT query and return a paginated result.

        If the query fails and sql_agent is provided,
        ask the SQL Generator to fix the SQL and retry once.
        Queries rejected by the SQL safety validator are NOT auto-fixed.

        Pagination:
            page=1, page_size=50 -> rows 1-50
            page=2, page_size=50 -> rows 51-100

        Returns:
        {
            "columns": [...],
            "rows": [[...], ...],
            "row_count": int,
            "total_rows": int,
            "page": int,
            "page_size": int,
            "has_next": bool,
            "sql_used": str,
            "retried": bool,
            "error": None | str
        }
        """

        # -------------------------------------------------
        # Validate pagination values
        # -------------------------------------------------

        if page < 1:
            return _empty(
                "Page must be greater than or equal to 1.",
                page=page,
                page_size=page_size,
            )

        if page_size < 1:
            return _empty(
                "Page size must be greater than or equal to 1.",
                page=page,
                page_size=page_size,
            )

        # Prevent excessively large pages
        page_size = min(page_size, MAX_PAGE_SIZE)

        # -------------------------------------------------
        # Validate SQL input
        # -------------------------------------------------

        if not sql:
            return _empty(
                "No SQL query provided.",
                page=page,
                page_size=page_size,
            )

        # -------------------------------------------------
        # First execution
        # -------------------------------------------------

        result = await self._run(
            sql,
            page=page,
            page_size=page_size,
        )

        # -------------------------------------------------
        # Self-healing retry
        #
        # Do not attempt AI auto-fix if the query failed
        # because it was rejected by the SQL safety validator.
        # -------------------------------------------------

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

                retry_result = await self._run(
                    fixed["sql"],
                    page=page,
                    page_size=page_size,
                )

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

    # -----------------------------------------------------
    # Validate and execute SQL
    # -----------------------------------------------------

    async def _run(
        self,
        sql: str,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> dict:
        """
        Validate and execute SQL against PostgreSQL,
        returning one page of results.
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
                    f"SQL validation failed: {validation_error}",
                    page=page,
                    page_size=page_size,
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

            # -------------------------------------------------
            # No results
            # -------------------------------------------------

            if not records:

                return {
                    **_empty(
                        None,
                        page=page,
                        page_size=page_size,
                    ),
                    "sql_used": sql,
                    "retried": False,
                    "validation_error": False,
                }

            # -------------------------------------------------
            # Total rows
            # -------------------------------------------------

            total_rows = len(records)

            # -------------------------------------------------
            # Pagination calculation
            # -------------------------------------------------

            start = (page - 1) * page_size
            end = start + page_size

            page_records = records[start:end]

            # -------------------------------------------------
            # Check whether another page exists
            # -------------------------------------------------

            has_next = end < total_rows

            # -------------------------------------------------
            # Convert records
            # -------------------------------------------------

            columns = list(records[0].keys())

            rows = _serialize(
                [
                    list(record.values())
                    for record in page_records
                ]
            )

            # -------------------------------------------------
            # Return result
            # -------------------------------------------------

            return {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "total_rows": total_rows,
                "page": page,
                "page_size": page_size,
                "has_next": has_next,
                "sql_used": sql,
                "retried": False,
                "error": None,
                "validation_error": False,
            }

        except asyncpg.PostgresError as exc:

            return {
                **_empty(
                    f"Database error: {exc}",
                    page=page,
                    page_size=page_size,
                ),
                "sql_used": sql,
                "retried": False,
                "validation_error": False,
            }

        except Exception as exc:

            return {
                **_empty(
                    f"Unexpected error: {exc}",
                    page=page,
                    page_size=page_size,
                ),
                "sql_used": sql,
                "retried": False,
                "validation_error": False,
            }

    # -----------------------------------------------------
    # Convert rows to text
    # -----------------------------------------------------

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


# ---------------------------------------------------------
# Empty result helper
# ---------------------------------------------------------

def _empty(
    error: str | None,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> dict:
    """
    Return a standard empty result structure.
    """

    return {
        "columns": [],
        "rows": [],
        "row_count": 0,
        "total_rows": 0,
        "page": page,
        "page_size": page_size,
        "has_next": False,
        "error": error,
    }


# ---------------------------------------------------------
# Serialize PostgreSQL values
# ---------------------------------------------------------

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
