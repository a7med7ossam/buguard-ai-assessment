def merge_metadata(existing: dict, incoming: dict) -> dict:
    """
    Recursively merge two metadata dictionaries.

    Nested dictionaries are merged rather than overwritten, so that data
    arriving from a second source enriches the existing record instead of
    clobbering it. Non-dict values from `incoming` win on conflict
    (last-write-wins at the leaf level).
    """
    merged = existing.copy()

    for key, value in incoming.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = merge_metadata(merged[key], value)
        else:
            merged[key] = value

    return merged
