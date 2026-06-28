import datetime

from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

from app.ai.llm import llm
from app.ai.utils import format_asset_data, add_lifecycle_context


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

- risk score (1-10)
- risk level
- concise professional summary

{format_instructions}

Asset:

{asset_data}
""",
    input_variables=["asset_data", "today"],
    partial_variables={
        "format_instructions": risk_parser.get_format_instructions()
    },
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
