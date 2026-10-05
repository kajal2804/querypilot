"""
agents/sql_validator.py
-----------------------
SQL safety validation layer.

Ensures that only safe read-only SELECT/WITH queries
are allowed to reach the database.
"""

import sqlparse
from sqlparse import tokens as T


# SQL commands that must never be executed by the application.
FORBIDDEN_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "CREATE",
    "MERGE",
    "GRANT",
    "REVOKE",
    "CALL",
    "DO",
    "COMMENT",
    "LOCK",
    "VACUUM",
    "REINDEX",
}


def validate_sql(sql: str) -> tuple[bool, str | None]:
    """
    Validate SQL before it is sent to PostgreSQL.

    Returns:
        (True, None) if the query is safe.
        (False, error_message) if the query is unsafe.
    """

    if not sql or not sql.strip():
        return False, "SQL query is empty."

    # Parse the SQL into statements.
    statements = [
        statement
        for statement in sqlparse.parse(sql)
        if statement.value.strip()
    ]

    # Only one SQL statement is allowed.
    if len(statements) != 1:
        return False, "Multiple SQL statements are not allowed."

    statement = statements[0]

    # Find the first meaningful token.
    first_token = statement.token_first(
        skip_ws=True,
        skip_cm=True
    )

    if first_token is None:
        return False, "SQL query is empty."

    first_word = first_token.value.upper()

    # Only SELECT and WITH queries are allowed.
    if first_word not in {"SELECT", "WITH"}:
        return False, (
            f"Only SELECT or WITH queries are allowed. "
            f"Found '{first_word}'."
        )

    # Check all SQL keywords for dangerous operations.
    for token in statement.flatten():

        # Ignore comments and string literals.
        if token.ttype in T.Comment:
            continue

        if token.ttype in T.Literal.String:
            continue

        keyword = token.value.upper().strip()

        if keyword in FORBIDDEN_KEYWORDS:
            return False, (
                f"Unsafe SQL operation '{keyword}' detected."
            )

    return True, None