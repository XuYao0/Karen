DEFAULT_HTTP_TIMEOUT_SECONDS = 50.0


def normalize_base_url(value: str) -> str:
    return value.rstrip("/")
