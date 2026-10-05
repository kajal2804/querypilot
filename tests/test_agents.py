"""
tests/test_agents.py
--------------------
Unit tests for individual agent classes.
Run with:  pytest tests/test_agents.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── SQL Generator Agent ───────────────────────────────────────────────────────

class TestSQLGeneratorAgent:

    def setup_method(self):
        from agents.sql_generator_agent import SQLGeneratorAgent
        self.agent = SQLGeneratorAgent()

    def test_strips_code_fences(self):
        """Generated SQL with markdown fences should be cleaned."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "```sql\nSELECT * FROM customers\n```"
        with patch.object(self.agent.client.chat.completions, "create",
                          return_value=mock_response):
            result = self.agent.generate(
                "show customers", "Table: customers\n  - customer_id (int)")
        assert result["sql"] == "SELECT * FROM customers"
        assert result["error"] is None

    def test_blocks_unsafe_sql(self):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "DROP TABLE customers"
        with patch.object(self.agent.client.chat.completions, "create",
                          return_value=mock_response):
            result = self.agent.generate(
                "drop customers", "Table: customers\n")
        assert result["sql"] is None
        assert result["error"] is not None

    def test_unsupported_query(self):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "UNSUPPORTED_QUERY"
        with patch.object(self.agent.client.chat.completions, "create",
                          return_value=mock_response):
            result = self.agent.generate(
                "what is the weather?", "Table: customers\n")
        assert result["sql"] is None
        assert result["error"] is not None

    def test_valid_with_query(self):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "WITH cte AS (SELECT 1) SELECT * FROM cte"
        with patch.object(self.agent.client.chat.completions, "create",
                          return_value=mock_response):
            result = self.agent.generate("complex query", "Table: customers\n")
        assert result["sql"] is not None
        assert result["error"] is None


# ── Retriever Agent ───────────────────────────────────────────────────────────

class TestRetrieverAgent:

    def test_rows_to_text_empty(self):
        from agents.retriever_agent import RetrieverAgent
        assert RetrieverAgent.rows_to_text([], []) == "No results."

    def test_rows_to_text_normal(self):
        from agents.retriever_agent import RetrieverAgent
        text = RetrieverAgent.rows_to_text(
            ["name", "age"], [["Alice", 30], ["Bob", 25]])
        assert "name" in text
        assert "Alice" in text
        assert "Bob" in text

    @pytest.mark.asyncio
    async def test_execute_no_sql(self):
        from agents.retriever_agent import RetrieverAgent
        agent = RetrieverAgent()
        result = await agent.execute("")
        assert result["error"] == "No SQL query provided."
        assert result["row_count"] == 0


# ── Synthesizer Agent ─────────────────────────────────────────────────────────

class TestSynthesizerAgent:

    def setup_method(self):
        from agents.synthesizer_agent import SynthesizerAgent
        self.agent = SynthesizerAgent()

    def test_synthesize_success(self):
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "There are 200 customers in total."
        with patch.object(self.agent.client.chat.completions, "create",
                          return_value=mock_response):
            result = self.agent.synthesize(
                "How many customers?", ["count"], [[200]]
            )
        assert result["answer"] == "There are 200 customers in total."
        assert result["error"] is None

    def test_synthesize_api_error(self):
        with patch.object(self.agent.client.chat.completions, "create",
                          side_effect=Exception("API timeout")):
            result = self.agent.synthesize(
                "How many customers?", ["count"], [[200]])
        assert result["answer"] is None
        assert "Synthesis failed" in result["error"]
