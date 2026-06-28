import os

from langchain_core.prompts import PromptTemplate
from langchain_community.utilities import SQLDatabase
from langchain_community.tools import QuerySQLDatabaseTool

from app.ai.llm import llm
from app.ai.guardrails import check_query_guardrails


def generate_sql_query(user_query: str, db: SQLDatabase) -> str:
    schema = db.get_table_info()

    prompt = PromptTemplate.from_template(
        """
        You are a PostgreSQL expert.

        Database schema:
        {schema}

        Convert the following natural language query into a SQL SELECT query.

        Rules:
        - ONLY generate SELECT statements
        - NEVER generate INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE
        - Use ONLY the tables and columns provided in the schema
        - Do NOT invent table or column names
        - Return ONLY SQL

        Query:
        {query}
        """
    )

    chain = prompt | llm

    result = chain.invoke(
        {
            "query": user_query,
            "schema": schema,
        }
    )

    return result.content.strip()


def nl_asset_query(user_query: str) -> dict:
    """
    Translate a plain-English question into a read-only SQL query and execute
    it. Layered guardrails keep this safe and grounded:

      1. Pre-flight term checks (forbidden write verbs, ambiguous adjectives).
      2. SELECT-only enforcement on the generated SQL.
      3. Schema-aware prompt so the model can't reference non-existent columns.
    """
    db = SQLDatabase.from_uri(os.getenv("DATABASE_URL"))
    tool = QuerySQLDatabaseTool(db=db)

    guardrail_error = check_query_guardrails(user_query)
    if guardrail_error is not None:
        return guardrail_error

    try:
        # 1. Generate SQL from natural language with schema awareness.
        sql_query = generate_sql_query(user_query, db)

        sql_lower = sql_query.lower().strip()

        if not sql_lower.startswith("select"):
            return {
                "success": False,
                "error": "Only SELECT statements are allowed.",
            }

        # 2. Execute the validated SQL.
        result = tool.invoke(sql_query)

        return {
            "success": True,
            "sql": sql_query,
            "result": result,
        }

    except Exception as e:
        return {
            "success": False,
            "error": "Failed to execute generated query.",
            "details": str(e),
        }
