"""Test 1: Ollama gemma4:e4b 연결 테스트."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.llm.ollama_client import is_available, list_models, chat

TARGET_MODEL = "gemma4:e4b"


def test_server_running():
    assert is_available(), "Ollama 서버가 실행 중이 아닙니다. `ollama serve` 를 먼저 실행하세요."
    print("✅ Ollama 서버 연결 성공")


def test_model_available():
    models = list_models()
    print(f"   사용 가능한 모델: {models}")
    assert any(TARGET_MODEL in m for m in models), f"모델 {TARGET_MODEL} 을 찾을 수 없습니다."
    print(f"✅ 모델 확인: {TARGET_MODEL}")


def test_simple_inference():
    prompt = "안녕하세요! 한 문장으로 자기소개 해주세요."
    print(f"\n   프롬프트: {prompt}")
    response = chat(prompt, model=TARGET_MODEL)
    print(f"   응답: {response[:200]}")
    assert len(response) > 0, "빈 응답이 반환되었습니다."
    print("✅ 추론 성공")


if __name__ == "__main__":
    print("=" * 50)
    print("Test 1: Ollama 연결 테스트")
    print("=" * 50)
    test_server_running()
    test_model_available()
    test_simple_inference()
    print("\n모든 Ollama 테스트 통과!")
