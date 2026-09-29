"""Unified LLM access for remote OpenAI-compatible APIs and local Ollama."""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None

if load_dotenv:
    load_dotenv()
else:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


DEFAULT_REMOTE_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_REMOTE_TEXT_MODEL = "doubao-seed-2-1-pro-260628"
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_TEXT_MODEL = "qwen2.5:7b"
DEFAULT_OLLAMA_VISION_MODEL = "qwen3-vl:4b-instruct"
DEFAULT_SEED = 42


def provider() -> str:
    return os.getenv("LLM_PROVIDER", "remote").strip().lower() or "remote"


def is_ollama_provider() -> bool:
    return provider() == "ollama"


def remote_text_model() -> str:
    return os.getenv("LLM_TEXT_MODEL", DEFAULT_REMOTE_TEXT_MODEL).strip() or DEFAULT_REMOTE_TEXT_MODEL


def ollama_host() -> str:
    return os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST).strip() or DEFAULT_OLLAMA_HOST


def ollama_text_model() -> str:
    return os.getenv("OLLAMA_TEXT_MODEL", DEFAULT_OLLAMA_TEXT_MODEL).strip() or DEFAULT_OLLAMA_TEXT_MODEL


def ollama_vision_model() -> str:
    return os.getenv("OLLAMA_VISION_MODEL", DEFAULT_OLLAMA_VISION_MODEL).strip() or DEFAULT_OLLAMA_VISION_MODEL


def text_model() -> str:
    return ollama_text_model() if is_ollama_provider() else remote_text_model()


def vision_model() -> str:
    return ollama_vision_model()


def _ollama_request_json(
    host: str, route: str, payload: dict[str, Any] | None = None
) -> Any:
    url = f"{host.rstrip('/')}{route}"
    data = (
        None
        if payload is None
        else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    )
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="GET" if data is None else "POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接 Ollama ({url})，请检查本地 Ollama 服务。") from exc


def _content_from_response(response: Any) -> str:
    message = response.choices[0].message
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
    return str(content or "")


def _remote_chat_text(
    messages: list[dict[str, Any]],
    *,
    model: str | None,
    temperature: float,
    json_response: bool,
) -> str:
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("远程模型调用失败：缺少 LLM_API_KEY，请在 .env 或环境变量中填写。")
    base_url = os.getenv("LLM_BASE_URL", DEFAULT_REMOTE_BASE_URL).strip() or DEFAULT_REMOTE_BASE_URL
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("远程模型调用失败：缺少 openai 依赖，请先安装 requirements.txt。") from exc

    client = OpenAI(api_key=api_key, base_url=base_url)
    kwargs: dict[str, Any] = {
        "model": model or remote_text_model(),
        "messages": messages,
        "temperature": temperature,
    }
    if json_response:
        kwargs["response_format"] = {"type": "json_object"}
    debug_timing = os.getenv("LLM_DEBUG_TIMING", "").strip().lower() in {"1", "true", "yes"}
    started_at = time.perf_counter()
    try:
        response = client.chat.completions.create(**kwargs)
    except Exception as exc:
        if json_response and "response_format" in kwargs:
            kwargs.pop("response_format", None)
            try:
                response = client.chat.completions.create(**kwargs)
            except Exception as retry_exc:
                raise RuntimeError(f"远程模型调用失败：{retry_exc}") from retry_exc
        else:
            raise RuntimeError(f"远程模型调用失败：{exc}") from exc
    if debug_timing:
        elapsed = time.perf_counter() - started_at
        print(
            f"Remote LLM call finished in {elapsed:.2f}s; model={kwargs['model']}; json_response={json_response}",
            flush=True,
        )
    return _content_from_response(response)


def _ollama_chat_text(
    messages: list[dict[str, Any]],
    *,
    model: str | None,
    host: str | None = None,
    schema: dict[str, Any] | None,
    temperature: float,
    images: list[str] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "model": model or ollama_text_model(),
        "stream": False,
        "options": {"temperature": temperature, "seed": DEFAULT_SEED},
        "messages": messages,
    }
    if schema is not None:
        payload["format"] = schema
    if images:
        payload["messages"] = _attach_ollama_images(messages, images)
        payload["model"] = model or ollama_vision_model()
    response = _ollama_request_json(host or ollama_host(), "/api/chat", payload)
    return str(response.get("message", {}).get("content", ""))


def _extract_json_object(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _json_from_text(text: str, purpose: str = "模型") -> Any:
    try:
        return _extract_json_object(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{purpose}未返回有效 JSON：{text}") from exc


def _attach_ollama_images(
    messages: list[dict[str, Any]], images: list[str]
) -> list[dict[str, Any]]:
    prepared = [dict(message) for message in messages]
    if not prepared:
        prepared = [{"role": "user", "content": ""}]
    prepared[-1] = {**prepared[-1], "images": images}
    return prepared


def _image_to_data_url(image: str) -> str:
    if image.startswith("data:"):
        return image
    return f"data:image/jpeg;base64,{image}"


def _remote_vision_messages(
    messages: list[dict[str, Any]], images: list[str]
) -> list[dict[str, Any]]:
    prepared = [dict(message) for message in messages]
    if not prepared:
        prepared = [{"role": "user", "content": ""}]
    last = prepared[-1]
    content = last.get("content", "")
    parts: list[dict[str, Any]] = []
    if content:
        parts.append({"type": "text", "text": str(content)})
    for image in images:
        parts.append({"type": "image_url", "image_url": {"url": _image_to_data_url(image)}})
    prepared[-1] = {**last, "content": parts}
    return prepared


def chat_text(
    messages: list[dict[str, Any]],
    temperature: float = 0,
    model: str | None = None,
    host: str | None = None,
) -> str:
    if is_ollama_provider():
        return _ollama_chat_text(
            messages, model=model, host=host, schema=None, temperature=temperature
        )
    return _remote_chat_text(
        messages, model=model, temperature=temperature, json_response=False
    )


def chat_json(
    messages: list[dict[str, Any]],
    schema: dict[str, Any] | None = None,
    temperature: float = 0,
    model: str | None = None,
    host: str | None = None,
) -> Any:
    if is_ollama_provider():
        text = _ollama_chat_text(
            messages, model=model, host=host, schema=schema, temperature=temperature
        )
    else:
        text = _remote_chat_text(
            messages, model=model, temperature=temperature, json_response=schema is not None
        )
    return _json_from_text(text)


def chat_vision(
    messages: list[dict[str, Any]],
    images: list[str] | None = None,
    schema: dict[str, Any] | None = None,
    temperature: float = 0,
    model: str | None = None,
    host: str | None = None,
) -> Any:
    image_list = list(images or [])
    if is_ollama_provider():
        text = _ollama_chat_text(
            messages,
            model=model or ollama_vision_model(),
            host=host,
            schema=schema,
            temperature=temperature,
            images=image_list,
        )
        return _json_from_text(text, "视觉模型") if schema is not None else text

    if image_list:
        try:
            remote_messages = _remote_vision_messages(messages, image_list)
            text = _remote_chat_text(
                remote_messages,
                model=model or remote_text_model(),
                temperature=temperature,
                json_response=schema is not None,
            )
            return _json_from_text(text, "远程视觉模型") if schema is not None else text
        except RuntimeError as remote_exc:
            try:
                text = _ollama_chat_text(
                    messages,
                    model=ollama_vision_model(),
                    host=host,
                    schema=schema,
                    temperature=temperature,
                    images=image_list,
                )
                return _json_from_text(text, "Ollama 视觉 fallback") if schema is not None else text
            except RuntimeError as ollama_exc:
                raise RuntimeError(
                    "远程视觉调用失败，且本地 Ollama 视觉 fallback 不可用。"
                    f"远程错误：{remote_exc}；Ollama 错误：{ollama_exc}"
                ) from ollama_exc

    return chat_json(messages, schema=schema, temperature=temperature, model=model, host=host)


def image_bytes_to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("ascii")
