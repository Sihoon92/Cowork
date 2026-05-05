"""LLM provider configuration loader.

회사 내부 환경에서 LLM API를 사용할 때:
- 시스템에 설정된 HTTP(S)_PROXY가 사내 LLM endpoint 호출을 방해하므로
  이 모듈 import 시점에 일괄 제거한다.
- provider/base_url/api_key/model 등은 `.env` 파일 또는 환경변수로 주입한다.

지원 provider:
  - ollama  : 로컬 Ollama 서버 (집/외부 환경 기본값)
  - openai  : OpenAI 호환 REST API (사내 LLM gateway 등)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    _DOTENV_PATH = Path(__file__).resolve().parents[2] / ".env"
    if _DOTENV_PATH.exists():
        load_dotenv(_DOTENV_PATH, override=False)
except ImportError:
    # python-dotenv 미설치 시에도 시스템 환경변수만으로 동작 가능하도록 graceful fallback
    pass


# ---------------------------------------------------------------------------
# Proxy 초기화 — 사내 LLM endpoint는 사내망 직결이라 프록시 통과 시 실패한다.
# import 시점에 한 번만 수행 (멱등).
# ---------------------------------------------------------------------------
def _strip_proxy_env() -> None:
    for var in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
        "http_proxy", "https_proxy", "all_proxy",
    ):
        os.environ.pop(var, None)


_strip_proxy_env()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LLMConfig:
    provider: str           # "ollama" | "openai"
    base_url: str
    api_key: str            # ollama provider면 빈 문자열 허용
    model: str              # 기본 텍스트 모델
    vision_model: str       # 멀티모달 모델
    timeout: int
    verify_ssl: bool


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def load_config() -> LLMConfig:
    """환경변수에서 LLM 설정을 읽어 LLMConfig를 반환한다.

    매 호출마다 새로 읽으므로, 테스트에서 monkeypatch로 환경변수를 바꾸면
    즉시 반영된다.
    """
    provider = _env("LLM_PROVIDER", "ollama").lower()

    if provider == "ollama":
        return LLMConfig(
            provider="ollama",
            base_url=_env("LLM_BASE_URL", "http://localhost:11434"),
            api_key="",
            model=_env("LLM_MODEL", "qwen2.5-coder:7b"),
            vision_model=_env("LLM_VISION_MODEL", "gemma4:e4b"),
            timeout=_env_int("LLM_TIMEOUT", 300),
            verify_ssl=_env_bool("LLM_VERIFY_SSL", True),
        )

    if provider == "openai":
        base_url = _env("LLM_BASE_URL")
        api_key = _env("LLM_API_KEY")
        if not base_url:
            raise RuntimeError(
                "LLM_PROVIDER=openai 인 경우 LLM_BASE_URL 환경변수가 필요합니다. "
                ".env 파일을 확인하세요."
            )
        if not api_key:
            raise RuntimeError(
                "LLM_PROVIDER=openai 인 경우 LLM_API_KEY 환경변수가 필요합니다."
            )
        return LLMConfig(
            provider="openai",
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            model=_env("LLM_MODEL", "gpt-oss-120b"),
            vision_model=_env("LLM_VISION_MODEL", "gemma-4-31B-it"),
            timeout=_env_int("LLM_TIMEOUT", 300),
            verify_ssl=_env_bool("LLM_VERIFY_SSL", True),
        )

    raise RuntimeError(
        f"지원하지 않는 LLM_PROVIDER: '{provider}'. 'ollama' 또는 'openai' 중 하나여야 합니다."
    )
