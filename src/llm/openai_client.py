"""OpenAI-compatible LLM client.

사내 LLM gateway(OpenAI 호환 스펙)를 호출하기 위한 얇은 wrapper.
SDK를 쓰지 않고 requests로 직접 호출 — ollama_client와 동일한 컨벤션.

`requests.Session(trust_env=False)`로 시스템 프록시까지 무시한다
(config.py에서 env 변수를 비우는 것과 이중 안전장치).
"""
from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Any

import requests

from src.llm.config import LLMConfig


def _session(verify_ssl: bool) -> requests.Session:
    s = requests.Session()
    s.trust_env = False  # 시스템 프록시/환경변수 무시
    s.verify = verify_ssl
    return s


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _extract_text(payload: dict[str, Any]) -> str:
    """OpenAI chat completions 응답에서 첫 번째 메시지 텍스트를 추출."""
    try:
        return payload["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"예상치 못한 LLM 응답 형식: {payload!r}") from exc


def chat(
    cfg: LLMConfig,
    prompt: str,
    *,
    model: str | None = None,
    timeout: int | None = None,
    format: str | dict | None = None,
) -> str:
    """OpenAI 호환 /chat/completions 호출.

    `format`이 "json" 또는 dict이면 `response_format={"type": "json_object"}`로
    JSON 모드를 활성화한다 (사내 gateway가 지원하는 경우에만 의미 있음).
    """
    url = f"{cfg.base_url}/chat/completions"
    body: dict[str, Any] = {
        "model": model or cfg.model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    if format is not None:
        body["response_format"] = {"type": "json_object"}

    with _session(cfg.verify_ssl) as s:
        r = s.post(
            url,
            headers=_headers(cfg.api_key),
            data=json.dumps(body),
            timeout=timeout or cfg.timeout,
        )
        r.raise_for_status()
        return _extract_text(r.json())


def chat_with_image(
    cfg: LLMConfig,
    prompt: str,
    image_path: str,
    *,
    model: str | None = None,
    timeout: int | None = None,
) -> str:
    """OpenAI 호환 멀티모달 호출 — image_url(base64 data URI) 방식."""
    p = Path(image_path)
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    data_uri = f"data:{mime};base64,{b64}"

    url = f"{cfg.base_url}/chat/completions"
    body = {
        "model": model or cfg.vision_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            }
        ],
        "stream": False,
    }

    with _session(cfg.verify_ssl) as s:
        r = s.post(
            url,
            headers=_headers(cfg.api_key),
            data=json.dumps(body),
            timeout=timeout or cfg.timeout,
        )
        r.raise_for_status()
        return _extract_text(r.json())


def is_available(cfg: LLMConfig) -> bool:
    """models 엔드포인트로 간단 헬스체크."""
    try:
        with _session(cfg.verify_ssl) as s:
            r = s.get(
                f"{cfg.base_url}/models",
                headers=_headers(cfg.api_key),
                timeout=10,
            )
        return r.status_code < 500
    except requests.RequestException:
        return False
