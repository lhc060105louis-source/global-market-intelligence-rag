ALIASES = {
    "UK": "GB",
    "UNITED KINGDOM": "GB",
    "GB": "GB",
    "英国": "GB",
    "FR": "FR",
    "FRANCE": "FR",
    "法国": "FR",
    "DE": "DE",
    "GERMANY": "DE",
    "德国": "DE",
    "MULTI": "MULTI",
}


def normalize_market(value: str) -> str:
    stripped = value.strip()
    key = stripped.upper() if stripped.isascii() else stripped
    try:
        return ALIASES[key]
    except KeyError as exc:
        raise ValueError(f"Unsupported market: {value}") from exc
