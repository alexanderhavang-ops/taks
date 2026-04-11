from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from .config import ConfigError, VoiceConfig

LOG = logging.getLogger("martine.voice.mumble")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
        self._queue: queue.Queue[ReceivedSoundChunk] = queue.Queue(maxsize=4096)
        self._lock = threading.Lock()
        self._started = False

    def start(self) -> None:
        with self._lock:
            if self._started:
                return

            mumble_mod, cbk_sound_received = _import_pymumble()

            mumble = mumble_mod.Mumble(
                self.cfg.host,
                self.cfg.username,
                password=self.cfg.password,
                port=self.cfg.port,
            )
            mumble.callbacks.set_callback(cbk_sound_received, self._on_sound_received)
            mumble.set_receive_sound(True)
            mumble.start()
            mumble.is_ready()

            self._mumble = mumble
            self._move_to_target_channel(self.cfg.channel)

            self._started = True
            LOG.info(
                "mumble ingest connected host=%s port=%s channel=%s username=%s",
                self.cfg.host,
                self.cfg.port,
                self.cfg.channel,
                self.cfg.username,
            )

    def stop(self) -> None:
        with self._lock:
            mumble = self._mumble
            self._mumble = None
            self._started = False

        if mumble is not None:
            try:
                mumble.stop()
            except Exception:
                LOG.exception("mumble stop failed")

    def poll(self, timeout: float = 0.5) -> ReceivedSoundChunk | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _move_to_target_channel(self, channel_name: str) -> None:
        assert self._mumble is not None

        deadline = time.time() + 10.0
        chan = None
        while time.time() < deadline:
            chan = self._mumble.channels.find_by_name(channel_name)
            if chan is not None:
                break
            time.sleep(0.1)

        if chan is None:
            raise ConfigError(f"Mumble channel not found: {channel_name}")

        chan.move_in()

        # Give pymumble a brief moment to update local state after move.
        time.sleep(0.2)

        try:
            current = self._mumble.my_channel()
            current_name = _channel_name(current)
        except Exception:
            current_name = "unknown"

        LOG.info("moved to mumble channel target=%s current=%s", channel_name, current_name)

    def _on_sound_received(self, user, soundchunk) -> None:
        # Keep this callback very short. It runs on pymumble's callback thread.
        try:
            if not self._is_same_channel(user):
                return

            speaker = _user_name(user)
            session = _user_session(user)
            channel = self.cfg.channel

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

    def _is_same_channel(self, user) -> bool:
        if self._mumble is None:
            return False

        try:
            my_channel = self._mumble.my_channel()
            my_channel_id = _channel_id(my_channel)
            user_channel_id = _user_channel_id(user)
            return (
                my_channel_id is not None
                and user_channel_id is not None
                and my_channel_id == user_channel_id
            )
        except Exception:
            return False


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

    for key in ("name",):
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
