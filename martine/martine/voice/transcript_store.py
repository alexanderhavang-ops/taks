from __future__ import annotations

import json
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import VoiceConfig
from .models import AudioSegment, TranscriptEvent, transcript_event_from_segment


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _run_id_now() -> str:
    return _utc_now().strftime("%Y%m%d-%H%M%S")


@dataclass(frozen=True)
class TranscriptStorePaths:
    state_root: Path
    transcripts_dir: Path
    runs_dir: Path
    current_jsonl: Path
    run_dir: Path
    run_events_jsonl: Path
    run_audio_dir: Path


class TranscriptStore:
    def __init__(self, cfg: VoiceConfig) -> None:
        self.cfg = cfg
        self.paths = self._build_paths(cfg)
        self._ensure_dirs()

    @staticmethod
    def _build_paths(cfg: VoiceConfig) -> TranscriptStorePaths:
        run_id = _run_id_now()
        run_dir = cfg.runs_dir / run_id
        return TranscriptStorePaths(
            state_root=cfg.state_root,
            transcripts_dir=cfg.transcripts_dir,
            runs_dir=cfg.runs_dir,
            current_jsonl=cfg.current_jsonl,
            run_dir=run_dir,
            run_events_jsonl=run_dir / "events.jsonl",
            run_audio_dir=run_dir / "audio",
        )

    def _ensure_dirs(self) -> None:
        self.paths.state_root.mkdir(parents=True, exist_ok=True)
        self.paths.transcripts_dir.mkdir(parents=True, exist_ok=True)
        self.paths.runs_dir.mkdir(parents=True, exist_ok=True)
        self.paths.run_dir.mkdir(parents=True, exist_ok=True)
        self.paths.run_audio_dir.mkdir(parents=True, exist_ok=True)

        if not self.paths.current_jsonl.exists():
            self.paths.current_jsonl.touch()
        if not self.paths.run_events_jsonl.exists():
            self.paths.run_events_jsonl.touch()

    @property
    def run_id(self) -> str:
        return self.paths.run_dir.name

    def append_event(self, event: TranscriptEvent) -> None:
        line = json.dumps(event.to_json_dict(), ensure_ascii=False)
        self._append_line(self.paths.current_jsonl, line)
        self._append_line(self.paths.run_events_jsonl, line)

    def append_transcript_for_segment(
        self,
        segment: AudioSegment,
        *,
        text: str,
        save_debug_wav: bool | None = None,
    ) -> TranscriptEvent:
        audio_relpath: str | None = None

        should_save_wav = self.cfg.save_debug_wav if save_debug_wav is None else save_debug_wav
        if should_save_wav:
            wav_path = self.save_debug_wav(segment)
            audio_relpath = str(wav_path.relative_to(self.paths.state_root))

        event = transcript_event_from_segment(
            segment,
            text=text,
            audio_path=audio_relpath,
        )
        self.append_event(event)
        return event

    def save_debug_wav(self, segment: AudioSegment) -> Path:
        filename = self._audio_filename(segment)
        wav_path = self.paths.run_audio_dir / filename

        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(segment.channels)
            wf.setsampwidth(segment.sample_width_bytes)
            wf.setframerate(segment.sample_rate_hz)
            wf.writeframes(segment.pcm_s16le)

        return wav_path

    @staticmethod
    def _append_line(path: Path, line: str) -> None:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.write("\n")

    @staticmethod
    def _audio_filename(segment: AudioSegment) -> str:
        safe_speaker = _safe_name(segment.speaker)
        safe_channel = _safe_name(segment.channel)
        return f"{segment.segment_id}-{safe_channel}-{safe_speaker}.wav"


def _safe_name(value: str) -> str:
    chars: list[str] = []
    for ch in value.strip():
        if ch.isalnum() or ch in ("-", "_", "."):
            chars.append(ch)
        else:
            chars.append("_")
    s = "".join(chars).strip("._")
    return s or "unknown"
