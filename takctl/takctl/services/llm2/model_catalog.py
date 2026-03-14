from __future__ import annotations

from typing import Dict, List


_LOCAL = [
    {"id": "local-small", "label": "Local (llama.cpp) — local-small"},
]

_BEDROCK = [
    {"id": "anthropic.claude-3-5-sonnet-20240620-v1:0", "label": "Claude 3.5 Sonnet"},
    {"id": "anthropic.claude-3-5-haiku-20241022-v1:0", "label": "Claude 3.5 Haiku"},
    {"id": "amazon.titan-text-premier-v1:0", "label": "Titan Text Premier"},
    {"id": "amazon.titan-text-express-v1", "label": "Titan Text Express"},
    {"id": "meta.llama3-70b-instruct-v1:0", "label": "Llama 3 70B Instruct"},
    {"id": "meta.llama3-8b-instruct-v1:0", "label": "Llama 3 8B Instruct"},
    {"id": "mistral.mistral-large-2402-v1:0", "label": "Mistral Large"},
    {"id": "mistral.mistral-small-2402-v1:0", "label": "Mistral Small"},
]


def list_models(provider: str) -> List[Dict[str, str]]:
    p = (provider or "local").strip().lower()
    if p == "bedrock":
        return list(_BEDROCK)
    return list(_LOCAL)
