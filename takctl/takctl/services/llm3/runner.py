from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from martine_server import AgentLoop, RunContext, load_config as load_martine_config, resolve_profile
from martine_server.tracing import TraceWriter, new_run_id

from takctl.config import load_config as load_takctl_config
from takctl.services.llm3.paths import latest_root, runs_root
from takctl.services.llm3.domain_config import (
    discover_enabled_domains,
    load_domain_config,
    phase_enabled,
    phase_input,
    phase_output_schema,
    upstream_domains,
)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _read_json(p: Path) -> Any:
    return json.loads(_read_text(p))


def _write_json(p: Path, payload: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _runtime_language() -> str:
    try:
        return str(load_takctl_config().get("language", "sv") or "sv").strip().lower() or "sv"
    except Exception:
        return "sv"


def _load_prompt_text_pair(base: Path, file_stem: str = "") -> tuple[str, str]:
    lang = _runtime_language()
    name_prefix = f"{file_stem}_" if file_stem else ""
    candidates = [
        (base / lang / f"{name_prefix}system.txt", base / lang / f"{name_prefix}user.txt"),
        (base / "en" / f"{name_prefix}system.txt", base / "en" / f"{name_prefix}user.txt"),
        (base / f"{name_prefix}system.txt", base / f"{name_prefix}user.txt"),
    ]
    for sys_p, usr_p in candidates:
        s = _read_text(sys_p).strip()
        u = _read_text(usr_p).strip()
        if s and u:
            return s, u
    return "", ""


def _phase1_payload(dom: str) -> dict[str, Any]:
    p = Path("/opt/tak/tools/takctl/state/llm2/latest") / dom / "phase1" / "latest.json"
    if not p.exists():
        return {}
    try:
        obj = _read_json(p)
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _upstream_findings(cfg: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": True, "domains": {}}
    for upstream in upstream_domains(cfg):
        p = Path("/opt/tak/tools/takctl/state/llm2/latest") / upstream / "phase2" / "findings.json"
        if not p.exists():
            continue
        try:
            out["domains"][upstream] = {"ok": True, "findings": _read_json(p)}
        except Exception as e:
            out["domains"][upstream] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return out


def _build_phase2_input(dom: str, cfg: dict[str, Any]) -> str:
    input_kind = phase_input(cfg, "phase2")
    if input_kind == "upstream_phase2_findings":
        payload = _upstream_findings(cfg)
    else:
        payload = _phase1_payload(dom)
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _selected_domains(infra_dir: Path, domain: str | None, phase: str) -> list[str]:
    if domain:
        return [domain]
    return [d for d in discover_enabled_domains(infra_dir) if phase_enabled(load_domain_config(infra_dir, d), phase)]


def run_phase2(*, domain: str | None = None) -> dict[str, Any]:
    takctl_cfg = load_takctl_config()
    infra_dir = Path(str(takctl_cfg.get("llm_infra_dir", "/opt/tak/tools/takctl/llm-infra")))
    martine_cfg = load_martine_config()
    run_id = new_run_id("llm3")
    results: dict[str, Any] = {"ok": True, "run_id": run_id, "phase": "phase2", "domains": {}}

    for dom in _selected_domains(infra_dir, domain, "phase2"):
        cfg = load_domain_config(infra_dir, dom)
        prompt_base = infra_dir / "domains" / dom / "prompts" / "phase2"
        system_txt, user_txt = _load_prompt_text_pair(prompt_base)
        if not system_txt or not user_txt:
            results["domains"][dom] = {"ok": False, "error": "missing_phase2_prompts"}
            results["ok"] = False
            continue

        workload = f"{dom}.phase2"
        profile = resolve_profile("llm3", workload)
        trace = TraceWriter(martine_cfg.trace_dir, f"{run_id}-{dom}-phase2")
        ctx = RunContext(
            client="llm3",
            workload=workload,
            run_id=run_id,
            state_root=martine_cfg.state_dir,
            trace_root=martine_cfg.trace_dir,
            language=_runtime_language(),
            output_schema=phase_output_schema(cfg, "phase2"),
            max_turns=int(profile.get("max_turns", 8)),
            max_tool_calls=int(profile.get("max_tool_calls", 12)),
            max_output_tokens=int(profile.get("max_output_tokens", getattr(martine_cfg, "default_max_output_tokens", 2000))),
            allow_repair_turn=bool(profile.get("allow_repair_turn", True)),
            purpose_prefix=f"llm3:{dom}:phase2",
        )
        loop = AgentLoop(ctx, trace)
        user_input = user_txt.strip() + "\n\n## INPUT\n" + _build_phase2_input(dom, cfg)
        res = loop.run(
            system_prompt=system_txt,
            user_input=user_input,
            final_format=f"structured JSON object matching {ctx.output_schema or 'domain schema'}",
        )

        payload = res.answer_json if isinstance(res.answer_json, dict) else {}
        trace_payload = {
            "ok": res.ok,
            "domain": dom,
            "phase": "phase2",
            "run_id": run_id,
            "started_at_utc": _now_iso(),
            "output_schema": ctx.output_schema,
            "trace_dir": str(trace.path),
            "error": res.error,
        }
        dom_latest = latest_root() / dom / "phase2"
        dom_run = runs_root() / run_id / dom / "phase2"
        _write_json(dom_latest / "findings.json", payload)
        _write_json(dom_latest / "trace.json", trace_payload)
        _write_json(dom_run / "findings.json", payload)
        _write_json(dom_run / "trace.json", trace_payload)

        results["domains"][dom] = {
            "ok": res.ok,
            "findings": payload,
            "trace_dir": str(trace.path),
            "error": res.error,
        }
        if not res.ok:
            results["ok"] = False

    _write_json(latest_root() / "run.latest.json", {"ok": True, "run_id": run_id, "phase": "phase2"})
    return results


def run_phase3(*, domain: str | None = None) -> dict[str, Any]:
    takctl_cfg = load_takctl_config()
    infra_dir = Path(str(takctl_cfg.get("llm_infra_dir", "/opt/tak/tools/takctl/llm-infra")))
    martine_cfg = load_martine_config()
    run_id = new_run_id("llm3")
    results: dict[str, Any] = {"ok": True, "run_id": run_id, "phase": "phase3", "domains": {}}

    for dom in _selected_domains(infra_dir, domain, "phase3"):
        findings_p = latest_root() / dom / "phase2" / "findings.json"
        if not findings_p.exists():
            results["domains"][dom] = {"ok": False, "error": "missing_llm3_phase2_findings"}
            results["ok"] = False
            continue

        findings_json = json.dumps(_read_json(findings_p), ensure_ascii=False, indent=2)
        prompt_base = infra_dir / "domains" / dom / "prompts" / "phase3"
        card_out: dict[str, Any] = {}
        detail_out: dict[str, Any] = {}
        errors: list[str] = []

        for kind in ("card", "detail"):
            system_txt, user_txt = _load_prompt_text_pair(prompt_base, kind)
            if not system_txt or not user_txt:
                errors.append(f"missing_phase3_{kind}_prompts")
                continue

            workload = f"{dom}.phase3.{kind}"
            profile = resolve_profile("llm3", workload)
            trace = TraceWriter(martine_cfg.trace_dir, f"{run_id}-{dom}-phase3-{kind}")
            ctx = RunContext(
                client="llm3",
                workload=workload,
                run_id=run_id,
                state_root=martine_cfg.state_dir,
                trace_root=martine_cfg.trace_dir,
                language=_runtime_language(),
                output_schema="phase3.html.v1",
                max_turns=int(profile.get("max_turns", 6)),
                max_tool_calls=int(profile.get("max_tool_calls", 10)),
                max_output_tokens=int(profile.get("max_output_tokens", getattr(martine_cfg, "default_max_output_tokens", 2000))),
                allow_repair_turn=bool(profile.get("allow_repair_turn", True)),
                purpose_prefix=f"llm3:{dom}:phase3:{kind}",
            )
            loop = AgentLoop(ctx, trace)
            user_input = user_txt.strip() + "\n\n## INPUT_FINDINGS_JSON\n" + findings_json
            res = loop.run(system_prompt=system_txt, user_input=user_input, final_format="JSON object with html field")
            payload = res.answer_json if isinstance(res.answer_json, dict) else {}
            trace_payload = {
                "ok": res.ok,
                "domain": dom,
                "phase": "phase3",
                "kind": kind,
                "run_id": run_id,
                "trace_dir": str(trace.path),
                "error": res.error,
            }
            dom_run = runs_root() / run_id / dom / "phase3"
            _write_json(dom_run / f"{kind}.json", payload)
            _write_json(dom_run / f"trace.{kind}.json", trace_payload)
            if kind == "card":
                card_out = payload
            else:
                detail_out = payload
            if not res.ok:
                errors.append(f"{kind}:{res.error}")

        dom_latest = latest_root() / dom / "phase3"
        _write_json(dom_latest / "card.json", card_out)
        _write_json(dom_latest / "detail.json", detail_out)
        _write_json(dom_latest / "trace.json", {"ok": not errors, "domain": dom, "run_id": run_id, "errors": errors})
        results["domains"][dom] = {"ok": not errors, "card": card_out, "detail": detail_out, "errors": errors}
        if errors:
            results["ok"] = False

    _write_json(latest_root() / "run.latest.json", {"ok": True, "run_id": run_id, "phase": "phase3"})
    return results
