from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse


router = APIRouter(prefix="/api/library", tags=["library"])

LIBRARY_ROOT = Path("/opt/tak/tools/takctl/data/library")
ALLOWED_SUBTREES = ("packages", "branding", "users", "plugins", "maps", "missions", "misc")


def _ensure_root() -> None:
    for name in ALLOWED_SUBTREES:
        p = LIBRARY_ROOT / name
        p.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(p, 0o2770)
        except Exception:
            pass


def _subtree_root(subtree: str) -> Path:
    value = str(subtree or "").strip().lower()
    if value not in ALLOWED_SUBTREES:
        raise HTTPException(status_code=400, detail=f"unsupported subtree: {subtree}")
    root = LIBRARY_ROOT / value
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_rel_path(relpath: str) -> Path:
    rel = Path(str(relpath or "").strip())
    if not str(rel).strip():
        raise HTTPException(status_code=400, detail="relpath required")
    if rel.is_absolute() or ".." in rel.parts:
        raise HTTPException(status_code=400, detail="illegal relpath")
    return rel


def _safe_subdir(subdir: str) -> Path:
    raw = str(subdir or "").strip().strip("/")
    if not raw:
        return Path(".")
    rel = Path(raw)
    if rel.is_absolute() or ".." in rel.parts:
        raise HTTPException(status_code=400, detail="illegal subdir")
    return rel


def _file_rows(root: Path) -> list[dict]:
    rows: list[dict] = []
    if not root.exists():
        return rows
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        rows.append(
            {
                "relpath": rel,
                "size_bytes": p.stat().st_size,
            }
        )
    return rows


def _render_ui() -> str:
    cards = "\n".join(
        f"""
        <section class="card" data-subtree="{name}">
          <div class="head">
            <h2>{name}</h2>
            <button onclick="refreshOne('{name}')">Reload</button>
          </div>
          <form class="upload-form" data-subtree="{name}">
            <div class="row">
              <label>Subdir</label>
              <input type="text" name="subdir" placeholder="optional/subdir"/>
            </div>
            <div class="row">
              <label>Files</label>
              <input type="file" name="files" multiple required />
            </div>
            <div class="row">
              <button type="submit">Upload</button>
            </div>
          </form>
          <div class="files" id="files-{name}">Loading…</div>
        </section>
        """
        for name in ALLOWED_SUBTREES
    )

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>TAKS Library</title>
  <style>
    body {{
      font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
      margin: 24px;
      background: #111827;
      color: #f3f4f6;
    }}
    h1 {{ margin: 0 0 18px 0; }}
    .muted {{ color: #9ca3af; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
      gap: 16px;
    }}
    .card {{
      border: 1px solid #374151;
      border-radius: 12px;
      padding: 14px;
      background: #1f2937;
    }}
    .head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }}
    .head h2 {{
      margin: 0;
      font-size: 18px;
      text-transform: none;
    }}
    .row {{
      display: grid;
      gap: 6px;
      margin-bottom: 10px;
    }}
    input[type="text"], input[type="file"] {{
      width: 100%;
      box-sizing: border-box;
    }}
    button {{
      cursor: pointer;
    }}
    .files {{
      margin-top: 14px;
      border-top: 1px solid #374151;
      padding-top: 12px;
      font-size: 14px;
    }}
    .file-row {{
      display: grid;
      grid-template-columns: minmax(0,1fr) auto auto;
      gap: 8px;
      align-items: center;
      padding: 6px 0;
      border-bottom: 1px solid rgba(255,255,255,0.06);
    }}
    .file-row:last-child {{
      border-bottom: none;
    }}
    .mono {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      word-break: break-all;
    }}
    a {{
      color: #93c5fd;
      text-decoration: none;
    }}
  </style>
</head>
<body>
  <h1>TAKS Library</h1>
  <div class="muted">Runtime root: <span class="mono">{LIBRARY_ROOT}</span></div>
  <div style="height:16px"></div>
  <div class="grid">
    {cards}
  </div>

  <script>
    const API_BASE = location.pathname.replace(/\\/ui$/, "");

    function esc(s) {{
      return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }}

    function encRel(path) {{
      return String(path).split("/").map(encodeURIComponent).join("/");
    }}

    async function refreshOne(subtree) {{
      const box = document.getElementById("files-" + subtree);
      box.innerHTML = "Loading…";
      const r = await fetch(API_BASE + "/" + encodeURIComponent(subtree));
      const data = await r.json();
      const files = Array.isArray(data.files) ? data.files : [];
      if (!files.length) {{
        box.innerHTML = '<div class="muted">Empty</div>';
        return;
      }}
      box.innerHTML = files.map(f => {{
        const rawUrl = API_BASE + "/" + encodeURIComponent(subtree) + "/raw/" + encRel(f.relpath);
        return `
          <div class="file-row">
            <div class="mono">${{esc(f.relpath)}}</div>
            <div>${{Number(f.size_bytes || 0)}} B</div>
            <div>
              <a href="${{rawUrl}}" target="_blank" rel="noopener">open</a>
              &nbsp;|&nbsp;
              <a href="#" onclick="deleteOne('${{subtree}}','${{encodeURIComponent(f.relpath)}}'); return false;">delete</a>
            </div>
          </div>
        `;
      }}).join("");
    }}

    async function deleteOne(subtree, relEncoded) {{
      const relpath = decodeURIComponent(relEncoded);
      const url = API_BASE + "/" + encodeURIComponent(subtree) + "/raw/" + encRel(relpath);
      const r = await fetch(url, {{ method: "DELETE" }});
      if (!r.ok) {{
        alert("Delete failed");
        return;
      }}
      await refreshOne(subtree);
    }}

    async function refreshAll() {{
      for (const name of {list(ALLOWED_SUBTREES)!r}) {{
        await refreshOne(name);
      }}
    }}

    document.querySelectorAll(".upload-form").forEach(form => {{
      form.addEventListener("submit", async (ev) => {{
        ev.preventDefault();
        const subtree = form.getAttribute("data-subtree");
        const fd = new FormData();
        const subdir = form.querySelector('input[name="subdir"]').value || "";
        const files = form.querySelector('input[name="files"]').files;
        fd.append("subdir", subdir);
        for (const f of files) {{
          fd.append("files", f);
        }}
        const r = await fetch(API_BASE + "/" + encodeURIComponent(subtree) + "/upload", {{
          method: "POST",
          body: fd,
        }});
        if (!r.ok) {{
          const txt = await r.text();
          alert("Upload failed: " + txt);
          return;
        }}
        form.reset();
        await refreshOne(subtree);
      }});
    }});

    refreshAll();
  </script>
</body>
</html>
"""


@router.get("", response_class=JSONResponse)
def library_index():
    _ensure_root()
    return {
        "root": str(LIBRARY_ROOT),
        "subtrees": [
            {
                "name": name,
                "files": _file_rows(LIBRARY_ROOT / name),
            }
            for name in ALLOWED_SUBTREES
        ],
    }


@router.get("/ui", response_class=HTMLResponse)
def library_ui():
    _ensure_root()
    return HTMLResponse(_render_ui())


@router.get("/{subtree}", response_class=JSONResponse)
def library_subtree(subtree: str):
    _ensure_root()
    root = _subtree_root(subtree)
    return {
        "subtree": str(subtree).strip().lower(),
        "root": str(root),
        "files": _file_rows(root),
    }


@router.get("/{subtree}/raw/{relpath:path}")
def library_raw(subtree: str, relpath: str):
    _ensure_root()
    root = _subtree_root(subtree)
    rel = _safe_rel_path(relpath)
    path = (root / rel).resolve()
    try:
        path.relative_to(root.resolve())
    except Exception as e:
        raise HTTPException(status_code=400, detail="illegal relpath") from e
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(str(path), filename=path.name)


@router.delete("/{subtree}/raw/{relpath:path}", response_class=JSONResponse)
def library_delete(subtree: str, relpath: str):
    _ensure_root()
    root = _subtree_root(subtree)
    rel = _safe_rel_path(relpath)
    path = (root / rel).resolve()
    try:
        path.relative_to(root.resolve())
    except Exception as e:
        raise HTTPException(status_code=400, detail="illegal relpath") from e
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    path.unlink()
    return {"ok": True, "deleted": rel.as_posix()}


@router.post("/{subtree}/upload", response_class=JSONResponse)
async def library_upload(
    subtree: str,
    files: list[UploadFile] = File(...),
    subdir: str = Form(""),
):
    _ensure_root()
    root = _subtree_root(subtree)
    rel_subdir = _safe_subdir(subdir)
    target_dir = (root / rel_subdir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        target_dir.relative_to(root.resolve())
    except Exception as e:
        raise HTTPException(status_code=400, detail="illegal subdir") from e

    saved: list[dict] = []
    for upload in files:
        name = Path(str(upload.filename or "")).name
        if not name or name in (".", ".."):
            raise HTTPException(status_code=400, detail="illegal filename")
        dst = target_dir / name
        tmp = dst.with_suffix(dst.suffix + ".tmp")
        with tmp.open("wb") as f:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
        os.replace(tmp, dst)
        try:
            os.chmod(dst, 0o660)
        except Exception:
            pass
        saved.append(
            {
                "filename": name,
                "relpath": dst.relative_to(root).as_posix(),
                "size_bytes": dst.stat().st_size,
            }
        )
        await upload.close()

    return {"ok": True, "saved": saved}
