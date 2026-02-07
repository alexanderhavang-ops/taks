from __future__ import annotations

import typer
from rich.console import Console

from takctl.infra.db import DB
from takctl.infra import jsonout
from takctl.services.llmchat import build_llmchat_from_env

console = Console()


def register(app: typer.Typer) -> None:
    @app.command("llmchat")
    def llmchat(
        ctx: typer.Context,
        prompt: str = typer.Argument(..., help="Your question/prompt for the LLM"),
        mode: str = typer.Option(
            "agent",
            "--mode",
            help="plain: prompt→LLM(text).  agent: JSON protocol loop with SQL execution.",
        ),
        model: str = typer.Option("", "--model", help="Override model alias (default: env TAKS_LLM_MODEL or local-small)"),
        llm_url: str = typer.Option("", "--llm-url", help="Override LLM URL (default: env TAKS_LLM_URL or http://127.0.0.1:8090)"),
        max_steps: int = typer.Option(6, "--max-steps", help="agent mode: max LLM↔DB iterations"),
        max_rows: int = typer.Option(80, "--max-rows", help="agent mode: row cap per SQL execution"),
    ) -> None:
        """
        Fast dev loop for LLM integration.
        """
        appctx = (ctx.obj or {}).get("appctx")
        json_flag = bool((ctx.obj or {}).get("json"))

        llmchat = build_llmchat_from_env()
        if llm_url.strip():
            llmchat.llm.llm_url = llm_url.strip()
        if model.strip():
            llmchat.llm.model = model.strip()

        m = (mode or "agent").strip().lower()
        if m not in ("plain", "agent"):
            raise typer.BadParameter("mode must be 'plain' or 'agent'")

        if m == "plain":
            out = llmchat.ask_plain(prompt)
        else:
            if appctx is None or getattr(appctx, "cfg", None) is None:
                raise RuntimeError("No AppContext available on typer ctx.obj['appctx']")
            db = DB(appctx.cfg)
            out = llmchat.ask_agent(
                db=db,
                question=prompt,
                max_steps=max_steps,
                max_rows=max_rows,
                schema_bundle=None,  # wired later (schema snapshot / bundle)
            )

        if json_flag:
            console.print(jsonout.dumps(out))
            return

        # Human readable (minimal)
        if m == "plain":
            console.print(out.get("answer", ""))
            return

        # agent mode: RenderPlan-ish blocks
        blocks = out.get("blocks") or []
        for b in blocks:
            if (b.get("type") or "") == "markdown":
                console.print(f"\n[bold]{b.get('title','')}[/bold]\n{b.get('body','')}")
            elif (b.get("type") or "") == "json":
                console.print(f"\n[bold]{b.get('title','JSON')}[/bold]\n{jsonout.dumps(b.get('body'))}")
            else:
                console.print(str(b))


# Optional: Typer fallback (not used if register() exists)
app = typer.Typer(add_completion=False)

