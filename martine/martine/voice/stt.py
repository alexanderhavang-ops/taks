from __future__ import annotations

import os
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import ConfigError, VoiceConfig
from .models import AudioSegment


LOCAL_MODEL_DIR_BY_NAME = {
    "small": Path("/opt/tak/tools/martine/state/models/faster-whisper-small"),
    "large-v3": Path("/opt/tak/tools/martine/state/models/faster-whisper-large-v3"),
}

WHISPER_PROMPT_CANDIDATES = [
    Path("/opt/tak/tools/martine/conf.d/whisper_prompt.sv.txt"),
    Path("/opt/taks/martine/confmeta/whisper_prompt.sv.txt"),
]


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str
    duration_ms: int


class FasterWhisperTranscriber:
    def __init__(self, cfg: VoiceConfig) -> None:
        self.cfg = cfg
        self._model = None
        self._initial_prompt: Optional[str] = None
        self._initial_prompt_loaded = False

    def transcribe_segment(self, segment: AudioSegment) -> TranscriptionResult:
        self._validate_segment(segment)

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            self._write_wav(tmp_path, segment)
            text = self._transcribe_wav(tmp_path)
            return TranscriptionResult(
                text=text,
                language=self.cfg.language,
                duration_ms=segment.duration_ms,
            )
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _transcribe_wav(self, wav_path: Path) -> str:
        model = self._get_model()

        segments, _info = model.transcribe(
            str(wav_path),
            language=self.cfg.language,
            task=self.cfg.task,
            initial_prompt=self._load_initial_prompt(),
            condition_on_previous_text=False,
            beam_size=1,
            vad_filter=False,
            word_timestamps=False,
        )

        texts: list[str] = []
        for seg in segments:
            t = str(getattr(seg, "text", "") or "").strip()
            if t:
                texts.append(t)

        return _normalize_text(" ".join(texts))

    def _load_initial_prompt(self) -> str | None:
        if self._initial_prompt_loaded:
            return self._initial_prompt

        self._initial_prompt_loaded = True

        for path in WHISPER_PROMPT_CANDIDATES:
            try:
                text = path.read_text(encoding="utf-8").strip()
            except FileNotFoundError:
                continue
            except OSError:
                continue

            text = _normalize_prompt(text)
            if text:
                self._initial_prompt = text
                return self._initial_prompt

        self._initial_prompt = None
        return None

    def _get_model(self):
        if self._model is not None:
            return self._model

        try:
            from faster_whisper import WhisperModel
        except Exception as e:
            raise ConfigError(
                "faster-whisper is not available in the Martine runtime environment"
            ) from e

        model_ref = _resolve_local_model_ref(self.cfg.model)
        device, compute_type = _pick_runtime_device()

        self._model = WhisperModel(
            model_ref,
            device=device,
            compute_type=compute_type,
            local_files_only=True,
            num_workers=self.cfg.inter_threads,
            cpu_threads=self.cfg.intra_threads,
        )
        return self._model

    @staticmethod
    def _write_wav(path: Path, segment: AudioSegment) -> None:
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(segment.channels)
            wf.setsampwidth(segment.sample_width_bytes)
            wf.setframerate(segment.sample_rate_hz)
            wf.writeframes(segment.pcm_s16le)

    @staticmethod
    def _validate_segment(segment: AudioSegment) -> None:
        if not segment.pcm_s16le:
            raise ValueError("AudioSegment.pcm_s16le is empty")
        if segment.sample_rate_hz <= 0:
            raise ValueError("AudioSegment.sample_rate_hz must be > 0")
        if segment.sample_width_bytes <= 0:
            raise ValueError("AudioSegment.sample_width_bytes must be > 0")
        if segment.channels <= 0:
            raise ValueError("AudioSegment.channels must be > 0")


def _resolve_local_model_ref(model_name: str) -> str:
    path = LOCAL_MODEL_DIR_BY_NAME.get(model_name)
    if path is None:
        allowed = ", ".join(sorted(LOCAL_MODEL_DIR_BY_NAME))
        raise ConfigError(
            f"Unsupported local faster-whisper model '{model_name}', expected one of: {allowed}"
        )

    if not path.is_dir():
        raise ConfigError(
            f"Missing local faster-whisper model directory: {path} "
            f"(run tak-installer apply to prefetch it)"
        )

    return str(path)


def _pick_runtime_device() -> tuple[str, str]:
    if _looks_like_cuda_available():
        return ("cuda", "float16")
    return ("cpu", "int8")


def _looks_like_cuda_available() -> bool:
    cuda_visible = os.environ.get("CUDA_VISIBLE_DEVICES", "").strip()
    if cuda_visible and cuda_visible not in {"-1", "none", "None"}:
        return True

    return Path("/dev/nvidiactl").exists() or Path("/dev/nvidia0").exists()


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _normalize_prompt(value: str) -> str:
    lines: list[str] = []
    for raw in str(value or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#") or line.startswith(";"):
            continue
        lines.append(line)
    return "\n".join(lines)
