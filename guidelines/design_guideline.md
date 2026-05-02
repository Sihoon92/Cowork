# Design Guideline

This document tells the LLM **what to draw and when**, not how to write the code.
For drawing primitives see [primitives_api.md](primitives_api.md).

When generating a slide, pick the single most appropriate pattern below for the
content, then compose primitives to realize it. Patterns are organized by intent.

## How to read each pattern
- **언제**: situations where this pattern is the right choice
- **구성**: how to lay out the slide using primitives
- **주의**: common mistakes to avoid

---

## A. 수치·데이터 표현

### Stat 강조 (Big Number)
- **언제**: 핵심 수치 1~3개를 청중에게 각인시킬 때. KPI, 성과 보고
- **구성**: 헤드 메시지(상단, 28pt bold) + 수치 1~3개를 가로로 큰 글자(72pt+, primary 색)로 배치 + 각 수치 아래 단위·라벨(14pt) + 하단에 1줄 해석(16pt)
- **주의**: 수치는 슬라이드 1장에 최대 3개. 수치보다 큰 시각 요소가 있으면 강조 효과가 무너짐

## B. 비교·대조

### Matrix 비교
- **언제**: 2~4개 옵션을 여러 기준으로 동시에 비교, 의사결정 지원
- **구성**: 1행=헤더(primary 색 사각형 + 흰 글씨), 1열=옵션 라벨. 각 셀은 짧은 텍스트(●●● 또는 점수). 추천안 행은 굵은 테두리 또는 accent 강조
- **주의**: 셀이 6×6 초과 시 가독성↓. 기준 5개 이하

### As-Is / To-Be
- **언제**: 현재 상태와 개선 후 상태를 대비할 때. 변화의 방향성 강조
- **구성**: 슬라이드 좌·우 50% 분할. 왼쪽 As-Is(neutral 어두운 톤), 오른쪽 To-Be(primary 색). 중앙에 큰 화살표(→). 각 영역 상단에 라벨, 하단에 3~4개 bullet
- **주의**: As-Is에 감정적 단어 금지("나쁜", "문제"). 사실 기술만. To-Be는 측정 가능한 결과로

## C. 프로세스·흐름

### Flow 다이어그램
- **언제**: 순서가 있는 프로세스, 단계별 작업 흐름
- **구성**: 사각형(단계)을 가로로 3~6개 배치, 화살표로 연결. 각 사각형 안에 단계명(16pt). 각 사각형 아래 1줄 설명(12pt). 핵심 단계는 accent 색
- **주의**: 7단계 초과 시 두 줄로 꺾기. 분기 3개 이상은 별도 슬라이드

## D. 시간·일정

### 추진계획 로드맵 (시간 × 카테고리)
- **언제**: 여러 카테고리의 작업이 시간 축 위에서 언제 진행되는지 보여줄 때
- **구성**: 1행=시간 헤더(월/분기, primary 사각형 + 흰 글씨), 1열=카테고리 라벨. 각 셀 위에 사각형 블록으로 작업 기간 표시. 마일스톤은 ◆(또는 작은 원). 카테고리별 같은 색
- **주의**: 셀 경계는 옅게. 블록 텍스트 8pt 이상 유지. 12개월 초과 시 분기 단위로 축약

## E. 구조·관계

### 피라미드 / 계층 구조
- **언제**: 우선순위, 위계, Maslow식 욕구, 조직 구조
- **구성**: 사다리꼴 사각형(또는 단순 사각형)을 위에서 아래로 점점 넓게 4~5단. 위=가장 중요/희소. 색은 진→옅 또는 옅→진
- **주의**: 5단 초과 시 라벨 잘림 주의. 가로 배치도 가능

## F. 메시지 전달

### Cover (표지)
- **언제**: 첫 슬라이드. 발표 시작
- **구성**: 배경 전체 primary 색. 제목 44pt+ 중앙 또는 좌하단 정렬. 부제목/날짜 18pt. 선택적으로 하단 accent 띠(높이 15%)
- **주의**: 본문 슬라이드와 동일 레이아웃 금지

### 인용
- **언제**: 실제 인용문, 핵심 원칙, 전환 슬라이드
- **구성**: 큰 따옴표 " 를 배경 장식(60pt, primary opacity 20%). 인용 텍스트 22pt 중앙 정렬. 출처 14pt 이탤릭 우측 정렬
- **주의**: 출처 없는 인용 금지. 슬라이드에 다른 요소 최소화

## G. 콘텐츠 밀도

### Bullet List
- **언제**: 나열형 정보. 다른 패턴이 맞지 않을 때 기본 선택
- **구성**: 헤드 메시지 24pt(상단). 그 아래 bullet 16pt, 앞에 ▪ 또는 primary 색 작은 사각형. 최대 5개
- **주의**: 6개 이상이면 두 컬럼으로 나누거나 슬라이드 분리
