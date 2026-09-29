ALIASES = {
    "UK": "GB",
    "UNITED KINGDOM": "GB",
    "GB": "GB",
    "United Kingdom": "GB",
    "FR": "FR",
    "FRANCE": "FR",
    "France": "FR",
    "DE": "DE",
    "GERMANY": "DE",
    "Germany": "DE",
    "MULTI": "MULTI",
}


def normalize_market(value: str) -> str:
    stripped = value.strip()
    key = stripped.upper() if stripped.isascii() else stripped
    try:
        return ALIASES[key]
    except KeyError as exc:
        raise ValueError(f"Unsupported market: {value}") from exc
