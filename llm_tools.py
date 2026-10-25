"""Shared LLM tool-calling engine used by on-prem agent modules (home_assistant, crm).

Talks to whichever backend DuyGPT is already configured with (Ollama or an
OpenAI-compatible endpoint) -- see app.config(). Domain-agnostic: callers
supply the tool specs and per-tool handler callables.
"""
import json
import urllib.request


def http_json(url, payload, headers=None, timeout=180):
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=req_headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def chat_ollama(cfg, model, messages, tools):
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": cfg.get("ollama_think", False),
        "options": {"temperature": 0.4},
    }
    if cfg.get("ollama_num_ctx"):
        payload["options"]["num_ctx"] = int(cfg["ollama_num_ctx"])
    if cfg.get("response_schema"):
        payload["format"] = cfg["response_schema"]
        payload["options"]["temperature"] = 0
    if cfg.get("llm_max_output_tokens"):
        payload["options"]["num_predict"] = cfg["llm_max_output_tokens"]
    if tools:
        payload["tools"] = tools
    data = http_json(f"{cfg['ollama_url']}/api/chat", payload, timeout=cfg.get("llm_timeout_seconds", 180))
    return {**(data.get("message") or {}), "finish_reason": data.get("done_reason")}


def chat_openai(cfg, model, messages, tools):
    payload = {"model": model, "messages": messages, "temperature": 0.4, "stream": False}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    headers = {}
    if cfg.get("openai_api_key"):
        headers["Authorization"] = f"Bearer {cfg['openai_api_key']}"
    data = http_json(f"{cfg['openai_base_url']}/chat/completions", payload, headers=headers,
                     timeout=cfg.get("llm_timeout_seconds", 180))
    choices = data.get("choices") or []
    if not choices:
        return {}
    return {**(choices[0].get("message") or {}), "finish_reason": choices[0].get("finish_reason")}


def chat_with_tools(cfg, model, messages, tools):
    if cfg.get("provider") == "ollama":
        return chat_ollama(cfg, model, messages, tools)
    return chat_openai(cfg, model, messages, tools)


def parse_tool_call(call):
    function = call.get("function") or {}
    name = function.get("name") or ""
    raw_args = function.get("arguments")
    if isinstance(raw_args, str):
        try:
            arguments = json.loads(raw_args) if raw_args.strip() else {}
        except json.JSONDecodeError:
            arguments = {}
    elif isinstance(raw_args, dict):
        arguments = raw_args
    else:
        arguments = {}
    return name, arguments


DEFAULT_EXHAUSTED_REPLY = "Xin lỗi, tôi chưa xử lý xong yêu cầu này, bạn thử nói lại giúp mình nhé."


def run_tool_loop(cfg, model, messages, tools, handlers, max_iterations=6, exhausted_reply=None):
    """Run a tool-calling agent loop.

    handlers: dict of tool name -> callable(arguments) -> JSON-serializable result.
    Returns (reply_text, tool_events) where tool_events is a list of
    {"name", "arguments", "result"} in call order.
    """
    working_messages = list(messages)
    tool_events = []
    for _ in range(max_iterations):
        message = chat_with_tools(cfg, model, working_messages, tools)
        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            return message.get("content") or "", tool_events

        working_messages.append(
            {"role": "assistant", "content": message.get("content") or "", "tool_calls": tool_calls}
        )
        for call in tool_calls:
            name, arguments = parse_tool_call(call)
            handler = handlers.get(name)
            result = handler(arguments) if handler else {"error": f"unknown tool {name}"}
            tool_events.append({"name": name, "arguments": arguments, "result": result})
            working_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", name),
                    "name": name,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

    final_message = chat_with_tools(cfg, model, working_messages, tools=None)
    return final_message.get("content") or (exhausted_reply or DEFAULT_EXHAUSTED_REPLY), tool_events
