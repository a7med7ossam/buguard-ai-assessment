import datetime

from app.ai.utils import add_lifecycle_context


def _date_str(days_from_today: int) -> str:
    today = datetime.datetime.now(datetime.UTC).date()
    return (today + datetime.timedelta(days=days_from_today)).strftime("%Y-%m-%d")


def test_no_expires_returns_asset_without_lifecycle():
    asset = {"id": "x", "metadata": {"banner": "nginx"}}
    result = add_lifecycle_context(asset)
    assert "lifecycle" not in result


def test_expired_certificate_is_flagged():
    asset = {"id": "cert", "metadata": {"expires": _date_str(-10)}}
    result = add_lifecycle_context(asset)
    assert result["lifecycle"]["expired"] is True
    assert result["lifecycle"]["expiring_soon"] is False
    assert result["lifecycle"]["days_until_expiration"] < 0


def test_expiring_soon_certificate_is_flagged():
    asset = {"id": "cert", "metadata": {"expires": _date_str(10)}}
    result = add_lifecycle_context(asset)
    assert result["lifecycle"]["expired"] is False
    assert result["lifecycle"]["expiring_soon"] is True


def test_far_future_certificate_is_neither():
    asset = {"id": "cert", "metadata": {"expires": _date_str(365)}}
    result = add_lifecycle_context(asset)
    assert result["lifecycle"]["expired"] is False
    assert result["lifecycle"]["expiring_soon"] is False


def test_malformed_date_is_reported_not_crashing():
    asset = {"id": "cert", "metadata": {"expires": "not-a-date"}}
    result = add_lifecycle_context(asset)
    assert result["lifecycle"] == {"date_parse_error": True}
