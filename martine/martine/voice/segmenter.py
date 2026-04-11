from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .config import ConfigError, VoiceConfig
from .models import AudioSegment
from .mumble_ingest import ReceivedSoundChunk


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class _ActiveSegment:
    channel: str
    speaker: str
    language: str
    started_at: datetime
    last_chunk_at: datetime
    sample_rate_hz: int
    sample_width_bytes: int
    channels: int
    pcm_parts: list[bytes]
    total_bytes: int
    segment_index: int = 0
    is_split_from_long_tx: bool = False


class Segmenter:
    def __init__(self, cfg: VoiceConfig) -> None:
        self.cfg = cfg
        self._active: dict[str, _ActiveSegment] = {}
        self._next_segment_counter = 1

        if cfg.segment_mode != "ptt_preferred":
            raise ConfigError(f"Unsupported segment_mode: {cfg.segment_mode}")

    def push_chunk(self, chunk: ReceivedSoundChunk) -> list[AudioSegment]:
        out: list[AudioSegment] = []

        key = self._speaker_key(chunk)
        active = self._active.get(key)

        if active is None:
            active = _ActiveSegment(
                channel=chunk.channel,
                speaker=chunk.speaker,
                language=self.cfg.language,
                started_at=chunk.ts,
                last_chunk_at=chunk.ts,
                sample_rate_hz=chunk.sample_rate_hz,
                sample_width_bytes=chunk.sample_width_bytes,
                channels=chunk.channels,
                pcm_parts=[],
                total_bytes=0,
                segment_index=0,
                is_split_from_long_tx=False,
            )
            self._active[key] = active

        active.pcm_parts.append(chunk.pcm_s16le)
        active.total_bytes += len(chunk.pcm_s16le)
        active.last_chunk_at = chunk.ts

        current_duration_ms = _pcm_duration_ms(
            num_bytes=active.total_bytes,
            sample_rate_hz=active.sample_rate_hz,
            sample_width_bytes=active.sample_width_bytes,
            channels=active.channels,
        )

        if current_duration_ms >= self.cfg.max_segment_ms:
            out.append(self._flush_key(key, split_from_long_tx=True))

        return out

    def flush_ready(self, now: datetime | None = None) -> list[AudioSegment]:
        now = now or _utc_now()
        out: list[AudioSegment] = []

        for key, active in list(self._active.items()):
            idle_ms = int((now - active.last_chunk_at).total_seconds() * 1000.0)
            if idle_ms >= self.cfg.silence_split_ms:
                out.append(self._flush_key(key, split_from_long_tx=False))

        return out

    def flush_all(self) -> list[AudioSegment]:
        out: list[AudioSegment] = []
        for key in list(self._active.keys()):
            out.append(self._flush_key(key, split_from_long_tx=False))
        return out

    def _flush_key(self, key: str, *, split_from_long_tx: bool) -> AudioSegment:
        active = self._active.pop(key)

        pcm = b"".join(active.pcm_parts)
        duration_ms = _pcm_duration_ms(
            num_bytes=len(pcm),
            sample_rate_hz=active.sample_rate_hz,
            sample_width_bytes=active.sample_width_bytes,
            channels=active.channels,
        )

        if duration_ms < self.cfg.min_segment_ms:
            # Return a tiny “empty-text-worthy” segment anyway? No.
            # Drop it silently by returning a zero-length-but-valid segment would be ugly.
            # Better to create a real segment only when it passes min length.
            raise _DroppedShortSegment()

        segment = AudioSegment(
            segment_id=self._new_segment_id(),
            channel=active.channel,
            speaker=active.speaker,
            language=active.language,
            started_at=active.started_at,
            duration_ms=duration_ms,
            segment_index=active.segment_index,
            is_split_from_long_tx=active.is_split_from_long_tx or split_from_long_tx,
            sample_rate_hz=active.sample_rate_hz,
            sample_width_bytes=active.sample_width_bytes,
            channels=active.channels,
            pcm_s16le=pcm,
        )

        if split_from_long_tx:
            continued = _ActiveSegment(
                channel=active.channel,
                speaker=active.speaker,
                language=active.language,
                started_at=active.last_chunk_at + timedelta(milliseconds=1),
                last_chunk_at=active.last_chunk_at + timedelta(milliseconds=1),
                sample_rate_hz=active.sample_rate_hz,
                sample_width_bytes=active.sample_width_bytes,
                channels=active.channels,
                pcm_parts=[],
                total_bytes=0,
                segment_index=active.segment_index + 1,
                is_split_from_long_tx=True,
            )
            self._active[key] = continued

        return segment

    def safe_flush_ready(self, now: datetime | None = None) -> list[AudioSegment]:
        now = now or _utc_now()
        out: list[AudioSegment] = []

        for key, active in list(self._active.items()):
            idle_ms = int((now - active.last_chunk_at).total_seconds() * 1000.0)
            if idle_ms < self.cfg.silence_split_ms:
                continue
            try:
                out.append(self._flush_key(key, split_from_long_tx=False))
            except _DroppedShortSegment:
                self._active.pop(key, None)

        return out

    def safe_flush_all(self) -> list[AudioSegment]:
        out: list[AudioSegment] = []
        for key in list(self._active.keys()):
            try:
                out.append(self._flush_key(key, split_from_long_tx=False))
            except _DroppedShortSegment:
                self._active.pop(key, None)
        return out

    @staticmethod
    def _speaker_key(chunk: ReceivedSoundChunk) -> str:
        return f"{chunk.channel}\x1f{chunk.session}\x1f{chunk.speaker}"

    def _new_segment_id(self) -> str:
        ts = _utc_now().strftime("%Y%m%d-%H%M%S")
        n = self._next_segment_counter
        self._next_segment_counter += 1
        return f"{ts}-{n:04d}"


class _DroppedShortSegment(Exception):
    pass


def _pcm_duration_ms(
    *,
    num_bytes: int,
    sample_rate_hz: int,
    sample_width_bytes: int,
    channels: int,
) -> int:
    bytes_per_second = sample_rate_hz * sample_width_bytes * channels
    if bytes_per_second <= 0:
        return 0
    return int((num_bytes / bytes_per_second) * 1000.0)
