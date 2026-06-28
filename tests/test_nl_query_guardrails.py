from app.ai.guardrails import check_query_guardrails


def test_forbidden_write_keyword_is_rejected():
    result = check_query_guardrails("delete all stale assets")
    assert result is not None
    assert result["success"] is False
    assert "not allowed" in result["error"].lower()


def test_ambiguous_term_is_rejected():
    result = check_query_guardrails("show me the risky assets")
    assert result is not None
    assert result["success"] is False
    assert "ambiguous" in result["error"].lower()


def test_well_formed_read_query_passes():
    result = check_query_guardrails(
        "list all certificates that expire before 2025-01-01"
    )
    assert result is None


def test_check_is_case_insensitive():
    assert check_query_guardrails("DROP TABLE assets") is not None
