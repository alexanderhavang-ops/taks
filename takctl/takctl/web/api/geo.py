from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Tuple

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


def _feature_limit() -> int:
    cfg = _cfg_dict()
    try:
        return max(50, min(int(cfg.get("area_geometry_feature_limit", "400")), 1500))
    except Exception:
        return 400


def _center_of(el: Dict[str, Any]) -> Tuple[float | None, float | None]:
    if "lat" in el and "lon" in el:
        try:
            return float(el["lat"]), float(el["lon"])
        except Exception:
            return None, None
    c = el.get("center") or {}
    if "lat" in c and "lon" in c:
        try:
            return float(c["lat"]), float(c["lon"])
        except Exception:
            return None, None
    return None, None


def _overpass_query(lat: float, lon: float, radius_m: int) -> str:
    return f"""
[out:json][timeout:25];
(
  way(around:{radius_m},{lat},{lon})[highway];
  way(around:{radius_m},{lat},{lon})[building];
  way(around:{radius_m},{lat},{lon})[landuse];
  way(around:{radius_m},{lat},{lon})[natural];
  way(around:{radius_m},{lat},{lon})[waterway];
  way(around:{radius_m},{lat},{lon})[water];
  way(around:{radius_m},{lat},{lon})[railway];
  way(around:{radius_m},{lat},{lon})[leisure];
  way(around:{radius_m},{lat},{lon})[amenity];
  way(around:{radius_m},{lat},{lon})[tourism];
  relation(around:{radius_m},{lat},{lon})[landuse];
  relation(around:{radius_m},{lat},{lon})[natural];
  relation(around:{radius_m},{lat},{lon})[water];
  relation(around:{radius_m},{lat},{lon})[leisure];
  relation(around:{radius_m},{lat},{lon})[building];
  node(around:{radius_m},{lat},{lon})[amenity];
  node(around:{radius_m},{lat},{lon})[tourism];
  node(around:{radius_m},{lat},{lon})[shop];
  node(around:{radius_m},{lat},{lon})[place];
);
out body center tags geom qt;
""".strip()


def _fetch_overpass(lat: float, lon: float, radius_m: int) -> List[Dict[str, Any]]:
    try:
        r = requests.post(
            _overpass_url(),
            data={"data": _overpass_query(lat, lon, radius_m)},
            timeout=40,
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


def _feature_type(tags: Dict[str, Any]) -> Tuple[str, str]:
    if tags.get("highway"):
        return "road", str(tags.get("highway"))
    if tags.get("building"):
        return "building", str(tags.get("building"))
    if tags.get("landuse"):
        return "landuse", str(tags.get("landuse"))
    if tags.get("natural"):
        return "natural", str(tags.get("natural"))
    if tags.get("waterway"):
        return "waterway", str(tags.get("waterway"))
    if tags.get("water"):
        return "water", str(tags.get("water"))
    if tags.get("railway"):
        return "railway", str(tags.get("railway"))
    if tags.get("leisure"):
        return "leisure", str(tags.get("leisure"))
    if tags.get("amenity"):
        return "amenity", str(tags.get("amenity"))
    if tags.get("tourism"):
        return "tourism", str(tags.get("tourism"))
    if tags.get("shop"):
        return "shop", str(tags.get("shop"))
    if tags.get("place"):
        return "place", str(tags.get("place"))
    return "other", ""


def _geometry_of(el: Dict[str, Any]) -> Dict[str, Any] | None:
    geom = el.get("geometry")
    if isinstance(geom, list) and geom:
        coords = []
        for pt in geom:
            if not isinstance(pt, dict):
                continue
            if "lon" not in pt or "lat" not in pt:
                continue
            try:
                coords.append([float(pt["lon"]), float(pt["lat"])])
            except Exception:
                continue
        if len(coords) >= 2:
            if coords[0] == coords[-1] and len(coords) >= 4:
                return {"type": "Polygon", "coordinates": [coords]}
            return {"type": "LineString", "coordinates": coords}

    lat, lon = _center_of(el)
    if lat is not None and lon is not None:
        return {"type": "Point", "coordinates": [lon, lat]}
    return None


def _to_feature(el: Dict[str, Any]) -> Dict[str, Any] | None:
    tags = dict(el.get("tags") or {})
    geometry = _geometry_of(el)
    if geometry is None:
        return None
    ftype, subtype = _feature_type(tags)
    lat, lon = _center_of(el)
    return {
        "id": f'{el.get("type","?")}/{el.get("id","?")}',
        "feature_type": ftype,
        "subtype": subtype,
        "name": str(tags.get("name") or ""),
        "geometry": geometry,
        "center": {"lat": lat, "lon": lon} if lat is not None and lon is not None else None,
        "tags": tags,
    }


def _build_geometry_packet(lat: float, lon: float, radius_m: int) -> Dict[str, Any]:
    elements = _fetch_overpass(lat, lon, radius_m)
    features: List[Dict[str, Any]] = []

    for el in elements:
        f = _to_feature(el)
        if f is not None:
            features.append(f)
        if len(features) >= _feature_limit():
            break

    return {
        "ok": True,
        "source": {
            "provider": "overpass",
            "url": _overpass_url(),
            "element_count": len(elements),
            "feature_count": len(features),
        },
        "center": {"lat": lat, "lon": lon},
        "radius_m": radius_m,
        "features": features,
    }


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


def _top_named_pois(features: List[Dict[str, Any]], limit: int) -> List[str]:
    rows: List[str] = []
    seen = set()
    for f in features:
        name = str(f.get("name") or "").strip()
        if not name:
            continue
        subtype = str(f.get("subtype") or "")
        label = f"{name} ({subtype})" if subtype else name
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

    return {
        "likely_approach_routes": likely_routes[:4],
        "good_op_positions": op_positions[:4],
        "risk_areas": risk_areas[:4],
        "named_features": named_pois[:6],
    }


def _summarize_from_geometry_packet(packet: Dict[str, Any]) -> Dict[str, Any]:
    features = list(packet.get("features") or [])

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

    for f in features:
        ftype = str(f.get("feature_type") or "")
        subtype = str(f.get("subtype") or "")
        tags = dict(f.get("tags") or {})

        if ftype == "road":
            roads[subtype] += 1
        elif ftype == "building":
            building_count += 1
        elif ftype == "landuse":
            landuse[subtype] += 1
        elif ftype == "natural":
            natural[subtype] += 1
        elif ftype in {"waterway", "water"}:
            water[subtype or "water"] += 1
        elif ftype == "railway":
            railway[subtype] += 1
        elif ftype == "leisure":
            leisure[subtype] += 1
        elif ftype == "amenity":
            amenity_count += 1
        elif ftype == "tourism":
            tourism_count += 1
        elif ftype == "place":
            place_count += 1

        if subtype in {"wetland", "marsh"} or tags.get("landuse") in {"basin", "reservoir"}:
            wet += 1
        if tags.get("water") or subtype == "water":
            water["water"] += 1
        if subtype == "coastline":
            water["coastline"] += 1

    named_pois = _top_named_pois(features, _area_summary_poi_limit())

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
        "source": packet.get("source") or {},
        "center": packet.get("center") or {},
        "radius_m": packet.get("radius_m"),
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


@router.get("/area_geometry")
def geo_area_geometry(
    lat: float = Query(...),
    lon: float = Query(...),
    radius_m: int = Query(None),
):
    cfg = _cfg_dict()
    if not _truthy(cfg.get("area_summary_enabled", "true")):
        raise HTTPException(status_code=404, detail="area geometry disabled")

    rr = radius_m if radius_m is not None else _area_summary_default_radius_m()
    rr = max(100, min(int(rr), 5000))
    return JSONResponse(_build_geometry_packet(float(lat), float(lon), rr))


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
    packet = _build_geometry_packet(float(lat), float(lon), rr)
    return JSONResponse(_summarize_from_geometry_packet(packet))


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
