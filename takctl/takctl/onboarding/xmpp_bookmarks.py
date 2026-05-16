from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import ssl
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import xml.etree.ElementTree as ET


PUBSUB_NS = "http://jabber.org/protocol/pubsub"
BOOKMARKS2_NS = "urn:xmpp:bookmarks:1"

STATE_ROOT = Path("/opt/tak/takctl-state/onboarding")
BOOKMARK_STATE_DIR = STATE_ROOT / "xmpp_bookmarks"
PENDING_DIR = BOOKMARK_STATE_DIR / "pending"
DONE_DIR = BOOKMARK_STATE_DIR / "done"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 5222


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_name(s: str) -> str:
    v = str(s or "").strip()
    out = "".join(c if (c.isalnum() or c in "._-@") else "_" for c in v)
    return out or "unknown"


def _write_json_atomic(path: Path, obj: dict[str, Any], *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{uuid.uuid4().hex}")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        os.chmod(tmp, mode)
    except Exception:
        pass
    tmp.replace(path)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _cfg_get(*keys: str) -> str:
    try:
        from takctl.config import load_config

        cfg = load_config()
        for key in keys:
            v = str(cfg.get(key, "") or "").strip()
            if v:
                return v
    except Exception:
        pass
    return ""


def _domain_from_openfire_xml() -> str:
    p = Path("/etc/openfire/openfire.xml")
    if not p.exists():
        return ""
    try:
        root = ET.fromstring(p.read_text(encoding="utf-8"))
        for elem in root.iter():
            if elem.tag.lower().endswith("domain") and elem.text and elem.text.strip():
                return elem.text.strip().lower()
    except Exception:
        return ""
    return ""


def default_xmpp_domain() -> str:
    v = _cfg_get("xmpp_domain", "openfire_domain", "node_fqdn", "fqdn")
    if v:
        return v.lower()

    base = _cfg_get("onboarding_external_base")
    if base:
        try:
            host = urlparse(base).hostname or ""
            if host:
                return host.lower()
        except Exception:
            pass

    v = _domain_from_openfire_xml()
    if v:
        return v.lower()

    try:
        return socket.getfqdn().strip().lower()
    except Exception:
        return ""


def _identity_to_dict(identity: Any) -> dict[str, Any]:
    if identity is None:
        return {}
    if isinstance(identity, dict):
        return dict(identity)
    try:
        d = getattr(identity, "identity", None)
        if isinstance(d, dict):
            return dict(d)
    except Exception:
        pass
    return {}


def _ctx_from_inputs(username: str, selection: dict[str, Any] | None, identity: Any = None) -> dict[str, Any]:
    if isinstance(selection, dict):
        ctx = selection.get("ctx")
        if isinstance(ctx, dict) and ctx:
            return dict(ctx)

    try:
        from takctl.onboarding.selection import load_selection

        sel = load_selection(username)
        ctx = sel.get("ctx") if isinstance(sel, dict) else None
        if isinstance(ctx, dict) and ctx:
            return dict(ctx)
    except Exception:
        pass

    try:
        ctx = getattr(identity, "ctx", None)
        if isinstance(ctx, dict) and ctx:
            return dict(ctx)
    except Exception:
        pass

    try:
        from takctl.onboarding.store_filejson import FileJsonOnboardingStore

        ident = FileJsonOnboardingStore(STATE_ROOT).get_identity(username)
        ctx = getattr(ident, "ctx", None)
        if isinstance(ctx, dict) and ctx:
            return dict(ctx)
    except Exception:
        pass

    return {}


def _password_from_store(username: str) -> str:
    try:
        from takctl.onboarding.store_filejson import FileJsonOnboardingStore

        ident = FileJsonOnboardingStore(STATE_ROOT).get_identity(username)
        if ident is not None and getattr(ident, "password_known", False):
            return str(getattr(ident, "password", "") or "").strip()
    except Exception:
        pass
    return ""


def derive_user_bookmarks(
    *,
    username: str,
    password: str | None = None,
    selection: dict[str, Any] | None = None,
    identity: Any = None,
    domain: str | None = None,
) -> dict[str, Any]:
    username = str(username or "").strip()
    if not username:
        raise ValueError("username required")

    domain = str(domain or default_xmpp_domain() or "").strip().lower()
    if not domain:
        raise RuntimeError("cannot determine XMPP domain")

    ctx = _ctx_from_inputs(username, selection, identity)
    ident_d = _identity_to_dict(identity)

    if not ident_d:
        try:
            from takctl.onboarding.store_filejson import FileJsonOnboardingStore

            ident = FileJsonOnboardingStore(STATE_ROOT).get_identity(username)
            ident_d = _identity_to_dict(ident)
            if not ctx and ident is not None:
                ctx = dict(getattr(ident, "ctx", None) or {})
        except Exception:
            ident_d = {}

    if "policy_id" not in ctx or not str(ctx.get("policy_id") or "").strip():
        try:
            from takctl.onboarding.policy_registry import default_policy_id

            pid = default_policy_id()
            if pid:
                ctx = dict(ctx)
                ctx["policy_id"] = pid
        except Exception:
            pass

    try:
        from takctl.onboarding.channels import build_selection_channels

        channel_state = build_selection_channels(ctx, selection=selection)
        rooms = [str(x).strip() for x in (channel_state.get("selected") or []) if str(x or "").strip()]
        available_rooms = [str(x).strip() for x in (channel_state.get("available") or []) if str(x or "").strip()]
        default_rooms = [str(x).strip() for x in (channel_state.get("default") or []) if str(x or "").strip()]
    except Exception:
        channel_state = {}
        available_rooms = []
        default_rooms = []
        try:
            from takctl.onboarding.voice_topology import derive_voice_topology

            topo = derive_voice_topology(None, ctx)
            rooms = [str(x).strip() for x in (topo.get("seed_channels") or []) if str(x or "").strip()]
            available_rooms = [str(x).strip() for x in (topo.get("channels") or []) if str(x or "").strip()]
            default_rooms = list(rooms)
        except Exception:
            rooms = []

        if not rooms:
            fallback = str(ctx.get("battalion_fal") or ctx.get("unit") or "VQ").strip() or "VQ"
            rooms = [fallback]
            available_rooms = [fallback]
            default_rooms = [fallback]

    def _conf_for_room(room: str) -> dict[str, Any]:
        return {
            "name": room,
            "jid": f"{room}@conference.{domain}",
            "nick": nick,
            "autojoin": True,
        }

    nick = (
        str(ident_d.get("callsign") or "").strip()
        or str(ctx.get("callsign") or "").strip()
        or username
    )

    rooms = list(dict.fromkeys(rooms))
    available_rooms = list(dict.fromkeys(list(available_rooms) + list(rooms)))
    default_rooms = list(dict.fromkeys(default_rooms))

    conferences = [_conf_for_room(room) for room in rooms]
    available_conferences = [_conf_for_room(room) for room in available_rooms]

    return {
        "username": username,
        "domain": domain,
        "jid": f"{username}@{domain}",
        "nick": nick,
        "ctx": ctx,
        "rooms": rooms,
        "available_rooms": available_rooms,
        "default_rooms": default_rooms,
        "conferences": conferences,
        "available_conferences": available_conferences,
        "channel_state": channel_state,
        "password_known": bool(str(password or "").strip() or _password_from_store(username)),
    }


def enqueue_user_bookmarks(
    *,
    username: str,
    password: str | None = None,
    selection: dict[str, Any] | None = None,
    identity: Any = None,
    reason: str = "unspecified",
) -> dict[str, Any]:
    derived = derive_user_bookmarks(
        username=username,
        password=password,
        selection=selection,
        identity=identity,
    )

    job = {
        "schema": 2,
        "username": derived["username"],
        "jid": derived["jid"],
        "domain": derived["domain"],
        "host": DEFAULT_HOST,
        "port": DEFAULT_PORT,
        "nick": derived["nick"],
        "rooms": derived["rooms"],
        "available_rooms": derived.get("available_rooms") or [],
        "default_rooms": derived.get("default_rooms") or [],
        "conferences": derived["conferences"],
        "available_conferences": derived.get("available_conferences") or [],
        "ctx": derived["ctx"],
        "reason": str(reason or "unspecified"),
        "auth": {
            "password": str(password or "").strip() or None,
        },
        "attempts": 0,
        "requested_at_utc": _now_iso(),
        "updated_at_utc": _now_iso(),
        "last_error": None,
    }

    p = PENDING_DIR / f"{_safe_name(derived['username'])}.json"
    _write_json_atomic(p, job)

    return {
        "ok": True,
        "queued": True,
        "username": derived["username"],
        "jid": derived["jid"],
        "rooms": derived["rooms"],
        "pending_path": str(p),
        "password_known": bool(job["auth"]["password"] or derived["password_known"]),
    }


@dataclass
class _PublishResult:
    ok: bool
    error: str = ""


def _publish_bookmarks_once(
    *,
    jid: str,
    password: str,
    host: str,
    port: int,
    conferences: list[dict[str, Any]],
    retract_conferences: list[dict[str, Any]] | None = None,
    timeout_s: int = 25,
) -> _PublishResult:
    try:
        import slixmpp
    except Exception as e:
        return _PublishResult(False, f"slixmpp import failed: {type(e).__name__}: {e}")

    class BookmarkPublisher(slixmpp.ClientXMPP):
        def __init__(self) -> None:
            super().__init__(jid, password)
            self.result = _PublishResult(False, "not completed")
            self.add_event_handler("session_start", self.session_start)
            self.add_event_handler("failed_auth", self.failed_auth)
            self.ssl_context = ssl.create_default_context()
            self.ssl_context.check_hostname = False
            self.ssl_context.verify_mode = ssl.CERT_NONE

        def failed_auth(self, event) -> None:
            self.result = _PublishResult(False, "auth failed")
            self.disconnect()

        async def publish_iq(self, *, item_id: str, payload: ET.Element) -> None:
            iq = self.Iq()
            iq["type"] = "set"
            iq["to"] = self.boundjid.bare

            pubsub = ET.Element(f"{{{PUBSUB_NS}}}pubsub")
            publish = ET.SubElement(pubsub, f"{{{PUBSUB_NS}}}publish", {"node": BOOKMARKS2_NS})
            item = ET.SubElement(publish, f"{{{PUBSUB_NS}}}item", {"id": item_id})
            item.append(payload)

            iq.append(pubsub)
            await iq.send(timeout=timeout_s)

        async def retract_iq(self, *, item_id: str) -> None:
            iq = self.Iq()
            iq["type"] = "set"
            iq["to"] = self.boundjid.bare

            pubsub = ET.Element(f"{{{PUBSUB_NS}}}pubsub")
            retract = ET.SubElement(
                pubsub,
                f"{{{PUBSUB_NS}}}retract",
                {"node": BOOKMARKS2_NS, "notify": "true"},
            )
            ET.SubElement(retract, f"{{{PUBSUB_NS}}}item", {"id": item_id})

            iq.append(pubsub)
            await iq.send(timeout=timeout_s)

        async def session_start(self, event) -> None:
            try:
                self.send_presence()
                for conf in conferences:
                    room_jid = str(conf.get("jid") or "").strip()
                    name = str(conf.get("name") or room_jid).strip()
                    nick = str(conf.get("nick") or "").strip()
                    if not room_jid:
                        continue

                    payload = ET.Element(
                        f"{{{BOOKMARKS2_NS}}}conference",
                        {"name": name, "autojoin": "true"},
                    )
                    payload.set("jid", room_jid)
                    if nick:
                        nick_el = ET.SubElement(payload, f"{{{BOOKMARKS2_NS}}}nick")
                        nick_el.text = nick

                    await self.publish_iq(item_id=room_jid, payload=payload)

                selected_ids = {
                    str(conf.get("jid") or "").strip()
                    for conf in conferences
                    if str(conf.get("jid") or "").strip()
                }
                for conf in (retract_conferences or []):
                    item_id = str(conf.get("jid") or "").strip()
                    if not item_id or item_id in selected_ids:
                        continue
                    try:
                        await self.retract_iq(item_id=item_id)
                    except Exception as e:
                        # Missing bookmark item is already the desired end-state.
                        if "item-not-found" in str(e).lower():
                            continue
                        raise

                self.result = _PublishResult(True, "")
            except Exception as e:
                self.result = _PublishResult(False, f"{type(e).__name__}: {e}")
            finally:
                self.disconnect()

    xmpp = BookmarkPublisher()
    try:
        xmpp.register_plugin("xep_0030")
    except Exception:
        pass

    try:
        connect_future = xmpp.connect(host=host, port=int(port))

        loop = getattr(xmpp, "loop", None)
        if loop is None:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

        try:
            if connect_future is not None:
                loop.run_until_complete(asyncio.wait_for(connect_future, timeout=timeout_s))
            loop.run_until_complete(asyncio.wait_for(xmpp.disconnected, timeout=timeout_s + 5))
        except asyncio.TimeoutError as e:
            try:
                xmpp.disconnect()
            except Exception:
                pass
            raise RuntimeError(f"timed out waiting for XMPP bookmark publish host={host} port={port}") from e
        return xmpp.result
    except Exception as e:
        return _PublishResult(False, f"{type(e).__name__}: {e}")


def sync_bookmark_job(path: Path) -> dict[str, Any]:
    job = _load_json(path)
    username = str(job.get("username") or "").strip()
    if not username:
        raise RuntimeError(f"invalid bookmark job without username: {path}")

    password = str(((job.get("auth") or {}).get("password")) or "").strip()
    if not password:
        password = _password_from_store(username)
    if not password:
        raise RuntimeError(f"password not known to TAKS for {username}")

    domain = str(job.get("domain") or default_xmpp_domain()).strip().lower()
    host = str(job.get("host") or DEFAULT_HOST).strip() or DEFAULT_HOST
    port = int(job.get("port") or DEFAULT_PORT)

    has_conferences_key = "conferences" in job
    conferences = list(job.get("conferences") or [])
    available_conferences = list(job.get("available_conferences") or job.get("all_conferences") or [])

    if not has_conferences_key:
        derived = derive_user_bookmarks(username=username, password=password, domain=domain)
        conferences = list(derived.get("conferences") or [])
        available_conferences = list(derived.get("available_conferences") or available_conferences)
    elif not available_conferences:
        try:
            derived = derive_user_bookmarks(username=username, password=password, domain=domain)
            available_conferences = list(derived.get("available_conferences") or [])
        except Exception:
            available_conferences = []

    res = _publish_bookmarks_once(
        jid=f"{username}@{domain}",
        password=password,
        host=host,
        port=port,
        conferences=conferences,
        retract_conferences=available_conferences,
    )
    if not res.ok:
        raise RuntimeError(res.error or "publish failed")

    done = dict(job)
    done["attempts"] = int(done.get("attempts") or 0) + 1
    done["updated_at_utc"] = _now_iso()
    done["published_at_utc"] = _now_iso()
    done["last_error"] = None
    done_path = DONE_DIR / path.name
    _write_json_atomic(done_path, done)
    try:
        path.unlink()
    except FileNotFoundError:
        pass

    return {
        "ok": True,
        "username": username,
        "rooms": [str(c.get("name") or c.get("jid") or "") for c in conferences],
        "done_path": str(done_path),
    }


def sync_pending_bookmark_jobs(*, limit: int = 100) -> dict[str, Any]:
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    DONE_DIR.mkdir(parents=True, exist_ok=True)

    paths = sorted(PENDING_DIR.glob("*.json"))[: max(1, int(limit))]
    results: list[dict[str, Any]] = []

    for path in paths:
        try:
            results.append(sync_bookmark_job(path))
        except Exception as e:
            try:
                job = _load_json(path)
            except Exception:
                job = {}
            job["attempts"] = int(job.get("attempts") or 0) + 1
            job["updated_at_utc"] = _now_iso()
            job["last_error"] = f"{type(e).__name__}: {e}"
            _write_json_atomic(path, job)
            results.append({
                "ok": False,
                "path": str(path),
                "username": str(job.get("username") or ""),
                "error": job["last_error"],
            })

    return {
        "ok": all(bool(r.get("ok")) for r in results) if results else True,
        "count": len(results),
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sync pending TAKS XMPP conference bookmarks.")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--strict", action="store_true", help="return non-zero if any job fails")
    args = ap.parse_args(argv)

    out = sync_pending_bookmark_jobs(limit=args.limit)
    print(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False))
    if args.strict and not out.get("ok"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
