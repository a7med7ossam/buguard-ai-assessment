import os
import json
import datetime

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

from langchain_community.utilities import SQLDatabase
from langchain_community.tools import QuerySQLDatabaseTool

from dotenv import load_dotenv
load_dotenv()


# model="gemini-3-flash-preview"
# 1. Initialize the LangChain ChatOpenAI wrapper, pointing it to Gemini!
llm = ChatOpenAI(
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    model="gemini-3.1-flash-lite", 
    temperature=0
)


def format_asset_data(data: dict) -> str:
    """
    Format asset data as pretty JSON for improved LLM readability.
    """
    return json.dumps(data, indent=2, default=str)


def add_lifecycle_context(asset_data: dict) -> dict:
    """
    Compute lifecycle information for assets that contain an 'expires' date
    in metadata and add it to the payload sent to the LLM.
    """
    asset = dict(asset_data)  # shallow copy

    metadata = dict(asset.get("metadata", {}))
    expires = metadata.get("expires")

    if not expires:
        return asset

    try:
        expiry_date = datetime.datetime.strptime(expires, "%Y-%m-%d").date()
        today = datetime.datetime.now(datetime.UTC).date()

        days_remaining = (expiry_date - today).days

        asset["lifecycle"] = {
            "days_until_expiration": days_remaining,
            "expired": days_remaining < 0,
            "expiring_soon": 0 <= days_remaining <= 30,
        }

    except ValueError:
        asset["lifecycle"] = {
            "date_parse_error": True
        }

    return asset


# --- 1. Automated Enrichment & Categorization ---

class EnrichmentResult(BaseModel):
    environment: str = Field(description="One of: prod, staging, dev, or unknown")
    category: str = Field(description="e.g., web_server, database, mail, internal_tool")
    criticality: str = Field(description="low, medium, high, or critical")

enrichment_parser = PydanticOutputParser(pydantic_object=EnrichmentResult)

enrichment_prompt = PromptTemplate(
    template="""
        You are a senior cybersecurity analyst specializing in Attack Surface Management (ASM).

        Today's date:
        {today}

        Your task is to classify and enrich the following asset.

        The supplied asset may already include computed lifecycle information
        (e.g. expired, expiring_soon, days_until_expiration).

        Use those computed values when present instead of recalculating them.

        If lifecycle information is absent, reason from the metadata and today's date.

        Rules:

        - Use ONLY the supplied asset data.
        - Never invent missing metadata.
        - If information is unavailable, return "unknown".
        - Determine:
            • environment (prod, staging, dev, unknown)
            • category
            • criticality
        - Consider:
            • asset type
            • hostname
            • tags
            • metadata
            • naming conventions

        Return ONLY the structured output requested.

        {format_instructions}

        Asset:

        {asset_data}
    """,
    input_variables=["asset_data", "today"],
    partial_variables={
        "format_instructions": enrichment_parser.get_format_instructions()
    }
)

def enrich_asset(asset_data: dict) -> dict:
    chain = enrichment_prompt | llm | enrichment_parser
    prepared_asset = add_lifecycle_context(asset_data)
    result = chain.invoke(
        {
            "asset_data": format_asset_data(prepared_asset),
            "today": datetime.datetime.now(datetime.UTC).date().isoformat(),
        }
    )
    return result.dict()


# --- 2. Risk Scoring & Summarization ---

class RiskScoreResult(BaseModel):
    risk_score: int = Field(description="Score from 1 to 10")
    risk_level: str = Field(description="Low, Medium, High, or Critical")
    summary: str = Field(description="A concise summary of the risk")

risk_parser = PydanticOutputParser(pydantic_object=RiskScoreResult)

risk_prompt = PromptTemplate(
    template="""
You are a senior cybersecurity risk analyst.

Today's date:

{today}

Assess the cybersecurity risk of the supplied asset.

Use ONLY the supplied data.

Never invent vulnerabilities.

The supplied asset may already include computed lifecycle information
(e.g. expired, expiring_soon, days_until_expiration).

Use those computed values when present instead of recalculating them.

If lifecycle information is absent, reason from the metadata and today's date.

Consider:

- asset status
- exposed services
- technology versions
- certificate expiry
- metadata
- tags

Assign:

- risk score (1–10)
- risk level
- concise professional summary

{format_instructions}

Asset:

{asset_data}
""",
    input_variables=["asset_data", "today"],
    partial_variables={
        "format_instructions": risk_parser.get_format_instructions()
    }
)

def evaluate_risk(asset_data: dict) -> dict:
    chain = risk_prompt | llm | risk_parser
    prepared_asset = add_lifecycle_context(asset_data)
    result = chain.invoke(
        {
            "asset_data": format_asset_data(prepared_asset),
            "today": datetime.datetime.now(datetime.UTC).date().isoformat(),
        }
    )    
    return result.dict()


# --- 3. Report Generation ---

def generate_report(inventory_data: list) -> str:
    report_prompt = PromptTemplate(
        template="""
    You are preparing an executive Attack Surface Management report.

    Today's date:

    {today}

    Review ONLY the supplied inventory.

    Do not invent assets.

    Summarize:

    - inventory size
    - asset distribution
    - exposed services
    - expired or expiring certificates
    - stale assets
    - notable risks
    - recommendations

    Write in a concise professional style suitable for a security manager.

    Inventory:

    {inventory}
    """
    )

    chain = report_prompt | llm
    result = chain.invoke(
        {
            "inventory": json.dumps(inventory_data, indent=2),
            "today": datetime.datetime.now(datetime.UTC).date().isoformat(),
        }
    )    
    return result.content


# --- 4. SQL Generation from NL ---

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

    result = chain.invoke({
        "query": user_query,
        "schema": schema
    })

    return result.content.strip()


def nl_asset_query(user_query: str) -> str:
    db = SQLDatabase.from_uri(os.getenv("DATABASE_URL"))
    tool = QuerySQLDatabaseTool(db=db)

    FORBIDDEN_TERMS = [
        "delete",
        "drop",
        "update",
        "insert"
    ]

    if any(term in user_query.lower() for term in FORBIDDEN_TERMS):
        return {
            "success": False,
            "error": "Dangerous queries are not allowed."
        }
    
    AMBIGUOUS_TERMS = [
        "risky",
        "important",
        "critical",
        "interesting",
        "dangerous"
    ]

    if any(term in user_query.lower() for term in AMBIGUOUS_TERMS):
        return {
            "success": False,
            "error": "Query is ambiguous. Please specify measurable criteria."
        }

    try:
        # 1. Generate SQL from natural language with schema awareness
        sql_query = generate_sql_query(user_query, db)

        sql_lower = sql_query.lower().strip()

        if not sql_lower.startswith("select"):
            return {
                "success": False,
                "error": "Only SELECT statements are allowed."
            }

        # 2. Execute SQL
        result = tool.invoke(sql_query)

        return {
                    "success": True,
                    "sql": sql_query,
                    "result": result
                }
    
    except Exception as e:
        return {
            "success": False,
            "error": "Failed to execute generated query.",
            "details": str(e)
        }


