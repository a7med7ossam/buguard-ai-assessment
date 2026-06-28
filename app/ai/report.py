import json
import datetime

from langchain_core.prompts import PromptTemplate

from app.ai.llm import llm


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

    Formatting requirements:

    - Return the report in GitHub-Flavored Markdown.
    - Use:
        - # for the title
        - ## for major sections
        - Bullet lists where appropriate
        - Numbered lists for recommendations
    - Do not wrap the output in Markdown code fences (```).

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
