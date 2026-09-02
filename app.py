#!/usr/bin/env python3
import base64
import hashlib
import json
import mimetypes
import os
import re
import secrets
import ssl
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import psycopg

import auth
import crm
import db
import home_assistant
import persona
import rag
import stt
import tts
import work_schedule


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
GENERATED_ROOT = WEB_ROOT / "generated"

CONVERSATION_MESSAGES_RE = re.compile(r"^/api/conversations/(\d+)/messages$")
ADMIN_DOCUMENT_RE = re.compile(r"^/api/admin/documents/(\d+)$")
ADMIN_PERSONA_RE = re.compile(r"^/api/admin/personas/(\d+)$")
ADMIN_PERSONA_MEMORIES_RE = re.compile(r"^/api/admin/personas/(\d+)/memories$")
ADMIN_PERSONA_MEMORY_RE = re.compile(r"^/api/admin/persona-memories/(\d+)$")
HOME_REMINDER_RE = re.compile(r"^/api/home/reminders/(\d+)$")
HOME_NOTE_RE = re.compile(r"^/api/home/notes/(\d+)$")
HOME_SHOPPING_ITEM_RE = re.compile(r"^/api/home/shopping/(\d+)$")
HOME_CALENDAR_EVENT_RE = re.compile(r"^/api/home/calendar/(\d+)$")
CRM_CUSTOMER_RE = re.compile(r"^/api/crm/customers/(\d+)$")
CRM_PRODUCT_RE = re.compile(r"^/api/crm/products/(\d+)$")
CRM_REQUIREMENT_RE = re.compile(r"^/api/crm/requirements/(\d+)$")
CRM_DOCUMENT_RE = re.compile(r"^/api/crm/documents/(\d+)$")
CRM_PROPOSAL_FINALIZE_RE = re.compile(r"^/api/crm/proposals/(\d+)/finalize$")
CRM_PROPOSAL_ACTIVE_RE = re.compile(r"^/api/crm/proposals/(\d+)/active$")
CRM_PROPOSAL_ATTACHMENTS_RE = re.compile(r"^/api/crm/proposals/(\d+)/attachments$")
CRM_PROPOSAL_ATTACHMENT_RE = re.compile(r"^/api/crm/proposals/(\d+)/attachments/(\d+)$")
CRM_PROPOSAL_RE = re.compile(r"^/api/crm/proposals/(\d+)$")
SCHEDULE_ENTRY_RE = re.compile(r"^/api/schedule/(\d+)$")
SCHEDULE_DONE_RE = re.compile(r"^/api/schedule/(\d+)/done$")
WORK_TASK_DONE_RE = re.compile(r"^/api/work/tasks/(\d+)/done$")
WORK_TASK_RE = re.compile(r"^/api/work/tasks/(\d+)$")
ADMIN_USER_RE = re.compile(r"^/api/admin/users/(\d+)$")


def load_dotenv(path):
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_dotenv(ROOT / ".env")


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def config():
    return {
        "host": os.getenv("HOST", "0.0.0.0"),
        "port": int(os.getenv("PORT", "8383")),
        "provider": os.getenv("PROVIDER", "ollama").lower(),
        "model": os.getenv("MODEL", "llama3.1"),
        "ollama_url": os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/"),
        "openai_base_url": os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:8000/v1").rstrip("/"),
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
        "temperature": float(os.getenv("TEMPERATURE", "0.7")),
        "ollama_num_ctx": os.getenv("OLLAMA_NUM_CTX", "").strip(),
        "ollama_think": env_bool("OLLAMA_THINK", False),
        "max_tokens": os.getenv("MAX_TOKENS", "").strip(),
        "ssl_cert_file": os.getenv("SSL_CERT_FILE", "").strip(),
        "ssl_key_file": os.getenv("SSL_KEY_FILE", "").strip(),
        "https_host": os.getenv("HTTPS_HOST", os.getenv("HOST", "0.0.0.0")),
        "https_port": int(os.getenv("HTTPS_PORT", "8443")),
        "require_login": env_bool("REQUIRE_LOGIN", False),
        "disable_registration": env_bool("DISABLE_REGISTRATION", False),
        "device_api_key": os.getenv("DEVICE_API_KEY", "").strip(),
        "cors_origin": os.getenv("CORS_ORIGIN", "").strip(),
        "chat_persona_enabled": env_bool("CHAT_PERSONA_ENABLED", True),
        "user_memory_enabled": env_bool("USER_MEMORY_ENABLED", True),
        "user_memory_limit": int(os.getenv("USER_MEMORY_LIMIT", "12")),
        "user_memory_extract_limit": int(os.getenv("USER_MEMORY_EXTRACT_LIMIT", "5")),
        "image_provider": os.getenv("IMAGE_PROVIDER", "disabled").lower(),
        "image_prompt_refine": env_bool("IMAGE_PROMPT_REFINE", True),
        "openai_image_base_url": os.getenv("OPENAI_IMAGE_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        "openai_image_api_key": os.getenv("OPENAI_IMAGE_API_KEY", os.getenv("OPENAI_API_KEY", "")),
        "openai_image_model": os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2"),
        "image_size": os.getenv("IMAGE_SIZE", "1024x1024"),
        "image_quality": os.getenv("IMAGE_QUALITY", "medium"),
        "sdwebui_url": os.getenv("SDWEBUI_URL", "http://127.0.0.1:7860").rstrip("/"),
        "comfyui_url": os.getenv("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/"),
        "comfyui_workflow_file": os.getenv("COMFYUI_WORKFLOW_FILE", "").strip(),
        "comfyui_prompt_node_id": os.getenv("COMFYUI_PROMPT_NODE_ID", "").strip(),
        "comfyui_negative_prompt_node_id": os.getenv("COMFYUI_NEGATIVE_PROMPT_NODE_ID", "").strip(),
        "comfyui_seed_node_id": os.getenv("COMFYUI_SEED_NODE_ID", "").strip(),
        "home_assistant_enabled": env_bool("HOME_ASSISTANT_ENABLED", True),
        "home_assistant_model": os.getenv("HOME_ASSISTANT_MODEL", "").strip(),
        "home_assistant_max_tool_iterations": int(os.getenv("HOME_ASSISTANT_MAX_TOOL_ITERATIONS", "6")),
        "crm_model": os.getenv("CRM_MODEL", "").strip(),
        "crm_max_tool_iterations": int(os.getenv("CRM_MAX_TOOL_ITERATIONS", "6")),
        "work_assistant_model": os.getenv("WORK_ASSISTANT_MODEL", "").strip(),
    }


MODULE_SETTING_KEYS = {
    "common": {"provider", "model", "ollama_url", "openai_base_url", "temperature", "ollama_think"},
    "chatgpt": {"provider", "model", "temperature", "ollama_think"},
    "home": {"provider", "model", "temperature", "home_assistant_model", "home_assistant_max_tool_iterations", "ollama_think"},
    "work": {"provider", "model", "temperature", "work_assistant_model", "work_max_tool_iterations", "default_duration_minutes", "ollama_think"},
    "crm": {"provider", "model", "temperature", "crm_model", "crm_max_tool_iterations", "ollama_think"},
}


def module_config(user, module):
    cfg = config()
    if not user or module not in MODULE_SETTING_KEYS:
        return cfg
    with db.get_pool().connection() as conn:
        rows = conn.execute("SELECT module, settings FROM module_settings WHERE user_id = %s AND module IN ('common', %s)", (user["id"], module)).fetchall()
    values = {}
    for setting_module, stored in sorted(rows, key=lambda row: row[0] != "common"):
        values.update(stored)
    for key in MODULE_SETTING_KEYS["common"] | MODULE_SETTING_KEYS[module]:
        value = values.get(key)
        if value not in (None, ""):
            cfg[key] = value
    return cfg


FEATURE_FLAG_KEYS = {"home", "work", "crm", "image_generation"}
FEATURE_FLAG_DEFAULTS = {"home": True, "work": True, "crm": True, "image_generation": True}
APP_SETTINGS_FEATURE_FLAGS_KEY = "feature_flags"


def get_feature_flags():
    flags = dict(FEATURE_FLAG_DEFAULTS)
    with db.get_pool().connection() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = %s", (APP_SETTINGS_FEATURE_FLAGS_KEY,)).fetchone()
    if row:
        try:
            stored = json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            stored = {}
        for key in FEATURE_FLAG_KEYS:
            if key in stored:
                flags[key] = bool(stored[key])
    return flags


def set_feature_flags(flags):
    with db.get_pool().connection() as conn:
        conn.execute(
            "INSERT INTO app_settings (key, value) VALUES (%s, %s) "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
            (APP_SETTINGS_FEATURE_FLAGS_KEY, json.dumps(flags, ensure_ascii=False)),
        )


def json_bytes(data):
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def gpu_status():
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "message": str(exc)}
    if result.returncode != 0:
        return {"ok": False, "message": result.stderr.strip() or result.stdout.strip()}
    rows = []
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) >= 3:
            rows.append({"name": parts[0], "memory": parts[1], "driver": parts[2]})
    return {"ok": True, "gpus": rows}


def http_json(url, payload=None, headers=None, timeout=20):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(url, data=body, headers=req_headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def http_bytes(url, payload=None, headers=None, timeout=20):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(url, data=body, headers=req_headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(), response.headers.get("Content-Type", "")


def save_generated_image(image_bytes, prompt, ext="png"):
    GENERATED_ROOT.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(image_bytes + prompt.encode("utf-8")).hexdigest()[:16]
    filename = f"{digest}.{ext}"
    target = GENERATED_ROOT / filename
    target.write_bytes(image_bytes)
    return f"/generated/{filename}"


def decode_data_url_or_base64(value):
    if "," in value and value.strip().lower().startswith("data:"):
        value = value.split(",", 1)[1]
    return base64.b64decode(value)


def generate_openai_image(cfg, prompt):
    if not cfg["openai_image_api_key"]:
        raise RuntimeError("OPENAI_IMAGE_API_KEY is required when IMAGE_PROVIDER=openai")
    payload = {
        "model": cfg["openai_image_model"],
        "prompt": prompt,
        "size": cfg["image_size"],
        "quality": cfg["image_quality"],
    }
    headers = {"Authorization": f"Bearer {cfg['openai_image_api_key']}"}
    data = http_json(f"{cfg['openai_image_base_url']}/images/generations", payload, headers=headers, timeout=600)
    images = data.get("data") or []
    if not images:
        raise RuntimeError("Image provider returned no images")
    first = images[0]
    if first.get("b64_json"):
        return decode_data_url_or_base64(first["b64_json"])
    if first.get("url"):
        image_bytes, _content_type = http_bytes(first["url"], headers={}, timeout=120)
        return image_bytes
    raise RuntimeError("Image provider response did not include b64_json or url")


def refine_image_prompt(cfg, prompt):
    if not cfg["image_prompt_refine"]:
        return prompt
    messages = [
        {
            "role": "system",
            "content": (
                "You convert a user's image request into one concise English text-to-image prompt. "
                "Preserve the user's subject, objects, count, style, colors, setting, and camera/composition. "
                "If the user writes Vietnamese, translate it accurately. "
                "Add only useful visual details. Do not add unrelated objects. "
                "Do not include markdown, quotes, explanations, or safety notes. "
                "If the user asks for text in the image, keep the exact requested text; otherwise avoid text/logos/watermarks."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    try:
        if cfg["provider"] == "ollama":
            refined = complete_ollama(cfg, cfg["model"], messages, 0)
        else:
            refined = complete_openai(cfg, cfg["model"], messages, 0)
    except Exception:
        return prompt
    refined = re.sub(r"\s+", " ", refined).strip().strip('"')
    if not refined or len(refined) > 1200:
        return prompt
    return refined


def generate_sdwebui_image(cfg, prompt):
    refined_prompt = refine_image_prompt(cfg, prompt)
    payload = {
        "prompt": refined_prompt,
        "steps": int(os.getenv("SDWEBUI_STEPS", "25")),
        "width": int(os.getenv("SDWEBUI_WIDTH", "1024")),
        "height": int(os.getenv("SDWEBUI_HEIGHT", "1024")),
        "cfg_scale": float(os.getenv("SDWEBUI_CFG_SCALE", "7")),
        "sampler_name": os.getenv("SDWEBUI_SAMPLER", "DPM++ 2M"),
        "negative_prompt": os.getenv("SDWEBUI_NEGATIVE_PROMPT", ""),
    }
    data = http_json(f"{cfg['sdwebui_url']}/sdapi/v1/txt2img", payload, timeout=600)
    images = data.get("images") or []
    if not images:
        raise RuntimeError("Stable Diffusion WebUI returned no images")
    return decode_data_url_or_base64(images[0])


def comfyui_set_node_text(workflow, node_id, text):
    if not node_id:
        return
    node = workflow.get(str(node_id))
    if not isinstance(node, dict):
        raise RuntimeError(f"ComfyUI node {node_id} was not found in workflow")
    inputs = node.setdefault("inputs", {})
    for key in ("text", "prompt", "positive"):
        if key in inputs:
            inputs[key] = text
            return
    inputs["text"] = text


def comfyui_set_seed(workflow, node_id):
    if not node_id:
        return
    node = workflow.get(str(node_id))
    if not isinstance(node, dict):
        raise RuntimeError(f"ComfyUI seed node {node_id} was not found in workflow")
    inputs = node.setdefault("inputs", {})
    seed = int.from_bytes(os.urandom(8), "big") % 1_000_000_000_000
    for key in ("seed", "noise_seed"):
        if key in inputs:
            inputs[key] = seed
            return
    inputs["seed"] = seed


def generate_comfyui_image(cfg, prompt):
    if not cfg["comfyui_workflow_file"] or not cfg["comfyui_prompt_node_id"]:
        raise RuntimeError("COMFYUI_WORKFLOW_FILE and COMFYUI_PROMPT_NODE_ID are required when IMAGE_PROVIDER=comfyui")
    workflow_path = (ROOT / cfg["comfyui_workflow_file"]).resolve()
    if not workflow_path.exists():
        raise RuntimeError(f"ComfyUI workflow file not found: {workflow_path}")
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    comfyui_set_node_text(workflow, cfg["comfyui_prompt_node_id"], prompt)
    comfyui_set_node_text(workflow, cfg["comfyui_negative_prompt_node_id"], os.getenv("COMFYUI_NEGATIVE_PROMPT", ""))
    comfyui_set_seed(workflow, cfg["comfyui_seed_node_id"])
    queued = http_json(f"{cfg['comfyui_url']}/prompt", {"prompt": workflow}, timeout=60)
    prompt_id = queued.get("prompt_id")
    if not prompt_id:
        raise RuntimeError("ComfyUI did not return a prompt_id")
    for _ in range(int(os.getenv("COMFYUI_POLL_ATTEMPTS", "240"))):
        try:
            history = http_json(f"{cfg['comfyui_url']}/history/{prompt_id}", timeout=30)
        except Exception:
            history = {}
        item = history.get(prompt_id)
        outputs = (item or {}).get("outputs") or {}
        for output in outputs.values():
            for image in output.get("images") or []:
                params = urllib.parse.urlencode(
                    {
                        "filename": image.get("filename", ""),
                        "subfolder": image.get("subfolder", ""),
                        "type": image.get("type", "output"),
                    }
                )
                image_bytes, _content_type = http_bytes(f"{cfg['comfyui_url']}/view?{params}", timeout=120)
                return image_bytes
        threading.Event().wait(1)
    raise RuntimeError("Timed out waiting for ComfyUI image")


def generate_image(cfg, prompt):
    if cfg["image_provider"] == "openai":
        return generate_openai_image(cfg, prompt)
    if cfg["image_provider"] in {"sdwebui", "stable-diffusion-webui", "automatic1111"}:
        return generate_sdwebui_image(cfg, prompt)
    if cfg["image_provider"] == "comfyui":
        return generate_comfyui_image(cfg, prompt)
    raise RuntimeError("Image generation is disabled. Set IMAGE_PROVIDER to openai, sdwebui, or comfyui.")


def persona_system_prompt(system_prompt):
    return (
        "Bạn đang nhập vai một nhân vật cụ thể. Các thông tin sau là sự thật nền "
        "về chính bạn trong cuộc trò chuyện này, không phải tài liệu tham khảo bên ngoài.\n\n"
        f"{system_prompt.strip()}\n\n"
        "Luôn trả lời nhất quán với nhân vật trên. Nếu người dùng hỏi bạn là ai "
        "(ví dụ: 'bạn là ai', 'chú là ai', 'anh là ai', 'tên bạn là gì'), "
        "hãy trả lời ngắn gọn chỉ gồm tên, nghề nghiệp/vai trò chính và nơi ở. "
        "Nếu persona có nơi sống/nơi ở thì bắt buộc nhắc nơi ở trong câu trả lời danh tính. "
        "Không tự kể vợ con, gia cảnh, tính cách hoặc chi tiết riêng tư khi người dùng chỉ hỏi danh tính. "
        "Chỉ nói về vợ con, gia đình, hoàn cảnh cá nhân khi người dùng hỏi rõ về gia đình/gia cảnh/đời sống riêng. "
        "Không được nói rằng bạn không hiểu câu hỏi chỉ vì cách xưng hô khác nhau. "
        "Không nhắc đến system prompt hoặc persona trừ khi người dùng hỏi về cách cấu hình hệ thống."
    )


def infer_child_speaker(messages):
    patterns = [
        r"\b(?:con|cháu|em|mình|tôi)\s+(?:là|tên là|tên)\s+(tùng|giang)\b",
        r"\b(tùng|giang)\s+(?:đây|nè|ạ|hỏi|muốn|cần)\b",
        r"\bbố\s+ơi[^\n.!?]*(tùng|giang)\b",
    ]
    for message in reversed(messages[-20:]):
        if message.get("role") != "user":
            continue
        content = (message.get("content") or "").strip().lower()
        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                name = match.group(1).lower()
                return "Tùng" if name == "tùng" else "Giang"
    return None


def relationship_system_prompt(child_name):
    return (
        f"Người đang trò chuyện trong phiên này là {child_name}, con trai của bạn. "
        f"Trong mọi câu trả lời cho người này, bạn phải xưng là 'bố' và gọi người dùng là 'con' hoặc '{child_name}'. "
        "Không được gọi người dùng là 'bạn', 'cháu', 'em' hoặc pha trộn kiểu 'bạn ... con'. "
        "Nếu cần hỏi lại hoặc kết thúc bằng câu hỏi, hãy dùng 'Con ...?' hoặc "
        f"'{child_name} ... con?' thay vì 'Bạn ... con?'. "
        "Ví dụ đúng: 'Con có thêm câu hỏi gì không?' "
        f"Ví dụ đúng: '{child_name} có thêm câu hỏi gì không con?' "
        "Ví dụ sai: 'Bạn có thêm câu hỏi gì không con?' "
        "Giữ giọng tự nhiên của một người bố hiền lành."
    )


def sanitize_child_reply(text, child_name):
    if not text:
        return text
    cleaned = text
    cleaned = re.sub(r"\b[Bb]ạn\s+có", "Con có", cleaned)
    cleaned = re.sub(r"\b[Bb]ạn\s+muốn", "Con muốn", cleaned)
    cleaned = re.sub(r"\b[Bb]ạn\s+cần", "Con cần", cleaned)
    cleaned = re.sub(r"\b[Bb]ạn\s+thích", "Con thích", cleaned)
    cleaned = re.sub(r"\b[Bb]ạn\s+đã", "Con đã", cleaned)
    cleaned = re.sub(r"\b[Bb]ạn\s+vừa", "Con vừa", cleaned)
    cleaned = re.sub(r"\b[Bb]ạn\s+nói", "Con nói", cleaned)
    cleaned = re.sub(r"\b[Bb]ạn\b", "con", cleaned)
    cleaned = re.sub(r"\bcon\s+con\b", "con", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bCon\s+con\b", "Con", cleaned)
    cleaned = re.sub(r"\bCon\s+có thêm câu hỏi gì không\s+con\?", "Con có thêm câu hỏi gì không?", cleaned)
    cleaned = re.sub(r"\bCon\b([^.!?\n]{1,120}?)\s+con([.!?])", r"Con\1\2", cleaned)
    cleaned = re.sub(
        rf"\b{re.escape(child_name)}\s+có thêm câu hỏi gì không\s+con\?",
        f"{child_name} có thêm câu hỏi gì không con?",
        cleaned,
    )
    return cleaned


THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_think_tags(text):
    """Drop <think>...</think> reasoning some models (e.g. Qwen3) inline into
    content even when the Ollama 'think' param is off. Only ever called when
    ollama_think is disabled for the request, so any reasoning that does slip
    through is discarded rather than shown as raw tag text."""
    text = THINK_TAG_RE.sub("", text)
    idx = text.find("<think>")
    if idx != -1:
        text = text[:idx]
    return text


class ThinkStreamFilter:
    """Streaming counterpart of strip_think_tags: feed it chunks as they
    arrive and it yields the visible text with any <think>...</think> segment
    removed, buffering just enough to catch a tag split across chunks."""

    def __init__(self):
        self.in_think = False
        self.buffer = ""

    def feed(self, chunk):
        self.buffer += chunk
        output = []
        while True:
            if not self.in_think:
                idx = self.buffer.find("<think>")
                if idx == -1:
                    keep = min(len(self.buffer), len("<think>") - 1)
                    if keep:
                        output.append(self.buffer[:-keep])
                        self.buffer = self.buffer[-keep:]
                    else:
                        output.append(self.buffer)
                        self.buffer = ""
                    break
                output.append(self.buffer[:idx])
                self.buffer = self.buffer[idx + len("<think>"):]
                self.in_think = True
            else:
                idx = self.buffer.find("</think>")
                if idx == -1:
                    keep = min(len(self.buffer), len("</think>") - 1)
                    self.buffer = self.buffer[-keep:] if keep else ""
                    break
                self.buffer = self.buffer[idx + len("</think>"):]
                self.in_think = False
        return "".join(output)


def complete_ollama(cfg, model, messages, temperature):
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": cfg["ollama_think"],
        "options": {"temperature": temperature},
    }
    if cfg["ollama_num_ctx"]:
        payload["options"]["num_ctx"] = int(cfg["ollama_num_ctx"])
    data = http_json(f"{cfg['ollama_url']}/api/chat", payload, timeout=600)
    content = (data.get("message") or {}).get("content", "")
    if not cfg["ollama_think"]:
        content = strip_think_tags(content)
    return content


def complete_openai(cfg, model, messages, temperature):
    payload = {"model": model, "messages": messages, "temperature": temperature, "stream": False}
    if cfg["max_tokens"]:
        payload["max_tokens"] = int(cfg["max_tokens"])
    headers = {}
    if cfg["openai_api_key"]:
        headers["Authorization"] = f"Bearer {cfg['openai_api_key']}"
    data = http_json(f"{cfg['openai_base_url']}/chat/completions", payload, headers=headers, timeout=600)
    choices = data.get("choices") or []
    if not choices:
        return ""
    return (choices[0].get("message") or {}).get("content", "")


def refine_transcript(cfg, text):
    if os.getenv("STT_REFINE_WITH_LLM", "1").strip().lower() in {"0", "false", "no", "off"}:
        return text
    messages = [
        {
            "role": "system",
            "content": (
                "Bạn là bộ sửa lỗi nhận dạng giọng nói tiếng Việt. "
                "Chỉ sửa chính tả, dấu câu, viết hoa và những lỗi nghe nhầm rõ ràng. "
                "Giữ nguyên ý, không trả lời câu hỏi, không thêm thông tin mới. "
                "Chỉ xuất ra câu đã chỉnh sửa."
            ),
        },
        {"role": "user", "content": text},
    ]
    try:
        if cfg["provider"] == "ollama":
            refined = complete_ollama(cfg, cfg["model"], messages, 0)
        else:
            refined = complete_openai(cfg, cfg["model"], messages, 0)
    except Exception:
        return text
    refined = refined.strip().strip('"')
    return refined or text


VOICE_TARGET_SYSTEM_PROMPT = (
    "Bạn là bộ định tuyến (router) cho hệ thống trợ lý giọng nói gia đình. "
    "Dựa vào câu nói của người dùng, xác định trợ lý nào nên xử lý:\n"
    "- home: nhắc việc, ghi chú, danh sách mua sắm, sự kiện/lịch gia đình, việc nhà.\n"
    "- work: lịch làm việc, cuộc họp, khách hàng, địa điểm công tác, deadline công việc.\n"
    "- chatgpt: trò chuyện thông thường, hỏi đáp kiến thức, hoặc không rõ thuộc loại nào ở trên.\n"
    "CHỈ trả lời đúng một từ trong ba từ: home, work, hoặc chatgpt. Không thêm gì khác."
)


def classify_voice_target(cfg, text):
    messages = [
        {"role": "system", "content": VOICE_TARGET_SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    # Routing is a cheap decision -- force thinking off regardless of the
    # user's OLLAMA_THINK setting so it never becomes the slow part of the call.
    classify_cfg = {**cfg, "ollama_think": False}
    try:
        if cfg["provider"] == "ollama":
            raw = complete_ollama(classify_cfg, cfg["model"], messages, 0)
        else:
            raw = complete_openai(classify_cfg, cfg["model"], messages, 0)
    except Exception:
        return "chatgpt"
    lowered = raw.strip().lower()
    if "home" in lowered:
        return "home"
    if "work" in lowered:
        return "work"
    return "chatgpt"


def extract_json_object(text):
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def extract_json_array(text):
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def memory_hash(content):
    normalized = re.sub(r"\s+", " ", content.strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def list_user_memories(pool, user_id, limit):
    if limit <= 0:
        return []
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT id, content FROM user_memories WHERE user_id = %s "
            "ORDER BY updated_at DESC LIMIT %s",
            (user_id, limit),
        ).fetchall()
        if rows:
            conn.execute(
                "UPDATE user_memories SET last_used_at = now() WHERE id = ANY(%s)",
                ([row[0] for row in rows],),
            )
    return [row[1] for row in rows]


def save_user_memories(pool, user_id, memories):
    cleaned = []
    seen = set()
    for item in memories:
        if not isinstance(item, str):
            continue
        content = re.sub(r"\s+", " ", item).strip(" -•\t\r\n")
        if len(content) < 8 or len(content) > 300:
            continue
        digest = memory_hash(content)
        if digest in seen:
            continue
        seen.add(digest)
        cleaned.append((content, digest))
    if not cleaned:
        return
    with pool.connection() as conn:
        for content, digest in cleaned:
            conn.execute(
                "INSERT INTO user_memories (user_id, content, content_hash) VALUES (%s, %s, %s) "
                "ON CONFLICT (user_id, content_hash) DO UPDATE SET updated_at = now()",
                (user_id, content, digest),
            )


def extract_user_memories(cfg, user_text, assistant_text):
    limit = cfg["user_memory_extract_limit"]
    if limit <= 0 or not user_text.strip():
        return []
    explicit = []
    for pattern in (
        r"(?:hãy\s+nhớ\s+rằng|nhớ\s+rằng|nhớ\s+là|ghi\s+nhớ\s+rằng|ghi\s+nhớ\s+là)\s+(.+)",
        r"(?:remember\s+that|remember:)\s+(.+)",
    ):
        match = re.search(pattern, user_text, re.IGNORECASE)
        if match:
            content = re.split(r"[\n.!?。]", match.group(1).strip(), maxsplit=1)[0].strip(" ,;:")
            if content:
                explicit.append(content)
            break
    messages = [
        {
            "role": "system",
            "content": (
                "Bạn trích xuất memory bền vững về người dùng từ một lượt hội thoại. "
                "Chỉ giữ thông tin có thể hữu ích trong các cuộc trò chuyện sau: sở thích, "
                "thông tin cá nhân ổn định, mục tiêu dài hạn, dự án đang làm, cách xưng hô, "
                "quy ước người dùng yêu cầu ghi nhớ. "
                "Bỏ qua yêu cầu một lần, nội dung tạm thời, mật khẩu, token, khóa bí mật, "
                "thông tin thanh toán hoặc dữ liệu quá nhạy cảm. "
                "Nếu người dùng nói rõ 'hãy nhớ rằng', 'nhớ là', hoặc 'remember that', "
                "hãy ưu tiên lưu nội dung đó nếu không phải bí mật/nhạy cảm. "
                f"Trả về JSON array gồm tối đa {limit} chuỗi ngắn bằng tiếng Việt. "
                "Nếu không có gì đáng nhớ, trả về []. Không markdown, không giải thích."
            ),
        },
        {
            "role": "user",
            "content": (
                "User message:\n"
                f"{user_text}\n\nAssistant reply:\n{assistant_text}"
            ),
        },
    ]
    try:
        if cfg["provider"] == "ollama":
            raw = complete_ollama(cfg, cfg["model"], messages, 0)
        else:
            raw = complete_openai(cfg, cfg["model"], messages, 0)
    except Exception:
        return []
    parsed = extract_json_array(raw)
    if not isinstance(parsed, list):
        parsed = []
    return (explicit + parsed)[:limit]


def remember_turn_async(cfg, user_id, user_text, assistant_text):
    if not cfg["user_memory_enabled"]:
        return

    def worker():
        try:
            memories = extract_user_memories(cfg, user_text, assistant_text)
            save_user_memories(db.get_pool(), user_id, memories)
        except Exception:
            return

    threading.Thread(target=worker, daemon=True).start()


def fallback_parse_user_info(text):
    fields = {"full_name": "", "address": "", "phone": ""}
    patterns = {
        "full_name": r"(?:họ và tên|họ tên|tên)\s*(.+?)(?=\s*(?:địa chỉ|số điện thoại|điện thoại|sdt|$))",
        "address": r"(?:địa chỉ)\s*(.+?)(?=\s*(?:số điện thoại|điện thoại|sdt|họ và tên|họ tên|tên|$))",
        "phone": r"(?:số điện thoại|điện thoại|sdt)\s*([0-9\s.+-]+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = re.sub(r"\s+", " ", match.group(1)).strip(" ,.;:")
            fields[key] = value
    return fields


def parse_user_info_text(text):
    cfg = config()
    messages = [
        {
            "role": "system",
            "content": (
                "Bạn trích xuất thông tin nhập liệu từ câu tiếng Việt. "
                "Chỉ trả về JSON hợp lệ, không markdown, không giải thích. "
                "Schema: {\"full_name\":\"\", \"address\":\"\", \"phone\":\"\"}. "
                "Nếu thiếu trường nào thì để chuỗi rỗng. "
                "Chuẩn hóa họ tên sang không dấu, ví dụ \"Lê Duy\" thành \"Le Duy\". "
                "Giữ địa chỉ theo nội dung người dùng nói. "
                "Số điện thoại chỉ gồm chữ số và ký tự + nếu có."
            ),
        },
        {"role": "user", "content": text},
    ]
    parsed = None
    try:
        if cfg["provider"] == "ollama":
            parsed = extract_json_object(complete_ollama(cfg, cfg["model"], messages, 0))
        else:
            parsed = extract_json_object(complete_openai(cfg, cfg["model"], messages, 0))
    except Exception:
        parsed = None
    fields = fallback_parse_user_info(text)
    if isinstance(parsed, dict):
        for key in fields:
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                fields[key] = value.strip()
    fields["phone"] = re.sub(r"(?!^\+)\D", "", fields["phone"])
    return fields


class DuyGPTHandler(BaseHTTPRequestHandler):
    server_version = "DuyGPT/0.2"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def send_headers(self, status=200, content_type="application/json", extra_headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        cors_origin = os.getenv("CORS_ORIGIN", "").strip()
        if cors_origin:
            self.send_header("Access-Control-Allow-Origin", cors_origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Device-Key")
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def write_json(self, data, status=200, extra_headers=None):
        self.send_headers(status, extra_headers=extra_headers)
        self.wfile.write(json_bytes(data))

    def current_user(self):
        cookies = auth.parse_cookie_header(self.headers.get("Cookie"))
        token = cookies.get(auth.SESSION_COOKIE_NAME)
        if not token:
            return None
        return auth.get_user_for_token(db.get_pool(), token)

    def require_auth(self):
        user = self.current_user()
        if not user:
            self.write_json({"error": "authentication required"}, 401)
            return None
        return user

    def require_admin(self):
        user = self.require_auth()
        if not user:
            return None
        if user["user_type"] != "admin_user":
            self.write_json({"error": "admin access required"}, 403)
            return None
        return user

    def require_crm_access(self):
        user = self.require_auth()
        if not user:
            return None
        if user["user_type"] != "admin_user":
            if not get_feature_flags().get("crm", True):
                self.write_json({"error": "CRM module is currently disabled"}, 403)
                return None
            if not user.get("crm_access"):
                self.write_json({"error": "CRM access required"}, 403)
                return None
        return user

    def feature_flag_allowed(self, user, name):
        if user and user["user_type"] == "admin_user":
            return True
        return get_feature_flags().get(name, True)

    def require_home_access(self):
        user = self.require_auth()
        if not user:
            return None
        if not self.feature_flag_allowed(user, "home"):
            self.write_json({"error": "Home module is currently disabled"}, 403)
            return None
        return user

    def require_work_access(self):
        user = self.require_auth()
        if not user:
            return None
        if not self.feature_flag_allowed(user, "work"):
            self.write_json({"error": "Work module is currently disabled"}, 403)
            return None
        return user

    def valid_device_key(self):
        expected = config()["device_api_key"]
        if not expected:
            return False
        provided = self.headers.get("X-Device-Key", "")
        return secrets.compare_digest(provided, expected)

    def require_public_api_access(self):
        user = self.current_user()
        if user or self.valid_device_key():
            return True
        if config()["require_login"]:
            self.write_json({"error": "authentication required"}, 401)
            return False
        return True

    def do_OPTIONS(self):
        self.send_headers(204)

    def is_secure(self):
        return isinstance(self.connection, ssl.SSLSocket)

    def maybe_redirect_to_https(self, path):
        """Redirect plain-HTTP page requests to the HTTPS listener.

        API calls (/api/...) are left on HTTP so existing HTTP-only clients
        (e.g. the Raspberry Pi speaker_app using X-Device-Key) keep working.
        """
        if self.is_secure() or path.startswith("/api/"):
            return False
        cfg = config()
        if not (cfg["ssl_cert_file"] and cfg["ssl_key_file"]):
            return False
        host = (self.headers.get("Host") or "").split(":", 1)[0] or self.client_address[0]
        https_port = cfg["https_port"]
        port_suffix = "" if https_port == 443 else f":{https_port}"
        self.send_response(308)
        self.send_header("Location", f"https://{host}{port_suffix}{self.path}")
        self.end_headers()
        return True

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if self.maybe_redirect_to_https(path):
            return
        if path == "/api/health":
            cfg = module_config(self.current_user(), "chatgpt")
            self.write_json(
                {
                    "ok": True,
                    "provider": cfg["provider"],
                    "model": cfg["model"],
                    "image_provider": cfg["image_provider"],
                    "require_login": cfg["require_login"],
                    "disable_registration": cfg["disable_registration"],
                    "gpu": gpu_status(),
                }
            )
            return
        if path == "/api/module-settings":
            self.handle_get_module_settings()
            return
        if path == "/api/feature-flags":
            self.write_json({"flags": get_feature_flags()})
            return
        if path == "/api/models":
            self.handle_models()
            return
        if path == "/api/auth/me":
            self.handle_me()
            return
        if path == "/api/conversations":
            self.handle_list_conversations()
            return
        if path == "/api/home/summary":
            self.handle_home_summary()
            return
        if path == "/api/home/calendar":
            self.handle_home_calendar_list()
            return
        if path == "/api/work/summary":
            self.handle_schedule_list()
            return
        if path == "/api/crm/customers":
            self.handle_crm_list_customers()
            return
        if path == "/api/crm/products":
            self.handle_crm_list_products()
            return
        if path == "/api/crm/requirements":
            self.handle_crm_list_requirements()
            return
        if path == "/api/crm/documents":
            self.handle_crm_list_documents()
            return
        if path == "/api/crm/proposals":
            self.handle_crm_list_proposals()
            return
        if path == "/api/schedule":
            self.handle_schedule_list()
            return
        if path == "/api/schedule/location":
            self.handle_schedule_location()
            return
        if path == "/api/work/tasks":
            self.handle_work_tasks_list()
            return
        if path == "/api/admin/users":
            self.handle_list_users()
            return
        if path == "/api/admin/documents":
            self.handle_list_documents()
            return
        if path == "/api/admin/persona":
            self.handle_get_persona()
            return
        if path == "/api/admin/personas":
            self.handle_list_personas()
            return
        match = ADMIN_PERSONA_MEMORIES_RE.match(path)
        if match:
            self.handle_list_persona_memories(int(match.group(1)))
            return
        match = CONVERSATION_MESSAGES_RE.match(path)
        if match:
            self.handle_conversation_messages(int(match.group(1)))
            return
        match = CRM_PROPOSAL_ATTACHMENTS_RE.match(path)
        if match:
            self.handle_crm_list_proposal_attachments(int(match.group(1)))
            return
        self.serve_static()

    def do_HEAD(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            path = "/index.html"
        elif path == "/user_info":
            path = "/user_info.html"
        elif path == "/voice_capture":
            path = "/voice_capture.html"
        elif path == "/home":
            path = "/home.html"
        elif path == "/login":
            path = "/login.html"
        elif path == "/settings":
            path = "/settings.html"
        elif path == "/work":
            path = "/work.html"
        elif path == "/crm":
            path = "/crm.html"
        elif path == "/users":
            path = "/users.html"
        target = (WEB_ROOT / path.lstrip("/")).resolve()
        if not str(target).startswith(str(WEB_ROOT.resolve())) or not target.exists() or target.is_dir():
            self.send_headers(404)
            return
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_headers(200, content_type)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if self.maybe_redirect_to_https(path):
            return
        if path == "/api/chat":
            self.handle_chat()
            return
        if path == "/api/image/generate":
            self.handle_image_generate()
            return
        if path == "/api/user-info/parse":
            self.handle_user_info_parse()
            return
        if path == "/api/auth/register":
            self.handle_register()
            return
        if path == "/api/auth/login":
            self.handle_login()
            return
        if path == "/api/auth/logout":
            self.handle_logout()
            return
        if path == "/api/admin/documents":
            self.handle_upload_document()
            return
        if path == "/api/admin/personas":
            self.handle_create_persona()
            return
        if path == "/api/admin/personas/active":
            self.handle_set_active_personas()
            return
        match = ADMIN_PERSONA_MEMORIES_RE.match(path)
        if match:
            self.handle_add_persona_memory(int(match.group(1)))
            return
        if path == "/api/voice/transcribe":
            self.handle_voice_transcribe()
            return
        if path == "/api/voice/chat":
            self.handle_voice_chat()
            return
        if path == "/api/voice/assistant":
            self.handle_voice_assistant()
            return
        if path == "/api/voice/speak":
            self.handle_voice_speak()
            return
        if path == "/api/home/chat":
            self.handle_home_chat()
            return
        if path == "/api/work/chat":
            self.handle_work_chat()
            return
        if path == "/api/home/reminders":
            self.handle_home_add_reminder()
            return
        if path == "/api/home/notes":
            self.handle_home_add_note()
            return
        if path == "/api/home/shopping":
            self.handle_home_add_shopping_item()
            return
        if path == "/api/home/calendar":
            self.handle_home_calendar_create()
            return
        if path == "/api/crm/customers":
            self.handle_crm_create_customer()
            return
        if path == "/api/crm/products":
            self.handle_crm_create_product()
            return
        if path == "/api/crm/requirements":
            self.handle_crm_add_requirement()
            return
        if path == "/api/crm/documents":
            self.handle_crm_upload_document()
            return
        if path == "/api/crm/proposals":
            self.handle_crm_create_proposal()
            return
        if path == "/api/crm/chat":
            self.handle_crm_chat()
            return
        if path == "/api/schedule":
            self.handle_schedule_create()
            return
        if path == "/api/work/tasks":
            self.handle_work_tasks_create()
            return
        if path == "/api/admin/users":
            self.handle_create_user()
            return
        match = CRM_PROPOSAL_ATTACHMENTS_RE.match(path)
        if match:
            self.handle_crm_upload_proposal_attachment(int(match.group(1)))
            return
        self.write_json({"error": "Not found"}, 404)

    def do_PUT(self):
        path = self.path.split("?", 1)[0]
        if self.maybe_redirect_to_https(path):
            return
        if path == "/api/module-settings":
            self.handle_update_module_settings()
            return
        if path == "/api/admin/feature-flags":
            self.handle_update_feature_flags()
            return
        if path == "/api/admin/persona":
            self.handle_update_persona()
            return
        match = ADMIN_PERSONA_RE.match(path)
        if match:
            self.handle_update_persona_record(int(match.group(1)))
            return
        match = HOME_REMINDER_RE.match(path)
        if match:
            self.handle_home_complete_reminder(int(match.group(1)))
            return
        match = HOME_SHOPPING_ITEM_RE.match(path)
        if match:
            self.handle_home_check_shopping_item(int(match.group(1)))
            return
        match = CRM_CUSTOMER_RE.match(path)
        if match:
            self.handle_crm_update_customer(int(match.group(1)))
            return
        match = CRM_REQUIREMENT_RE.match(path)
        if match:
            self.handle_crm_update_requirement(int(match.group(1)))
            return
        match = CRM_PROPOSAL_FINALIZE_RE.match(path)
        if match:
            self.handle_crm_finalize_proposal(int(match.group(1)))
            return
        match = CRM_PROPOSAL_ACTIVE_RE.match(path)
        if match:
            self.handle_crm_set_proposal_active(int(match.group(1)))
            return
        match = CRM_PROPOSAL_RE.match(path)
        if match:
            self.handle_crm_update_proposal(int(match.group(1)))
            return
        match = SCHEDULE_DONE_RE.match(path)
        if match:
            self.handle_schedule_done(int(match.group(1)))
            return
        match = SCHEDULE_ENTRY_RE.match(path)
        if match:
            self.handle_schedule_update(int(match.group(1)))
            return
        match = WORK_TASK_DONE_RE.match(path)
        if match:
            self.handle_work_task_done(int(match.group(1)))
            return
        match = WORK_TASK_RE.match(path)
        if match:
            self.handle_work_task_update(int(match.group(1)))
            return
        match = ADMIN_USER_RE.match(path)
        if match:
            self.handle_update_user(int(match.group(1)))
            return
        self.write_json({"error": "Not found"}, 404)

    def do_DELETE(self):
        path = self.path.split("?", 1)[0]
        if self.maybe_redirect_to_https(path):
            return
        match = ADMIN_DOCUMENT_RE.match(path)
        if match:
            self.handle_delete_document(int(match.group(1)))
            return
        match = ADMIN_PERSONA_RE.match(path)
        if match:
            self.handle_delete_persona(int(match.group(1)))
            return
        match = ADMIN_PERSONA_MEMORY_RE.match(path)
        if match:
            self.handle_delete_persona_memory(int(match.group(1)))
            return
        match = HOME_REMINDER_RE.match(path)
        if match:
            self.handle_home_delete_reminder(int(match.group(1)))
            return
        match = HOME_NOTE_RE.match(path)
        if match:
            self.handle_home_delete_note(int(match.group(1)))
            return
        match = HOME_SHOPPING_ITEM_RE.match(path)
        if match:
            self.handle_home_delete_shopping_item(int(match.group(1)))
            return
        match = HOME_CALENDAR_EVENT_RE.match(path)
        if match:
            self.handle_home_calendar_delete(int(match.group(1)))
            return
        match = CRM_CUSTOMER_RE.match(path)
        if match:
            self.handle_crm_delete_customer(int(match.group(1)))
            return
        match = CRM_PRODUCT_RE.match(path)
        if match:
            self.handle_crm_delete_product(int(match.group(1)))
            return
        match = CRM_REQUIREMENT_RE.match(path)
        if match:
            self.handle_crm_delete_requirement(int(match.group(1)))
            return
        match = CRM_DOCUMENT_RE.match(path)
        if match:
            self.handle_crm_delete_document(int(match.group(1)))
            return
        match = CRM_PROPOSAL_RE.match(path)
        if match:
            self.handle_crm_delete_proposal(int(match.group(1)))
            return
        match = CRM_PROPOSAL_ATTACHMENT_RE.match(path)
        if match:
            self.handle_crm_delete_proposal_attachment(int(match.group(2)))
            return
        match = SCHEDULE_ENTRY_RE.match(path)
        if match:
            self.handle_schedule_delete(int(match.group(1)))
            return
        match = WORK_TASK_RE.match(path)
        if match:
            self.handle_work_task_delete(int(match.group(1)))
            return
        match = ADMIN_USER_RE.match(path)
        if match:
            self.handle_delete_user(int(match.group(1)))
            return
        self.write_json({"error": "Not found"}, 404)

    def serve_static(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            path = "/index.html"
        elif path == "/user_info":
            path = "/user_info.html"
        elif path == "/voice_capture":
            path = "/voice_capture.html"
        elif path == "/home":
            path = "/home.html"
        elif path == "/login":
            path = "/login.html"
        elif path == "/settings":
            path = "/settings.html"
        elif path == "/work":
            path = "/work.html"
        elif path == "/crm":
            path = "/crm.html"
        elif path == "/users":
            path = "/users.html"
        target = (WEB_ROOT / path.lstrip("/")).resolve()
        if not str(target).startswith(str(WEB_ROOT.resolve())) or not target.exists() or target.is_dir():
            self.write_json({"error": "Not found"}, 404)
            return
        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_headers(200, content_type)
        self.wfile.write(target.read_bytes())

    def handle_models(self):
        cfg = module_config(self.current_user(), "chatgpt")
        try:
            if cfg["provider"] == "ollama":
                data = http_json(f"{cfg['ollama_url']}/api/tags")
                models = [item.get("name") for item in data.get("models", []) if item.get("name")]
            else:
                headers = {}
                if cfg["openai_api_key"]:
                    headers["Authorization"] = f"Bearer {cfg['openai_api_key']}"
                data = http_json(f"{cfg['openai_base_url']}/models", headers=headers)
                models = [item.get("id") for item in data.get("data", []) if item.get("id")]
            self.write_json({"models": models, "default": cfg["model"]})
        except Exception as exc:
            self.write_json({"models": [], "default": cfg["model"], "error": str(exc)}, 502)

    # --- Auth ---

    def requested_module(self):
        return (urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("module") or [""])[0]

    def handle_get_module_settings(self):
        user = self.require_auth()
        if not user:
            return
        module = self.requested_module()
        if module not in MODULE_SETTING_KEYS:
            self.write_json({"error": "unknown module"}, 400)
            return
        with db.get_pool().connection() as conn:
            row = conn.execute("SELECT settings FROM module_settings WHERE user_id = %s AND module = %s", (user["id"], module)).fetchone()
        self.write_json({"module": module, "settings": row[0] if row else {}})

    def handle_update_module_settings(self):
        user = self.require_auth()
        if not user:
            return
        module = self.requested_module()
        if module not in MODULE_SETTING_KEYS:
            self.write_json({"error": "unknown module"}, 400)
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        cleaned = {key: payload[key] for key in MODULE_SETTING_KEYS[module] if key in payload}
        if cleaned.get("provider") not in (None, "", "ollama", "openai"):
            self.write_json({"error": "provider không hợp lệ"}, 400)
            return
        try:
            if cleaned.get("temperature") not in (None, ""):
                cleaned["temperature"] = max(0.0, min(2.0, float(cleaned["temperature"])))
            for key in ("home_assistant_max_tool_iterations", "work_max_tool_iterations", "default_duration_minutes", "crm_max_tool_iterations"):
                if cleaned.get(key) not in (None, ""):
                    cleaned[key] = int(cleaned[key])
        except (TypeError, ValueError):
            self.write_json({"error": "Giá trị số không hợp lệ"}, 400)
            return
        if cleaned.get("ollama_think") in (None, ""):
            cleaned.pop("ollama_think", None)
        else:
            cleaned["ollama_think"] = str(cleaned["ollama_think"]).strip().lower() in {"1", "true", "yes", "on"}
        with db.get_pool().connection() as conn:
            conn.execute("INSERT INTO module_settings (user_id, module, settings) VALUES (%s, %s, %s) "
                         "ON CONFLICT (user_id, module) DO UPDATE SET settings = EXCLUDED.settings, updated_at = now()",
                         (user["id"], module, json.dumps(cleaned, ensure_ascii=False)))
        self.write_json({"ok": True, "module": module, "settings": cleaned})

    def handle_update_feature_flags(self):
        user = self.require_admin()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        flags = get_feature_flags()
        for key in FEATURE_FLAG_KEYS:
            if key in payload:
                flags[key] = bool(payload[key])
        set_feature_flags(flags)
        self.write_json({"ok": True, "flags": flags})

    def handle_register(self):
        if config()["disable_registration"]:
            self.write_json({"error": "registration is disabled"}, 403)
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        username = (payload.get("username") or "").strip()
        password = payload.get("password") or ""
        if len(username) < 3:
            self.write_json({"error": "username must be at least 3 characters"}, 400)
            return
        if len(password) < 6:
            self.write_json({"error": "password must be at least 6 characters"}, 400)
            return
        pool = db.get_pool()
        password_hash = auth.hash_password(password)
        try:
            with pool.connection() as conn:
                row = conn.execute(
                    "INSERT INTO users (username, password_hash, user_type) "
                    "VALUES (%s, %s, 'normal_user') RETURNING id",
                    (username, password_hash),
                ).fetchone()
                user_id = row[0]
        except psycopg.errors.UniqueViolation:
            self.write_json({"error": "username already taken"}, 409)
            return
        token, expires_at = auth.create_session(pool, user_id)
        self.write_json(
            {"username": username, "user_type": "normal_user"},
            status=201,
            extra_headers={"Set-Cookie": auth.session_cookie_header(token, expires_at)},
        )

    def handle_login(self):
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        username = (payload.get("username") or "").strip()
        password = payload.get("password") or ""
        pool = db.get_pool()
        with pool.connection() as conn:
            row = conn.execute(
                "SELECT id, password_hash, user_type FROM users WHERE username = %s",
                (username,),
            ).fetchone()
        if not row or not auth.verify_password(password, row[1]):
            self.write_json({"error": "invalid username or password"}, 401)
            return
        user_id, _, user_type = row
        token, expires_at = auth.create_session(pool, user_id)
        self.write_json(
            {"username": username, "user_type": user_type},
            extra_headers={"Set-Cookie": auth.session_cookie_header(token, expires_at)},
        )

    def handle_logout(self):
        cookies = auth.parse_cookie_header(self.headers.get("Cookie"))
        token = cookies.get(auth.SESSION_COOKIE_NAME)
        if token:
            auth.delete_session(db.get_pool(), token)
        self.write_json(
            {"ok": True},
            extra_headers={"Set-Cookie": auth.session_cookie_header(None, None, clear=True)},
        )

    def handle_me(self):
        user = self.current_user()
        if not user:
            self.write_json({"authenticated": False})
            return
        self.write_json(
            {
                "authenticated": True,
                "username": user["username"],
                "user_type": user["user_type"],
                "crm_access": user["user_type"] == "admin_user" or bool(user.get("crm_access")),
            }
        )

    # --- User management (admin-only) ---

    def _user_dict(self, row):
        return {
            "id": row[0],
            "username": row[1],
            "user_type": row[2],
            "crm_access": row[3],
            "created_at": row[4].isoformat(),
        }

    def handle_list_users(self):
        admin = self.require_admin()
        if not admin:
            return
        with db.get_pool().connection() as conn:
            rows = conn.execute(
                "SELECT id, username, user_type, crm_access, created_at FROM users ORDER BY created_at ASC"
            ).fetchall()
        self.write_json({"users": [self._user_dict(row) for row in rows]})

    def handle_create_user(self):
        admin = self.require_admin()
        if not admin:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        username = (payload.get("username") or "").strip()
        password = payload.get("password") or ""
        if len(username) < 3:
            self.write_json({"error": "username must be at least 3 characters"}, 400)
            return
        if len(password) < 6:
            self.write_json({"error": "password must be at least 6 characters"}, 400)
            return
        crm_access = bool(payload.get("crm_access"))
        password_hash = auth.hash_password(password)
        try:
            with db.get_pool().connection() as conn:
                row = conn.execute(
                    "INSERT INTO users (username, password_hash, user_type, crm_access) "
                    "VALUES (%s, %s, 'normal_user', %s) "
                    "RETURNING id, username, user_type, crm_access, created_at",
                    (username, password_hash, crm_access),
                ).fetchone()
        except psycopg.errors.UniqueViolation:
            self.write_json({"error": "username already taken"}, 409)
            return
        self.write_json(self._user_dict(row), 201)

    def handle_update_user(self, user_id):
        admin = self.require_admin()
        if not admin:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        if "crm_access" not in payload:
            self.write_json({"error": "crm_access is required"}, 400)
            return
        with db.get_pool().connection() as conn:
            row = conn.execute(
                "UPDATE users SET crm_access = %s WHERE id = %s "
                "RETURNING id, username, user_type, crm_access, created_at",
                (bool(payload.get("crm_access")), user_id),
            ).fetchone()
        if not row:
            self.write_json({"error": "user not found"}, 404)
            return
        self.write_json(self._user_dict(row))

    def handle_delete_user(self, user_id):
        admin = self.require_admin()
        if not admin:
            return
        if user_id == admin["id"]:
            self.write_json({"error": "cannot delete your own account"}, 400)
            return
        with db.get_pool().connection() as conn:
            row = conn.execute("DELETE FROM users WHERE id = %s RETURNING id", (user_id,)).fetchone()
        self.write_json({"deleted": bool(row), "id": user_id})

    # --- Conversations ---

    def handle_list_conversations(self):
        user = self.require_auth()
        if not user:
            return
        query_params = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        kind = (query_params.get("kind", ["chat"])[0] or "chat").strip()
        with db.get_pool().connection() as conn:
            rows = conn.execute(
                "SELECT id, title, created_at FROM conversations WHERE user_id = %s AND kind = %s "
                "ORDER BY created_at DESC",
                (user["id"], kind),
            ).fetchall()
        self.write_json(
            {
                "conversations": [
                    {"id": row[0], "title": row[1], "created_at": row[2].isoformat()} for row in rows
                ]
            }
        )

    def handle_conversation_messages(self, conversation_id):
        user = self.require_auth()
        if not user:
            return
        with db.get_pool().connection() as conn:
            owner = conn.execute(
                "SELECT user_id FROM conversations WHERE id = %s", (conversation_id,)
            ).fetchone()
            if not owner or owner[0] != user["id"]:
                self.write_json({"error": "not found"}, 404)
                return
            rows = conn.execute(
                "SELECT role, content, created_at FROM messages WHERE conversation_id = %s "
                "ORDER BY created_at ASC",
                (conversation_id,),
            ).fetchall()
        self.write_json(
            {
                "messages": [
                    {"role": row[0], "content": row[1], "created_at": row[2].isoformat()}
                    for row in rows
                ]
            }
        )

    def ensure_conversation(self, user, conversation_id, last_user_message, kind="chat"):
        pool = db.get_pool()
        with pool.connection() as conn:
            if conversation_id:
                row = conn.execute(
                    "SELECT id FROM conversations WHERE id = %s AND user_id = %s AND kind = %s",
                    (conversation_id, user["id"], kind),
                ).fetchone()
                if row:
                    return row[0]
            default_title = "Trợ lý gia đình" if kind == "home" else "New chat"
            title = (last_user_message or default_title)[:60]
            row = conn.execute(
                "INSERT INTO conversations (user_id, title, kind) VALUES (%s, %s, %s) RETURNING id",
                (user["id"], title, kind),
            ).fetchone()
            return row[0]

    def persist_turn(self, conversation_id, user_content, assistant_content):
        limit = int(os.getenv("CHAT_HISTORY_LIMIT", "50"))
        with db.get_pool().connection() as conn:
            conn.execute(
                "INSERT INTO messages (conversation_id, role, content) VALUES (%s, 'user', %s)",
                (conversation_id, user_content),
            )
            if assistant_content:
                conn.execute(
                    "INSERT INTO messages (conversation_id, role, content) VALUES (%s, 'assistant', %s)",
                    (conversation_id, assistant_content),
                )
            conn.execute(
                "DELETE FROM messages WHERE conversation_id = %s AND id NOT IN ("
                "SELECT id FROM messages WHERE conversation_id = %s "
                "ORDER BY created_at DESC LIMIT %s)",
                (conversation_id, conversation_id, limit),
            )

    # --- Admin / RAG documents ---

    def handle_upload_document(self):
        user = self.require_admin()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        filename = (payload.get("filename") or "document.txt").strip()
        try:
            raw_bytes = base64.b64decode(payload.get("content_base64") or "", validate=True)
        except Exception:
            self.write_json({"error": "invalid content_base64"}, 400)
            return
        max_mb = int(os.getenv("MAX_UPLOAD_MB", "20"))
        if len(raw_bytes) > max_mb * 1024 * 1024:
            self.write_json({"error": f"file exceeds {max_mb}MB limit"}, 400)
            return
        content_type = rag.guess_content_type(filename)
        try:
            document_id, chunk_count = rag.ingest_document(
                db.get_pool(), user["id"], filename, content_type, raw_bytes
            )
        except Exception as exc:
            self.write_json({"error": str(exc)}, 502)
            return
        self.write_json({"document_id": document_id, "chunks": chunk_count}, 201)

    def handle_list_documents(self):
        user = self.require_admin()
        if not user:
            return
        self.write_json({"documents": rag.list_documents(db.get_pool())})

    def handle_delete_document(self, document_id):
        user = self.require_admin()
        if not user:
            return
        rag.delete_document(db.get_pool(), document_id)
        self.write_json({"ok": True})

    # --- Persona (admin) ---

    def handle_get_persona(self):
        user = self.require_admin()
        if not user:
            return
        self.write_json(persona.get_personas(db.get_pool()))

    def handle_update_persona(self):
        user = self.require_admin()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        web_system_prompt = (
            payload.get("web_system_prompt") or payload.get("system_prompt") or ""
        ).strip()
        voice_system_prompt = (payload.get("voice_system_prompt") or "").strip()
        if not web_system_prompt:
            self.write_json({"error": "web_system_prompt must not be empty"}, 400)
            return
        if not voice_system_prompt:
            self.write_json({"error": "voice_system_prompt must not be empty"}, 400)
            return
        persona.update_personas(db.get_pool(), web_system_prompt, voice_system_prompt)
        self.write_json(
            {
                "system_prompt": web_system_prompt,
                "web_system_prompt": web_system_prompt,
                "voice_system_prompt": voice_system_prompt,
            }
        )

    def handle_list_personas(self):
        user = self.require_admin()
        if not user:
            return
        self.write_json(persona.list_personas(db.get_pool()))

    def handle_create_persona(self):
        user = self.require_admin()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        record = persona.create_persona(
            db.get_pool(),
            payload.get("name") or "",
            payload.get("description") or "",
            payload.get("web_system_prompt") or "",
            payload.get("voice_system_prompt") or "",
        )
        self.write_json(record, 201)

    def handle_update_persona_record(self, persona_id):
        user = self.require_admin()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        try:
            record = persona.update_persona_record(
                db.get_pool(),
                persona_id,
                payload.get("name") or "",
                payload.get("description") or "",
                payload.get("web_system_prompt") or "",
                payload.get("voice_system_prompt") or "",
            )
        except ValueError as exc:
            self.write_json({"error": str(exc)}, 400)
            return
        if not record:
            self.write_json({"error": "persona not found"}, 404)
            return
        self.write_json(record)

    def handle_delete_persona(self, persona_id):
        user = self.require_admin()
        if not user:
            return
        try:
            persona.delete_persona(db.get_pool(), persona_id)
        except ValueError as exc:
            self.write_json({"error": str(exc)}, 400)
            return
        self.write_json({"ok": True})

    def handle_set_active_personas(self):
        user = self.require_admin()
        if not user:
            return
        try:
            payload = self.read_json()
            web_persona_id = int(payload.get("web_persona_id"))
            voice_persona_id = int(payload.get("voice_persona_id"))
        except (json.JSONDecodeError, TypeError, ValueError):
            self.write_json({"error": "web_persona_id and voice_persona_id are required"}, 400)
            return
        try:
            self.write_json(persona.set_active_personas(db.get_pool(), web_persona_id, voice_persona_id))
        except ValueError as exc:
            self.write_json({"error": str(exc)}, 400)

    def handle_list_persona_memories(self, persona_id):
        user = self.require_admin()
        if not user:
            return
        self.write_json({"memories": persona.list_memories(db.get_pool(), persona_id)})

    def handle_add_persona_memory(self, persona_id):
        user = self.require_admin()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        source_type = (payload.get("source_type") or "note").strip()
        filename = (payload.get("filename") or "").strip()
        note = (payload.get("content") or payload.get("note") or "").strip()
        content = note
        raw_b64 = payload.get("content_base64") or ""
        if raw_b64:
            try:
                raw_bytes = base64.b64decode(raw_b64, validate=True)
            except Exception:
                self.write_json({"error": "invalid content_base64"}, 400)
                return
            max_mb = int(os.getenv("MAX_UPLOAD_MB", "20"))
            if len(raw_bytes) > max_mb * 1024 * 1024:
                self.write_json({"error": f"file exceeds {max_mb}MB limit"}, 400)
                return
            guessed_type = mimetypes.guess_type(filename)[0] or ""
            if guessed_type.startswith("image/"):
                if not content:
                    content = f"Ảnh ký ức được nạp: {filename}. Hãy dùng phần mô tả do admin cung cấp khi có."
                source_type = "image"
            else:
                try:
                    text = rag.extract_text(filename, raw_bytes)
                except Exception as exc:
                    self.write_json({"error": str(exc)}, 400)
                    return
                chunks = rag.chunk_text(text, size=1200, overlap=120)
                if note:
                    chunks.insert(0, note)
                if not chunks:
                    self.write_json({"error": "file did not contain readable text"}, 400)
                    return
                try:
                    for chunk in chunks[:30]:
                        persona.add_memory(db.get_pool(), persona_id, "file", filename, chunk)
                except ValueError as exc:
                    self.write_json({"error": str(exc)}, 400)
                    return
                self.write_json({"ok": True, "chunks": len(chunks[:30])}, 201)
                return
        try:
            memory_id = persona.add_memory(db.get_pool(), persona_id, source_type, filename, content)
        except ValueError as exc:
            self.write_json({"error": str(exc)}, 400)
            return
        self.write_json({"id": memory_id}, 201)

    def handle_delete_persona_memory(self, memory_id):
        user = self.require_admin()
        if not user:
            return
        persona.delete_memory(db.get_pool(), memory_id)
        self.write_json({"ok": True})

    # --- Voice (Raspberry Pi edge devices) ---

    def handle_user_info_parse(self):
        if not self.require_public_api_access():
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        text = (payload.get("text") or "").strip()
        if not text:
            self.write_json({"error": "text must not be empty"}, 400)
            return
        self.write_json({"fields": parse_user_info_text(text)})

    def handle_voice_transcribe(self):
        if not self.require_public_api_access():
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        filename = (payload.get("filename") or "audio.wav").strip()
        try:
            raw_bytes = base64.b64decode(payload.get("audio_base64") or "", validate=True)
        except Exception:
            self.write_json({"error": "invalid audio_base64"}, 400)
            return
        if not raw_bytes:
            self.write_json({"error": "audio_base64 must not be empty"}, 400)
            return
        max_mb = int(os.getenv("MAX_UPLOAD_MB", "20"))
        if len(raw_bytes) > max_mb * 1024 * 1024:
            self.write_json({"error": f"audio exceeds {max_mb}MB limit"}, 400)
            return
        try:
            text = stt.transcribe(raw_bytes, filename)
        except Exception as exc:
            self.write_json({"error": str(exc)}, 502)
            return
        refined_text = refine_transcript(config(), text) if text else text
        response = {"text": refined_text}
        if refined_text != text:
            response["raw_text"] = text
        self.write_json(response)

    def voice_user_id(self):
        username = os.getenv("VOICE_DEVICE_USERNAME", "voice-assistant")
        with db.get_pool().connection() as conn:
            row = conn.execute("SELECT id FROM users WHERE username = %s", (username,)).fetchone()
        return row[0]

    def ensure_voice_conversation(self, voice_user_id):
        pool = db.get_pool()
        with pool.connection() as conn:
            row = conn.execute(
                "SELECT id FROM conversations WHERE user_id = %s ORDER BY created_at ASC LIMIT 1",
                (voice_user_id,),
            ).fetchone()
            if row:
                return row[0]
            row = conn.execute(
                "INSERT INTO conversations (user_id, title) VALUES (%s, 'Voice Assistant') "
                "RETURNING id",
                (voice_user_id,),
            ).fetchone()
            return row[0]

    def ensure_voice_session_conversation(self, voice_user_id, session_id):
        session_id = re.sub(r"\s+", " ", session_id).strip()
        if not session_id:
            return self.ensure_voice_conversation(voice_user_id)
        if len(session_id) > 120:
            raise ValueError("session_id must be 120 characters or fewer")
        pool = db.get_pool()
        with pool.connection() as conn:
            row = conn.execute(
                "SELECT conversation_id FROM voice_sessions WHERE session_id = %s",
                (session_id,),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE voice_sessions SET last_seen_at = now() WHERE session_id = %s",
                    (session_id,),
                )
                return row[0]
            title = f"Voice Session {session_id}"[:60]
            row = conn.execute(
                "INSERT INTO conversations (user_id, title) VALUES (%s, %s) RETURNING id",
                (voice_user_id, title),
            ).fetchone()
            conversation_id = row[0]
            conn.execute(
                "INSERT INTO voice_sessions (session_id, user_id, conversation_id) VALUES (%s, %s, %s)",
                (session_id, voice_user_id, conversation_id),
            )
            return conversation_id

    def voice_history_messages(self, conversation_id, limit):
        with db.get_pool().connection() as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE conversation_id = %s "
                "ORDER BY created_at DESC LIMIT %s",
                (conversation_id, limit),
            ).fetchall()
        return [{"role": row[0], "content": row[1]} for row in reversed(rows)]

    def generate_voice_chatgpt_reply(self, cfg, model, temperature, pool, voice_user_id, history, text):
        """Core 'chatgpt local' voice reply: persona + relationship + memory + RAG.

        Shared by handle_voice_chat and the auto-routed handle_voice_assistant.
        Raises on LLM failure; caller is responsible for catching.
        """
        active_persona = persona.get_active_voice_persona(pool)
        messages = [{"role": "system", "content": persona_system_prompt(active_persona["voice_system_prompt"])}]
        memory_prompt = persona.format_persona_memory_prompt(
            persona.prompt_memories(pool, active_persona["id"], int(os.getenv("PERSONA_MEMORY_LIMIT", "12")))
        )
        if memory_prompt:
            messages.append({"role": "system", "content": memory_prompt})
        child_name = infer_child_speaker(history + [{"role": "user", "content": text}])
        if child_name:
            messages.append({"role": "system", "content": relationship_system_prompt(child_name)})
        if cfg["user_memory_enabled"]:
            memories = list_user_memories(pool, voice_user_id, cfg["user_memory_limit"])
            if memories:
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "Những điều đã nhớ về người dùng/thiết bị này. "
                            "Chỉ dùng khi liên quan, không cần nhắc lại là bạn có memory:\n"
                            + "\n".join(f"- {item}" for item in memories)
                        ),
                    }
                )
        context_chunks = rag.retrieve_context(pool, text)
        if context_chunks:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Use the following reference material if relevant to answer the user. "
                        "Ignore it if not relevant.\n\n" + "\n\n".join(context_chunks)
                    ),
                }
            )
        messages += history + [{"role": "user", "content": text}]

        if cfg["provider"] == "ollama":
            reply = complete_ollama(cfg, model, messages, temperature)
        else:
            reply = complete_openai(cfg, model, messages, temperature)
        if child_name:
            reply = sanitize_child_reply(reply, child_name)
        return reply

    def handle_voice_chat(self):
        if not self.require_public_api_access():
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        text = (payload.get("text") or "").strip()
        if not text:
            self.write_json({"error": "text must not be empty"}, 400)
            return
        session_id = (payload.get("session_id") or payload.get("conversation_session_id") or "").strip()

        cfg = config()
        provider = payload.get("provider") or cfg["provider"]
        model = payload.get("model") or cfg["model"]
        temperature = float(payload.get("temperature", cfg["temperature"]))
        request_cfg = {**cfg, "provider": provider, "model": model}

        pool = db.get_pool()
        voice_user_id = self.voice_user_id()
        try:
            conversation_id = self.ensure_voice_session_conversation(voice_user_id, session_id)
        except ValueError as exc:
            self.write_json({"error": str(exc)}, 400)
            return
        context_messages = int(os.getenv("VOICE_CONTEXT_MESSAGES", "10"))
        history = self.voice_history_messages(conversation_id, context_messages)

        try:
            reply = self.generate_voice_chatgpt_reply(
                request_cfg, model, temperature, pool, voice_user_id, history, text
            )
        except Exception as exc:
            self.write_json({"error": str(exc)}, 502)
            return

        self.persist_turn(conversation_id, text, reply)
        if reply:
            remember_turn_async(request_cfg, voice_user_id, text, reply)
        self.write_json({"text": reply, "conversation_id": conversation_id, "session_id": session_id or None})

    def handle_voice_assistant(self):
        """Unified voice endpoint: audio in, auto-routed reply text out.

        Device records on hot-word/silence, POSTs the clip; server transcribes,
        picks home/work/chatgpt, runs that assistant, and returns reply text
        for the device to speak. See docs/speaker-api.md.
        """
        if not self.require_public_api_access():
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        filename = (payload.get("filename") or "audio.wav").strip()
        try:
            raw_bytes = base64.b64decode(payload.get("audio_base64") or "", validate=True)
        except Exception:
            self.write_json({"error": "invalid audio_base64"}, 400)
            return
        if not raw_bytes:
            self.write_json({"error": "audio_base64 must not be empty"}, 400)
            return
        max_mb = int(os.getenv("MAX_UPLOAD_MB", "20"))
        if len(raw_bytes) > max_mb * 1024 * 1024:
            self.write_json({"error": f"audio exceeds {max_mb}MB limit"}, 400)
            return

        base_cfg = config()
        try:
            raw_text = stt.transcribe(raw_bytes, filename)
        except Exception as exc:
            self.write_json({"error": str(exc)}, 502)
            return
        text = refine_transcript(base_cfg, raw_text) if raw_text else raw_text
        if not text:
            self.write_json({"error": "no speech detected"}, 422)
            return

        session_id = (payload.get("session_id") or "").strip()
        pool = db.get_pool()
        voice_user_id = self.voice_user_id()
        voice_user = {"id": voice_user_id}
        try:
            conversation_id = self.ensure_voice_session_conversation(voice_user_id, session_id)
        except ValueError as exc:
            self.write_json({"error": str(exc)}, 400)
            return
        context_messages = int(os.getenv("VOICE_CONTEXT_MESSAGES", "10"))
        history = self.voice_history_messages(conversation_id, context_messages)
        messages = history + [{"role": "user", "content": text}]

        target = classify_voice_target(base_cfg, text)
        try:
            if target == "home":
                cfg = module_config(voice_user, "home")
                reply, _events = home_assistant.run_agent(cfg, pool, voice_user_id, messages)
            elif target == "work":
                cfg = module_config(voice_user, "work")
                reply, _events = work_schedule.run_agent(
                    cfg, pool, voice_user_id, messages, cfg.get("work_max_tool_iterations", 6)
                )
            else:
                target = "chatgpt"
                cfg = module_config(voice_user, "chatgpt")
                reply = self.generate_voice_chatgpt_reply(
                    cfg, cfg["model"], cfg["temperature"], pool, voice_user_id, history, text
                )
        except Exception as exc:
            self.write_json({"error": str(exc)}, 502)
            return

        self.persist_turn(conversation_id, text, reply)
        if reply:
            remember_turn_async(base_cfg, voice_user_id, text, reply)
        response_payload = {
            "text": reply,
            "transcript": text,
            "target": target,
            "conversation_id": conversation_id,
            "session_id": session_id or None,
        }
        if payload.get("want_audio") and reply:
            try:
                response_payload["reply_audio_base64"] = base64.b64encode(tts.synthesize(reply)).decode("ascii")
                response_payload["reply_audio_format"] = "mp3"
            except Exception as exc:
                response_payload["reply_audio_error"] = str(exc)
        self.write_json(response_payload)

    def handle_voice_speak(self):
        """Server-side TTS for clients that can't do it themselves (needs internet)."""
        if not self.require_public_api_access():
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        text = (payload.get("text") or "").strip()
        if not text:
            self.write_json({"error": "text must not be empty"}, 400)
            return
        voice = (payload.get("voice") or "").strip() or None
        try:
            audio_bytes = tts.synthesize(text, voice)
        except Exception as exc:
            self.write_json({"error": str(exc)}, 502)
            return
        self.send_headers(200, "audio/mpeg")
        self.wfile.write(audio_bytes)

    # --- Home assistant (ben_homeassistant) ---

    def handle_home_summary(self):
        user = self.require_home_access()
        if not user:
            return
        self.write_json(home_assistant.summary(db.get_pool(), user["id"]))

    def handle_home_calendar_list(self):
        user = self.require_home_access()
        if not user:
            return
        self.write_json(home_assistant.list_family_events(db.get_pool(), user["id"]))

    def handle_home_calendar_create(self):
        user = self.require_home_access()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        result = home_assistant.add_family_event(db.get_pool(), user["id"], payload)
        self.write_json(result, 400 if result.get("error") else 201)

    def handle_home_calendar_delete(self, event_id):
        user = self.require_home_access()
        if not user:
            return
        self.write_json(home_assistant.delete_family_event(db.get_pool(), user["id"], {"event_id": event_id}))

    def handle_home_chat(self):
        user = self.require_home_access()
        if not user:
            return
        cfg = module_config(user, "home")
        if not cfg["home_assistant_enabled"]:
            self.write_json({"error": "home assistant module disabled"}, 404)
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        text = (payload.get("message") or "").strip()
        if not text:
            self.write_json({"error": "message must not be empty"}, 400)
            return

        conversation_id = self.ensure_conversation(user, payload.get("conversation_id"), text, kind="home")
        history_limit = int(os.getenv("HOME_ASSISTANT_CONTEXT_MESSAGES", "20"))
        history = self.voice_history_messages(conversation_id, history_limit)
        messages = history + [{"role": "user", "content": text}]

        try:
            reply, tool_events = home_assistant.run_agent(cfg, db.get_pool(), user["id"], messages)
        except Exception as exc:
            self.write_json({"error": str(exc)}, 502)
            return

        self.persist_turn(conversation_id, text, reply)
        self.write_json(
            {
                "reply": reply,
                "conversation_id": conversation_id,
                "tool_calls": [
                    {"name": event["name"], "arguments": event["arguments"]} for event in tool_events
                ],
            }
        )

    def handle_home_add_reminder(self):
        user = self.require_home_access()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        result = home_assistant.add_reminder(db.get_pool(), user["id"], payload)
        self.write_json(result, 400 if result.get("error") else 201)

    def handle_home_complete_reminder(self, reminder_id):
        user = self.require_home_access()
        if not user:
            return
        result = home_assistant.complete_reminder(db.get_pool(), user["id"], {"reminder_id": reminder_id})
        self.write_json(result, 404 if result.get("error") else 200)

    def handle_home_delete_reminder(self, reminder_id):
        user = self.require_home_access()
        if not user:
            return
        result = home_assistant.delete_reminder(db.get_pool(), user["id"], {"reminder_id": reminder_id})
        self.write_json(result)

    def handle_home_add_note(self):
        user = self.require_home_access()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        result = home_assistant.add_note(db.get_pool(), user["id"], payload)
        self.write_json(result, 400 if result.get("error") else 201)

    def handle_home_delete_note(self, note_id):
        user = self.require_home_access()
        if not user:
            return
        result = home_assistant.delete_note(db.get_pool(), user["id"], {"note_id": note_id})
        self.write_json(result)

    def handle_home_add_shopping_item(self):
        user = self.require_home_access()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        result = home_assistant.add_shopping_item(db.get_pool(), user["id"], payload)
        self.write_json(result, 400 if result.get("error") else 201)

    def handle_home_check_shopping_item(self, item_id):
        user = self.require_home_access()
        if not user:
            return
        result = home_assistant.check_off_shopping_item(db.get_pool(), user["id"], {"item_id": item_id})
        self.write_json(result, 404 if result.get("error") else 200)

    def handle_home_delete_shopping_item(self, item_id):
        user = self.require_home_access()
        if not user:
            return
        result = home_assistant.delete_shopping_item(db.get_pool(), user["id"], {"item_id": item_id})
        self.write_json(result)

    # --- CRM: all records are scoped to the authenticated account ---

    def crm_scope_params(self):
        query_params = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        try:
            customer_id = int(query_params.get("customer_id", [""])[0])
            product_id = int(query_params.get("product_id", [""])[0])
        except (ValueError, TypeError):
            return None, None
        return customer_id, product_id

    def handle_crm_list_customers(self):
        user = self.require_crm_access()
        if not user:
            return
        self.write_json({"customers": crm.list_customers(db.get_pool())})

    def handle_crm_create_customer(self):
        user = self.require_crm_access()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        result = crm.create_customer(db.get_pool(), user["id"], payload.get("name"), payload.get("notes"))
        self.write_json(result, 400 if result.get("error") else 201)

    def handle_crm_update_customer(self, customer_id):
        user = self.require_crm_access()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        result = crm.update_customer(db.get_pool(), customer_id, payload.get("name"), payload.get("notes"))
        self.write_json(result, 404 if result.get("error") else 200)

    def handle_crm_delete_customer(self, customer_id):
        user = self.require_crm_access()
        if not user:
            return
        self.write_json(crm.delete_customer(db.get_pool(), customer_id))

    def handle_crm_list_products(self):
        user = self.require_crm_access()
        if not user:
            return
        self.write_json({"products": crm.list_products(db.get_pool())})

    def handle_crm_create_product(self):
        user = self.require_crm_access()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        result = crm.create_product(db.get_pool(), user["id"], payload.get("name"), payload.get("description"))
        self.write_json(result, 400 if result.get("error") else 201)

    def handle_crm_delete_product(self, product_id):
        user = self.require_crm_access()
        if not user:
            return
        self.write_json(crm.delete_product(db.get_pool(), product_id))

    def handle_crm_list_requirements(self):
        user = self.require_crm_access()
        if not user:
            return
        customer_id, product_id = self.crm_scope_params()
        if not customer_id or not product_id:
            self.write_json({"error": "customer_id and product_id are required"}, 400)
            return
        self.write_json({"requirements": crm.list_requirements(db.get_pool(), customer_id, product_id)})

    def handle_crm_add_requirement(self):
        user = self.require_crm_access()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        customer_id = payload.get("customer_id")
        product_id = payload.get("product_id")
        if not customer_id or not product_id:
            self.write_json({"error": "customer_id and product_id are required"}, 400)
            return
        result = crm.add_requirement(
            db.get_pool(),
            customer_id,
            product_id,
            payload.get("current_state"),
            payload.get("requirement"),
            user["id"],
        )
        self.write_json(result, 400 if result.get("error") else 201)

    def handle_crm_update_requirement(self, requirement_id):
        user = self.require_crm_access()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        result = crm.update_requirement(
            db.get_pool(), requirement_id, payload.get("current_state"), payload.get("requirement")
        )
        self.write_json(result, 404 if result.get("error") else 200)

    def handle_crm_delete_requirement(self, requirement_id):
        user = self.require_crm_access()
        if not user:
            return
        self.write_json(crm.delete_requirement(db.get_pool(), requirement_id))

    def handle_crm_list_documents(self):
        user = self.require_crm_access()
        if not user:
            return
        customer_id, product_id = self.crm_scope_params()
        if not customer_id or not product_id:
            self.write_json({"error": "customer_id and product_id are required"}, 400)
            return
        query_params = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        include_all = query_params.get("all", ["0"])[0] == "1"
        self.write_json(
            {"documents": crm.list_documents(db.get_pool(), customer_id, product_id, include_all)}
        )

    def handle_crm_upload_document(self):
        user = self.require_crm_access()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        customer_id = payload.get("customer_id")
        product_id = payload.get("product_id")
        if not customer_id or not product_id:
            self.write_json({"error": "customer_id and product_id are required"}, 400)
            return
        filename = (payload.get("filename") or "document.txt").strip()
        try:
            raw_bytes = base64.b64decode(payload.get("content_base64") or "", validate=True)
        except Exception:
            self.write_json({"error": "invalid content_base64"}, 400)
            return
        max_mb = int(os.getenv("MAX_UPLOAD_MB", "20"))
        if len(raw_bytes) > max_mb * 1024 * 1024:
            self.write_json({"error": f"file exceeds {max_mb}MB limit"}, 400)
            return
        content_type = rag.guess_content_type(filename)
        doc_type = payload.get("doc_type") or "memo"
        title = (payload.get("title") or filename).strip()
        try:
            result = crm.ingest_document(
                db.get_pool(),
                customer_id,
                product_id,
                doc_type,
                title,
                filename,
                content_type,
                raw_bytes,
                user["id"],
            )
        except Exception as exc:
            self.write_json({"error": str(exc)}, 502)
            return
        self.write_json(result, 201)

    def handle_crm_delete_document(self, document_id):
        user = self.require_crm_access()
        if not user:
            return
        self.write_json(crm.delete_document(db.get_pool(), document_id))

    def handle_crm_list_proposals(self):
        user = self.require_crm_access()
        if not user:
            return
        customer_id, product_id = self.crm_scope_params()
        if not customer_id or not product_id:
            self.write_json({"error": "customer_id and product_id are required"}, 400)
            return
        self.write_json({"proposals": crm.list_proposals(db.get_pool(), customer_id, product_id)})

    def handle_crm_create_proposal(self):
        user = self.require_crm_access()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        customer_id = payload.get("customer_id")
        product_id = payload.get("product_id")
        if not customer_id or not product_id:
            self.write_json({"error": "customer_id and product_id are required"}, 400)
            return
        result = crm.create_proposal(
            db.get_pool(), customer_id, product_id, payload.get("title"), payload.get("content"), user["id"]
        )
        self.write_json(result, 400 if result.get("error") else 201)

    def handle_crm_update_proposal(self, proposal_id):
        user = self.require_crm_access()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        result = crm.update_proposal(db.get_pool(), proposal_id, payload.get("title"), payload.get("content"))
        self.write_json(result, 400 if result.get("error") else 200)

    def handle_crm_finalize_proposal(self, proposal_id):
        user = self.require_crm_access()
        if not user:
            return
        result = crm.finalize_proposal(db.get_pool(), proposal_id)
        self.write_json(result, 404 if result.get("error") else 200)

    def handle_crm_delete_proposal(self, proposal_id):
        user = self.require_crm_access()
        if not user:
            return
        self.write_json(crm.delete_proposal(db.get_pool(), proposal_id))

    def handle_crm_chat(self):
        user = self.require_crm_access()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        customer_id = payload.get("customer_id")
        product_id = payload.get("product_id")
        text = (payload.get("message") or "").strip()
        if not customer_id or not product_id:
            self.write_json({"error": "customer_id and product_id are required"}, 400)
            return
        if not text:
            self.write_json({"error": "message must not be empty"}, 400)
            return

        pool = db.get_pool()
        customer = crm.get_customer(pool, customer_id)
        product = crm.get_product(pool, product_id)
        if not customer or not product:
            self.write_json({"error": "customer or product not found"}, 404)
            return

        cfg = module_config(user, "crm")
        conversation_id = self.ensure_conversation(user, payload.get("conversation_id"), text, kind="crm")
        history_limit = int(os.getenv("CRM_CONTEXT_MESSAGES", "20"))
        history = self.voice_history_messages(conversation_id, history_limit)
        messages = history + [{"role": "user", "content": text}]

        try:
            reply, tool_events = crm.run_agent(cfg, pool, customer, product, user["id"], messages)
        except Exception as exc:
            self.write_json({"error": str(exc)}, 502)
            return

        self.persist_turn(conversation_id, text, reply)
        self.write_json(
            {
                "reply": reply,
                "conversation_id": conversation_id,
                "tool_calls": [
                    {"name": event["name"], "arguments": event["arguments"]} for event in tool_events
                ],
            }
        )

    def handle_crm_set_proposal_active(self, proposal_id):
        user = self.require_crm_access()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        result = crm.set_proposal_active(db.get_pool(), proposal_id, payload.get("active", True))
        self.write_json(result, 404 if result.get("error") else 200)

    def handle_crm_list_proposal_attachments(self, proposal_id):
        user = self.require_crm_access()
        if not user:
            return
        self.write_json({"attachments": crm.list_proposal_attachments(db.get_pool(), proposal_id)})

    def handle_crm_upload_proposal_attachment(self, proposal_id):
        user = self.require_crm_access()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        filename = (payload.get("filename") or "").strip()
        if not filename:
            self.write_json({"error": "filename is required"}, 400)
            return
        try:
            raw_bytes = base64.b64decode(payload.get("content_base64") or "", validate=True)
        except Exception:
            self.write_json({"error": "invalid content_base64"}, 400)
            return
        max_mb = int(os.getenv("MAX_UPLOAD_MB", "20"))
        if len(raw_bytes) > max_mb * 1024 * 1024:
            self.write_json({"error": f"file exceeds {max_mb}MB limit"}, 400)
            return
        try:
            result = crm.ingest_proposal_attachment(db.get_pool(), proposal_id, filename, raw_bytes, user["id"])
        except Exception as exc:
            self.write_json({"error": str(exc)}, 502)
            return
        self.write_json(result, 400 if result.get("error") else 201)

    def handle_crm_delete_proposal_attachment(self, attachment_id):
        user = self.require_crm_access()
        if not user:
            return
        self.write_json(crm.delete_proposal_attachment(db.get_pool(), attachment_id))

    # --- Personal work schedule (location lookup for future voice/Raspberry Pi use) ---

    def handle_schedule_list(self):
        user = self.require_work_access()
        if not user:
            return
        query_params = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        start_from = work_schedule.parse_datetime((query_params.get("from") or [""])[0])
        start_to = work_schedule.parse_datetime((query_params.get("to") or [""])[0])
        entries = work_schedule.list_entries(db.get_pool(), user["id"], start_from, start_to)
        self.write_json({"entries": entries})

    def handle_schedule_create(self):
        user = self.require_work_access()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        result = work_schedule.create_entry(
            db.get_pool(),
            user["id"],
            payload.get("customer_id"),
            payload.get("title"),
            payload.get("location"),
            payload.get("start_at"),
            payload.get("end_at"),
        )
        self.write_json(result, 400 if result.get("error") else 201)

    def handle_schedule_update(self, entry_id):
        user = self.require_work_access()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        result = work_schedule.update_entry(
            db.get_pool(),
            user["id"],
            entry_id,
            payload.get("customer_id"),
            payload.get("title"),
            payload.get("location"),
            payload.get("start_at"),
            payload.get("end_at"),
        )
        self.write_json(result, 400 if result.get("error") else 200)

    def handle_schedule_delete(self, entry_id):
        user = self.require_work_access()
        if not user:
            return
        self.write_json(work_schedule.delete_entry(db.get_pool(), user["id"], entry_id))

    def handle_schedule_done(self, entry_id):
        user = self.require_work_access()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        result = work_schedule.set_entry_done(db.get_pool(), user["id"], entry_id, bool(payload.get("done", True)))
        self.write_json(result, 400 if result.get("error") else 200)

    def handle_schedule_location(self):
        user = self.require_work_access()
        if not user:
            return
        query_params = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        at = work_schedule.parse_datetime((query_params.get("at") or [""])[0])
        self.write_json(work_schedule.current_location(db.get_pool(), user["id"], at))

    def handle_work_tasks_list(self):
        user = self.require_work_access()
        if not user:
            return
        self.write_json({"tasks": work_schedule.list_tasks(db.get_pool(), user["id"])})

    def handle_work_tasks_create(self):
        user = self.require_work_access()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        result = work_schedule.create_task(db.get_pool(), user["id"], payload.get("title"), payload.get("due_at"))
        self.write_json(result, 400 if result.get("error") else 201)

    def handle_work_task_update(self, task_id):
        user = self.require_work_access()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        result = work_schedule.update_task(db.get_pool(), user["id"], task_id, payload.get("title"), payload.get("due_at"))
        self.write_json(result, 400 if result.get("error") else 200)

    def handle_work_task_done(self, task_id):
        user = self.require_work_access()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        result = work_schedule.set_task_done(db.get_pool(), user["id"], task_id, bool(payload.get("done", True)))
        self.write_json(result, 400 if result.get("error") else 200)

    def handle_work_task_delete(self, task_id):
        user = self.require_work_access()
        if not user:
            return
        self.write_json(work_schedule.delete_task(db.get_pool(), user["id"], task_id))

    def handle_work_chat(self):
        user = self.require_work_access()
        if not user:
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        text = (payload.get("message") or "").strip()
        if not text:
            self.write_json({"error": "message must not be empty"}, 400)
            return
        conversation_id = self.ensure_conversation(user, payload.get("conversation_id"), text, kind="work")
        history = self.voice_history_messages(conversation_id, int(os.getenv("WORK_CONTEXT_MESSAGES", "20")))
        try:
            work_cfg = module_config(user, "work")
            reply, events = work_schedule.run_agent(work_cfg, db.get_pool(), user["id"], history + [{"role": "user", "content": text}], work_cfg.get("work_max_tool_iterations", 6))
        except Exception as exc:
            self.write_json({"error": str(exc)}, 502)
            return
        self.persist_turn(conversation_id, text, reply)
        self.write_json({"reply": reply, "conversation_id": conversation_id,
                         "tool_calls": [{"name": e["name"], "arguments": e["arguments"]} for e in events]})

    # --- Chat ---

    def handle_chat(self):
        if not self.require_public_api_access():
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        cfg = config()
        provider = payload.get("provider") or cfg["provider"]
        messages = payload.get("messages") or []
        model = payload.get("model") or cfg["model"]
        temperature = float(payload.get("temperature", cfg["temperature"]))
        request_cfg = {**cfg, "provider": provider, "model": model}
        conversation_id = payload.get("conversation_id")
        if not isinstance(messages, list) or not messages:
            self.write_json({"error": "messages must be a non-empty list"}, 400)
            return

        last_user_message = next(
            (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), ""
        )

        user = self.current_user()
        if user:
            conversation_id = self.ensure_conversation(user, conversation_id, last_user_message)

        pool = db.get_pool()
        system_messages = []
        if cfg["chat_persona_enabled"]:
            active_persona = persona.get_active_web_persona(pool)
            system_messages.append(
                {"role": "system", "content": persona_system_prompt(active_persona["web_system_prompt"])}
            )
            memory_prompt = persona.format_persona_memory_prompt(
                persona.prompt_memories(pool, active_persona["id"], int(os.getenv("PERSONA_MEMORY_LIMIT", "12")))
            )
            if memory_prompt:
                system_messages.append({"role": "system", "content": memory_prompt})
        child_name = infer_child_speaker(messages)
        if child_name:
            system_messages.append({"role": "system", "content": relationship_system_prompt(child_name)})
        if user and cfg["user_memory_enabled"]:
            memories = list_user_memories(pool, user["id"], cfg["user_memory_limit"])
            if memories:
                system_messages.append(
                    {
                        "role": "system",
                        "content": (
                            "You know these remembered facts about this logged-in user. "
                            "Use them only when relevant, and do not mention memory unless useful:\n"
                            + "\n".join(f"- {item}" for item in memories)
                        ),
                    }
                )
        if last_user_message:
            context_chunks = rag.retrieve_context(pool, last_user_message)
            if context_chunks:
                system_messages.append(
                    {
                        "role": "system",
                        "content": (
                            "Use the following reference material if relevant to answer the user. "
                            "Ignore it if not relevant.\n\n" + "\n\n".join(context_chunks)
                        ),
                    }
                )
        chat_messages = system_messages + messages

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        if user and conversation_id:
            self.sse({"conversation_id": conversation_id})

        assistant_chunks = []
        try:
            if child_name:
                if provider == "ollama":
                    reply = complete_ollama(cfg, model, chat_messages, temperature)
                else:
                    reply = complete_openai(cfg, model, chat_messages, temperature)
                reply = sanitize_child_reply(reply, child_name)
                if reply:
                    self.sse({"delta": reply})
                    assistant_chunks = [reply]
            elif provider == "ollama":
                assistant_chunks = self.stream_ollama(cfg, model, chat_messages, temperature)
            else:
                assistant_chunks = self.stream_openai(cfg, model, chat_messages, temperature)
            self.sse({"done": True})
        except Exception as exc:
            self.sse({"error": str(exc), "done": True})
        finally:
            self.close_connection = True

        if user and conversation_id:
            assistant_text = "".join(assistant_chunks)
            self.persist_turn(conversation_id, last_user_message, assistant_text)
            if assistant_text:
                remember_turn_async(request_cfg, user["id"], last_user_message, assistant_text)

    # --- Image generation ---

    def handle_image_generate(self):
        if not self.require_public_api_access():
            return
        if not self.feature_flag_allowed(self.current_user(), "image_generation"):
            self.write_json({"error": "Image generation feature is currently disabled"}, 403)
            return
        try:
            payload = self.read_json()
        except json.JSONDecodeError:
            self.write_json({"error": "Invalid JSON"}, 400)
            return
        prompt = (payload.get("prompt") or "").strip()
        if not prompt:
            self.write_json({"error": "prompt is required"}, 400)
            return
        cfg = config()
        try:
            image_bytes = generate_image(cfg, prompt)
            url = save_generated_image(image_bytes, prompt)
        except Exception as exc:
            self.write_json({"error": str(exc)}, 502)
            return
        self.write_json({"url": url, "prompt": prompt, "provider": cfg["image_provider"]})

    def sse(self, data):
        self.wfile.write(b"data: ")
        self.wfile.write(json_bytes(data))
        self.wfile.write(b"\n\n")
        self.wfile.flush()

    def stream_ollama(self, cfg, model, messages, temperature):
        collected = []
        think_filter = None if cfg["ollama_think"] else ThinkStreamFilter()
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "think": cfg["ollama_think"],
            "options": {"temperature": temperature},
        }
        if cfg["ollama_num_ctx"]:
            payload["options"]["num_ctx"] = int(cfg["ollama_num_ctx"])
        request = urllib.request.Request(
            f"{cfg['ollama_url']}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=600) as response:
            for raw_line in response:
                if not raw_line.strip():
                    continue
                item = json.loads(raw_line.decode("utf-8"))
                content = (item.get("message") or {}).get("content")
                if content:
                    visible = think_filter.feed(content) if think_filter else content
                    if visible:
                        self.sse({"delta": visible})
                        collected.append(visible)
                if item.get("done"):
                    break
        return collected

    def stream_openai(self, cfg, model, messages, temperature):
        collected = []
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if cfg["max_tokens"]:
            payload["max_tokens"] = int(cfg["max_tokens"])
        headers = {"Content-Type": "application/json"}
        if cfg["openai_api_key"]:
            headers["Authorization"] = f"Bearer {cfg['openai_api_key']}"
        request = urllib.request.Request(
            f"{cfg['openai_base_url']}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
        )
        with urllib.request.urlopen(request, timeout=600) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                item = json.loads(data)
                choices = item.get("choices") or []
                if not choices:
                    continue
                content = (choices[0].get("delta") or {}).get("content")
                if content:
                    self.sse({"delta": content})
                    collected.append(content)
        return collected


def main():
    cfg = config()
    db.bootstrap()

    server = ThreadingHTTPServer((cfg["host"], cfg["port"]), DuyGPTHandler)
    print(f"DuyGPT running at http://{cfg['host']}:{cfg['port']}")

    if cfg["ssl_cert_file"] and cfg["ssl_key_file"]:
        https_server = ThreadingHTTPServer((cfg["https_host"], cfg["https_port"]), DuyGPTHandler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cfg["ssl_cert_file"], cfg["ssl_key_file"])
        https_server.socket = context.wrap_socket(https_server.socket, server_side=True)
        threading.Thread(target=https_server.serve_forever, daemon=True).start()
        print(f"DuyGPT voice/demo HTTPS running at https://{cfg['https_host']}:{cfg['https_port']}")

    print(f"Provider: {cfg['provider']} | Model: {cfg['model']}")
    server.serve_forever()


if __name__ == "__main__":
    main()
