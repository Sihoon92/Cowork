"""LLM 연결 점검 스크립트.

회사 내부 환경에서 코드 변경 없이 LLM 연결만 먼저 검증하기 위한 도구.

사용:
    PYTHONIOENCODING=utf-8 python scripts/check_llm.py
    PYTHONIOENCODING=utf-8 python scripts/check_llm.py --image path/to/img.png

흐름:
    1) 활성 config 출력 (api_key는 마스킹)
    2) is_available() 체크
    3) 짧은 텍스트 ping → 응답·지연 출력
    4) (옵션) 이미지가 주어지면 vision 모델로도 ping
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# 프로젝트 루트를 import 경로에 추가 (scripts/에서 직접 실행 가능하게)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.llm.client import (  # noqa: E402
    chat,
    chat_with_image,
    is_available,
    get_config,
)


def _mask(secret: str) -> str:
    if not secret:
        return "(empty)"
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}...{secret[-4:]}"


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM 연결 점검")
    parser.add_argument("--image", help="vision 모델까지 점검할 이미지 경로", default=None)
    parser.add_argument("--prompt", default="Reply with the single word: pong")
    args = parser.parse_args()

    cfg = get_config()
    print("=" * 60)
    print("LLM Config")
    print("-" * 60)
    print(f"  provider     : {cfg.provider}")
    print(f"  base_url     : {cfg.base_url}")
    print(f"  api_key      : {_mask(cfg.api_key)}")
    print(f"  model        : {cfg.model}")
    print(f"  vision_model : {cfg.vision_model}")
    print(f"  timeout      : {cfg.timeout}s")
    print(f"  verify_ssl   : {cfg.verify_ssl}")
    print("=" * 60)

    print("\n[1/3] is_available() ...")
    if not is_available():
        print("  ❌ 서버에 도달할 수 없음. base_url / 네트워크 / api_key 확인 필요.")
        return 1
    print("  ✅ reachable")

    print(f"\n[2/3] text chat ping ({cfg.model}) ...")
    t0 = time.time()
    try:
        reply = chat(args.prompt)
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ 호출 실패: {type(e).__name__}: {e}")
        return 2
    dt = time.time() - t0
    print(f"  ✅ {dt:.2f}s | response: {reply.strip()[:200]}")

    if args.image:
        print(f"\n[3/3] vision chat ping ({cfg.vision_model}) ...")
        if not Path(args.image).exists():
            print(f"  ⚠ 이미지 파일 없음: {args.image} — 스킵")
            return 0
        t0 = time.time()
        try:
            reply = chat_with_image("Describe this image in one short sentence.", args.image)
        except Exception as e:  # noqa: BLE001
            print(f"  ❌ vision 호출 실패: {type(e).__name__}: {e}")
            return 3
        dt = time.time() - t0
        print(f"  ✅ {dt:.2f}s | response: {reply.strip()[:300]}")
    else:
        print("\n[3/3] vision chat ping — 이미지 미지정으로 스킵 (--image PATH 사용)")

    print("\n모든 점검 통과 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
