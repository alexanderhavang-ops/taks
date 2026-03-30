from __future__ import annotations

from pathlib import Path

from tak_installer.log import get_logger

log = get_logger(__name__)


def _parse_simple_kv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _truthy(v: str) -> bool:
    return str(v or "").strip().lower() in {"1", "true", "yes", "on"}


def _geo_cfg() -> dict[str, str]:
    return _parse_simple_kv(Path("/opt/tak/tools/takctl/conf.d/geo.conf"))


def _replay_enabled() -> bool:
    return _truthy(_parse_simple_kv(Path("/opt/tak/tools/takctl/conf.d/replay.conf")).get("replay_enabled", "false"))


class _Action:
    ID = "osm-tiles-runtime"

    def inspect(self, ctx) -> int:
        cfg = _geo_cfg()
        log.info("Inspecting %s action...", self.ID)
        log.info("  replay_enabled: %s", str(_replay_enabled()).lower())
        log.info("  osm_tiles_enabled: %s", str(_truthy(cfg.get("osm_tiles_enabled", "false"))).lower())
        log.info("  osm_tiles_mode: %s", cfg.get("osm_tiles_mode", "external"))
        log.info("  osm_tiles_url: %s", cfg.get("osm_tiles_url", ""))
        log.info("%s: local OSM tile runtime disabled; use /api/geo proxy with external/dedicated/node_local later", self.ID)
        return 0

    def apply(self, ctx) -> int:
        cfg = _geo_cfg()
        log.info("Applying %s action...", self.ID)
        log.info("  replay_enabled: %s", str(_replay_enabled()).lower())
        log.info("  osm_tiles_enabled: %s", str(_truthy(cfg.get("osm_tiles_enabled", "false"))).lower())
        log.info("  osm_tiles_mode: %s", cfg.get("osm_tiles_mode", "external"))
        log.info("%s: no local OSM tile install performed; geo is served via takctl proxy", self.ID)
        return 0


ACTION = _Action()
