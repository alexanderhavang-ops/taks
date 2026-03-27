from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from takctl.config import load_config


def fetch_weather_cache() -> dict[str, Any]:
    cfg = load_config()

    if not cfg.weather_enabled:
        raise RuntimeError("weather_enabled=false")

    if cfg.weather_provider != "met.no":
        raise RuntimeError(f"unsupported weather_provider={cfg.weather_provider!r}")

    cache_path = Path(cfg.weather_cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    params = {
        "lat": str(cfg.weather_lat),
        "lon": str(cfg.weather_lon),
        "altitude": str(cfg.weather_altitude_m),
    }

    url = (
        "https://api.met.no/weatherapi/locationforecast/2.0/compact?"
        + urllib.parse.urlencode(params)
    )

    headers = {
        "User-Agent": cfg.weather_user_agent,
        "Accept": "application/json",
    }

    req = urllib.request.Request(url=url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=float(cfg.weather_timeout_s)) as resp:
        raw = resp.read()
        status = getattr(resp, "status", 200)
        if int(status) != 200:
            raise RuntimeError(f"weather_http_status={status}")
        payload = json.loads(raw.decode("utf-8"))

    fetched_at_epoch = time.time()
    fetched_at_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    out = {
        "_fetched_at_epoch": fetched_at_epoch,
        "_fetched_at_utc": fetched_at_utc,
        "_lat": cfg.weather_lat,
        "_lon": cfg.weather_lon,
        "_altitude_m": cfg.weather_altitude_m,
        "_cache_ttl_sec": cfg.weather_cache_ttl_sec,
        "_fetch_error": None,
        "source": {
            "provider": cfg.weather_provider,
            "product": "locationforecast/2.0 compact",
            "location_name": cfg.weather_location_name,
            "lat": cfg.weather_lat,
            "lon": cfg.weather_lon,
            "altitude_m": cfg.weather_altitude_m,
            "fetched_at_utc": fetched_at_utc,
            "used_cache": False,
            "cache_ttl_sec": cfg.weather_cache_ttl_sec,
            "cache_path": str(cache_path),
            "fetch_error": None,
        },
        "payload": payload,
    }

    tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(cache_path)

    return out


def main() -> int:
    out = fetch_weather_cache()
    print(
        json.dumps(
            {
                "ok": True,
                "cache_path": out["source"]["cache_path"],
                "fetched_at_utc": out["_fetched_at_utc"],
                "lat": out["_lat"],
                "lon": out["_lon"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
