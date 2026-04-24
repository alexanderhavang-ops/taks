from __future__ import annotations

import html
import re
import secrets
from xml.sax.saxutils import escape as _xml_escape

_ALLOWED_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[#%])[A-Za-z0-9#%]{20,24}$")
_ENTRY_RE = re.compile(r"(<entry\b[^>]*>)(.*?)(</entry>)", re.DOTALL)

_WORDS = (
    "amber", "anchor", "apex", "arrow", "atlas", "aurora", "badger", "baker",
    "baron", "beacon", "birch", "blaze", "bravo", "brick", "bronze", "cabin",
    "cannon", "cedar", "charlie", "cinder", "cobalt", "comet", "copper", "coral",
    "crane", "crisp", "crown", "delta", "ember", "falcon", "fern", "fjord",
    "flare", "flint", "forest", "frost", "galaxy", "gamma", "garden", "glacier",
    "granite", "harbor", "hazel", "helix", "hickory", "horizon", "hunter", "iris",
    "jaguar", "jasmine", "juniper", "keeper", "kilo", "ladder", "lantern", "laser",
    "legend", "lima", "linen", "magnet", "maple", "matrix", "meadow", "mercury",
    "meteor", "micro", "midnight", "mistral", "monarch", "moose", "mosaic", "navy",
    "nectar", "nickel", "nova", "oasis", "omega", "onyx", "opal", "orbit",
    "orchid", "origin", "otter", "panther", "paper", "paradox", "phoenix", "pilot",
    "pine", "pixel", "plasma", "polar", "prairie", "prime", "prism", "pulse",
    "python", "quartz", "quest", "quill", "radar", "ranger", "raven", "reef",
    "relay", "resin", "rhino", "rocket", "rook", "rose", "saber", "saffron",
    "sage", "saturn", "scarlet", "shadow", "signal", "silver", "skane", "solstice",
    "sparrow", "spirit", "spruce", "star", "steel", "stone", "storm", "summit",
    "swift", "talon", "tango", "terra", "thunder", "tiger", "timber", "topaz",
    "torch", "tower", "tracker", "trident", "tulip", "turbo", "umbra", "vector",
    "velvet", "vertex", "violet", "viper", "vivid", "voyage", "walnut", "whiskey",
    "willow", "winter", "wolf", "xray", "yankee", "zephyr", "zinc", "zulu",
)

_SPECIALS = "#%"
_SEP_CHARS = "0123456789#%"


def xml_escape_text(value: object) -> str:
    s = "" if value is None else str(value)
    return _xml_escape(s, {"'": "&apos;", '"': "&quot;"})


def sanitize_pref_xml(xml_text: str) -> str:
    def _repl(m: re.Match[str]) -> str:
        inner = html.unescape(m.group(2))
        return f"{m.group(1)}{xml_escape_text(inner)}{m.group(3)}"
    return _ENTRY_RE.sub(_repl, xml_text)


def is_valid_friendly_password(value: str) -> bool:
    return bool(_ALLOWED_RE.match(value))


def _mix_case(word: str) -> str:
    out = []
    for ch in word:
        if ch.isalpha():
            out.append(ch.upper() if secrets.randbelow(2) else ch.lower())
        else:
            out.append(ch)
    return "".join(out)


def _force_requirements(s: str) -> str:
    chars = list(s)

    if not any(c.islower() for c in chars):
        for i, c in enumerate(chars):
            if c.isalpha():
                chars[i] = c.lower()
                break

    if not any(c.isupper() for c in chars):
        for i, c in enumerate(chars):
            if c.isalpha():
                chars[i] = c.upper()
                break

    if not any(c.isdigit() for c in chars):
        for i, c in enumerate(chars):
            if c in _SEP_CHARS:
                chars[i] = secrets.choice("0123456789")
                break

    if not any(c in _SPECIALS for c in chars):
        for i, c in enumerate(chars):
            if c in _SEP_CHARS:
                chars[i] = secrets.choice(_SPECIALS)
                break

    return "".join(chars)


def generate_friendly_password(min_len: int = 20, max_len: int = 24) -> str:
    for _ in range(10000):
        word_count = secrets.choice((4, 5))
        words = [_mix_case(secrets.choice(_WORDS)) for _ in range(word_count)]

        sep_chunks = []
        for _i in range(word_count - 1):
            sep_len = 1 + secrets.randbelow(2)
            sep_chunks.append("".join(secrets.choice(_SEP_CHARS) for _ in range(sep_len)))

        parts = []
        for i, word in enumerate(words):
            parts.append(word)
            if i < len(sep_chunks):
                parts.append(sep_chunks[i])

        candidate = "".join(parts)
        candidate = _force_requirements(candidate)

        if len(candidate) < min_len:
            continue
        if len(candidate) > max_len:
            continue
        if is_valid_friendly_password(candidate):
            return candidate

    raise RuntimeError("failed to generate a password matching the friendly policy")
