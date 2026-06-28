from typing import Optional

# Write-type SQL keywords are refused outright. The NL->SQL layer is read-only.
FORBIDDEN_TERMS = [
    "delete",
    "drop",
    "update",
    "insert",
]

# Subjective words have no measurable mapping to columns, so we refuse rather
# than let the model guess a definition of "risky" / "important" / etc.
AMBIGUOUS_TERMS = [
    "risky",
    "important",
    "critical",
    "interesting",
    "dangerous",
]


def check_query_guardrails(user_query: str) -> Optional[dict]:
    """
    Pre-flight checks on a natural-language query, run *before* any LLM call.

    Returns an error dict if the query should be rejected, or None if it is
    allowed to proceed to SQL generation.
    """
    lowered = user_query.lower()

    if any(term in lowered for term in FORBIDDEN_TERMS):
        return {
            "success": False,
            "error": "Dangerous queries are not allowed.",
        }

    if any(term in lowered for term in AMBIGUOUS_TERMS):
        return {
            "success": False,
            "error": "Query is ambiguous. Please specify measurable criteria.",
        }

    return None
