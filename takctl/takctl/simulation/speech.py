"""Bounded local audio generation and Mumble identity binding."""

import hashlib
from pathlib import Path
import re
import subprocess
import tempfile

from .transports import opus_clip


def voice_identity(speaker, user_id, allowed_uids):
    if not isinstance(speaker, str) or len(speaker) > 192 or type(user_id) is not int:
        return None
    callsign = speaker.strip().split("---", 1)[0].split("/", 1)[0].strip()
    if not callsign or len(callsign) > 64:
        return None
    matches = []
    for uid in allowed_uids:
        digest = hashlib.sha256(f"{callsign.upper()}|{uid}|{speaker}".encode()).digest()
        if user_id == 100000 + int.from_bytes(digest[:4], "big") % 2000000000:
            matches.append(uid)
    return (matches[0], callsign) if len(matches) == 1 else None


def spoken_target(text, actors):
    if not isinstance(text, str) or len(text) > 1000:
        return None
    matches = []
    for actor in actors:
        label = r"[ -]?".join(re.escape(part) for part in actor["callsign"].split("-"))
        match = re.match(r"^\s*" + label + r"(?:\s*[,.:;—-]\s*|\s+)(\S.*)$", text, re.IGNORECASE)
        if match and 0 < len(match[1].strip()) <= 400:
            matches.append((actor, match[1].strip()))
    return matches[0] if len(matches) == 1 else None


def speech_frames(text, language):
    if language not in ("en", "sv") or not isinstance(text, str) or not 1 <= len(text.strip()) <= 160:
        raise ValueError("Speech requires 1–160 characters and a supported node language")
    notice = "Synthetic voice. " if language == "en" else "Syntetisk röst. "
    try:
        with tempfile.TemporaryDirectory(prefix="taks-speech-") as directory:
            raw = Path(directory) / "speech.wav"
            wav = Path(directory) / "mumble.wav"
            subprocess.run(
                ["espeak-ng", "-v", language, "-s", "175", "-w", str(raw), "--stdin"],
                input=(notice + text).encode(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=3, check=True,
            )
            subprocess.run(
                ["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(raw), "-t", "10",
                 "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(wav)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4, check=True,
            )
            return opus_clip(wav)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("Voice synthesis unavailable") from exc
