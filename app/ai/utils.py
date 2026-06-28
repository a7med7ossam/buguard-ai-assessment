import json
import datetime


def format_asset_data(data: dict) -> str:
    """Format asset data as pretty JSON for improved LLM readability."""
    return json.dumps(data, indent=2, default=str)


def add_lifecycle_context(asset_data: dict) -> dict:
    """
    Compute lifecycle information for assets that carry an 'expires' date in
    metadata, and attach it to the payload before it goes to the LLM.

    Pre-computing this (rather than asking the model to do date math) is a
    grounding guardrail: the model is told to trust these values instead of
    inventing its own, which keeps expired/expiring-soon judgements correct.
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
        asset["lifecycle"] = {"date_parse_error": True}

    return asset
