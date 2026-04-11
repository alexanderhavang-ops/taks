from __future__ import annotations

import logging
import signal
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone

from .config import ConfigError, VoiceConfig, load_voice_config
from .mumble_ingest import MumbleIngest
from .segmenter import Segmenter
from .stt import FasterWhisperTranscriber
from .transcript_store import TranscriptStore


LOG = logging.getLogger("martine.voice")


class _StopRequested(SystemExit):
    pass


def main() -> int:
    try:
        cfg = load_voice_config()
    except ConfigError as e:
        _setup_logging("INFO")
        LOG.error("voice config error: %s", e)
        return 2

    _setup_logging(cfg.log_level)
    _install_signal_handlers()

    if not cfg.enabled:
        LOG.info("martine voice disabled in config")
        return 0

    ingest: MumbleIngest | None = None

    try:
        store = TranscriptStore(cfg)
        transcriber = FasterWhisperTranscriber(cfg)
        ingest = MumbleIngest(cfg)
        segmenter = Segmenter(cfg)
    except Exception as e:
        LOG.exception("failed to initialize martine voice runtime: %s", e)
        return 3

    _log_startup(cfg, store.run_id)

    try:
        ingest.start()
        _run_forever(cfg, store, transcriber, ingest, segmenter)
    except _StopRequested:
        LOG.info("stop requested, shutting down")
        return 0
    except KeyboardInterrupt:
        LOG.info("keyboard interrupt, shutting down")
        return 0
    except Exception as e:
        LOG.exception("fatal martine voice error: %s", e)
        return 4
    finally:
        if ingest is not None:
            try:
                ingest.stop()
            except Exception:
                LOG.exception("failed to stop mumble ingest cleanly")


def _run_forever(
    cfg: VoiceConfig,
    store: TranscriptStore,
    transcriber: FasterWhisperTranscriber,
    ingest: MumbleIngest,
    segmenter: Segmenter,
) -> None:
    LOG.info("voice runtime is up; waiting for mumble audio on channel=%s", cfg.channel)

    last_idle_flush = time.monotonic()

    while True:
        chunk = ingest.poll(timeout=0.25)
        if chunk is not None:
            segments = segmenter.push_chunk(chunk)
            _process_segments(store, transcriber, segments)

        now_mono = time.monotonic()
        if now_mono - last_idle_flush >= 0.25:
            ready = segmenter.safe_flush_ready(now=_utc_now())
            _process_segments(store, transcriber, ready)
            last_idle_flush = now_mono


def _process_segments(
    store: TranscriptStore,
    transcriber: FasterWhisperTranscriber,
    segments,
) -> None:
    for segment in segments:
        LOG.info(
            "segment ready id=%s speaker=%s channel=%s duration_ms=%d split=%s",
            segment.segment_id,
            segment.speaker,
            segment.channel,
            segment.duration_ms,
            segment.is_split_from_long_tx,
        )

        try:
            result = transcriber.transcribe_segment(segment)
        except Exception:
            LOG.exception(
                "transcription failed segment_id=%s speaker=%s channel=%s",
                segment.segment_id,
                segment.speaker,
                segment.channel,
            )
            continue

        text = (result.text or "").strip()
        if not text:
            LOG.info(
                "transcription empty segment_id=%s speaker=%s channel=%s duration_ms=%d",
                segment.segment_id,
                segment.speaker,
                segment.channel,
                segment.duration_ms,
            )
            continue

        event = store.append_transcript_for_segment(
            segment,
            text=text,
        )

        LOG.info(
            "transcript appended segment_id=%s speaker=%s channel=%s text=%r output=%s",
            event.segment_id,
            event.speaker,
            event.channel,
            event.text,
            store.paths.current_jsonl,
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _setup_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _install_signal_handlers() -> None:
    def _handler(signum, _frame):
        signame = signal.Signals(signum).name
        LOG.info("received signal %s", signame)
        raise _StopRequested()

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


def _log_startup(cfg: VoiceConfig, run_id: str) -> None:
    redacted = _redacted_cfg_dict(cfg)
    LOG.info("martine voice starting")
    LOG.info("run_id=%s", run_id)
    for key in sorted(redacted):
        LOG.info("config %s=%r", key, redacted[key])


def _redacted_cfg_dict(cfg: VoiceConfig) -> dict[str, object]:
    data = asdict(cfg)
    if "password" in data:
        data["password"] = "***redacted***"
    return data


if __name__ == "__main__":
    sys.exit(main())
