from __future__ import annotations

import os
import json
import shutil
import tempfile
from pathlib import Path

from tak_installer.util import log

RUNTIME_DIR = Path("/opt/tak/tools/takctl")
UPLOADS_DIR = RUNTIME_DIR / "user-uploads"
ASSETS_DIR = RUNTIME_DIR / "web" / "assets"
TOPBAR_DIR = ASSETS_DIR / "topbar"

UNIT_CURRENT_SVG = ASSETS_DIR / "unit-current.svg"
UNIT_CURRENT_PNG = ASSETS_DIR / "unit-current.png"   # square icon for top-right badge
BRAND_JSON = ASSETS_DIR / "brand.json"

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


def _atomic_write_bytes(path: Path, data: bytes, mode: int = GEN_FILE_MODE) -> None:
    _ensure_dir(path.parent)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
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


def _write_topbar_png_derived(dst_png: Path, src: Path, w: int = 360, h: int = 96) -> None:
    """
    Create a derived topbar banner PNG for UI use (does NOT modify uploads).
    Uses center 'cover' scaling into w×h.
    """
    try:
        from PIL import Image
    except Exception as e:
        raise RuntimeError(
            "Pillow (python3-pil) is required to derive logos. "
            "Install with: sudo apt-get update && sudo apt-get install -y python3-pil"
        ) from e

    im = Image.open(src).convert("RGBA")
    sw, sh = im.size
    if sw <= 0 or sh <= 0:
        raise RuntimeError(f"bad image size: {src} size={im.size}")

    scale = max(w / sw, h / sh)
    rw, rh = int(sw * scale + 0.5), int(sh * scale + 0.5)
    im2 = im.resize((rw, rh), resample=Image.LANCZOS)

    left = max(0, (rw - w) // 2)
    top = max(0, (rh - h) // 2)
    im3 = im2.crop((left, top, left + w, top + h))

    from io import BytesIO
    buf = BytesIO()
    im3.save(buf, format="PNG", optimize=True)
    _atomic_write_bytes(dst_png, buf.getvalue())


def _write_topbar_png_from_svg(dst_png: Path, svg_path: Path, w: int = 360, h: int = 96) -> None:
    """
    Render an SVG to a derived topbar PNG (does NOT modify uploads).
    Uses rsvg-convert (librsvg2-bin).
    """
    import subprocess
    _ensure_dir(dst_png.parent)
    tmp = dst_png.with_suffix(dst_png.suffix + ".tmp")
    subprocess.run(
        ["rsvg-convert", "-w", str(w), "-h", str(h), "-o", str(tmp), str(svg_path)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    tmp.replace(dst_png)
    try:
        os.chmod(dst_png, GEN_FILE_MODE)
    except Exception:
        pass


def _pick_upload(name: str) -> Path | None:
    for ext in EXTS:
        cand = UPLOADS_DIR / f"{name}.{ext}"
        if cand.exists():
            return cand
    return None


def _upload_truth(name: str) -> tuple[bool, str | None]:
    for ext in EXTS:
        cand = UPLOADS_DIR / f"{name}.{ext}"
        if cand.exists():
            return True, ext
    return False, None


def _write_placeholder_svg(dst_svg: Path, label: str) -> None:
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="360" height="96" viewBox="0 0 360 96">
  <rect x="0" y="0" width="360" height="96" rx="12" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.18)"/>
  <text x="180" y="56" text-anchor="middle" font-family="system-ui, -apple-system, Segoe UI, Roboto, Arial" font-size="20" fill="rgba(255,255,255,0.55)">{label}</text>
</svg>
"""
    _atomic_write_text(dst_svg, svg)


def _write_svg_wrapper_for_raster(dst_svg: Path, rel_filename: str) -> None:
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="360" height="96" viewBox="0 0 360 96">
  <image href="./{rel_filename}" x="0" y="0" width="360" height="96" preserveAspectRatio="xMidYMid meet"/>
</svg>
"""
    _atomic_write_text(dst_svg, svg)


def _write_square_icon_png(dst_png: Path, src: Path, size: int = 96) -> None:
    """
    Create a square icon PNG (contain + centered, transparent padding).
    This is what the top-right unit badge should use (NOT the 360x96 banner).
    """
    try:
        from PIL import Image
    except Exception as e:
        raise RuntimeError(
            "Pillow (python3-pil) is required to derive logos. "
            "Install with: sudo apt-get update && sudo apt-get install -y python3-pil"
        ) from e

    # If SVG, render to a temp PNG first using rsvg-convert
    if src.suffix.lower() == ".svg":
        import subprocess
        tmp = dst_png.with_suffix(".tmp.render.png")
        subprocess.run(
            ["rsvg-convert", "-w", str(size), "-h", str(size), "-o", str(tmp), str(src)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        src2 = tmp
    else:
        src2 = src

    try:
        im = Image.open(src2).convert("RGBA")
        sw, sh = im.size
        if sw <= 0 or sh <= 0:
            raise RuntimeError(f"bad image size: {src} size={im.size}")

        scale = min(size / sw, size / sh)
        rw, rh = max(1, int(sw * scale + 0.5)), max(1, int(sh * scale + 0.5))
        im2 = im.resize((rw, rh), resample=Image.LANCZOS)

        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        left = (size - rw) // 2
        top = (size - rh) // 2
        canvas.paste(im2, (left, top), im2)

        from io import BytesIO
        buf = BytesIO()
        canvas.save(buf, format="PNG", optimize=True)
        _atomic_write_bytes(dst_png, buf.getvalue())
    finally:
        if src2 != src:
            try:
                Path(src2).unlink()
            except Exception:
                pass


def apply(ctx) -> None:
    _ensure_dir(UPLOADS_DIR)
    _ensure_dir(ASSETS_DIR)
    _ensure_dir(TOPBAR_DIR)

    # Ensure logos exist in assets as SVG (UI can reference svg)
    for name in LOGOS:
        src = _pick_upload(name)

        dst_svg = ASSETS_DIR / f"{name}.svg"
        dst_png = ASSETS_DIR / f"{name}.png"

        if src is None:
            if not dst_svg.exists() or dst_svg.is_symlink():
                _safe_unlink(dst_svg)
                _write_placeholder_svg(dst_svg, name)
            try:
                dst_topbar = TOPBAR_DIR / f"{name}.png"
                _write_topbar_png_from_svg(dst_topbar, dst_svg)
                log.info(f"takctl-user-uploads: {name}: topbar derive (placeholder) -> {dst_topbar}")
            except Exception as e:
                log.info(f"takctl-user-uploads: {name}: topbar derive skipped (placeholder): {e}")
            log.info(f"takctl-user-uploads: {name}: no upload -> placeholder svg")
            continue

        if src.suffix.lower() == ".svg":
            _symlink_force(dst_svg, src)
            log.info(f"takctl-user-uploads: {name}: linked svg from user-uploads")
            try:
                dst_topbar = TOPBAR_DIR / f"{name}.png"
                _write_topbar_png_from_svg(dst_topbar, dst_svg)
                log.info(f"takctl-user-uploads: {name}: topbar derive (svg) -> {dst_topbar}")
            except Exception as e:
                log.info(f"takctl-user-uploads: {name}: topbar derive skipped (svg): {e}")

            if dst_png.is_symlink() and not dst_png.exists():
                _safe_unlink(dst_png)

        elif src.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            ext = src.suffix.lower()
            dst_raster = ASSETS_DIR / f"{name}{ext}"
            _symlink_force(dst_raster, src)
            if ext != ".png" and dst_png.is_symlink():
                _safe_unlink(dst_png)
            _safe_unlink(dst_svg)
            _write_svg_wrapper_for_raster(dst_svg, f"{name}{ext}")
            log.info(f"takctl-user-uploads: {name}: linked {ext} + wrote svg wrapper")

            try:
                dst_topbar = TOPBAR_DIR / f"{name}.png"
                _write_topbar_png_derived(dst_topbar, src)
                log.info(f"takctl-user-uploads: {name}: wrote derived topbar png -> {dst_topbar}")
            except Exception as e:
                log.info(f"takctl-user-uploads: {name}: topbar png derive skipped: {e}")

        else:
            _safe_unlink(dst_svg)
            _write_placeholder_svg(dst_svg, name)
            log.info(f"takctl-user-uploads: {name}: upload {src.name} unsupported for wrapper -> placeholder svg")

    # --- brand.json + unit-current.* (UI truth) ---
    logos = []
    current_n = None
    for name in LOGOS:
        uploaded, ext = _upload_truth(name)
        n = int(name.replace("logo", ""))
        logos.append({
            "n": n,
            "uploaded": uploaded,
            "ext": ext,
            "asset_svg": f"./assets/{name}.svg",
        })
        if uploaded and (current_n is None or n > current_n):
            current_n = n

    # slogan: read user upload if present (else empty)
    slogan_src = UPLOADS_DIR / "slogan.txt"
    slogan = ""
    if slogan_src.exists():
        try:
            slogan = slogan_src.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            slogan = ""

    brand = {
        "logos": sorted(logos, key=lambda x: x["n"]),
        "current_n": current_n,
        "slogan": slogan,
    }
    _atomic_write_text(BRAND_JSON, json.dumps(brand, indent=2) + "\n")

    # unit-current.svg -> highest uploaded logoN.svg wrapper; remove if none uploaded
    _safe_unlink(UNIT_CURRENT_SVG)
    if current_n is not None:
        _symlink_force(UNIT_CURRENT_SVG, ASSETS_DIR / f"logo{current_n}.svg")
        log.info(f"takctl-user-uploads: unit-current.svg -> logo{current_n}.svg")
    else:
        log.info("takctl-user-uploads: unit-current.svg removed (no uploaded logos)")

    # unit-current.png -> square icon derived from the highest uploaded original (NOT topbar banner)
    _safe_unlink(UNIT_CURRENT_PNG)
    if current_n is not None:
        name = f"logo{current_n}"
        src = _pick_upload(name)
        if src is not None:
            try:
                _write_square_icon_png(UNIT_CURRENT_PNG, src, size=96)
                log.info(f"takctl-user-uploads: unit-current.png (square) -> derived from {src.name}")
            except Exception as e:
                log.info(f"takctl-user-uploads: unit-current.png derive skipped: {e}")

    # Also keep slogan.txt in assets for any other UI bits that want it
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
