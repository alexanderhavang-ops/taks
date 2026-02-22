from __future__ import annotations

from takctl.services.llm_jobs.store import read_job, write_job, write_latest
from takctl.services.llm_planner import plan_with_tools
from takctl.services.snapshots.tactical import build_tactical_snapshot


def run_tactical_job(job_id: str) -> None:
    rec = read_job(job_id) or {"ok": False, "job_id": job_id, "view": "tactical-operations"}
    view = str(rec.get("view") or "tactical-operations")

    rec["ok"] = True
    rec["status"] = "running"
    write_job(rec)

    try:
        snapshot = build_tactical_snapshot()
        plan = plan_with_tools(
            view=view,
            snapshot=snapshot,
            model="local-small",
            max_iters=6,
            max_tokens=450,
        )

        # Persist latest view output (what UI reads on page-load)
        write_latest(view, plan)

        rec["status"] = "done"
        rec["plan"] = plan
        write_job(rec)

    except Exception as e:
        rec["status"] = "error"
        rec["error"] = f"{type(e).__name__}: {e}"
        write_job(rec)
