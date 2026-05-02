import requests
import json

OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "gemma4:e4b"
DEFAULT_TIMEOUT = 300


def chat(prompt: str, model: str = DEFAULT_MODEL, stream: bool = False, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Send a prompt to Ollama and return the response text."""
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": stream}

    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()

    if stream:
        result = ""
        for line in response.iter_lines():
            if line:
                data = json.loads(line)
                result += data.get("response", "")
                if data.get("done"):
                    break
        return result
    else:
        return response.json()["response"]


def list_models() -> list[str]:
    """Return list of available model names."""
    response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=10)
    response.raise_for_status()
    return [m["name"] for m in response.json().get("models", [])]


def is_available() -> bool:
    """Check if Ollama server is running."""
    try:
        requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        return True
    except requests.exceptions.ConnectionError:
        return False
