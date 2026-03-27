from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


CACHE_PATH = Path("/opt/tak/tools/takctl/state/llm2/weather_api_cache.json")


def _num(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except Exception:
        return None


def _get_nested(obj: Any, *keys: str) -> Any:
    cur = obj
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _load_cache() -> Dict[str, Any]:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _pick_timeseries(cache: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates = [
        _get_nested(cache, "timeseries"),
        _get_nested(cache, "properties", "timeseries"),
        _get_nested(cache, "data", "properties", "timeseries"),
        _get_nested(cache, "payload", "timeseries"),
        _get_nested(cache, "payload", "properties", "timeseries"),
        _get_nested(cache, "payload", "data", "properties", "timeseries"),
    ]
    for c in candidates:
        if isinstance(c, list):
            return [x for x in c if isinstance(x, dict)]
    return []


def _pick_source(cache: Dict[str, Any]) -> Dict[str, Any]:
    candidates = [
        _get_nested(cache, "source"),
        _get_nested(cache, "meta", "source"),
        _get_nested(cache, "metadata", "source"),
    ]
    for c in candidates:
        if isinstance(c, dict):
            return c

    return {
        "provider": "met.no",
        "product": "locationforecast/2.0 compact",
        "location_name": "Ystad Harbor",
        "lat": cache.get("_lat"),
        "lon": cache.get("_lon"),
        "altitude_m": cache.get("_altitude_m"),
        "fetched_at_utc": cache.get("_fetched_at_utc"),
        "used_cache": True if cache else None,
        "cache_ttl_sec": cache.get("_cache_ttl_sec"),
        "cache_path": str(CACHE_PATH),
        "fetch_error": cache.get("_fetch_error"),
    }


def _instant_details(ts_item: Dict[str, Any]) -> Dict[str, Any]:
    details = _get_nested(ts_item, "data", "instant", "details")
    return details if isinstance(details, dict) else {}


def _next_1h_summary(ts_item: Dict[str, Any]) -> Dict[str, Any]:
    nxt = _get_nested(ts_item, "data", "next_1_hours", "summary")
    return nxt if isinstance(nxt, dict) else {}


def _next_1h_details(ts_item: Dict[str, Any]) -> Dict[str, Any]:
    nxt = _get_nested(ts_item, "data", "next_1_hours", "details")
    return nxt if isinstance(nxt, dict) else {}


def _normalize_hour(ts_item: Dict[str, Any]) -> Dict[str, Any]:
    instant = _instant_details(ts_item)
    summary = _next_1h_summary(ts_item)
    next1 = _next_1h_details(ts_item)

    return {
        "time_utc": ts_item.get("time"),
        "air_temperature_c": _num(instant.get("air_temperature")),
        "cloud_area_fraction": _num(instant.get("cloud_area_fraction")),
        "fog_area_fraction": _num(instant.get("fog_area_fraction")),
        "precipitation_amount_1h": _num(next1.get("precipitation_amount")),
        "symbol_code": summary.get("symbol_code"),
        "wind_from_deg": _num(instant.get("wind_from_direction")),
        "wind_speed_mps": _num(instant.get("wind_speed")),
    }


def _build_now(first_hour: Dict[str, Any], cache: Dict[str, Any]) -> Dict[str, Any]:
    ts = _pick_timeseries(cache)
    first_raw = ts[0] if ts else {}

    instant = _instant_details(first_raw)

    return {
        "time_utc": first_hour.get("time_utc"),
        "air_pressure_hpa": _num(instant.get("air_pressure_at_sea_level")),
        "air_temperature_c": first_hour.get("air_temperature_c"),
        "cloud_area_fraction": first_hour.get("cloud_area_fraction"),
        "fog_area_fraction": first_hour.get("fog_area_fraction"),
        "precipitation_amount_1h": first_hour.get("precipitation_amount_1h"),
        "precipitation_amount_6h": _num(
            _get_nested(first_raw, "data", "next_6_hours", "details", "precipitation_amount")
        ),
        "relative_humidity": _num(instant.get("relative_humidity")),
        "symbol_code_1h": first_hour.get("symbol_code"),
        "wind_from_deg": first_hour.get("wind_from_deg"),
        "wind_speed_mps": first_hour.get("wind_speed_mps"),
    }


def _summary(hours: List[Dict[str, Any]]) -> Dict[str, Any]:
    temps = [x["air_temperature_c"] for x in hours if x.get("air_temperature_c") is not None]
    winds = [x["wind_speed_mps"] for x in hours if x.get("wind_speed_mps") is not None]
    precs = [x["precipitation_amount_1h"] for x in hours if x.get("precipitation_amount_1h") is not None]
    fogs = [x["fog_area_fraction"] for x in hours if x.get("fog_area_fraction") is not None]
    symbols = sorted({str(x["symbol_code"]) for x in hours if x.get("symbol_code")})

    return {
        "hours": len(hours),
        "temp_max_c": max(temps) if temps else None,
        "temp_min_c": min(temps) if temps else None,
        "wind_max_mps": max(winds) if winds else None,
        "precip_total_1h_sum": round(sum(precs), 3) if precs else 0.0,
        "fog_max_fraction": max(fogs) if fogs else None,
        "symbols": symbols,
    }


def enrich(evidence: Dict[str, Any]) -> Dict[str, Any]:
    cache = _load_cache()
    ts = _pick_timeseries(cache)

    forecast_12h = [_normalize_hour(item) for item in ts[:12]]
    now = _build_now(forecast_12h[0], cache) if forecast_12h else {}

    source_in = _pick_source(cache)
    source = {
        "provider": source_in.get("provider", "met.no"),
        "product": source_in.get("product", "locationforecast/2.0 compact"),
        "location_name": source_in.get("location_name", "Ystad Harbor"),
        "lat": _num(source_in.get("lat")),
        "lon": _num(source_in.get("lon")),
        "altitude_m": _num(source_in.get("altitude_m")),
        "fetched_at_utc": source_in.get("fetched_at_utc"),
        "used_cache": source_in.get("used_cache"),
        "cache_ttl_sec": source_in.get("cache_ttl_sec"),
        "cache_path": source_in.get("cache_path", str(CACHE_PATH)),
        "fetch_error": source_in.get("fetch_error"),
    }

    return {
        "domain": "weather",
        "generated_utc": evidence.get("generated_utc"),
        "ok": True,
        "phase": "phase1",
        "queries": evidence.get("queries", []),
        "weather": {
            "now": now,
            "forecast_12h": forecast_12h,
            "forecast_12h_summary": _summary(forecast_12h),
            "source": source,
        },
    }


def main() -> int:
    import sys
    evidence = json.load(sys.stdin)
    out = enrich(evidence)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
