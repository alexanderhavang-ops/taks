from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class AudioSegment:
    segment_id: str
    channel: str
    speaker: str
    language: str

    started_at: datetime
    duration_ms: int
    segment_index: int = 0
    is_split_from_long_tx: bool = False

    sample_rate_hz: int = 16000
    sample_width_bytes: int = 2
    channels: int = 1
    pcm_s16le: bytes = b""


@dataclass(frozen=True)
class TranscriptEvent:
    ts: datetime
    channel: str
    speaker: str
    language: str

    segment_id: str
    segment_index: int
    is_split_from_long_tx: bool
    duration_ms: int

    text: str
    audio_path: str | None = None

    def to_json_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "ts": isoformat_z(self.ts),
            "channel": self.channel,
            "speaker": self.speaker,
            "language": self.language,
            "segment_id": self.segment_id,
            "segment_index": self.segment_index,
            "is_split_from_long_tx": self.is_split_from_long_tx,
            "duration_ms": self.duration_ms,
            "text": self.text,
        }
        if self.audio_path:
            data["audio_path"] = self.audio_path
        return data


def transcript_event_from_segment(
    segment: AudioSegment,
    *,
    text: str,
    ts: datetime | None = None,
    audio_path: str | Path | None = None,
) -> TranscriptEvent:
    audio_path_s = None if audio_path is None else str(audio_path)
    return TranscriptEvent(
        ts=ts or utc_now(),
        channel=segment.channel,
        speaker=segment.speaker,
        language=segment.language,
        segment_id=segment.segment_id,
        segment_index=segment.segment_index,
        is_split_from_long_tx=segment.is_split_from_long_tx,
        duration_ms=segment.duration_ms,
        text=text,
        audio_path=audio_path_s,
    )
