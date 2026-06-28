import datetime

from pydantic import BaseModel, Field
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import PydanticOutputParser

from app.ai.llm import llm
from app.ai.utils import format_asset_data, add_lifecycle_context


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
    },
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
