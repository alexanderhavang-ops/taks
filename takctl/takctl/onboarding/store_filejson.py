from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Sequence

from .models import DeliveryMeta, OnboardingRecord, OnboardingStatus, PackageMeta
from .store import OnboardingStore


def _dt_to_iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat() + "Z"


def _iso_to_dt(s: str) -> datetime:
    s = s.rstrip("Z")
    return datetime.fromisoformat(s)


class FileJsonOnboardingStore(OnboardingStore):
    """
    Simple file-backed store:
      root/
        users/<username>.json
    """

    def __init__(self, root_dir: str | Path):
        self.root = Path(root_dir)
        self.users_dir = self.root / "users"
        self.users_dir.mkdir(parents=True, exist_ok=True)

    def list_records(self) -> Sequence[OnboardingRecord]:
        out = []
        for p in sorted(self.users_dir.glob("*.json")):
            out.append(self._load_file(p))
        return out

    def get_record(self, username: str) -> Optional[OnboardingRecord]:
        p = self.users_dir / f"{username}.json"
        if not p.exists():
            return None
        return self._load_file(p)

    def upsert_record(self, record: OnboardingRecord) -> None:
        p = self.users_dir / f"{record.username}.json"
        tmp = p.with_suffix(".json.tmp")
        data = self._to_json(record)
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(p)

    def _to_json(self, r: OnboardingRecord) -> Dict:
        d = {
            "username": r.username,
            "status": r.status.value,
            "package": None,
            "delivery": None,
        }
        if r.package:
            d["package"] = {
                "package_type": r.package.package_type,
                "version": r.package.version,
                "generated_at": _dt_to_iso(r.package.generated_at),
                "plugins": list(r.package.plugins),
                "maps": list(r.package.maps),
                "config_hash": r.package.config_hash,
            }
        if r.delivery:
            d["delivery"] = {
                "qr_generated": r.delivery.qr_generated,
                "download_url": r.delivery.download_url,
                "downloaded_at": _dt_to_iso(r.delivery.downloaded_at) if r.delivery.downloaded_at else None,
                "delivery_method": r.delivery.delivery_method,
            }
        return d

    def _load_file(self, p: Path) -> OnboardingRecord:
        raw = json.loads(p.read_text(encoding="utf-8"))

        pkg = None
        if raw.get("package"):
            pr = raw["package"]
            pkg = PackageMeta(
                package_type=pr["package_type"],
                version=pr["version"],
                generated_at=_iso_to_dt(pr["generated_at"]),
                plugins=pr.get("plugins", []),
                maps=pr.get("maps", []),
                config_hash=pr["config_hash"],
            )

        dlv = None
        if raw.get("delivery"):
            dr = raw["delivery"]
            dlv = DeliveryMeta(
                qr_generated=bool(dr.get("qr_generated", False)),
                download_url=dr.get("download_url"),
                downloaded_at=_iso_to_dt(dr["downloaded_at"]) if dr.get("downloaded_at") else None,
                delivery_method=dr.get("delivery_method"),
            )

        return OnboardingRecord(
            username=raw["username"],
            status=OnboardingStatus(raw["status"]),
            package=pkg,
            delivery=dlv,
        )

