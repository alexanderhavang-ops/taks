from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool

from takctl.services.llm3.paths import state_root, latest_root, runs_root
from takctl.services.llm3.runner import run_phase2, run_phase3
from takctl.services.llm3.domain_config import load_domain_config

router = APIRouter(prefix='/api/llm3', tags=['llm3'])


def _read_json(p: Path) -> Dict[str, Any]:
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception as e:
        return {'ok': False, 'error': f'{type(e).__name__}: {e}', 'path': str(p)}




def _domain_meta(domain: str) -> Dict[str, Any]:
    try:
        infra_dir = Path('/opt/tak/tools/takctl/llm-infra')
        cfg = load_domain_config(infra_dir, domain)
        return {
            'domain': domain,
            'section': str(cfg.get('section') or '').strip(),
            'card_title': str(cfg.get('card_title') or '').strip(),
            'mode': str(cfg.get('mode') or '').strip(),
            'enabled': bool(cfg.get('enabled', True)),
        }
    except Exception as e:
        return {
            'domain': domain,
            'section': '',
            'card_title': '',
            'mode': '',
            'enabled': True,
            'meta_error': f'{type(e).__name__}: {e}',
        }

def _latest_phase(domain: str, phase: str) -> Dict[str, Any]:
    d = latest_root() / domain / phase
    out: Dict[str, Any] = {'ok': True, 'dir': str(d), 'files': {}}
    if not d.exists():
        out['ok'] = False
        out['error'] = 'missing'
        return out
    for name in ('findings.json', 'trace.json', 'card.json', 'detail.json'):
        p = d / name
        if p.exists():
            out['files'][name] = _read_json(p)
    return out


@router.get('/latest')
def latest() -> Dict[str, Any]:
    resp: Dict[str, Any] = {
        'ok': True,
        'state_root': str(state_root()),
        'latest_root': str(latest_root()),
        'runs_root': str(runs_root()),
        'run': None,
        'domains': {},
    }
    run_ptr = latest_root() / 'run.latest.json'
    resp['run'] = _read_json(run_ptr) if run_ptr.exists() else {
        'ok': False,
        'error': 'missing',
        'path': str(run_ptr),
    }
    if not latest_root().exists():
        resp['ok'] = False
        resp['error'] = 'latest_root_missing'
        return resp
    for dom_dir in sorted([p for p in latest_root().iterdir() if p.is_dir()]):
        dom = dom_dir.name
        resp['domains'][dom] = {
            'meta': _domain_meta(dom),
            'phase2': _latest_phase(dom, 'phase2'),
            'phase3': _latest_phase(dom, 'phase3'),
        }
    return resp


@router.post('/run/phase2')
async def api_run_phase2(req: Request) -> Dict[str, Any]:
    try:
        body = await req.json()
    except Exception:
        body = {}
    dom = str((body or {}).get('domain') or '').strip() or None
    return await run_in_threadpool(run_phase2, domain=dom)


@router.post('/run/phase3')
async def api_run_phase3(req: Request) -> Dict[str, Any]:
    try:
        body = await req.json()
    except Exception:
        body = {}
    dom = str((body or {}).get('domain') or '').strip() or None
    return await run_in_threadpool(run_phase3, domain=dom)
