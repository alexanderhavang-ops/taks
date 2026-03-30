from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

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
    return (cfg.get("osm_tiles_url") or "https://tile.openstreetmap.org/{z}/{x}/{y}.png").strip()


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


def _overpass_url() -> str:
    cfg = _cfg_dict()
    return (cfg.get("overpass_url") or "https://overpass-api.de/api/interpreter").strip()


def _area_summary_default_radius_m() -> int:
    cfg = _cfg_dict()
    try:
        return max(100, min(int(cfg.get("area_summary_default_radius_m", "1000")), 5000))
    except Exception:
        return 1000


def _area_summary_poi_limit() -> int:
    cfg = _cfg_dict()
    try:
        return max(1, min(int(cfg.get("area_summary_poi_limit", "12")), 30))
    except Exception:
        return 12


def _classify_vehicle_mobility(roads: Counter, water: Counter, wet: int) -> str:
    good_roads = sum(roads.get(k, 0) for k in ("motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified"))
    small_roads = sum(roads.get(k, 0) for k in ("service", "track"))
    if water.total() > 0 or wet > 0:
        if good_roads >= 2:
            return "good_on_roads_limited_offroad"
        return "restricted"
    if good_roads >= 3:
        return "good_on_roads"
    if good_roads >= 1 or small_roads >= 2:
        return "mixed"
    return "limited"


def _classify_foot_mobility(roads: Counter, natural: Counter, water: Counter, wet: int) -> str:
    path_like = sum(roads.get(k, 0) for k in ("path", "footway", "track", "service", "residential"))
    woodland = natural.get("wood", 0) + natural.get("tree_row", 0) + natural.get("scrub", 0)
    if water.total() > 1 or wet > 0:
        if path_like >= 2:
            return "mixed"
        return "restricted"
    if path_like >= 2 or woodland >= 1:
        return "good"
    return "good"


def _classify_concealment(buildings: int, woodland: int, openish: int) -> str:
    cover = buildings + woodland
    if cover >= 20:
        return "good"
    if cover >= 6:
        return "moderate"
    if openish >= 3:
        return "poor"
    return "limited"


def _classify_observation(openish: int, woodland: int, buildings: int) -> str:
    if openish >= 4 and woodland <= 1 and buildings <= 10:
        return "good"
    if woodland >= 4 or buildings >= 20:
        return "limited"
    return "mixed"


def _top_named_pois(elements: List[Dict[str, Any]], limit: int) -> List[str]:
    rows: List[str] = []
    seen = set()
    for el in elements:
        tags = el.get("tags") or {}
        name = str(tags.get("name") or "").strip()
        if not name:
            continue
        kind = (
            tags.get("amenity")
            or tags.get("tourism")
            or tags.get("shop")
            or tags.get("leisure")
            or tags.get("building")
            or tags.get("place")
            or tags.get("landuse")
            or tags.get("natural")
            or tags.get("highway")
            or ""
        )
        label = f"{name} ({kind})" if kind else name
        if label in seen:
            continue
        seen.add(label)
        rows.append(label)
        if len(rows) >= limit:
            break
    return rows


def _build_tactical_assessment(
    roads: Counter,
    buildings: int,
    natural: Counter,
    water: Counter,
    named_pois: List[str],
) -> Dict[str, Any]:
    likely_routes: List[str] = []
    if sum(roads.get(k, 0) for k in ("primary", "secondary", "tertiary", "residential")) > 0:
        likely_routes.append("road approach likely")
    if roads.get("track", 0) > 0 or roads.get("path", 0) > 0 or roads.get("footway", 0) > 0:
        likely_routes.append("foot infiltration via tracks/paths possible")
    if buildings >= 15:
        likely_routes.append("covered movement through built-up area possible")
    if natural.get("wood", 0) + natural.get("scrub", 0) >= 2:
        likely_routes.append("concealed movement via tree cover possible")
    if not likely_routes:
        likely_routes.append("approach routes appear limited and exposed")

    op_positions: List[str] = []
    if buildings >= 10:
        op_positions.append("built-up edge positions")
    if natural.get("wood", 0) + natural.get("tree_row", 0) >= 2:
        op_positions.append("tree line / woodland edge")
    if water.get("coastline", 0) > 0 or water.get("water", 0) > 0:
        op_positions.append("waterfront observation line")
    if sum(roads.get(k, 0) for k in ("primary", "secondary", "tertiary")) > 0:
        op_positions.append("road junction overwatch")
    if not op_positions:
        op_positions.append("few obvious observation positions detected")

    risk_areas: List[str] = []
    if water.total() > 0:
        risk_areas.append("water obstacle / exposed shoreline")
    if sum(roads.get(k, 0) for k in ("primary", "secondary")) > 0:
        risk_areas.append("road crossing / avenue of approach")
    if buildings < 5 and natural.get("wood", 0) == 0:
        risk_areas.append("open ground exposure")
    if not risk_areas:
        risk_areas.append("terrain appears mixed with no single dominant risk area")

    key_features = named_pois[:6]
    return {
        "likely_approach_routes": likely_routes[:4],
        "good_op_positions": op_positions[:4],
        "risk_areas": risk_areas[:4],
        "named_features": key_features,
    }


def _overpass_query(lat: float, lon: float, radius_m: int) -> str:
    return f"""
[out:json][timeout:25];
(
  way(around:{radius_m},{lat},{lon})[highway];
  way(around:{radius_m},{lat},{lon})[building];
  way(around:{radius_m},{lat},{lon})[landuse];
  way(around:{radius_m},{lat},{lon})[natural];
  way(around:{radius_m},{lat},{lon})[waterway];
  way(around:{radius_m},{lat},{lon})[railway];
  way(around:{radius_m},{lat},{lon})[leisure];
  way(around:{radius_m},{lat},{lon})[amenity];
  way(around:{radius_m},{lat},{lon})[tourism];
  node(around:{radius_m},{lat},{lon})[amenity];
  node(around:{radius_m},{lat},{lon})[tourism];
  node(around:{radius_m},{lat},{lon})[shop];
  node(around:{radius_m},{lat},{lon})[place];
);
out tags center qt;
""".strip()


def _fetch_overpass(lat: float, lon: float, radius_m: int) -> List[Dict[str, Any]]:
    try:
        r = requests.post(
            _overpass_url(),
            data={"data": _overpass_query(lat, lon, radius_m)},
            timeout=35,
            headers={"User-Agent": "TAKS-GeoProxy/1.0"},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"overpass upstream error: {e}")

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"overpass upstream returned {r.status_code}")

    try:
        body = r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"overpass invalid json: {e}")

    return list(body.get("elements") or [])


def _summarize_area(lat: float, lon: float, radius_m: int) -> Dict[str, Any]:
    elements = _fetch_overpass(lat, lon, radius_m)

    roads: Counter = Counter()
    landuse: Counter = Counter()
    natural: Counter = Counter()
    water: Counter = Counter()
    railway: Counter = Counter()
    leisure: Counter = Counter()

    building_count = 0
    amenity_count = 0
    tourism_count = 0
    place_count = 0
    wet = 0

    for el in elements:
        tags = el.get("tags") or {}
        if tags.get("highway"):
            roads[str(tags.get("highway"))] += 1
        if tags.get("building"):
            building_count += 1
        if tags.get("landuse"):
            landuse[str(tags.get("landuse"))] += 1
        if tags.get("natural"):
            natural[str(tags.get("natural"))] += 1
        if tags.get("waterway"):
            water[str(tags.get("waterway"))] += 1
        if tags.get("railway"):
            railway[str(tags.get("railway"))] += 1
        if tags.get("leisure"):
            leisure[str(tags.get("leisure"))] += 1
        if tags.get("amenity"):
            amenity_count += 1
        if tags.get("tourism"):
            tourism_count += 1
        if tags.get("place"):
            place_count += 1
        if tags.get("natural") in {"wetland", "marsh"} or tags.get("landuse") in {"basin", "reservoir"}:
            wet += 1
        if tags.get("water") or tags.get("natural") == "water":
            water["water"] += 1
        if tags.get("natural") == "coastline":
            water["coastline"] += 1

    named_pois = _top_named_pois(elements, _area_summary_poi_limit())

    primary = roads.get("motorway", 0) + roads.get("trunk", 0) + roads.get("primary", 0)
    secondary = roads.get("secondary", 0) + roads.get("tertiary", 0)
    small_roads = roads.get("residential", 0) + roads.get("unclassified", 0) + roads.get("service", 0)
    tracks = roads.get("track", 0) + roads.get("path", 0) + roads.get("footway", 0) + roads.get("cycleway", 0)

    woodland = natural.get("wood", 0) + natural.get("scrub", 0) + natural.get("tree_row", 0) + landuse.get("forest", 0)
    openish = (
        natural.get("grassland", 0)
        + natural.get("heath", 0)
        + landuse.get("farmland", 0)
        + landuse.get("meadow", 0)
        + landuse.get("grass", 0)
    )

    return {
        "ok": True,
        "source": {
            "provider": "overpass",
            "url": _overpass_url(),
            "element_count": len(elements),
        },
        "center": {"lat": lat, "lon": lon},
        "radius_m": radius_m,
        "roads": {
            "primary": primary,
            "secondary": secondary,
            "small_roads": small_roads,
            "tracks_and_paths": tracks,
            "by_type": dict(sorted(roads.items())),
        },
        "built_up": {
            "buildings": building_count,
            "amenities": amenity_count,
            "tourism_features": tourism_count,
            "places": place_count,
        },
        "terrain": {
            "landuse": dict(sorted(landuse.items())),
            "natural": dict(sorted(natural.items())),
            "water": dict(sorted(water.items())),
            "railway": dict(sorted(railway.items())),
            "leisure": dict(sorted(leisure.items())),
        },
        "mobility": {
            "foot": _classify_foot_mobility(roads, natural, water, wet),
            "vehicle": _classify_vehicle_mobility(roads, water, wet),
            "concealment": _classify_concealment(building_count, woodland, openish),
            "observation": _classify_observation(openish, woodland, building_count),
        },
        "named_pois": named_pois,
        "tactical_assessment": _build_tactical_assessment(
            roads=roads,
            buildings=building_count,
            natural=natural,
            water=water,
            named_pois=named_pois,
        ),
    }


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
        "area_summary": {
            "enabled": _truthy(cfg.get("area_summary_enabled", "true")),
            "overpass_url": _overpass_url(),
            "default_radius_m": _area_summary_default_radius_m(),
            "poi_limit": _area_summary_poi_limit(),
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
        r = requests.get(upstream, timeout=20, headers={"User-Agent": "TAKS-GeoProxy/1.0"})
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"tile upstream error: {e}")

    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"tile upstream returned {r.status_code}")

    return Response(
        content=r.content,
        media_type=r.headers.get("Content-Type", "image/png"),
        headers={"Cache-Control": r.headers.get("Cache-Control", "public, max-age=3600")},
    )


@router.get("/area_summary")
def geo_area_summary(
    lat: float = Query(...),
    lon: float = Query(...),
    radius_m: int = Query(None),
):
    cfg = _cfg_dict()
    if not _truthy(cfg.get("area_summary_enabled", "true")):
        raise HTTPException(status_code=404, detail="area summary disabled")

    rr = radius_m if radius_m is not None else _area_summary_default_radius_m()
    rr = max(100, min(int(rr), 5000))
    return JSONResponse(_summarize_area(float(lat), float(lon), rr))


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

    try:
        r = requests.get(
            f"{base}/nearest/v1/{profile}/{lon:.6f},{lat:.6f}",
            params={"number": str(int(number))},
            timeout=20,
            headers={"User-Agent": "TAKS-GeoProxy/1.0"},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"osrm nearest upstream error: {e}")

    return Response(content=r.content, media_type=r.headers.get("Content-Type", "application/json"), status_code=r.status_code)


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

    try:
        r = requests.get(
            f"{base}/route/v1/{profile}/{coords}",
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

    return Response(content=r.content, media_type=r.headers.get("Content-Type", "application/json"), status_code=r.status_code)
