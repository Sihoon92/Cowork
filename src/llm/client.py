"""LLM provider facade.

기존 코드(`from src.llm.ollama_client import chat, ...`)를
`from src.llm.client import chat, ...`로만 바꾸면 provider가 자동 분기된다.

provider는 `LLM_PROVIDER` 환경변수로 결정 (ollama | openai).
설정 자세한 내용은 `src/llm/config.py` 및 `.env.example` 참고.
"""
from __future__ import annotations

from src.llm.config import load_config
from src.llm import ollama_client, openai_client


# 모듈 import 시점에 1회 로드.
# (테스트에서 환경변수를 바꿔서 다시 로드하고 싶다면 reload_config() 사용)
_cfg = load_config()


def reload_config() -> None:
    """테스트나 런타임 재설정용 — 환경변수 변경 후 호출."""
    global _cfg, DEFAULT_MODEL, VISION_MODEL, PROVIDER
    _cfg = load_config()
    DEFAULT_MODEL = _cfg.model
    VISION_MODEL = _cfg.vision_model
    PROVIDER = _cfg.provider


# 기존 코드 호환을 위한 모듈 레벨 상수
DEFAULT_MODEL = _cfg.model
VISION_MODEL = _cfg.vision_model
PROVIDER = _cfg.provider


def chat(
    prompt: str,
    model: str | None = None,
    stream: bool = False,
    timeout: int | None = None,
    format: str | dict | None = None,
) -> str:
    if _cfg.provider == "ollama":
        return ollama_client.chat(
            prompt,
            model=model or _cfg.model,
            stream=stream,
            timeout=timeout or _cfg.timeout,
            format=format,
        )
    # openai 호환은 stream을 지원하지 않는 (사내 gateway 미지원 가능성) 단순화 모드
    return openai_client.chat(
        _cfg, prompt, model=model, timeout=timeout, format=format,
    )


def chat_with_image(
    prompt: str,
    image_path: str,
    *,
    model: str | None = None,
    timeout: int | None = None,
) -> str:
    if _cfg.provider == "ollama":
        return ollama_client.chat_with_image(
            prompt,
            image_path,
            model=model or _cfg.vision_model,
            timeout=timeout or _cfg.timeout,
        )
    return openai_client.chat_with_image(
        _cfg, prompt, image_path, model=model, timeout=timeout,
    )


def is_available() -> bool:
    if _cfg.provider == "ollama":
        return ollama_client.is_available()
    return openai_client.is_available(_cfg)


def get_config():
    """현재 활성 LLMConfig 반환 (디버깅·테스트용)."""
    return _cfg
