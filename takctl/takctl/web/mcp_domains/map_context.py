"""Bounded OSM reads and pedestrian graph lookup, outside the simulation daemon."""
from collections import Counter, OrderedDict
from datetime import datetime, timezone
import copy
import heapq
import json
import math
import re
import threading
import time
import urllib.request
import urllib.parse
import urllib.error

from takctl.config import load_config
from takctl.simulation.model import distance, number, point

CACHE = OrderedDict()
LOCK = threading.Lock()
KINDS = {"highway", "building", "landuse", "natural", "waterway", "water", "railway", "leisure", "amenity", "shop", "place", "barrier"}
LIMIT = 4 * 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None


def fetch(query):
    cfg = load_config()
    urls = [cfg.get("overpass_url", "https://overpass-api.de/api/interpreter"),
            cfg.get("overpass_fallback_url", "https://lz4.overpass-api.de/api/interpreter")]
    key = (tuple(urls), query)
    with LOCK:
        cached = CACHE.get(key)
        if cached and time.monotonic() - cached[0] < 600:
            CACHE.move_to_end(key)
            return copy.deepcopy(cached[1]), True
    for url in dict.fromkeys(u for u in urls if u):
        try:
            request = urllib.request.Request(url, data=urllib.parse.urlencode({"data": query}).encode(),
                headers={"User-Agent": "TAKS-MapContext/2.0"}, method="POST")
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=6) as response:
                raw = bytearray()
                deadline = time.monotonic()+8
                while block := response.read(65536):
                    raw.extend(block)
                    if len(raw) > LIMIT: raise ValueError("OSM response exceeds 4 MiB; use a smaller radius")
                    if time.monotonic() > deadline: raise ValueError("OSM read deadline exceeded")
                result = json.loads(raw)
                if result.get("remark"): raise ValueError("OSM query incomplete; use a smaller radius or retry")
                elements = result.get("elements")
                if not isinstance(elements, list) or len(elements) > 5000: raise ValueError("OSM element limit exceeded")
                result = {"elements": elements, "fetched_at": datetime.now(timezone.utc).isoformat(),
                          "osm_timestamp": result.get("osm3s", {}).get("timestamp_osm_base"), "endpoint": url}
                with LOCK:
                    CACHE[key] = (time.monotonic(), result)
                    while len(CACHE) > 4: CACHE.popitem(last=False)
                return copy.deepcopy(result), False
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            continue
    raise ValueError("OSM unavailable or incomplete; no geometry was invented. Retry or reduce radius")


def area_query(center, radius, kinds):
    selectors = "".join(f'nwr(around:{radius},{center["lat"]},{center["lon"]})[{k}];' for k in sorted(kinds))
    return "[out:json][timeout:4];(" + selectors + ");out body geom qt;"


def feature(el):
    tags = el.get("tags", {})
    geometry = el.get("geometry", [])
    coordinates = [[g["lon"], g["lat"]] for g in geometry if "lat" in g and "lon" in g]
    if not coordinates and "lat" in el: coordinates = [[el["lon"], el["lat"]]]
    closed = len(coordinates) > 3 and coordinates[0] == coordinates[-1] and (
        tags.get("area") == "yes" or any(k in tags for k in ("building", "landuse", "natural", "water", "leisure")))
    return {"id": f'{el["type"]}/{el["id"]}', "name": tags.get("name", ""), "tags": tags,
            "geometry": {"type": "Point" if len(coordinates) == 1 else "Polygon" if closed else "LineString",
                         "coordinates": coordinates[0] if len(coordinates) == 1 else [coordinates] if closed else coordinates} if coordinates else None,
            "geometry_complete": bool(coordinates) and el["type"] != "relation"}


def provenance(data, cached):
    return {"provider": "OpenStreetMap / Overpass", "attribution": "© OpenStreetMap contributors; ODbL",
            "fetched_at": data["fetched_at"], "osm_timestamp": data["osm_timestamp"],
            "endpoint": data["endpoint"], "cached": cached,
            "limitations": "Mapped features only; completeness, terrain height, current obstacles and building interiors are unknown"}


def walk_route(elements, start, end):
    """Shortest mapped foot-eligible graph path; no tactical or terrain inference."""
    graph, positions = {}, {}
    accepted = {"yes", "designated", "official", "permissive"}
    excluded = {"motorway", "motorway_link", "trunk", "trunk_link", "construction", "proposed", "raceway", "road"}
    for el in elements:
        tags = el.get("tags", {})
        foot = tags.get("foot", tags.get("access", "yes"))
        if el.get("type") != "way" or not tags.get("highway") or foot not in accepted: continue
        if tags.get("highway") in excluded and tags.get("foot") not in accepted: continue
        if tags.get("area") == "yes" or tags.get("indoor") == "yes": continue
        nodes, geom = el.get("nodes", []), el.get("geometry", [])
        if len(nodes) != len(geom): continue
        for uid, p in zip(nodes, geom):
            positions[uid] = point({"lat": p["lat"], "lon": p["lon"]})
        for a, b in zip(nodes, nodes[1:]):
            length = distance(positions[a], positions[b])
            if tags.get("oneway:foot") != "-1": graph.setdefault(a, []).append((b, length, el["id"]))
            if tags.get("oneway:foot") != "yes": graph.setdefault(b, []).append((a, length, el["id"]))
    if len(positions) > 20000: raise ValueError("Walking graph too large")
    if not graph: raise ValueError("No mapped walking network in this area")
    source = min(positions, key=lambda n: distance(start, positions[n]))
    target = min(positions, key=lambda n: distance(end, positions[n]))
    snaps = [distance(start, positions[source]), distance(end, positions[target])]
    if max(snaps) > 100: raise ValueError("Endpoint more than 100m from a mapped foot-eligible node")
    queue, costs, parents = [(0, source)], {source: 0}, {}
    while queue:
        cost, node = heapq.heappop(queue)
        if cost != costs[node]: continue
        if node == target: break
        for neighbor, length, way in graph.get(node, []):
            candidate = cost + length
            if candidate < costs.get(neighbor, math.inf):
                costs[neighbor] = candidate; parents[neighbor] = (node, way)
                heapq.heappush(queue, (candidate, neighbor))
    if target not in costs: raise ValueError("No connected mapped walking path; do not substitute a straight line")
    chain, ways = [target], []
    while chain[-1] != source:
        parent, way = parents[chain[-1]]; chain.append(parent); ways.append(way)
    chain.reverse()
    if len(chain) > 500: raise ValueError("Route exceeds 500 vertices; request shorter legs")
    return {"path": [positions[n] for n in chain], "distance_m": round(costs[target], 2),
            "way_ids": sorted(set(ways)), "snap_distances_m": [round(x, 2) for x in snaps],
            "single_move_compatible": 2 <= len(chain) <= 100,
            "limitations": "Follows shared OSM node IDs and basic foot/access tags. Snap connectors, barriers, conditional restrictions, crossings and temporary closures are unverified. No automatic movement issued"}


def read(operation, args):
    if not isinstance(args, dict): raise ValueError("Map arguments must be an object")
    allowed = {"config": set(), "area": {"center", "radius_m", "kinds", "limit", "offset", "query"},
               "feature": {"feature_id"}, "route": {"start", "end", "speed_mps"}}
    if operation not in allowed or set(args) - allowed[operation]: raise ValueError("Unknown map operation/arguments")
    if operation == "config":
        return {"ok": True, "operations": list(allowed), "kinds": sorted(KINDS), "radius_limit_m": 1500,
                "routing": "bounded OSM pedestrian graph", "cache_ttl_s": 600, "simulation_daemon_dependency": False}
    if operation == "feature":
        fid = args.get("feature_id", "")
        match = re.fullmatch(r"(node|way|relation)/([0-9]{1,15})", fid)
        if not match: raise ValueError("feature_id must be node/ID, way/ID or relation/ID")
        data, cached = fetch(f"[out:json][timeout:4];{match[1]}({match[2]});out body geom;")
        items = [feature(e) for e in data["elements"]]
        if len(json.dumps(items)) > 400000: raise ValueError("Feature geometry too large")
        return {"ok": True, "features": items, "source": provenance(data, cached)}
    if operation == "route":
        start, end = point(args.get("start")), point(args.get("end"))
        direct = distance(start, end)
        if not 1 <= direct <= 2000: raise ValueError("Walking route endpoints must be 1m..2km apart")
        center = {"lat": (start["lat"]+end["lat"])/2, "lon": (start["lon"]+end["lon"])/2}
        data, cached = fetch(area_query(center, min(1500, int(direct/2+400)), {"highway"}))
        route = walk_route(data["elements"], start, end)
        speed = number(args.get("speed_mps", 1.2), "speed_mps", .1, 3)
        route["duration_s"] = round(route["distance_m"]/speed, 2)
        return {"ok": True, **route, "source": provenance(data, cached)}
    center = point(args.get("center")); radius = number(args.get("radius_m", 300), "radius_m", 100, 1500)
    kinds = args.get("kinds", ["highway", "building", "landuse", "natural", "waterway", "barrier"])
    if not isinstance(kinds, list) or not 1 <= len(kinds) <= len(KINDS) or any(k not in KINDS for k in kinds): raise ValueError("Invalid feature kinds")
    limit, offset = args.get("limit", 40), args.get("offset", 0)
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= 5000: raise ValueError("Invalid pagination")
    query = args.get("query", "")
    if not isinstance(query, str) or len(query) > 100: raise ValueError("Invalid feature search")
    data, cached = fetch(area_query(center, int(radius), kinds))
    items = [feature(e) for e in data["elements"]]
    counts = Counter(k for item in items for k in kinds if k in item["tags"])
    items = [f for f in items if query.casefold() in (f["name"]+" "+json.dumps(f["tags"], ensure_ascii=False)).casefold()]
    selected, size = [], 0
    for item in items[offset:offset+limit]:
        length = len(json.dumps(item, ensure_ascii=False).encode())
        if size+length > 400000:
            if not selected: raise ValueError("Feature too large; request a smaller area")
            break
        selected.append(item); size += length
    more = offset+len(selected) < len(items)
    return {"ok": True, "center": center, "radius_m": radius, "counts": dict(counts),
            "total_matching": len(items), "features": selected, "next_offset": offset+len(selected) if more else None,
            "source": provenance(data, cached)}
