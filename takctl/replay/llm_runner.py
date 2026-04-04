from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))
REPO_ROOT = SCRIPT_ROOT.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from takctl.services.llm2.llm_client import LlmClient  # type: ignore
from prompting import render_prompts


def run_model(
    *,
    packet: Dict[str, Any],
    temperature: float,
    max_tokens: int,
    seed: int,
    system_prompt_override: Optional[str] = None,
    user_prompt_override: Optional[str] = None,
    full_prompt_override: Optional[str] = None,
) -> Dict[str, Any]:
    client = LlmClient()

    if full_prompt_override is not None:
        system_prompt = system_prompt_override or ""
        user_prompt = user_prompt_override or ""
        full_prompt = full_prompt_override
    elif system_prompt_override is not None or user_prompt_override is not None:
        system_prompt = system_prompt_override or ""
        user_prompt = user_prompt_override or ""
        full_prompt = system_prompt.rstrip() + "\n\n" + user_prompt.rstrip() + "\n"
    else:
        prompts = render_prompts(packet)
        system_prompt = prompts["system_prompt"]
        user_prompt = prompts["user_prompt"]
        full_prompt = prompts["full_prompt"]

    resp = client.complete_text(
        prompt=full_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        seed=seed,
        purpose="replay:llm",
    )

    return {
        "ok": bool(resp.get("ok")),
        "text": resp.get("text") or "",
        "provider": resp.get("provider"),
        "model": resp.get("model"),
        "url": resp.get("url"),
        "http_status": resp.get("http_status"),
        "body_bytes": resp.get("body_bytes"),
        "error": resp.get("error"),
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "full_prompt": full_prompt,
        "raw": resp,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--packet", required=True, help="Path to JSON packet")
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--max-tokens", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--show-meta", action="store_true")
    ap.add_argument("--show-prompts", action="store_true")
    args = ap.parse_args()

    packet = json.loads(Path(args.packet).read_text(encoding="utf-8"))

    result = run_model(
        packet=packet,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        seed=args.seed,
    )

    if args.show_meta:
        meta = {
            "ok": result["ok"],
            "provider": result["provider"],
            "model": result["model"],
            "url": result["url"],
            "http_status": result["http_status"],
            "body_bytes": result["body_bytes"],
            "error": result["error"],
        }
        print(json.dumps(meta, ensure_ascii=False, indent=2))
        print()

    if args.show_prompts:
        print("SYSTEM PROMPT")
        print("=" * 80)
        print(result["system_prompt"].rstrip())
        print()
        print("USER PROMPT")
        print("=" * 80)
        print(result["user_prompt"].rstrip())
        print()
        print("FULL PROMPT")
        print("=" * 80)
        print(result["full_prompt"].rstrip())
        print()

    if not result["ok"]:
        raise RuntimeError(result["error"] or "LLM call failed")

    text = result["text"]
    sys.stdout.write(text)
    if text and not text.endswith("\n"):
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
