from __future__ import annotations

import io
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
LOCAL_MODEL_EXTRA_FILES = {
    "small": ("vocabulary.txt",),
    "large-v3": ("vocabulary.json", "preprocessor_config.json"),
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
            text = self._transcribe_wav(tmp_path, segment.language)
            return TranscriptionResult(
                text=text,
                language=segment.language,
                duration_ms=segment.duration_ms,
            )
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _transcribe_wav(self, wav_path: Path, language: str) -> str:
        model = self._get_model()

        segments, _info = model.transcribe(
            str(wav_path),
            language=language,
            task=self.cfg.task,
            initial_prompt=self._load_initial_prompt() if language == "sv" else None,
            condition_on_previous_text=False,
            beam_size=self.cfg.beam_size,
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

    required = ("config.json", "model.bin", "tokenizer.json", *LOCAL_MODEL_EXTRA_FILES[model_name])
    for filename in required:
        artifact = path / filename
        if not artifact.is_file() or artifact.stat().st_size == 0:
            raise ConfigError(
                f"Local faster-whisper model {model_name} is incomplete ({filename}). "
                "Prefetch the model before using local transcription."
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


class OpenAITranscriber:
    def __init__(self, client=None):
        if client is None:
            from openai import OpenAI
            from .config import _read_kv_optional

            secrets = _read_kv_optional(Path("/opt/tak/tools/martine/secrets.d/martine.conf"))
            key = os.environ.get("OPENAI_API_KEY") or secrets.get("openai_api_key")
            if not key:
                raise ConfigError("OpenAI voice transcription requires a node API key")
            client = OpenAI(api_key=key, timeout=12, max_retries=0)
        self.client = client

    def transcribe_segment(self, segment: AudioSegment) -> TranscriptionResult:
        FasterWhisperTranscriber._validate_segment(segment)
        if segment.duration_ms > 30000 or len(segment.pcm_s16le) > 3_000_000:
            raise ValueError("Voice segment exceeds transcription limit")
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(segment.channels)
            wav.setsampwidth(segment.sample_width_bytes)
            wav.setframerate(segment.sample_rate_hz)
            wav.writeframes(segment.pcm_s16le)
        response = self.client.audio.transcriptions.create(
            model="gpt-transcribe", file=("ptt.wav", buffer.getvalue(), "audio/wav"),
            extra_body={"languages": [segment.language]},
        )
        return TranscriptionResult(text=response.text, language=segment.language, duration_ms=segment.duration_ms)
