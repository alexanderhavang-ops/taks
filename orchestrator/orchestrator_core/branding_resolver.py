from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

CONF_REL = Path("config.d/branding.conf")
BRANDING_REL = Path("branding")

DEFAULT_MODE = "png-chain"
DEFAULT_MAX_PNG_PER_DIR = 1


def _parse_bool(raw: str) -> bool:
    s = str(raw).strip().lower()
    if s in {"1", "true", "yes", "on"}:
        return True
    if s in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {raw!r}")


def _load_kv_conf(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out

    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        s = raw.strip()
        if not s or s.startswith("#") or s.startswith(";"):
            continue
        if "=" not in s:
            raise SystemExit(f"invalid line in {path}:{lineno}: {raw!r}")
        k, v = s.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            raise SystemExit(f"empty key in {path}:{lineno}")
        out[k] = v
    return out


def _local_branding_conf(unit_dir: Path) -> dict[str, Any]:
    raw = _load_kv_conf(unit_dir / CONF_REL)
    out: dict[str, Any] = {}

    if "mode" in raw:
        out["mode"] = raw["mode"].strip()

    if "max_png_per_dir" in raw:
        try:
            out["max_png_per_dir"] = int(raw["max_png_per_dir"])
        except Exception:
            raise SystemExit(f"invalid max_png_per_dir in {unit_dir / CONF_REL}: {raw['max_png_per_dir']!r}")
        if out["max_png_per_dir"] < 1:
            raise SystemExit(f"max_png_per_dir must be >= 1 in {unit_dir / CONF_REL}")

    if "inherit" in raw:
        try:
            out["inherit"] = _parse_bool(raw["inherit"])
        except Exception as e:
            raise SystemExit(f"invalid inherit in {unit_dir / CONF_REL}: {e}") from e

    unknown = sorted(set(raw.keys()) - {"mode", "max_png_per_dir", "inherit"})
    if unknown:
        raise SystemExit(f"unknown key(s) in {unit_dir / CONF_REL}: {', '.join(unknown)}")

    return out


def _dirs_root_to_current(tree_root: Path, current_dir: Path) -> list[Path]:
    tree_root = tree_root.resolve()
    current_dir = current_dir.resolve()

    try:
        current_dir.relative_to(tree_root)
    except Exception:
        raise SystemExit(f"current_dir is not inside tree_root: {current_dir} vs {tree_root}")

    parts: list[Path] = []
    p = current_dir
    while True:
        parts.append(p)
        if p == tree_root:
            break
        p = p.parent
    parts.reverse()
    return parts


def _dirs_current_to_root(tree_root: Path, current_dir: Path) -> list[Path]:
    dirs = _dirs_root_to_current(tree_root, current_dir)
    dirs.reverse()
    return dirs


def _effective_branding_conf(tree_root: Path, unit_dir: Path) -> dict[str, Any]:
    mode = DEFAULT_MODE
    max_png_per_dir = DEFAULT_MAX_PNG_PER_DIR

    for p in _dirs_root_to_current(tree_root, unit_dir):
        local = _local_branding_conf(p)
        if "mode" in local:
            mode = local["mode"]
        if "max_png_per_dir" in local:
            max_png_per_dir = local["max_png_per_dir"]

    return {
        "mode": mode,
        "max_png_per_dir": max_png_per_dir,
    }


def _sole_png(branding_dir: Path, *, max_png_per_dir: int) -> Path | None:
    if not branding_dir.exists():
        return None
    if not branding_dir.is_dir():
        raise SystemExit(f"branding path exists but is not a directory: {branding_dir}")

    pngs = sorted(
        p for p in branding_dir.iterdir()
        if p.is_file() and p.suffix.lower() == ".png"
    )

    if len(pngs) > max_png_per_dir:
        names = ", ".join(p.name for p in pngs)
        raise SystemExit(
            f"too many png files in {branding_dir}: found {len(pngs)}, "
            f"max allowed {max_png_per_dir}: {names}"
        )

    if len(pngs) > 1:
        names = ", ".join(p.name for p in pngs)
        raise SystemExit(
            f"png-chain is ambiguous with more than one png in {branding_dir}: {names}"
        )

    return pngs[0] if pngs else None


def collect_branding_chain(tree_root: Path, current_dir: Path) -> list[dict[str, str]]:
    tree_root = tree_root.resolve()
    current_dir = current_dir.resolve()

    found: list[dict[str, str]] = []

    for unit_dir in _dirs_current_to_root(tree_root, current_dir):
        eff = _effective_branding_conf(tree_root, unit_dir)
        mode = eff["mode"]
        max_png_per_dir = eff["max_png_per_dir"]

        if mode != "png-chain":
            raise SystemExit(f"unsupported branding mode at {unit_dir}: {mode!r}")

        png = _sole_png(unit_dir / BRANDING_REL, max_png_per_dir=max_png_per_dir)
        if png is not None:
            try:
                rel_unit = str(unit_dir.relative_to(tree_root))
            except Exception:
                rel_unit = str(unit_dir)

            found.append(
                {
                    "source_unit_dir": str(unit_dir),
                    "source_unit_rel": rel_unit if rel_unit != "." else "",
                    "source_file": str(png),
                    "source_name": png.name,
                }
            )

        local = _local_branding_conf(unit_dir)
        inherit = bool(local.get("inherit", True))
        if not inherit:
            break

    return found


def materialize_branding_bundle(
    *,
    tree_root: Path,
    current_dir: Path,
    out_dir: Path,
) -> dict[str, Any]:
    tree_root = tree_root.resolve()
    current_dir = current_dir.resolve()
    out_dir = out_dir.resolve()

    out_dir.mkdir(parents=True, exist_ok=True)

    for p in out_dir.glob("unit*.png"):
        if p.is_file():
            p.unlink()

    files_json = out_dir / "files.json"
    if files_json.exists():
        files_json.unlink()

    chain = collect_branding_chain(tree_root, current_dir)

    emitted: list[dict[str, str]] = []

    for idx, item in enumerate(chain):
        src = Path(item["source_file"])
        if idx == 0:
            slot = "unit"
            dst_name = "unit.png"
        else:
            slot = f"parent{idx-1}"
            dst_name = f"unit-parent{idx-1}.png"

        dst = out_dir / dst_name
        shutil.copy2(src, dst)

        emitted.append(
            {
                "slot": slot,
                "filename": dst_name,
                "source_unit_dir": item["source_unit_dir"],
                "source_unit_rel": item["source_unit_rel"],
                "source_file": item["source_file"],
                "source_name": item["source_name"],
            }
        )

    manifest = {
        "mode": "png-chain",
        "tree_root": str(tree_root),
        "current_dir": str(current_dir),
        "effective_count": len(emitted),
        "files": emitted,
    }

    files_json.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree-root", required=True)
    ap.add_argument("--current-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    manifest = materialize_branding_bundle(
        tree_root=Path(args.tree_root),
        current_dir=Path(args.current_dir),
        out_dir=Path(args.out_dir),
    )

    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
