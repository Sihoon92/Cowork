import base64
import requests
import json

OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen2.5-coder:7b"
DEFAULT_TIMEOUT = 300
VISION_MODEL = "gemma4:e4b"


def chat(
    prompt: str,
    model: str = DEFAULT_MODEL,
    stream: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    format: str | dict | None = None,
) -> str:
    """Send a prompt to Ollama and return the response text.

    `format` enables Ollama's structured output. Pass "json" to constrain the
    decoder to syntactically valid JSON, or a JSON schema dict to also enforce
    structure. None preserves free-form text behaviour.
    """
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": stream}
    if format is not None:
        payload["format"] = format

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


def chat_with_image(
    prompt: str,
    image_path: str,
    *,
    model: str = VISION_MODEL,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """Send a prompt + image to Ollama vision model. Returns the response text."""
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "images": [b64],
    }
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
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
