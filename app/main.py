from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agents.schema_agent import SchemaAgent
from agents.sql_generator_agent import SQLGeneratorAgent
from agents.retriever_agent import RetrieverAgent
from agents.synthesizer_agent import SynthesizerAgent


app = FastAPI(title="QueryPilot")


# ---------------------------------------------------------
# Agents
# ---------------------------------------------------------

schema_agent = SchemaAgent()
sql_agent = SQLGeneratorAgent()
retriever_agent = RetrieverAgent()
synthesizer_agent = SynthesizerAgent()


# ---------------------------------------------------------
# Request Model
# ---------------------------------------------------------

class AskRequest(BaseModel):
    question: str
    page: int = 1
    page_size: int = 50


# ---------------------------------------------------------
# Response Model
# ---------------------------------------------------------

class AskResponse(BaseModel):
    question: str
    answer: str | None
    sql_query: str | None

    columns: list
    rows: list
    row_count: int

    # Pagination information
    total_rows: int = 0
    page: int = 1
    page_size: int = 50
    has_next: bool = False

    relevant_tables: list[str]

    retried: bool = False
    from_cache: bool = False

    doc_context: list = []

    error: str | None


# ---------------------------------------------------------
# Root Endpoint
# ---------------------------------------------------------

@app.get("/")
async def root():
    return {
        "message": "QueryPilot API is running"
    }


# ---------------------------------------------------------
# Ask Endpoint
# ---------------------------------------------------------

@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):

    question = req.question.strip()

    # -----------------------------------------------------
    # Validate question
    # -----------------------------------------------------

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty."
        )

    # -----------------------------------------------------
    # Validate pagination
    # -----------------------------------------------------

    if req.page < 1:
        raise HTTPException(
            status_code=400,
            detail="Page must be greater than or equal to 1."
        )

    if req.page_size < 1 or req.page_size > 200:
        raise HTTPException(
            status_code=400,
            detail="Page size must be between 1 and 200."
        )

    # -----------------------------------------------------
    # Error helper
    # -----------------------------------------------------

    def err(
        message: str,
        sql_query: str | None = None,
        relevant_tables: list[str] | None = None
    ):

        return AskResponse(
            question=question,

            answer=None,

            sql_query=sql_query,

            columns=[],

            rows=[],

            row_count=0,

            total_rows=0,

            page=req.page,

            page_size=req.page_size,

            has_next=False,

            relevant_tables=relevant_tables or [],

            retried=False,

            from_cache=False,

            doc_context=[],

            error=message
        )

    # -----------------------------------------------------
    # Step 1: Get database schema
    # -----------------------------------------------------

    try:

        schema = await schema_agent.get_schema()

    except Exception as exc:

        return err(
            f"Schema retrieval failed: {exc}"
        )

    # -----------------------------------------------------
    # Step 2: Generate SQL
    # -----------------------------------------------------

    try:

        sql_result = sql_agent.generate(
            question,
            schema
        )

    except Exception as exc:

        return err(
            f"SQL generation failed: {exc}"
        )

    # -----------------------------------------------------
    # Check SQL generation result
    # -----------------------------------------------------

    if not sql_result.get("sql"):

        return err(
            sql_result.get(
                "error",
                "Unable to generate SQL."
            )
        )

    sql_query = sql_result["sql"]

    relevant_tables = sql_result.get(
        "relevant_tables",
        []
    )

    # -----------------------------------------------------
    # Step 3: Execute SQL with pagination
    # -----------------------------------------------------

    try:

        db_result = await retriever_agent.execute(
            sql_query,
            question,
            sql_agent,
            page=req.page,
            page_size=req.page_size
        )

    except Exception as exc:

        return err(
            f"Database execution failed: {exc}",
            sql_query,
            relevant_tables
        )

    # -----------------------------------------------------
    # Check database result
    # -----------------------------------------------------

    if db_result.get("error"):

        return err(
            db_result["error"],

            db_result.get(
                "sql_used",
                sql_query
            ),

            relevant_tables
        )

    # -----------------------------------------------------
    # Extract database results
    # -----------------------------------------------------

    columns = db_result.get(
        "columns",
        []
    )

    rows = db_result.get(
        "rows",
        []
    )

    row_count = db_result.get(
        "row_count",
        len(rows)
    )

    sql_used = db_result.get(
        "sql_used",
        sql_query
    )

    retried = db_result.get(
        "retried",
        False
    )

    # -----------------------------------------------------
    # Pagination metadata
    # -----------------------------------------------------

    total_rows = db_result.get(
        "total_rows",
        row_count
    )

    page = db_result.get(
        "page",
        req.page
    )

    page_size = db_result.get(
        "page_size",
        req.page_size
    )

    has_next = db_result.get(
        "has_next",
        False
    )

    # -----------------------------------------------------
    # Document context
    # -----------------------------------------------------

    # No separate DocRAGAgent exists in the current project.
    doc_context = []

    # -----------------------------------------------------
    # Step 4: Generate final answer
    # -----------------------------------------------------

    try:

        answer = await synthesizer_agent.synthesize(
            question=question,
            columns=columns,
            rows=rows,
            doc_context=doc_context
        )

    except Exception as exc:

        return AskResponse(

            question=question,

            answer=None,

            sql_query=sql_used,

            columns=columns,

            rows=rows,

            row_count=row_count,

            total_rows=total_rows,

            page=page,

            page_size=page_size,

            has_next=has_next,

            relevant_tables=relevant_tables,

            retried=retried,

            from_cache=False,

            doc_context=doc_context,

            error=f"Answer synthesis failed: {exc}"
        )

    # -----------------------------------------------------
    # Final response
    # -----------------------------------------------------

    return AskResponse(

        question=question,

        answer=answer,

        sql_query=sql_used,

        columns=columns,

        rows=rows,

        row_count=row_count,

        total_rows=total_rows,

        page=page,

        page_size=page_size,

        has_next=has_next,

        relevant_tables=relevant_tables,

        retried=retried,

        from_cache=False,

        doc_context=doc_context,

        error=None
    )
