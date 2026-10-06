import pytest
from unittest.mock import AsyncMock, MagicMock

from agents.retriever_agent import RetrieverAgent


class FakeRecord:
    def __init__(self, data):
        self.data = data

    def keys(self):
        return self.data.keys()

    def values(self):
        return self.data.values()


class FakeConnection:
    def __init__(self, records):
        self.records = records

    async def fetch(self, sql):
        return self.records


class FakeAcquire:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, tb):
        pass


class FakePool:
    def __init__(self, records):
        self.connection = FakeConnection(records)

    def acquire(self):
        return FakeAcquire(self.connection)


@pytest.mark.asyncio
async def test_first_page(monkeypatch):

    records = [
        FakeRecord({"id": 1, "name": "A"}),
        FakeRecord({"id": 2, "name": "B"}),
        FakeRecord({"id": 3, "name": "C"}),
        FakeRecord({"id": 4, "name": "D"}),
        FakeRecord({"id": 5, "name": "E"}),
    ]

    monkeypatch.setattr(
        "agents.retriever_agent.get_pool",
        lambda: FakePool(records)
    )

    agent = RetrieverAgent()

    result = await agent.execute(
        "SELECT * FROM customers",
        page=1,
        page_size=2
    )

    assert result["rows"] == [
        [1, "A"],
        [2, "B"]
    ]

    assert result["row_count"] == 2
    assert result["total_rows"] == 5
    assert result["page"] == 1
    assert result["page_size"] == 2
    assert result["has_next"] is True


@pytest.mark.asyncio
async def test_second_page(monkeypatch):

    records = [
        FakeRecord({"id": 1, "name": "A"}),
        FakeRecord({"id": 2, "name": "B"}),
        FakeRecord({"id": 3, "name": "C"}),
        FakeRecord({"id": 4, "name": "D"}),
        FakeRecord({"id": 5, "name": "E"}),
    ]

    monkeypatch.setattr(
        "agents.retriever_agent.get_pool",
        lambda: FakePool(records)
    )

    agent = RetrieverAgent()

    result = await agent.execute(
        "SELECT * FROM customers",
        page=2,
        page_size=2
    )

    assert result["rows"] == [
        [3, "C"],
        [4, "D"]
    ]

    assert result["row_count"] == 2
    assert result["total_rows"] == 5
    assert result["page"] == 2
    assert result["has_next"] is True


@pytest.mark.asyncio
async def test_last_page(monkeypatch):

    records = [
        FakeRecord({"id": 1, "name": "A"}),
        FakeRecord({"id": 2, "name": "B"}),
        FakeRecord({"id": 3, "name": "C"}),
        FakeRecord({"id": 4, "name": "D"}),
        FakeRecord({"id": 5, "name": "E"}),
    ]

    monkeypatch.setattr(
        "agents.retriever_agent.get_pool",
        lambda: FakePool(records)
    )

    agent = RetrieverAgent()

    result = await agent.execute(
        "SELECT * FROM customers",
        page=3,
        page_size=2
    )

    assert result["rows"] == [
        [5, "E"]
    ]

    assert result["row_count"] == 1
    assert result["total_rows"] == 5
    assert result["page"] == 3
    assert result["has_next"] is False


@pytest.mark.asyncio
async def test_page_beyond_results(monkeypatch):

    records = [
        FakeRecord({"id": 1, "name": "A"}),
        FakeRecord({"id": 2, "name": "B"}),
        FakeRecord({"id": 3, "name": "C"}),
    ]

    monkeypatch.setattr(
        "agents.retriever_agent.get_pool",
        lambda: FakePool(records)
    )

    agent = RetrieverAgent()

    result = await agent.execute(
        "SELECT * FROM customers",
        page=5,
        page_size=2
    )

    assert result["rows"] == []
    assert result["row_count"] == 0
    assert result["total_rows"] == 3
    assert result["page"] == 5
    assert result["has_next"] is False
