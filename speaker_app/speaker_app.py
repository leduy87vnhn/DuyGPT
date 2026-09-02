#!/usr/bin/env python3
"""Raspberry Pi edge speaker for DuyGPT."""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unicodedata
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path

import requests


APP_DIR = Path(__file__).resolve().parent


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def env_int(name: str, default: int) -> int:
    value = env(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    value = env(name)
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


def normalize_vietnamese(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    without_marks = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return " ".join(without_marks.replace("đ", "d").split())


def is_hotword(text: str) -> bool:
    normalized = normalize_vietnamese(text)
    phrases = [p.strip() for p in env("HOTWORD_PHRASES", "loa oi,alo loa oi").split(",")]
    return any(phrase and normalize_vietnamese(phrase) in normalized for phrase in phrases)


def run_command(command: list[str], timeout: int | None = None) -> None:
    subprocess.run(command, check=True, timeout=timeout)


def audio_device_args(flag: str, device: str) -> list[str]:
    return [flag, device] if device else []


def record_wav(path: Path, seconds: int) -> None:
    capture_device = env("CAPTURE_DEVICE", "default")
    rate = env_int("AUDIO_RATE", 16000)
    channels = env_int("AUDIO_CHANNELS", 1)
    command = [
        "arecord",
        "-q",
        *audio_device_args("-D", capture_device),
        "-f",
        "S16_LE",
        "-r",
        str(rate),
        "-c",
        str(channels),
        "-d",
        str(seconds),
        str(path),
    ]
    run_command(command, timeout=seconds + 5)


def play_audio(path: Path) -> None:
    playback_device = env("PLAYBACK_DEVICE", "default")
    suffix = path.suffix.lower()
    if suffix == ".mp3":
        command = ["mpg123", "-q", *audio_device_args("-a", playback_device), str(path)]
    else:
        command = ["aplay", "-q", *audio_device_args("-D", playback_device), str(path)]
    run_command(command)


def speak_espeak(text: str) -> None:
    voice = env("ESPEAK_VOICE", "vi")
    speed = env("ESPEAK_SPEED", "150")
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = Path(tmp.name)
    try:
        run_command(["espeak-ng", "-v", voice, "-s", speed, "-w", str(wav_path), text])
        play_audio(wav_path)
    finally:
        wav_path.unlink(missing_ok=True)


def speak_edge_tts(text: str) -> None:
    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError("edge-tts is not installed. Run: pip install edge-tts") from exc

    import asyncio

    voice = env("EDGE_TTS_VOICE", "vi-VN-HoaiMyNeural")

    async def save_mp3(path: Path) -> None:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(path))

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        mp3_path = Path(tmp.name)
    try:
        asyncio.run(save_mp3(mp3_path))
        play_audio(mp3_path)
    finally:
        mp3_path.unlink(missing_ok=True)


def speak(text: str) -> None:
    if not text.strip():
        return
    log(f"TTS: {text}")
    mode = env("TTS_MODE", "espeak").lower()
    if mode == "edge":
        speak_edge_tts(text)
    else:
        speak_espeak(text)


def server_headers() -> dict[str, str]:
    key = env("DEVICE_API_KEY")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-Device-Key"] = key
    return headers


def server_url(path: str) -> str:
    base = env("DUYGPT_URL", "http://127.0.0.1:8383").rstrip("/")
    return f"{base}{path}"


def post_json(path: str, payload: dict) -> dict:
    timeout = env_int("SERVER_TIMEOUT_SECONDS", 120)
    response = requests.post(server_url(path), headers=server_headers(), json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def server_transcribe(wav_path: Path) -> str:
    audio_base64 = base64.b64encode(wav_path.read_bytes()).decode("ascii")
    data = post_json(
        "/api/voice/transcribe",
        {
            "audio_base64": audio_base64,
            "filename": wav_path.name,
        },
    )
    return str(data.get("text", "")).strip()


_VOSK_MODEL = None


def local_transcribe(wav_path: Path) -> str:
    global _VOSK_MODEL
    try:
        from vosk import KaldiRecognizer, Model
    except ImportError as exc:
        raise RuntimeError("vosk is not installed. Run: pip install vosk") from exc

    model_path = env("VOSK_MODEL_PATH")
    if not model_path:
        raise RuntimeError("VOSK_MODEL_PATH is required when STT_MODE=local")
    if _VOSK_MODEL is None:
        log(f"Loading Vosk model: {model_path}")
        _VOSK_MODEL = Model(model_path)

    with wave.open(str(wav_path), "rb") as audio:
        recognizer = KaldiRecognizer(_VOSK_MODEL, audio.getframerate())
        while True:
            data = audio.readframes(4000)
            if not data:
                break
            recognizer.AcceptWaveform(data)
        result = json.loads(recognizer.FinalResult())
    return str(result.get("text", "")).strip()


def transcribe(wav_path: Path) -> str:
    mode = env("STT_MODE", "server").lower()
    if mode == "local":
        return local_transcribe(wav_path)
    return server_transcribe(wav_path)


def chat(session_id: str, text: str) -> str:
    data = post_json(
        "/api/voice/chat",
        {
            "session_id": session_id,
            "text": text,
        },
    )
    return str(data.get("text", "")).strip()


def make_session_id() -> str:
    configured = env("SESSION_ID")
    if configured:
        return configured
    host = socket.gethostname() or "raspberrypi"
    boot_marker = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{host}-{boot_marker}-{uuid.uuid4().hex[:6]}"


def capture_and_transcribe(seconds: int, label: str) -> str:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = Path(tmp.name)
    try:
        log(f"Recording {label} for {seconds}s")
        record_wav(wav_path, seconds)
        text = transcribe(wav_path)
        log(f"STT {label}: {text or '(empty)'}")
        return text
    finally:
        wav_path.unlink(missing_ok=True)


def main_loop() -> None:
    session_id = make_session_id()
    hotword_seconds = env_int("HOTWORD_CHUNK_SECONDS", 2)
    question_seconds = env_int("QUESTION_SECONDS", 7)
    idle_seconds = env_float("WAKE_POLL_SECONDS", 0.2)
    ready_reply = env("READY_REPLY", "Có đây")
    unclear_reply = env("UNCLEAR_REPLY", "Mình chưa nghe rõ, con nói lại nhé.")
    error_reply = env("ERROR_REPLY", "Mình đang gặp lỗi kết nối, thử lại sau nhé.")

    log(f"Session: {session_id}")
    log(f"STT_MODE={env('STT_MODE', 'server')} TTS_MODE={env('TTS_MODE', 'espeak')}")
    log(f"Waiting for hotword: {env('HOTWORD_PHRASES', 'loa oi,alo loa oi')}")

    while True:
        try:
            hotword_text = capture_and_transcribe(hotword_seconds, "hotword")
            if not is_hotword(hotword_text):
                time.sleep(idle_seconds)
                continue

            log("Hotword detected")
            speak(ready_reply)
            question = capture_and_transcribe(question_seconds, "question")
            if not question:
                speak(unclear_reply)
                continue

            answer = chat(session_id, question)
            if answer:
                speak(answer)
            else:
                speak(unclear_reply)
        except KeyboardInterrupt:
            log("Stopping")
            return
        except Exception as exc:
            log(f"ERROR: {exc}")
            try:
                speak(error_reply)
            except Exception:
                pass
            time.sleep(2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DuyGPT Raspberry Pi speaker edge app")
    parser.add_argument("--env-file", default=str(APP_DIR / ".env"), help="Path to speaker .env file")
    parser.add_argument("--say", help="Speak one text and exit")
    parser.add_argument("--record-test", type=int, metavar="SECONDS", help="Record and transcribe once")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_env(Path(args.env_file))

    if args.say:
        speak(args.say)
        return 0

    if args.record_test:
        text = capture_and_transcribe(args.record_test, "test")
        print(text)
        return 0

    main_loop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
