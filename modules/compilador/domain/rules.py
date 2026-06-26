def is_invalid_qm_value(value: str) -> bool:
    if not value:
        return True

    upper = value.upper().strip()

    invalid_tokens = [
        "QUALQUER",
        "00-QUALQUER",
        "QMG 00-QUALQUER",
    ]

    return any(token in upper for token in invalid_tokens)