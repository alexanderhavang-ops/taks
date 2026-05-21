from __future__ import annotations

import argparse
import json
import tarfile
import tempfile
from pathlib import Path
from typing import Dict, List, Optional


UI_SUBTREES = ("branding", "packages", "users", "plugins", "maps", "missions", "documents", "misc", "logos")
FORBIDDEN_NAME_FRAGMENTS = (".bak.", "__pycache__")
FORBIDDEN_FILE_SUFFIXES = (".pyc", ".pyo", ".swp", ".tmp", ".orig", ".rej", "~")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _load_kv_dir(root: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not root.is_dir():
        return out
    for f in sorted(root.rglob("*.conf")):
        for raw in _read_text(f).splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _normalize_bundle_root(root: Path) -> Path:
    if (root / "startup.sh").is_file() and (root / "install").is_dir():
        return root
    dirs = [p for p in root.iterdir() if p.is_dir()]
    if len(dirs) == 1:
        d = dirs[0]
        if (d / "startup.sh").is_file() and (d / "install").is_dir():
            return d
    return root


def _find_first(root: Path, patterns: List[str]) -> Optional[Path]:
    for pat in patterns:
        matches = sorted(root.glob(pat))
        if matches:
            return matches[0]
    return None


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except Exception:
        return str(path)


def _err(report: Dict[str, object], msg: str) -> None:
    report["ok"] = False
    cast = report["errors"]
    assert isinstance(cast, list)
    cast.append(msg)


def _warn(report: Dict[str, object], msg: str) -> None:
    cast = report["warnings"]
    assert isinstance(cast, list)
    cast.append(msg)


def _is_placeholder_value(v: str) -> bool:
    return str(v or "").strip().upper() == "CHANGEME"

def _password_policy_problems(v: str) -> List[str]:
    password = str(v or "")
    problems: List[str] = []

    if len(password) < 15:
        problems.append("too short")
    if not any(c.isupper() for c in password):
        problems.append("missing uppercase")
    if not any(c.islower() for c in password):
        problems.append("missing lowercase")
    if not any(c.isdigit() for c in password):
        problems.append("missing digit")
    if not any(not c.isalnum() for c in password):
        problems.append("missing special char")

    return problems




def _need_file(report: Dict[str, object], root: Path, relpath: str, label: str) -> Optional[Path]:
    p = root / relpath
    if not p.is_file():
        _err(report, f"missing {label}: {relpath}")
        return None
    return p


def _need_any(report: Dict[str, object], root: Path, label: str, patterns: List[str]) -> Optional[Path]:
    p = _find_first(root, patterns)
    if p is None:
        _err(report, f"missing {label}: tried {patterns}")
        return None
    return p


def _need_contains(report: Dict[str, object], path: Path, needles: List[str], label: str) -> None:
    text = _read_text(path)
    for needle in needles:
        if needle not in text:
            _err(report, f"{label} missing anchor: {needle}")


def _need_absent(report: Dict[str, object], path: Path, needles: List[str], label: str) -> None:
    text = _read_text(path)
    for needle in needles:
        if needle in text:
            _err(report, f"{label} contains forbidden fragment: {needle}")


def _scan_forbidden_paths(report: Dict[str, object], root: Path) -> None:
    for p in sorted(root.rglob("*")):
        rel = _rel(p, root)
        name = p.name
        if any(fragment in rel for fragment in FORBIDDEN_NAME_FRAGMENTS):
            _err(report, f"bundle contains forbidden stale path: {rel}")
            continue
        if p.is_file() and any(name.endswith(suffix) for suffix in FORBIDDEN_FILE_SUFFIXES):
            _err(report, f"bundle contains forbidden stale file: {rel}")


def verify_bundle_tree(bundle_root: str | Path, unit_path: str = "", role: str = "tak-node") -> Dict[str, object]:
    root = Path(bundle_root)
    report: Dict[str, object] = {
        "ok": True,
        "bundle_root": str(root),
        "unit_path": unit_path,
        "role": role,
        "errors": [],
        "warnings": [],
        "artifacts": {},
        "derived": {},
    }

    if not root.is_dir():
        _err(report, f"bundle root is not a directory: {root}")
        report["missing"] = list(report["errors"])
        return report

    _scan_forbidden_paths(report, root)

    startup = _need_file(report, root, "startup.sh", "startup script")
    install_sh = _need_file(report, root, "install/install.sh", "install.sh")
    takserver_sh = _need_file(report, root, "install/takserver.sh", "takserver installer")
    cert_layout_sh = _need_file(report, root, "install/tak-certs-layout.sh", "cert layout script")
    coreconfig_sh = _need_file(report, root, "install/tak-coreconfig-render.sh", "CoreConfig render script")
    taks_sh = _need_file(report, root, "install/taks.sh", "taks apply script")
    taks_source = root / "taks-source"
    if not taks_source.is_dir():
        _err(report, "missing taks-source directory")
    else:
        report["artifacts"]["taks_source"] = "taks-source"
        if not (taks_source / "tak-installer" / "tak-installer").is_file():
            _err(report, "missing taks-source/tak-installer/tak-installer")

    deb = _need_any(
        report,
        root,
        "takserver deb",
        [
            "packages/takserver_*_all.deb",
            "files/packages/takserver_*_all.deb",
            "takserver_*_all.deb",
        ],
    )
    if deb is not None:
        report["artifacts"]["takserver_deb"] = _rel(deb, root)

    package_debs = sorted((root / "packages").glob("takserver_*_all.deb"))
    if len(package_debs) != 1:
        _err(report, f"packages subtree must contain exactly one takserver deb, found {len(package_debs)}")

    for subtree in UI_SUBTREES:
        subtree_dir = root / subtree
        if not subtree_dir.is_dir():
            _err(report, f"missing materialized UI subtree: {subtree}")

    conf_root = root / "install" / "taks-bootstrap" / "config.d"
    sec_root = root / "install" / "taks-bootstrap" / "secrets.d"
    if not conf_root.is_dir():
        _err(report, "missing install/taks-bootstrap/config.d")
    if not sec_root.is_dir():
        _err(report, "missing install/taks-bootstrap/secrets.d")

    conf = _load_kv_dir(conf_root)
    sec = _load_kv_dir(sec_root)

    fqdn = (conf.get("node_fqdn") or conf.get("fqdn") or "").strip()
    node_cert_model = (conf.get("node_cert_model") or "").strip()
    report["derived"]["fqdn"] = fqdn
    report["derived"]["node_cert_model"] = node_cert_model

    if not fqdn:
        _err(report, "missing critical bootstrap key: fqdn/node_fqdn")
    if node_cert_model != "letsencrypt":
        _err(report, f"node_cert_model must be letsencrypt, got: {node_cert_model or '<empty>'}")

    critical_conf = [
        "cert_country",
        "cert_state",
        "cert_city",
        "cert_organization",
        "takctl_admin_user",
    ]
    critical_sec = [
        "takctl_admin_password",
        "cert_capass",
        "cert_pass",
        "serverpassword",
    ]

    for key in critical_conf:
        val = (conf.get(key) or "").strip()
        if not val:
            _err(report, f"missing critical bootstrap config key: {key}")
        elif _is_placeholder_value(val):
            _err(report, f"placeholder critical bootstrap config key not allowed: {key}")

    for key in critical_sec:
        val = (sec.get(key) or "").strip()
        if not val:
            _err(report, f"missing critical bootstrap secret key: {key}")
        elif _is_placeholder_value(val):
            _err(report, f"placeholder critical bootstrap secret key not allowed: {key}")
        elif key == "takctl_admin_password":
            problems = _password_policy_problems(val)
            if problems:
                _err(report, f"takctl_admin_password does not meet policy: {', '.join(problems)}")

    le_cert = _need_file(report, root, "install/letsencrypt/fullchain.pem", "bundled letsencrypt fullchain")
    le_key = _need_file(report, root, "install/letsencrypt/privkey.pem", "bundled letsencrypt privkey")
    if le_cert is not None:
        report["artifacts"]["bundled_le_fullchain"] = _rel(le_cert, root)
    if le_key is not None:
        report["artifacts"]["bundled_le_privkey"] = _rel(le_key, root)

    if cert_layout_sh is not None:
        report["artifacts"]["tak_certs_layout"] = _rel(cert_layout_sh, root)
        _need_contains(
            report,
            cert_layout_sh,
            [
                'dst="$flat/03_PUBLIC/takserver-le-8446.p12"',
                'missing letsencrypt cert:',
                'missing letsencrypt key:',
                'reset_dir "$flat/03_PUBLIC"',
            ],
            "tak-certs-layout.sh",
        )
        _need_absent(
            report,
            cert_layout_sh,
            [
                "TAKS_UNIT_ID",
            ],
            "tak-certs-layout.sh",
        )

    if coreconfig_sh is not None:
        report["artifacts"]["tak_coreconfig_render"] = _rel(coreconfig_sh, root)
        _need_contains(
            report,
            coreconfig_sh,
            [
                "verify_coreconfig_keystores()",
                'server_store_rel="certs/files/02_SERVER/takserver-${fqdn}.p12"',
                'cert_https_store_rel="certs/files/03_PUBLIC/takserver-le-8446.p12"',
                'missing 8446 public LE store:',
                'CoreConfig alias missing/mismatch',
                'CoreConfig key alias/password mismatch',
            ],
            "tak-coreconfig-render.sh",
        )
        _need_absent(
            report,
            coreconfig_sh,
            [
                "certs/files/02_SERVERtakserver-",
                "takserver-${unit_id",
                "certs/files/takserver.jks",
            ],
            "tak-coreconfig-render.sh",
        )

    if startup is not None:
        report["artifacts"]["startup"] = _rel(startup, root)
    if install_sh is not None:
        report["artifacts"]["install_sh"] = _rel(install_sh, root)
    if takserver_sh is not None:
        report["artifacts"]["takserver_sh"] = _rel(takserver_sh, root)
    if taks_sh is not None:
        report["artifacts"]["taks_sh"] = _rel(taks_sh, root)

    report["missing"] = list(report["errors"])
    return report


def verify_bundle_archive(bundle_archive: str | Path, unit_path: str = "", role: str = "tak-node") -> Dict[str, object]:
    archive = Path(bundle_archive)
    if not archive.is_file():
        return {
            "ok": False,
            "bundle_archive": str(archive),
            "unit_path": unit_path,
            "role": role,
            "errors": [f"bundle archive missing: {archive}"],
            "warnings": [],
            "artifacts": {},
            "derived": {},
            "missing": [f"bundle archive missing: {archive}"],
        }

    with tempfile.TemporaryDirectory(prefix="bundle-verify-") as td:
        td_path = Path(td)
        with tarfile.open(archive, "r:*") as tf:
            tf.extractall(td_path)
        root = _normalize_bundle_root(td_path)
        report = verify_bundle_tree(root, unit_path=unit_path, role=role)
        report["bundle_archive"] = str(archive)
        report["bundle_root"] = str(root)
        return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify rendered TAKS unit bundle strictly.")
    ap.add_argument("bundle", help="bundle directory or tar.gz archive")
    ap.add_argument("unit_path", nargs="?", default="", help="unit path")
    ap.add_argument("role", nargs="?", default="tak-node", help="role")
    args = ap.parse_args()

    bundle = Path(args.bundle)
    if bundle.is_file():
        report = verify_bundle_archive(bundle, unit_path=args.unit_path, role=args.role)
    else:
        report = verify_bundle_tree(bundle, unit_path=args.unit_path, role=args.role)

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if bool(report.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
