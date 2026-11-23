"""Language for generated speech and text on this node."""

from pathlib import Path

CORE_CONFIG = Path("/opt/tak/tools/takctl/conf.d/core.conf")
LANGUAGE_NAMES = {"en": "English", "sv": "Swedish"}
_ALIASES = {
    "en": "en", "en_us": "en", "en_gb": "en", "english": "en",
    "sv": "sv", "sv_se": "sv", "swedish": "sv",
}


def normalize_language(value: str) -> str:
    language = _ALIASES.get(str(value).strip().lower().replace("-", "_"))
    if language is None:
        raise ValueError("Node language must be en (English) or sv (Swedish)")
    return language


def node_language(path: Path | None = None) -> str:
    path = path or CORE_CONFIG
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "en"
    language = "en"
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip().lower() == "language":
            language = normalize_language(value)
    return language
