from __future__ import annotations

from typing import Dict

import requests
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import JSONResponse

from takctl.config import load_config

router = APIRouter(prefix="/api/geo", tags=["geo"])


def _truthy(v: str) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


def _cfg_dict() -> Dict[str, str]:
    cfg = load_config()
    out: Dict[str, str] = {}
    try:
        vals = getattr(cfg, "values", {}) or {}
        for k, v in vals.items():
            out[str(k)] = "" if v is None else str(v)
    except Exception:
        pass
    return out


def _tiles_mode() -> str:
    cfg = _cfg_dict()
    return (cfg.get("osm_tiles_mode") or "external").strip().lower()


def _tiles_url_template() -> str:
    cfg = _cfg_dict()
    return (
        cfg.get("osm_tiles_url")
        or "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    ).strip()


def _routing_mode() -> str:
    cfg = _cfg_dict()
    return (cfg.get("routing_mode") or "external").strip().lower()


def _routing_url() -> str:
    cfg = _cfg_dict()
    return (cfg.get("routing_url") or "").strip().rstrip("/")


def _routing_local_url() -> str:
    cfg = _cfg_dict()
    return (cfg.get("routing_local_url") or "http://127.0.0.1:5000").strip().rstrip("/")


def _routing_base() -> str:
    mode = _routing_mode()
    if mode == "node_local":
        return _routing_local_url()
    return _routing_url()


@router.get("/config")
def geo_config():
    cfg = _cfg_dict()
    return JSONResponse({
        "ok": True,
        "tiles": {
            "enabled": _truthy(cfg.get("osm_tiles_enabled", "true")),
            "mode": _tiles_mode(),
            "url": _tiles_url_template(),
        },
        "routing": {
            "enabled": _truthy(cfg.get("routing_enabled", "true")),
            "mode": _routing_mode(),
            "url": _routing_url(),
            "local_url": _routing_local_url(),
            "effective_url": _routing_base(),
        },
    })


@router.get("/tiles/{z}/{x}/{y}.png")
def geo_tiles(z: int, x: int, y: int):
    cfg = _cfg_dict()
    if not _truthy(cfg.get("osm_tiles_enabled", "true")):
        raise HTTPException(status_code=404, detail="tiles disabled")

    tpl = _tiles_url_template()
    upstream = tpl.replace("{z}", str(int(z))).replace("{x}", str(int(x))).replace("{y}", str(int(y)))

    try:
        r = requests.get(
            upstream,
            timeout=20,
            headers={"User-Agent": "TAKS-GeoProxy/1.0"},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"tile upstream error: {e}")

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"tile upstream returned {r.status_code}")

    content_type = r.headers.get("Content-Type", "image/png")
    cache_control = r.headers.get("Cache-Control", "public, max-age=3600")

    return Response(
        content=r.content,
        media_type=content_type,
        headers={"Cache-Control": cache_control},
    )


@router.get("/osrm/nearest/v1/{profile}/{lon},{lat}")
def geo_osrm_nearest(
    profile: str,
    lon: float,
    lat: float,
    number: int = Query(1),
):
    cfg = _cfg_dict()
    if not _truthy(cfg.get("routing_enabled", "true")):
        raise HTTPException(status_code=404, detail="routing disabled")

    base = _routing_base()
    if not base:
        raise HTTPException(status_code=500, detail="routing base url missing")

    upstream = f"{base}/nearest/v1/{profile}/{lon:.6f},{lat:.6f}"
    try:
        r = requests.get(
            upstream,
            params={"number": str(int(number))},
            timeout=20,
            headers={"User-Agent": "TAKS-GeoProxy/1.0"},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"osrm nearest upstream error: {e}")

    return Response(
        content=r.content,
        media_type=r.headers.get("Content-Type", "application/json"),
        status_code=r.status_code,
    )


@router.get("/osrm/route/v1/{profile}/{coords}")
def geo_osrm_route(
    profile: str,
    coords: str,
    overview: str = Query("full"),
    geometries: str = Query("geojson"),
    steps: str = Query("true"),
    alternatives: str = Query("false"),
):
    cfg = _cfg_dict()
    if not _truthy(cfg.get("routing_enabled", "true")):
        raise HTTPException(status_code=404, detail="routing disabled")

    base = _routing_base()
    if not base:
        raise HTTPException(status_code=500, detail="routing base url missing")

    upstream = f"{base}/route/v1/{profile}/{coords}"
    try:
        r = requests.get(
            upstream,
            params={
                "overview": overview,
                "geometries": geometries,
                "steps": steps,
                "alternatives": alternatives,
            },
            timeout=30,
            headers={"User-Agent": "TAKS-GeoProxy/1.0"},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"osrm route upstream error: {e}")

    return Response(
        content=r.content,
        media_type=r.headers.get("Content-Type", "application/json"),
        status_code=r.status_code,
    )
