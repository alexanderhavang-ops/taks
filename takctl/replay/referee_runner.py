from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path("/opt/taks")
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from takctl.services.llm2.llm_client import LlmClient  # type: ignore


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def build_referee_prompt(packet: Dict[str, Any]) -> tuple[str, str, str]:
    system_prompt = _read_text("takctl/replay/prompts/system/referee_system.txt")
    user_template = _read_text("takctl/replay/prompts/user/referee_user.txt")
    input_json = json.dumps(packet, ensure_ascii=False, indent=2)
    user_prompt = user_template.replace("{{INPUT_JSON}}", input_json)
    full_prompt = system_prompt + "\n\n" + user_prompt
    return system_prompt, user_prompt, full_prompt


def run_referee_llm(
    packet: Dict[str, Any],
    *,
    temperature: float = 0.1,
    max_tokens: int = 500,
    seed: int = 7,
) -> Dict[str, Any]:
    system_prompt, user_prompt, full_prompt = build_referee_prompt(packet)

    client = LlmClient()
    resp = client.complete_text(
        prompt=full_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        seed=seed,
    )

    text = str(resp.get("text") or "")

    if not resp.get("ok"):
        return {
            "ok": False,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "full_prompt": full_prompt,
            "raw_text": text,
            "data": None,
            "provider": resp.get("provider"),
            "model": resp.get("model"),
            "url": resp.get("url"),
            "http_status": resp.get("http_status"),
            "body_bytes": resp.get("body_bytes"),
            "error": resp.get("error"),
            "raw": resp,
        }

    try:
        data = json.loads(text)
    except Exception as e:
        return {
            "ok": False,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "full_prompt": full_prompt,
            "raw_text": text,
            "data": None,
            "provider": resp.get("provider"),
            "model": resp.get("model"),
            "url": resp.get("url"),
            "http_status": resp.get("http_status"),
            "body_bytes": resp.get("body_bytes"),
            "error": f"JSON parse failed: {e}",
            "raw": resp,
        }

    return {
        "ok": True,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "full_prompt": full_prompt,
        "raw_text": text,
        "data": data,
        "provider": resp.get("provider"),
        "model": resp.get("model"),
        "url": resp.get("url"),
        "http_status": resp.get("http_status"),
        "body_bytes": resp.get("body_bytes"),
        "error": resp.get("error"),
        "raw": resp,
    }
