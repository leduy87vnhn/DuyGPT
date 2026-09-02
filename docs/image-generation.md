# Image Generation

Image generation is optional. Keep it disabled when chat speed matters because a local diffusion backend keeps a model in VRAM and can make the chat model offload to system RAM.

## Current Status

The current `.env` is configured with:

```env
IMAGE_PROVIDER=disabled
```

DuyGPT still runs normally on port `8383`.

## Local Backend On 8384

This machine has a lightweight SD WebUI-compatible backend installed at:

```text
/home/duy/Projects/image-backend
```

It exposes:

```http
POST http://127.0.0.1:8384/sdapi/v1/txt2img
```

## Enable

Start the backend:

```bash
cd /home/duy/Projects/image-backend
setsid .venv/bin/python -u sd_api_server.py >> image-backend.log 2>&1 < /dev/null &
```

Edit `.env`:

```env
IMAGE_PROVIDER=sdwebui
SDWEBUI_URL=http://127.0.0.1:8384
IMAGE_PROMPT_REFINE=1
SDWEBUI_WIDTH=512
SDWEBUI_HEIGHT=512
SDWEBUI_STEPS=4
SDWEBUI_CFG_SCALE=0
SDWEBUI_NEGATIVE_PROMPT=blurry, low quality, distorted, deformed, bad anatomy, watermark, logo, random text
```

Restart DuyGPT.

## Disable

Stop the backend:

```bash
pkill -f sd_api_server.py
```

Edit `.env`:

```env
IMAGE_PROVIDER=disabled
```

Restart DuyGPT.

## Web Usage

The web composer has an image button next to the microphone button. Type a prompt and click the image button, or send a message that starts with `/image`.

Generated files are saved under:

```text
web/generated/
```

## OpenAI Image API Option

```env
IMAGE_PROVIDER=openai
OPENAI_IMAGE_API_KEY=sk-...
OPENAI_IMAGE_MODEL=gpt-image-2
IMAGE_SIZE=1024x1024
IMAGE_QUALITY=medium
```
