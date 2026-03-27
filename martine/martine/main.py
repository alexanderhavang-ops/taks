from __future__ import annotations

import json
import sys

from martine.agent.simple_agent import run_once
from martine.config import load_config
from martine.llm.bedrock_adapter import MartineLlm
from martine.mcp_server.client import call_tool_via_mcp, list_tools_via_mcp
from martine.mcp_server.fastmcp_app import run_stdio, run_streamable_http
from martine.mcp_server.server import call_tool, list_tools


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cfg = load_config()

    if not argv:
        print(
            json.dumps(
                {
                    "name": "martine",
                    "status": "ok",
                    "config": {
                        "state_dir": cfg.state_dir,
                        "log_level": cfg.log_level,
                        "mcp_bind_host": cfg.mcp_bind_host,
                        "mcp_bind_port": cfg.mcp_bind_port,
                    },
                    "commands": [
                        "info",
                        "mcp-tools",
                        "mcp-call <tool_name> [json_args]",
                        "mcp-client-tools",
                        "mcp-client-call <tool_name> [json_args]",
                        "mcp-stdio",
                        "mcp-http",
                        "llm-info",
                        "llm-smoke [prompt]",
                        "ask <question>",
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    cmd = argv[0]

    if cmd == "info":
        print(
            json.dumps(
                {
                    "name": "martine",
                    "status": "ok",
                    "config": {
                        "state_dir": cfg.state_dir,
                        "log_level": cfg.log_level,
                        "mcp_bind_host": cfg.mcp_bind_host,
                        "mcp_bind_port": cfg.mcp_bind_port,
                    },
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if cmd == "mcp-tools":
        print(json.dumps({"tools": list_tools()}, indent=2, sort_keys=True))
        return 0

    if cmd == "mcp-call":
        if len(argv) < 2:
            raise SystemExit("usage: python -m martine.main mcp-call <tool_name> [json_args]")
        tool_name = argv[1]
        tool_args = json.loads(argv[2]) if len(argv) >= 3 else {}
        result = call_tool(tool_name, tool_args)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if cmd == "mcp-client-tools":
        print(json.dumps({"tools": list_tools_via_mcp()}, indent=2, sort_keys=True))
        return 0

    if cmd == "mcp-client-call":
        if len(argv) < 2:
            raise SystemExit("usage: python -m martine.main mcp-client-call <tool_name> [json_args]")
        tool_name = argv[1]
        tool_args = json.loads(argv[2]) if len(argv) >= 3 else {}
        result = call_tool_via_mcp(tool_name, tool_args)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if cmd == "mcp-stdio":
        run_stdio()
        return 0

    if cmd == "mcp-http":
        run_streamable_http()
        return 0

    if cmd == "llm-info":
        llm = MartineLlm()
        print(json.dumps(llm.info(), indent=2, sort_keys=True))
        return 0

    if cmd == "llm-smoke":
        prompt = argv[1] if len(argv) >= 2 else "Reply with exactly: MARTINE_OK"
        llm = MartineLlm()
        result = llm.complete_text(
            prompt=prompt,
            temperature=0.0,
            max_tokens=80,
            purpose="martine:smoke",
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if cmd == "ask":
        if len(argv) < 2:
            raise SystemExit('usage: python -m martine.main ask "<question>"')
        question = " ".join(argv[1:]).strip()
        result = run_once(question)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    raise SystemExit(f"unknown command: {cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
