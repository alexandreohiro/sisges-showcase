import re
import unicodedata


def slugify_filename(value: str, fallback: str = "registro") -> str:
    value = (value or "").strip()
    if not value:
        return fallback

    value = unicodedata.normalize("NFKD", value)
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")

    return value or fallback


def normalize_line_breaks(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value