# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**CoWork** — Claude 기반 에이전트 워크플로우 시스템. 현재 단계: JSON 정의 기반 PPTX 자동 생성.

핵심 아이디어: 자연어 대신 **JSON 스키마**로 슬라이드 내용을 명시하고, 로컬 LLM(Ollama)과 python-pptx로 파일을 생성한다.

## Commands

```bash
# 테스트 실행 (Windows 인코딩 문제 방지를 위해 항상 PYTHONIOENCODING 설정 필요)
PYTHONIOENCODING=utf-8 python tests/test_ollama.py
PYTHONIOENCODING=utf-8 python tests/test_pptx.py

# PPTX 직접 생성
PYTHONIOENCODING=utf-8 python -c "
from src.pptx.generator import build_from_json
build_from_json('data/sample_presentation.json', 'output/out.pptx')
"
```

## Architecture

```
CoWork/
├── src/
│   ├── llm/
│   │   └── ollama_client.py   # Ollama REST API 래퍼 (requests 사용, SDK 미사용)
│   └── pptx/
│       └── generator.py       # JSON → python-pptx 변환 엔진
├── data/
│   └── sample_presentation.json   # 슬라이드 JSON 스키마 예시
├── tests/
│   ├── test_ollama.py         # Ollama 서버 + gemma4:e4b 연결 검증
│   └── test_pptx.py           # PPTX 생성·슬라이드 수·크기 검증
└── output/                    # 생성된 .pptx 파일 저장 위치
```

### JSON 슬라이드 스키마

```json
{
  "slides": [
    {
      "background": { "color": "#1C2833" },
      "textboxes": [
        {
          "left": 1.0, "top": 2.5, "width": 11.3, "height": 1.5,
          "lines": [
            { "text": "제목", "font_size": 44, "bold": true, "color": "#FFFFFF", "align": "center" }
          ]
        }
      ]
    }
  ]
}
```

`textbox` 위치·크기 단위는 **인치(Inches)**. 슬라이드 기본 크기: 13.33 × 7.5 인치 (16:9).

### LLM 클라이언트

- `ollama_client.py`는 `http://localhost:11434` Ollama 서버에 직접 REST 호출
- 기본 모델: `gemma4:e4b`
- `chat(prompt)` → 단일 응답 문자열 반환
- `is_available()` → 서버 실행 여부 확인

## Environment

| 항목 | 버전/값 |
|------|---------|
| Python | 3.12.4 |
| python-pptx | 1.0.2 |
| Ollama 모델 | `gemma4:e4b` (9.6GB), `gemma4:26b` |
| Node.js | 22.17.0 (추후 html2pptx 워크플로우 확장 시 사용) |

## Known Issues

- Windows `cp949` 인코딩 환경에서 한글·이모지 출력 시 `UnicodeEncodeError` 발생 → `PYTHONIOENCODING=utf-8` 필수
- Ollama 서버가 꺼져 있으면 `test_ollama.py` 즉시 실패 → 실행 전 `ollama serve` 확인
