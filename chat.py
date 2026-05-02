"""Ollama 대화형 CLI."""
import sys
from src.llm.ollama_client import is_available, chat, DEFAULT_MODEL

def main():
    if not is_available():
        print("Ollama 서버가 실행 중이 아닙니다. `ollama serve` 를 먼저 실행하세요.")
        sys.exit(1)

    print(f"모델: {DEFAULT_MODEL}  |  종료: Ctrl+C 또는 'exit'\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n종료합니다.")
            break

        if not user_input or user_input.lower() == "exit":
            break

        print("AI: ", end="", flush=True)
        response = chat(user_input)
        print(response)
        print()

if __name__ == "__main__":
    main()
