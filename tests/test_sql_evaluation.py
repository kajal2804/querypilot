"""
tests/test_sql_evaluation.py
----------------------------
Evaluation tests for SQL generation.

The Groq API response is mocked so the evaluation is deterministic
and does not require an external API call.
"""

from unittest.mock import MagicMock, patch

import pytest

from agents.sql_generator_agent import SQLGeneratorAgent
from agents.sql_validator import validate_sql


EVALUATION_CASES = [
    {
        "name": "customer_count",
        "question": "How many customers are there?",
        "schema": "Table: customers\n- customer_id (int)",
        "generated_sql": "SELECT COUNT(*) FROM customers",
    },
    {
        "name": "sales_by_category",
        "question": "What is total revenue per product category?",
        "schema": "Table: sales\n- amount (numeric)\n- category (text)",
        "generated_sql": (
            "SELECT category, SUM(amount) "
            "FROM sales GROUP BY category"
        ),
    },
    {
        "name": "temporal_query",
        "question": "How many sales happened last year?",
        "schema": "Table: sales\n- sale_date (date)",
        "generated_sql": (
            "SELECT COUNT(*) FROM sales "
            "WHERE EXTRACT(YEAR FROM sale_date) = "
            "EXTRACT(YEAR FROM NOW()) - 1"
        ),
    },
]


@pytest.mark.parametrize("case", EVALUATION_CASES)
def test_sql_generation_evaluation(case):
    """Generated SQL should be valid and safe."""

    agent = SQLGeneratorAgent()

    mock_response = MagicMock()
    mock_response.choices[0].message.content = case["generated_sql"]

    with patch.object(
        agent.client.chat.completions,
        "create",
        return_value=mock_response,
    ):
        result = agent.generate(
            case["question"],
            case["schema"],
        )

    assert result["error"] is None
    assert result["sql"] is not None

    is_valid, error = validate_sql(result["sql"])
    assert is_valid, error


def test_sql_generation_handles_empty_response():
    """Empty model responses should fail gracefully."""

    agent = SQLGeneratorAgent()

    mock_response = MagicMock()
    mock_response.choices[0].message.content = ""

    with patch.object(
        agent.client.chat.completions,
        "create",
        return_value=mock_response,
    ):
        result = agent.generate(
            "How many customers are there?",
            "Table: customers",
        )

    assert result["sql"] is None
    assert result["error"] is not None


def test_sql_generation_handles_api_failure():
    """API failures should return a structured error."""

    agent = SQLGeneratorAgent()

    with patch.object(
        agent.client.chat.completions,
        "create",
        side_effect=Exception("API timeout"),
    ):
        result = agent.generate(
            "How many customers are there?",
            "Table: customers",
        )

    assert result["sql"] is None
    assert "SQL generation failed" in result["error"]