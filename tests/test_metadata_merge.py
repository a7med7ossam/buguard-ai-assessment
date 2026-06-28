from app.services.merge import merge_metadata


def test_new_keys_are_added():
    existing = {"banner": "nginx"}
    incoming = {"tls_version": "1.3"}
    assert merge_metadata(existing, incoming) == {
        "banner": "nginx",
        "tls_version": "1.3",
    }


def test_leaf_conflict_last_write_wins():
    existing = {"issuer": "Let's Encrypt"}
    incoming = {"issuer": "DigiCert"}
    assert merge_metadata(existing, incoming) == {"issuer": "DigiCert"}


def test_nested_dicts_are_merged_not_overwritten():
    existing = {"cert": {"issuer": "Let's Encrypt", "expires": "2025-01-02"}}
    incoming = {"cert": {"serial": "abc123"}}
    assert merge_metadata(existing, incoming) == {
        "cert": {
            "issuer": "Let's Encrypt",
            "expires": "2025-01-02",
            "serial": "abc123",
        }
    }


def test_original_is_not_mutated():
    existing = {"a": 1}
    incoming = {"b": 2}
    merge_metadata(existing, incoming)
    assert existing == {"a": 1}
