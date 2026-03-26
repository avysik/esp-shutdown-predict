def normalize_pandas_freq(freq: str) -> str:
    """
    Normalize pandas frequency string to lowercase aliases.

    Examples:
        1H -> 1h
        H  -> h
        15T -> 15min (опционально)
    """
    if not freq:
        raise ValueError("time_step is empty")

    return freq.lower()