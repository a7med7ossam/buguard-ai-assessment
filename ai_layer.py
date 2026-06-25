import os
from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

from langchain_community.utilities import SQLDatabase
from langchain_community.tools import QuerySQLDatabaseTool


from dotenv import load_dotenv
load_dotenv()

# Initialize the Gemini model
# Using flash for speed, temperature 0 for deterministic, factual outputs

# 1. Initialize the LangChain ChatOpenAI wrapper, pointing it to Gemini!
llm = ChatOpenAI(
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    model="gemini-3-flash-preview", 
    temperature=0
)


# --- 1. Automated Enrichment & Categorization ---

class EnrichmentResult(BaseModel):
    environment: str = Field(description="One of: prod, staging, dev, or unknown")
    category: str = Field(description="e.g., web_server, database, mail, internal_tool")
    criticality: str = Field(description="low, medium, high, or critical")

enrichment_parser = PydanticOutputParser(pydantic_object=EnrichmentResult)

enrichment_prompt = PromptTemplate(
    template="Analyze the following cybersecurity asset and categorize it.\n{format_instructions}\nAsset details:\n{asset_data}\n",
    input_variables=["asset_data"],
    partial_variables={"format_instructions": enrichment_parser.get_format_instructions()}
)

def enrich_asset(asset_data: dict) -> dict:
    chain = enrichment_prompt | llm | enrichment_parser
    result = chain.invoke({"asset_data": str(asset_data)})
    return result.dict()

# --- 2. Risk Scoring & Summarization ---

class RiskScoreResult(BaseModel):
    risk_score: int = Field(description="Score from 1 to 10")
    risk_level: str = Field(description="Low, Medium, High, or Critical")
    summary: str = Field(description="A concise 2-sentences summary of the risk")

risk_parser = PydanticOutputParser(pydantic_object=RiskScoreResult)

risk_prompt = PromptTemplate(
    template="Evaluate the cybersecurity risk of this asset. Look for expired certificates, exposed ports, or stale status.\n{format_instructions}\nAsset:\n{asset_data}\n",
    input_variables=["asset_data"],
    partial_variables={"format_instructions": risk_parser.get_format_instructions()}
)

def evaluate_risk(asset_data: dict) -> dict:
    chain = risk_prompt | llm | risk_parser
    result = chain.invoke({"asset_data": str(asset_data)})
    return result.dict()

# --- 3. Report Generation ---

def generate_report(inventory_data: list) -> str:
    prompt = PromptTemplate.from_template(
        "You are an expert security analyst. Review the following asset inventory and write a concise, professional executive summary detailing the overall attack surface risk. Do NOT invent data.\n\nInventory:\n{inventory}"
    )
    chain = prompt | llm
    result = chain.invoke({"inventory": str(inventory_data)})
    return result.content



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
            raise ValueError("Only SELECT statements are allowed.")

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
            "error": str(e)
        }


