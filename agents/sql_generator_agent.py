"""
agents/sql_generator_agent.py — Agent 2: SQL Generator Agent
--------------------------------------------------------------
Responsibilities:
  - Convert natural language question → valid PostgreSQL SELECT query
  - Handle temporal references
  - Validate generated SQL for safety
  - Graceful fallback when question is out of scope
  - Robust handling of malformed/empty model responses
"""

import re

from groq import Groq

from config import GROQ_API_KEY, GROQ_MODEL
from agents.sql_validator import validate_sql


_SYSTEM_PROMPT = """You are an expert PostgreSQL query writer.
Given a database schema and a natural-language question, write ONE valid
PostgreSQL SELECT query that answers the question.

Rules:
- Output ONLY the raw SQL — no markdown, no code fences, no explanation.
- Use table aliases for clarity on multi-table JOINs.
- For temporal references use PostgreSQL date functions:
    • "last year" → EXTRACT(YEAR FROM sale_date) = EXTRACT(YEAR FROM NOW()) - 1
    • "this year" → EXTRACT(YEAR FROM sale_date) = EXTRACT(YEAR FROM NOW())
    • "Q1 2023" → sale_date BETWEEN '2023-01-01' AND '2023-03-31'
    • "this month" → DATE_TRUNC('month', sale_date) = DATE_TRUNC('month', NOW())
- Never use DROP, INSERT, UPDATE, DELETE, TRUNCATE, or any DDL/DML.
- If the question cannot be answered from the provided schema, output exactly:
  UNSUPPORTED_QUERY
"""


class SQLGeneratorAgent:

    def __init__(self) -> None:
        self.client = Groq(api_key=GROQ_API_KEY)

    def generate(self, question: str, schema_text: str) -> dict:
        """
        Generate SQL from a natural-language question.

        Returns:
            {
                "sql": "<query>" | None,
                "error": None | "<message>"
            }
        """

        user_msg = (
            f"Database schema:\n{schema_text}\n\n"
            f"Question: {question}"
        )

        try:
            resp = self.client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": _SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": user_msg
                    },
                ],
                temperature=0.0,
                max_tokens=512,
            )

            # Handle malformed or empty model responses
            if (
                not getattr(resp, "choices", None)
                or not getattr(resp.choices[0], "message", None)
                or not getattr(resp.choices[0].message, "content", None)
            ):
                return {
                    "sql": None,
                    "error": "SQL generation returned an empty response."
                }

            raw = resp.choices[0].message.content.strip()

            if not raw:
                return {
                    "sql": None,
                    "error": "SQL generation returned an empty response."
                }

            # Remove accidental markdown code fences
            raw = re.sub(
                r"```[a-zA-Z]*",
                "",
                raw
            ).replace("```", "").strip()

            if not raw:
                return {
                    "sql": None,
                    "error": "SQL generation returned an empty response."
                }

            # Handle unsupported questions
            if raw.upper().startswith("UNSUPPORTED_QUERY"):
                return {
                    "sql": None,
                    "error": (
                        "This question cannot be answered "
                        "from the available schema."
                    )
                }

            # Validate generated SQL before returning it
            is_valid, validation_error = validate_sql(raw)

            if not is_valid:
                return {
                    "sql": None,
                    "error": validation_error
                }

            return {
                "sql": raw,
                "error": None
            }

        except Exception as exc:
            err_str = str(exc)

            if "429" in err_str or "rate_limit" in err_str.lower():
                return {
                    "sql": None,
                    "error": "RATE_LIMIT",
                    "rate_limited": True
                }

            return {
                "sql": None,
                "error": f"SQL generation failed: {exc}"
            }

    def fix(self, question: str, bad_sql: str, db_error: str) -> dict:
        """
        Attempt to correct SQL that failed during database execution.

        Returns:
            {
                "sql": "<corrected query>" | None,
                "error": None | "<message>"
            }
        """

        user_msg = (
            f"The following SQL query failed with this error:\n\n"
            f"SQL:\n{bad_sql}\n\n"
            f"Error:\n{db_error}\n\n"
            f"Original question: {question}\n\n"
            f"Please write a corrected PostgreSQL SELECT query."
        )

        try:
            resp = self.client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": _SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": user_msg
                    },
                ],
                temperature=0.0,
                max_tokens=512,
            )

            # Handle malformed or empty model responses
            if (
                not getattr(resp, "choices", None)
                or not getattr(resp.choices[0], "message", None)
                or not getattr(resp.choices[0].message, "content", None)
            ):
                return {
                    "sql": None,
                    "error": "SQL fix returned an empty response."
                }

            raw = resp.choices[0].message.content.strip()

            if not raw:
                return {
                    "sql": None,
                    "error": "SQL fix returned an empty response."
                }

            # Remove accidental markdown code fences
            raw = re.sub(
                r"```[a-zA-Z]*",
                "",
                raw
            ).replace("```", "").strip()

            if not raw:
                return {
                    "sql": None,
                    "error": "SQL fix returned an empty response."
                }

            # Validate corrected SQL before retrying it
            is_valid, validation_error = validate_sql(raw)

            if not is_valid:
                return {
                    "sql": None,
                    "error": (
                        f"Fix attempt produced unsafe SQL: "
                        f"{validation_error}"
                    )
                }

            return {
                "sql": raw,
                "error": None
            }

        except Exception as exc:
            return {
                "sql": None,
                "error": f"Fix attempt failed: {exc}"
            }
