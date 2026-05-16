from __future__ import annotations

import logging
import queue
import re
import ssl
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from .config import ConfigError, VoiceConfig

LOG = logging.getLogger("martine.voice.mumble")


def _ensure_ssl_wrap_socket_compat() -> None:
    # pymumble_py3 still calls ssl.wrap_socket(), which was removed in Python 3.12.
    # Keep the shim local to Martine voice so we do not patch site-packages.
    if hasattr(ssl, "wrap_socket"):
        return

    def _wrap_socket(
        sock,
        keyfile=None,
        certfile=None,
        server_side=False,
        cert_reqs=ssl.CERT_NONE,
        ssl_version=ssl.PROTOCOL_TLS,
        ca_certs=None,
        do_handshake_on_connect=True,
        suppress_ragged_eofs=True,
        ciphers=None,
    ):
        ctx = ssl.SSLContext(ssl_version)
        ctx.check_hostname = False
        ctx.verify_mode = cert_reqs

        if ca_certs:
            ctx.load_verify_locations(ca_certs)
        if certfile:
            ctx.load_cert_chain(certfile, keyfile)
        if ciphers:
            ctx.set_ciphers(ciphers)

        return ctx.wrap_socket(
            sock,
            server_side=server_side,
            do_handshake_on_connect=do_handshake_on_connect,
            suppress_ragged_eofs=suppress_ragged_eofs,
        )

    ssl.wrap_socket = _wrap_socket


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_all_channels(value: str) -> bool:
    return str(value or "").strip().lower() in {"*", "all", "alla", "any"}


@dataclass(frozen=True)
class ReceivedSoundChunk:
    ts: datetime
    channel: str
    speaker: str
    session: int
    sample_rate_hz: int
    sample_width_bytes: int
    channels: int
    pcm_s16le: bytes


class MumbleIngest:
    def __init__(self, cfg: VoiceConfig) -> None:
        self.cfg = cfg
        self._mumble = None
        self._watcher = None
        self._bots: dict[str, object] = {}
        self._bot_last_seen: dict[str, float] = {}
        self._queue: queue.Queue[ReceivedSoundChunk] = queue.Queue(maxsize=4096)
        self._lock = threading.Lock()
        self._started = False
        self._stop_event = threading.Event()
        self._watcher_thread: threading.Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self._started:
                return

            mumble_mod, cbk_sound_received = _import_pymumble()

            if _is_all_channels(self.cfg.channel):
                self._start_all_channel_mode_locked(mumble_mod, cbk_sound_received)
            else:
                self._start_single_channel_mode_locked(mumble_mod, cbk_sound_received)

            self._started = True

    def _start_single_channel_mode_locked(self, mumble_mod, cbk_sound_received) -> None:
        mumble = self._connect(
            mumble_mod,
            username=self.cfg.username,
            receive_sound=True,
            cbk_sound_received=cbk_sound_received,
            callback=lambda user, soundchunk: self._on_sound_received_for_channel(
                self.cfg.channel,
                user,
                soundchunk,
            ),
        )
        self._mumble = mumble
        self._move_to_target_channel(mumble, self.cfg.channel)

        LOG.info(
            "mumble ingest connected host=%s port=%s channel=%s username=%s",
            self.cfg.host,
            self.cfg.port,
            self.cfg.channel,
            self.cfg.username,
        )

    def _start_all_channel_mode_locked(self, mumble_mod, cbk_sound_received) -> None:
        self._stop_event.clear()

        watcher_username = _safe_username(self.cfg.username + "-watch")
        watcher = self._connect(
            mumble_mod,
            username=watcher_username,
            receive_sound=False,
            cbk_sound_received=None,
            callback=None,
        )
        self._watcher = watcher

        self._sync_active_channel_bots_locked(mumble_mod, cbk_sound_received)

        self._watcher_thread = threading.Thread(
            target=self._watch_active_channels,
            args=(mumble_mod, cbk_sound_received),
            name="martine-mumble-channel-watch",
            daemon=True,
        )
        self._watcher_thread.start()

        LOG.info(
            "mumble ingest connected host=%s port=%s channel=* username=%s mode=active-channel-listeners",
            self.cfg.host,
            self.cfg.port,
            self.cfg.username,
        )

    def _connect(
        self,
        mumble_mod,
        *,
        username: str,
        receive_sound: bool,
        cbk_sound_received,
        callback,
    ):
        _ensure_ssl_wrap_socket_compat()

        mumble = mumble_mod.Mumble(
            self.cfg.host,
            username,
            password=self.cfg.password,
            port=self.cfg.port,
        )
        if cbk_sound_received is not None and callback is not None:
            mumble.callbacks.set_callback(cbk_sound_received, callback)
        mumble.set_receive_sound(bool(receive_sound))
        mumble.start()
        mumble.is_ready()
        return mumble

    def stop(self) -> None:
        self._stop_event.set()

        with self._lock:
            watcher = self._watcher
            self._watcher = None

            mumble = self._mumble
            self._mumble = None

            bots = list(self._bots.values())
            self._bots.clear()
            self._bot_last_seen.clear()
            self._started = False

        for client in [watcher, mumble] + bots:
            if client is not None:
                try:
                    client.stop()
                except Exception:
                    LOG.exception("mumble stop failed")

        th = self._watcher_thread
        if th is not None and th.is_alive():
            th.join(timeout=2.0)
        self._watcher_thread = None

    def poll(self, timeout: float = 0.5) -> ReceivedSoundChunk | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _watch_active_channels(self, mumble_mod, cbk_sound_received) -> None:
        while not self._stop_event.wait(2.0):
            try:
                with self._lock:
                    if not self._started or self._watcher is None:
                        return
                    self._sync_active_channel_bots_locked(mumble_mod, cbk_sound_received)
            except Exception:
                LOG.exception("active channel watcher failed")

    def _sync_active_channel_bots_locked(self, mumble_mod, cbk_sound_received) -> None:
        watcher = self._watcher
        if watcher is None:
            return

        now = time.monotonic()
        active_channels = self._active_human_channels(watcher)

        for channel_name in sorted(active_channels):
            self._bot_last_seen[channel_name] = now
            if channel_name in self._bots:
                continue

            username = _safe_username(self.cfg.username + "-" + _safe_suffix(channel_name))
            bot = self._connect(
                mumble_mod,
                username=username,
                receive_sound=True,
                cbk_sound_received=cbk_sound_received,
                callback=lambda user, soundchunk, ch=channel_name: self._on_sound_received_for_channel(
                    ch,
                    user,
                    soundchunk,
                ),
            )
            self._move_to_target_channel(bot, channel_name)
            self._bots[channel_name] = bot

            LOG.info(
                "started mumble listener bot channel=%s username=%s",
                channel_name,
                username,
            )

        idle_cutoff_sec = 120.0
        for channel_name in list(self._bots.keys()):
            last_seen = self._bot_last_seen.get(channel_name, 0.0)
            if channel_name in active_channels or now - last_seen < idle_cutoff_sec:
                continue

            bot = self._bots.pop(channel_name, None)
            self._bot_last_seen.pop(channel_name, None)

            if bot is not None:
                try:
                    bot.stop()
                except Exception:
                    LOG.exception("failed stopping idle mumble listener bot channel=%s", channel_name)

            LOG.info("stopped idle mumble listener bot channel=%s", channel_name)

    def _active_human_channels(self, mumble) -> set[str]:
        channel_by_id: dict[int, str] = {}

        try:
            channels = getattr(mumble, "channels", {}) or {}
            for _k, ch in channels.items():
                cid = _channel_id(ch)
                name = _channel_name(ch)
                if cid is not None and name and name != "unknown":
                    channel_by_id[cid] = name
        except Exception:
            LOG.exception("failed reading mumble channels")
            return set()

        out: set[str] = set()

        try:
            users = getattr(mumble, "users", {}) or {}
            for _k, user in users.items():
                name = _user_name(user)
                if _is_martine_or_probe_user(name, self.cfg.username):
                    continue

                cid = _user_channel_id(user)
                channel_name = channel_by_id.get(cid or -1, "")
                if channel_name and channel_name.lower() != "root":
                    out.add(channel_name)
        except Exception:
            LOG.exception("failed reading mumble users")
            return set()

        return out

    def _move_to_target_channel(self, mumble, channel_name: str) -> None:
        deadline = time.time() + 10.0
        chan = None

        while time.time() < deadline:
            chan = mumble.channels.find_by_name(channel_name)
            if chan is not None:
                break
            time.sleep(0.1)

        if chan is None:
            raise ConfigError(f"Mumble channel not found: {channel_name}")

        chan.move_in()

        time.sleep(0.2)

        try:
            current = mumble.my_channel()
            current_name = _channel_name(current)
        except Exception:
            current_name = "unknown"

        LOG.info("moved to mumble channel target=%s current=%s", channel_name, current_name)

    def _on_sound_received_for_channel(self, channel: str, user, soundchunk) -> None:
        try:
            speaker = _user_name(user)
            if _is_martine_or_probe_user(speaker, self.cfg.username):
                return

            session = _user_session(user)
            pcm = bytes(getattr(soundchunk, "pcm", b"") or b"")
            if not pcm:
                return

            item = ReceivedSoundChunk(
                ts=_utc_now(),
                channel=channel,
                speaker=speaker,
                session=session,
                sample_rate_hz=48000,
                sample_width_bytes=2,
                channels=1,
                pcm_s16le=pcm,
            )

            try:
                self._queue.put_nowait(item)
            except queue.Full:
                LOG.warning("dropping sound chunk because ingest queue is full")
        except Exception:
            LOG.exception("sound receive callback failed")


def _import_pymumble():
    try:
        import pymumble_py3 as pymumble_py3
        from pymumble_py3.callbacks import PYMUMBLE_CLBK_SOUNDRECEIVED
        return pymumble_py3, PYMUMBLE_CLBK_SOUNDRECEIVED
    except Exception:
        pass

    try:
        import pymumble.pymumble_py3 as pymumble_py3
        from pymumble.pymumble_py3.callbacks import (
            PYMUMBLE_CLBK_SOUNDRECEIVED,
        )
        return pymumble_py3, PYMUMBLE_CLBK_SOUNDRECEIVED
    except Exception as e:
        raise ConfigError("pymumble is not available in the Martine runtime environment") from e


def _user_name(user) -> str:
    for key in ("name", "username"):
        try:
            value = user[key]
            if value:
                return str(value)
        except Exception:
            pass

    try:
        value = user.get_property("name")
        if value:
            return str(value)
    except Exception:
        pass

    return "unknown"


def _user_session(user) -> int:
    try:
        value = user["session"]
        if value is not None:
            return int(value)
    except Exception:
        pass

    try:
        value = user.get_property("session")
        if value is not None:
            return int(value)
    except Exception:
        pass

    return -1


def _user_channel_id(user) -> int | None:
    try:
        value = user["channel_id"]
        if value is not None:
            return int(value)
    except Exception:
        pass

    try:
        value = user.get_property("channel_id")
        if value is not None:
            return int(value)
    except Exception:
        pass

    return None


def _channel_id(channel) -> int | None:
    if channel is None:
        return None

    for key in ("channel_id", "id"):
        try:
            value = channel[key]
            if value is not None:
                return int(value)
        except Exception:
            pass

        try:
            value = channel.get_property(key)
            if value is not None:
                return int(value)
        except Exception:
            pass

    return None


def _channel_name(channel) -> str:
    if channel is None:
        return "unknown"

    for key in ("name", "channel_name"):
        try:
            value = channel[key]
            if value:
                return str(value)
        except Exception:
            pass

        try:
            value = channel.get_property(key)
            if value:
                return str(value)
        except Exception:
            pass

    return "unknown"


def _safe_suffix(value: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip())
    s = s.strip(".-_")
    return s[:32] or "channel"


def _safe_username(value: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip())
    s = s.strip(".-_")
    return s[:64] or "martine-voice"


def _is_martine_or_probe_user(name: str, base_username: str) -> bool:
    n = str(name or "").strip().lower()
    base = str(base_username or "martine-voice").strip().lower()
    return (
        not n
        or n == "unknown"
        or n == "takctl-mumble-dump"
        or n == base
        or n.startswith(base + "-")
        or n.startswith("martine-voice")
        or n.startswith("takctl-mumble")
    )
