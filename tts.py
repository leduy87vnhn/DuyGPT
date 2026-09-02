"""Server-side text-to-speech (edge-tts), for clients that can't do their own.

Raspberry Pi speaker devices are expected to do TTS locally (espeak or
edge-tts on-device, see docs/raspberry-pi-speaker.md) so DuyGPT only needs to
return text. This module exists for anything that can't: a browser-based test
client, a device without local TTS, or a quick way to sanity-check the voice
pipeline end-to-end. Needs internet (calls Microsoft's Edge TTS service) --
not part of the on-prem inference path, purely a convenience.
"""
import asyncio
import os
import tempfile

import edge_tts

DEFAULT_VOICE = "vi-VN-HoaiMyNeural"


def default_voice():
    return os.getenv("EDGE_TTS_VOICE", DEFAULT_VOICE).strip() or DEFAULT_VOICE


async def _synthesize_async(text, voice):
    communicate = edge_tts.Communicate(text, voice)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        path = tmp.name
    try:
        await communicate.save(path)
        with open(path, "rb") as f:
            return f.read()
    finally:
        os.remove(path)


def synthesize(text, voice=None):
    """Returns MP3 bytes for the given text."""
    text = (text or "").strip()
    if not text:
        raise ValueError("text must not be empty")
    return asyncio.run(_synthesize_async(text, voice or default_voice()))
