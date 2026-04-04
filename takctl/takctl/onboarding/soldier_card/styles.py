from __future__ import annotations

def print_pack_style_html() -> str:
    return """<style>
@page {
  size: A4 portrait;
  margin: 10mm;
}
html, body {
  margin: 0;
  padding: 0;
  background: #ffffff;
  color: #111111;
}
body.print-pack {
  background: #ffffff;
  color: #111111;
  font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
}
.print-pack-wrap {
  width: 100%;
}
.print-page {
  page-break-after: always;
  break-after: page;
  padding: 0;
  margin: 0;
}
.print-page:last-child {
  page-break-after: auto;
  break-after: auto;
}
.print-password-page {
  page-break-after: always;
  break-after: page;
  padding: 0;
  margin: 0;
}
.print-password-page:last-child {
  page-break-after: auto;
  break-after: auto;
}
.print-card-shell {
  padding: 0;
}
.print-password-shell {
  border: 1px solid #cfcfcf;
  border-radius: 10px;
  overflow: hidden;
  background: #fff;
}
.print-password-topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  background: linear-gradient(180deg, #1f2328 0%, #111418 100%);
  color: #fff;
  border-bottom: 3px solid #b08d2f;
}
.print-password-title {
  font-size: 24px;
  font-weight: 900;
  line-height: 1.05;
}
.print-password-subtitle {
  font-size: 15px;
  color: rgba(255,255,255,0.82);
  margin-top: 3px;
}
.print-password-box {
  border: 1px solid #d8d8d8;
  border-radius: 10px;
  padding: 14px;
  margin-top: 14px;
  background: #fff;
}
.print-row {
  display: grid;
  grid-template-columns: 160px minmax(0,1fr);
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.print-label {
  font-size: 11px;
  color: #6d7278;
  font-weight: 800;
  text-transform: uppercase;
  white-space: nowrap;
  letter-spacing: 0.04em;
}
.print-value {
  font-size: 15px;
  line-height: 1.25;
}
.print-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}
.print-big {
  font-size: 22px;
  line-height: 1.2;
  font-weight: 800;
  word-break: break-all;
}
@media screen {
  body.print-pack {
    background: #e9e9e9;
  }
  .print-page,
  .print-password-page {
    width: 210mm;
    min-height: 297mm;
    margin: 0 auto 8mm auto;
    background: #fff;
    padding: 10mm;
    box-sizing: border-box;
  }
}
@media print {
  .interactive-only {
    display: none !important;
  }
}

.print-password-page .btn,
.print-password-page button,
.print-password-page a.btn {
  display: none !important;
}

.print-password-page .profile-body .kvlabel {
  color: #6d7278 !important;
}

.print-password-page .profile-body .kvvalue,
.print-password-page .profile-body .kvvalue code,
.print-password-page .profile-body .kvvalue b,
.print-password-page .profile-body .kvvalue strong {
  color: #111111 !important;
}

.print-password-page .profile-body code,
.print-password-page .note code {
  background: #f3f5f8 !important;
  color: #111111 !important;
  border: 1px solid #d8d8d8 !important;
  padding: 1px 4px !important;
  border-radius: 4px !important;
}

.print-password-page .note,
.print-password-page .note * {
  color: #111111 !important;
}
</style>"""

def card_btn_css() -> str:
    return """
    .btn { font-size: 12px; padding: 7px 11px; border: 1px solid rgba(255,255,255,0.20); border-radius: 12px; background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.92); cursor: pointer; text-decoration:none; display:inline-block; font-weight:600; }
    .btn:hover { background: rgba(255,255,255,0.10); }
    .warn { color:#ffd27a; }
    .danger-note { margin-top:8px; padding:10px 12px; border-radius:10px; background:rgba(255,210,122,0.08); border:1px solid rgba(255,210,122,0.18); color:#ffe3ac; font-size:13px; line-height:1.45; }
    .stepcard { background: rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08); border-radius:16px; padding:16px; }
    .stepcard h4 { margin:0 0 8px 0; font-size:15px; }
    .qrimg { width:220px; max-width:100%; height:auto; border-radius:12px; background:#fff; padding:8px; }
    .choicegrid { display:grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap:14px; }
    .guidegrid { display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:14px; }
    .infogrid { display:grid; grid-template-columns: 1fr; gap:14px; }
    .dlrow { display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }
    code.inline { font-size:12px; }
    .hero { background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.03)); border:1px solid rgba(255,255,255,0.10); border-radius:18px; padding:18px 20px; margin-bottom:14px; box-shadow: 0 10px 30px rgba(0,0,0,0.22); }
    .eyebrow { font-size:12px; letter-spacing:0.14em; text-transform:uppercase; color:#8bb8ff; font-weight:700; }
    .hero-title { font-size:30px; line-height:1.1; font-weight:850; margin-top:10px; }
    .hero-sub { font-size:15px; line-height:1.6; color:rgba(255,255,255,0.78); margin-top:10px; max-width:760px; }
    .slogan { margin-top:8px; font-size:12px; letter-spacing:0.12em; text-transform:uppercase; color:rgba(255,255,255,0.58); }
    """

def card_style_html() -> str:
    return """<style>
:root {
  --bg0: #0b0c10;
  --bg1: #101218;
  --card: rgba(255,255,255,0.04);
  --card2: rgba(255,255,255,0.06);
  --bd: rgba(255,255,255,0.10);
  --txt: rgba(255,255,255,0.92);
  --muted: rgba(255,255,255,0.65);
  --link: #8bb8ff;
}
body {
  font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
  margin: 22px;
  color: var(--txt);
  background:
    radial-gradient(1200px 500px at 30% 0%, rgba(255,255,255,0.06), transparent 60%),
    radial-gradient(900px 450px at 80% 30%, rgba(255,255,255,0.04), transparent 55%),
    linear-gradient(180deg, var(--bg0), var(--bg1));
  min-height: 100vh;
}
.topbar { display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; margin-bottom: 12px; gap: 14px; }
.brand { display:flex; align-items:center; gap: 10px; flex-wrap:wrap; }
.taksmark img { height: 26px; width: auto; display:block; filter: drop-shadow(0 6px 18px rgba(0,0,0,0.55)); }
.brandchain-row { display:flex; align-items:center; gap: 10px; flex-wrap:wrap; }
.brandchain-row img { height: 24px; width: auto; max-width: 260px; object-fit: contain; display:block; filter: drop-shadow(0 2px 10px rgba(0,0,0,0.45)); }
.meta { font-size: 12px; color: var(--muted); line-height: 1.35; }
.muted { color: var(--muted); font-size: 12px; }
.card { background: var(--card); border: 1px solid var(--bd); border-radius: 16px; padding: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.22); }
.tabs { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:12px; }
.choicebtn { border:1px solid var(--bd); background:var(--card2); color:var(--txt); padding:8px 12px; border-radius:999px; cursor:pointer; font-size:13px; }
.choicebtn-active { outline:2px solid rgba(139,184,255,0.45); }
a { color: var(--link); }
pre { white-space: pre-wrap; word-break: break-word; }
.print-expanded > div[id^="tab_"],
.print-expanded > div[id^="flow_"] { display:block !important; }
.print-expanded .tabs.interactive-only,
.print-expanded .choicebtn.interactive-only,
.print-expanded .interactive-only,
.print-expanded .dlrow,
.print-expanded .btn,
.print-expanded a.btn { display:none !important; }
.print-expanded #tab_info { display:none !important; }

.print-expanded,
.print-expanded .card,
.print-expanded .stepcard {
  background: #ffffff !important;
  color: #111111 !important;
  border-color: #d8d8d8 !important;
  box-shadow: none !important;
}

.print-expanded .hero {
  background: #f3f5f8 !important;
  color: #111111 !important;
  border: 1px solid #d8d8d8 !important;
  box-shadow: none !important;
}

.print-expanded .hero * {
  text-shadow: none !important;
}

.print-expanded .hero-title,
.print-expanded .hero-title * {
  color: #111111 !important;
}

.print-expanded .hero-sub,
.print-expanded .hero-sub * {
  color: #555555 !important;
}

.print-expanded .slogan,
.print-expanded .slogan * {
  color: #555555 !important;
}

.print-expanded .hero .meta,
.print-expanded .hero .meta * {
  color: #555555 !important;
}

.print-expanded .eyebrow,
.print-expanded .eyebrow * {
  color: #355d9a !important;
}

.print-expanded .hero code,
.print-expanded .hero code * {
  background: #eef2f7 !important;
  color: #111111 !important;
  border: 1px solid #d8d8d8 !important;
}

.print-expanded code,
.print-expanded code.inline {
  background: #f3f5f8 !important;
  color: #111111 !important;
  border: 1px solid #d8d8d8 !important;
  padding: 1px 4px !important;
  border-radius: 4px !important;
}

.print-expanded strong,
.print-expanded b {
  color: #111111 !important;
}

.print-expanded ::selection {
  background: transparent !important;
  color: inherit !important;
}

.print-expanded a,
.print-expanded a:visited {
  color: #111111 !important;
}

.print-expanded .danger-note {
  background: #fff8e8 !important;
  color: #6a4b00 !important;
  border: 1px solid #e6cf95 !important;
}

.print-expanded .qrimg {
  background: #ffffff !important;
  border: 1px solid #d8d8d8 !important;
}

.print-nameplate {
  margin-bottom: 14px;
  padding: 12px 14px;
  border: 1px solid #d8d8d8;
  border-radius: 12px;
  background: linear-gradient(180deg, #1f4b87 0%, #183b6b 100%);
  color: #ffffff !important;
  box-shadow: none !important;
}
.print-nameplate .print-nameplate-callsign {
  font-size: 22px;
  font-weight: 900;
  line-height: 1.05;
  margin: 0 0 4px 0;
  color: #ffffff !important;
}
.print-nameplate .print-nameplate-meta {
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(255,255,255,0.88) !important;
  font-weight: 700;
}
</style>"""
