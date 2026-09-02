# Raspberry Pi Speaker Edge Device

This guide sets up a Raspberry Pi Zero 2W with ReSpeaker as a DuyGPT edge speaker.

Default flow:

1. The Pi listens for hotword `Loa ơi`.
2. The Pi says `Có đây`.
3. The Pi records the question (stops on silence or a max duration).
4. The Pi sends audio to the DuyGPT server for Whisper transcription.
5. The Pi sends text to `/api/voice/chat` with the same `session_id`.
6. The Pi receives answer text, converts it to voice, and plays it.

Steps 4-5 can be collapsed into one call: `POST /api/voice/assistant` takes the
recorded audio directly, transcribes it, and **automatically decides** whether
the utterance is for Trợ Lý Gia Đình (`home`), Trợ Lý Công Việc (`work`), or
the main ChatGPT persona (`chatgpt` fallback) before generating the reply.
See [Speaker Device API](speaker-api.md) for the full contract — this is the
recommended endpoint for a new Pi build; the rest of this guide's two-step
`/api/voice/transcribe` + `/api/voice/chat` flow still works if you want the
Pi (or another client) to control routing itself.

The code is in:

```text
speaker_app/
```

## Recommended Mode

Use server-side speech recognition first:

```env
STT_MODE=server
```

This is recommended for Raspberry Pi Zero 2W because local speech recognition can slow the Pi down.

Local mode is available:

```env
STT_MODE=local
```

but it requires a Vosk model on the Pi and is less accurate than the server Whisper setup.

## Server Requirements

On the DuyGPT machine:

```env
PORT=8383
DEVICE_API_KEY=<secret>
```

The Pi must be able to reach:

```text
http://<duygpt-lan-ip>:8383
```

Find the LAN IP of the DuyGPT machine:

```bash
hostname -I
```

Then test from another device on the same network:

```bash
curl http://<duygpt-lan-ip>:8383/api/health
```

## Copy Code To The Pi

From the DuyGPT project directory on the server:

```bash
rsync -av speaker_app/ pi@raspberrypi.local:/home/pi/speaker_app/
```

If `raspberrypi.local` does not resolve, use the Pi IP address:

```bash
rsync -av speaker_app/ pi@<pi-ip>:/home/pi/speaker_app/
```

## Install System Packages On Raspberry Pi

SSH into the Pi:

```bash
ssh pi@raspberrypi.local
```

Update packages:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip alsa-utils espeak-ng mpg123 curl
```

Check ReSpeaker audio devices:

```bash
arecord -l
aplay -l
```

Start with `default`. If recording or playback does not work, set `CAPTURE_DEVICE` and `PLAYBACK_DEVICE` in `/home/pi/speaker_app/.env`.

Common ALSA examples:

```env
CAPTURE_DEVICE=plughw:1,0
PLAYBACK_DEVICE=plughw:1,0
```

The exact card number depends on the Pi.

## Install Python Dependencies

On the Pi:

```bash
cd /home/pi/speaker_app
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

For server-side STT with offline `espeak-ng` TTS, `requests` is the only required Python package.

Optional packages:

```bash
pip install -r requirements-optional.txt
```

Install optional packages only if you want local Vosk STT or Edge TTS.

## Configure The Pi

Create config:

```bash
cd /home/pi/speaker_app
cp .env.example .env
nano .env
```

Set:

```env
DUYGPT_URL=http://<duygpt-lan-ip>:8383
DEVICE_API_KEY=<copy-from-duygpt-server-.env>
STT_MODE=server
TTS_MODE=espeak
```

Important: from the Pi, `127.0.0.1` means the Pi itself. Use the LAN IP of the DuyGPT server.

## Test Audio

Test TTS:

```bash
cd /home/pi/speaker_app
. .venv/bin/activate
python speaker_app.py --say "Có đây"
```

Test recording and speech recognition:

```bash
python speaker_app.py --record-test 5
```

Speak into the microphone during the 5 seconds. The command should print recognized text.

If recording fails, change `CAPTURE_DEVICE`.

If playback fails, change `PLAYBACK_DEVICE`.

## Run The Speaker App

```bash
cd /home/pi/speaker_app
. .venv/bin/activate
python speaker_app.py
```

Say:

```text
Loa ơi
```

The Pi should reply:

```text
Có đây
```

Then ask your question.

## Session Behavior

By default, the app creates one `session_id` each time it starts:

```text
<hostname>-<boot-time>-<random>
```

Every question during that app run uses the same `session_id`, so DuyGPT remembers previous turns in that speaker session.

If you want a fixed session id, set:

```env
SESSION_ID=living-room-speaker
```

Usually, leave `SESSION_ID` empty so each Pi app start begins a fresh conversation.

## Install As A Systemd Service

Create the service:

```bash
sudo nano /etc/systemd/system/duygpt-speaker.service
```

Paste:

```ini
[Unit]
Description=DuyGPT Raspberry Pi Speaker
After=network-online.target sound.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/speaker_app
ExecStart=/home/pi/speaker_app/.venv/bin/python /home/pi/speaker_app/speaker_app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now duygpt-speaker
```

View logs:

```bash
journalctl -u duygpt-speaker -f
```

Stop:

```bash
sudo systemctl stop duygpt-speaker
```

Start:

```bash
sudo systemctl start duygpt-speaker
```

## Option 1: Local Speech Recognition On Pi

Local STT uses Vosk.

Install dependencies:

```bash
cd /home/pi/speaker_app
. .venv/bin/activate
pip install -r requirements-optional.txt
```

Download a Vosk model that supports Vietnamese. Put it somewhere like:

```text
/home/pi/models/vosk-vi
```

Then configure:

```env
STT_MODE=local
VOSK_MODEL_PATH=/home/pi/models/vosk-vi
```

Test:

```bash
python speaker_app.py --record-test 5
```

Notes:

- Pi Zero 2W may transcribe slowly.
- Hotword detection in local mode depends on the Vosk model recognizing `Loa ơi`.
- If the local model is weak, switch back to `STT_MODE=server`.

## Option 2: Server Whisper Speech Recognition

Server mode sends WAV audio to:

```http
POST /api/voice/transcribe
```

Then sends recognized text to:

```http
POST /api/voice/chat
```

Both requests use:

```http
X-Device-Key: <DEVICE_API_KEY>
```

This mode gives better recognition and keeps the Pi lightweight.

Simpler alternative: send the recorded clip straight to `POST /api/voice/assistant`
(one call instead of two) and let the server also pick which assistant answers
(home/work/chatgpt) — see [Speaker Device API](speaker-api.md).

## Text To Speech Options

Offline and light:

```env
TTS_MODE=espeak
ESPEAK_VOICE=vi
```

Better voice, needs internet:

```env
TTS_MODE=edge
EDGE_TTS_VOICE=vi-VN-HoaiMyNeural
```

`edge` mode also needs:

```bash
sudo apt install -y mpg123
pip install -r requirements-optional.txt
```

## Troubleshooting

401 from server:

- `DEVICE_API_KEY` on the Pi is missing or wrong.
- Copy the value from the DuyGPT server `.env`.

Cannot connect to server:

- Check `DUYGPT_URL`.
- Use the DuyGPT server LAN IP, not `127.0.0.1`.
- Make sure port `8383` is reachable from the Pi.

No microphone input:

- Run `arecord -l`.
- Set `CAPTURE_DEVICE=plughw:<card>,<device>`.
- Test with `python speaker_app.py --record-test 5`.

No speaker output:

- Run `aplay -l`.
- Set `PLAYBACK_DEVICE=plughw:<card>,<device>`.
- Test with `python speaker_app.py --say "Có đây"`.

Hotword not detected:

- Speak clearly: `Loa ơi`.
- Increase `HOTWORD_CHUNK_SECONDS=3`.
- Keep `STT_MODE=server` for better Vietnamese recognition.

Responses forget context:

- Check that the app is not restarting between questions.
- Do not change `SESSION_ID` during the same session.
- The DuyGPT server maps one `session_id` to one conversation.
