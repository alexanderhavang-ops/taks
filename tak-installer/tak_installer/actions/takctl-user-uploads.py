from __future__ import annotations

import os
import tempfile
from pathlib import Path

from tak_installer.util import log

RUNTIME_DIR = Path("/opt/tak/tools/takctl")
UPLOADS_DIR = RUNTIME_DIR / "user-uploads"
ASSETS_DIR = RUNTIME_DIR / "web" / "assets"

# Prefer user uploads in this order
EXTS = ["svg", "png", "webp", "jpg", "jpeg"]

GEN_FILE_MODE = 0o644

# Canonical logo names the UI may always reference
LOGOS = ["logo1", "logo2", "logo3", "logo4"]


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except Exception:
        # best-effort
        return


def _symlink_force(link: Path, target: Path) -> None:
    _ensure_dir(link.parent)
    _safe_unlink(link)
    link.symlink_to(target)


def _atomic_write_text(path: Path, text: str, mode: int = GEN_FILE_MODE) -> None:
    _ensure_dir(path.parent)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
        try:
            os.chmod(path, mode)
        except Exception:
            pass
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def _pick_upload(name: str) -> Path | None:
    # returns first existing upload among EXTS
    for ext in EXTS:
        cand = UPLOADS_DIR / f"{name}.{ext}"
        if cand.exists():
            return cand
    return None


def _write_placeholder_svg(dst_svg: Path, label: str) -> None:
    # Simple placeholder (never 404)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="360" height="96" viewBox="0 0 360 96">
  <rect x="0" y="0" width="360" height="96" rx="12" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.18)"/>
  <text x="180" y="56" text-anchor="middle" font-family="system-ui, -apple-system, Segoe UI, Roboto, Arial" font-size="20" fill="rgba(255,255,255,0.55)">{label}</text>
</svg>
"""
    _atomic_write_text(dst_svg, svg)


def _write_svg_wrapper_for_raster(dst_svg: Path, rel_filename: str) -> None:
    # wrapper references ./<rel_filename> (e.g., logo3.png / logo3.jpg)
    svg = f"""<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"360\" height=\"96\" viewBox=\"0 0 360 96\">
  <image href=\"./{rel_filename}\" x=\"0\" y=\"0\" width=\"360\" height=\"96\" preserveAspectRatio=\"xMidYMid meet\"/>
</svg>
"""
    _atomic_write_text(dst_svg, svg)


def apply(ctx) -> None:
    _ensure_dir(UPLOADS_DIR)
    _ensure_dir(ASSETS_DIR)

    # Ensure logos exist in assets as SVG (UI references svg)
    for name in LOGOS:
        src = _pick_upload(name)

        dst_svg = ASSETS_DIR / f"{name}.svg"
        dst_png = ASSETS_DIR / f"{name}.png"

        if src is None:
            # No upload: ensure a non-404 placeholder SVG exists
            if not dst_svg.exists() or dst_svg.is_symlink():
                _safe_unlink(dst_svg)
                _write_placeholder_svg(dst_svg, name)
            log.info(f"takctl-user-uploads: {name}: no upload -> placeholder svg")
            continue

        # Upload exists
        if src.suffix.lower() == ".svg":
            # Canonical: assets/logoN.svg -> user upload svg
            _symlink_force(dst_svg, src)
            log.info(f"takctl-user-uploads: {name}: linked svg from user-uploads")
            # If UI ever requests png, we don't promise it, but avoid stale symlink:
            if dst_png.is_symlink() and not dst_png.exists():
                _safe_unlink(dst_png)

        elif src.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            # Link raster as assets/logoN.<ext>, then write svg wrapper so UI can always use svg
            ext = src.suffix.lower()
            dst_raster = ASSETS_DIR / f"{name}{ext}"
            _symlink_force(dst_raster, src)
            # Remove old png link if it exists but we are not using png now
            if ext != ".png" and dst_png.is_symlink():
                _safe_unlink(dst_png)
            _safe_unlink(dst_svg)
            _write_svg_wrapper_for_raster(dst_svg, f"{name}{ext}")
            log.info(f"takctl-user-uploads: {name}: linked {ext} + wrote svg wrapper")

        else:
            # Other types: just provide placeholder svg to avoid 404
            _safe_unlink(dst_svg)
            _write_placeholder_svg(dst_svg, name)
            log.info(f"takctl-user-uploads: {name}: upload {src.name} unsupported for wrapper -> placeholder svg")

    # slogan.txt: always ensure it exists (empty by default)
    slogan_src = UPLOADS_DIR / "slogan.txt"
    slogan_dst = ASSETS_DIR / "slogan.txt"
    if slogan_src.exists():
        _symlink_force(slogan_dst, slogan_src)
        log.info("takctl-user-uploads: linked slogan.txt from user-uploads")
    else:
        if not slogan_dst.exists() or slogan_dst.is_symlink():
            _safe_unlink(slogan_dst)
            _atomic_write_text(slogan_dst, "")
        log.info("takctl-user-uploads: no slogan.txt upload -> ensured empty slogan.txt")


class _Action:
    ID = "takctl-user-uploads"

    def inspect(self, ctx) -> int:
        log.info(f"Inspecting {self.ID} action...")
        return 0

    def apply(self, ctx) -> int:
        log.info(f"Applying {self.ID} action...")
        apply(ctx)
        return 0


ACTION = _Action()
