from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class VoiceConfigPaths:
    martine_voice_conf: Path = Path("/opt/tak/tools/takctl/conf.d/martine_voice.conf")
    core_conf: Path = Path("/opt/tak/tools/takctl/conf.d/core.conf")
    murmur_conf: Path = Path("/opt/tak/tools/takctl/secrets.d/murmur.conf")
    state_root: Path = Path("/opt/tak/tools/martine/state/voice_transcribe")


@dataclass(frozen=True)
class VoiceConfig:
    enabled: bool

    host: str
    port: int
    channel: str
    username: str
    password: str

    language: str
    provider: str
    model: str
    task: str
    inter_threads: int
    intra_threads: int

    segment_mode: str
    max_segment_ms: int
    silence_split_ms: int
    min_segment_ms: int
    max_buffer_ms: int

    emit_to_file: bool
    emit_cot_chat: bool
    output_format: str

    save_debug_wav: bool
    debug_wav_max_per_hour: int
    log_level: str

    state_root: Path
    transcripts_dir: Path
    runs_dir: Path
    current_jsonl: Path


def load_voice_config(paths: VoiceConfigPaths | None = None) -> VoiceConfig:
    paths = paths or VoiceConfigPaths()

    voice = _read_kv_required(paths.martine_voice_conf)
    password = _read_kv_optional(paths.murmur_conf).get("serverpassword", "").strip()
    if not password:
        raise ConfigError(
            f"Missing required key 'serverpassword' in {paths.murmur_conf}"
        )

    core = _read_kv_optional(paths.core_conf)
    language = _normalize_language(core.get("language", "sv"), source=str(paths.core_conf))

    host = _get_str(voice, "host", "127.0.0.1")
    port = _get_int(voice, "port", 64738, minimum=1)
    channel = _get_str(voice, "channel", "TQ")
    username = _get_str(voice, "username", "martine-voice")

    provider = _get_str(voice, "provider", "faster_whisper")
    model = _get_str(voice, "model", "small")
    task = _get_str(voice, "task", "transcribe")
    inter_threads = _get_int(voice, "inter_threads", 1, minimum=1)
    intra_threads = _get_int(voice, "intra_threads", 1, minimum=1)

    segment_mode = _get_str(voice, "segment_mode", "ptt_preferred")
    max_segment_ms = _get_int(voice, "max_segment_ms", 30000, minimum=1)
    silence_split_ms = _get_int(voice, "silence_split_ms", 1200, minimum=0)
    min_segment_ms = _get_int(voice, "min_segment_ms", 400, minimum=0)
    max_buffer_ms = _get_int(voice, "max_buffer_ms", 45000, minimum=1)

    emit_to_file = _get_bool(voice, "emit_to_file", True)
    emit_cot_chat = _get_bool(voice, "emit_cot_chat", False)
    output_format = _get_str(voice, "output_format", "jsonl")

    save_debug_wav = _get_bool(voice, "save_debug_wav", True)
    debug_wav_max_per_hour = _get_int(voice, "debug_wav_max_per_hour", 60, minimum=0)
    log_level = _get_str(voice, "log_level", "INFO").upper()

    _validate_choice("provider", provider, {"faster_whisper"})
    _validate_choice("task", task, {"transcribe"})
    _validate_choice("segment_mode", segment_mode, {"ptt_preferred"})
    _validate_choice("output_format", output_format, {"jsonl"})
    _validate_choice("log_level", log_level, {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})

    state_root = paths.state_root
    transcripts_dir = state_root / "transcripts"
    runs_dir = state_root / "runs"
    current_jsonl = transcripts_dir / "current.jsonl"

    return VoiceConfig(
        enabled=_get_bool(voice, "enabled", True),

        host=host,
        port=port,
        channel=channel,
        username=username,
        password=password,

        language=language,
        provider=provider,
        model=model,
        task=task,
        inter_threads=inter_threads,
        intra_threads=intra_threads,

        segment_mode=segment_mode,
        max_segment_ms=max_segment_ms,
        silence_split_ms=silence_split_ms,
        min_segment_ms=min_segment_ms,
        max_buffer_ms=max_buffer_ms,

        emit_to_file=emit_to_file,
        emit_cot_chat=emit_cot_chat,
        output_format=output_format,

        save_debug_wav=save_debug_wav,
        debug_wav_max_per_hour=debug_wav_max_per_hour,
        log_level=log_level,

        state_root=state_root,
        transcripts_dir=transcripts_dir,
        runs_dir=runs_dir,
        current_jsonl=current_jsonl,
    )


def _read_kv_required(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ConfigError(f"Required config file missing: {path}")
    return _read_kv_file(path)


def _read_kv_optional(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    return _read_kv_file(path)


def _read_kv_file(path: Path) -> dict[str, str]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"Failed reading {path}: {e}") from e

    out: dict[str, str] = {}
    for lineno, raw_line in enumerate(raw.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        if "=" not in line:
            raise ConfigError(
                f"Invalid config line in {path}:{lineno}: expected key=value"
            )

        k, v = line.split("=", 1)
        key = k.strip().lower()
        value = v.strip()

        if not key:
            raise ConfigError(f"Empty key in {path}:{lineno}")

        out[key] = value

    return out


def _normalize_language(value: str, source: str) -> str:
    v = value.strip().lower().replace("-", "_")

    mapping = {
        "sv": "sv",
        "sv_se": "sv",
        "swedish": "sv",
        "en": "en",
        "en_us": "en",
        "en_gb": "en",
        "english": "en",
    }

    if v in mapping:
        return mapping[v]

    raise ConfigError(
        f"Unsupported martine voice language '{value}' from {source}; expected sv or en"
    )


def _get_str(values: dict[str, str], key: str, default: str) -> str:
    value = values.get(key.lower(), default).strip()
    if not value:
        raise ConfigError(f"Key '{key}' may not be empty")
    return value


def _get_int(
    values: dict[str, str],
    key: str,
    default: int,
    *,
    minimum: int | None = None,
) -> int:
    raw = values.get(key.lower(), str(default)).strip()
    try:
        value = int(raw)
    except ValueError as e:
        raise ConfigError(f"Key '{key}' must be an integer, got {raw!r}") from e

    if minimum is not None and value < minimum:
        raise ConfigError(f"Key '{key}' must be >= {minimum}, got {value}")
    return value


def _get_bool(values: dict[str, str], key: str, default: bool) -> bool:
    raw = values.get(key.lower())
    if raw is None:
        return default

    v = raw.strip().lower()
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False

    raise ConfigError(f"Key '{key}' must be boolean, got {raw!r}")


def _validate_choice(name: str, value: str, allowed: set[str]) -> None:
    if value not in allowed:
        allowed_s = ", ".join(sorted(allowed))
        raise ConfigError(f"Unsupported {name} '{value}', expected one of: {allowed_s}")
