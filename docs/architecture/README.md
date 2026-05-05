# Architecture docs

설계 결정 기록. 무엇을·왜·다른 방식이 안 되는 이유·예상 효과를 보존한다.
구현 코드는 시간이 지나면 변하므로, 이 문서들은 **결정 시점의 맥락**을 남기는 역할.

## 색인

| 날짜 | 문서 | 주제 |
|---|---|---|
| 2026-05-04 | [phase1-three-tier-header](./2026-05-04-phase1-three-tier-header.md) | apply_master 3-tier 헤더 (section_title / head_message / sub_message) |
| 2026-05-04 | [outline-robustness](./2026-05-04-outline-robustness.md) | outline 단계 견고성 (SlideOutline schema + alias normalization + retry) |
| 2026-05-04 | [old-vs-new-mechanism](./2026-05-04-old-vs-new-mechanism.md) | composition+block → recipe+grid+primitive 마이그레이션 전체 비교 |

## 새 문서를 쓸 때

파일명: `YYYY-MM-DD-<slug>.md`

내용 구성:
1. 무엇을 바꿨는가 (변경 사실)
2. 왜 이렇게 해야 했는가 (구체 증상 + 근본 원인)
3. 대안과 그 한계 (왜 다른 방식이 안 되는지 명시)
4. 데이터 흐름 (mermaid 권장)
5. 구현 핵심 (코드 인용은 최소)
6. 예상 효과 (메커니즘과 함께)
7. 트레이드오프
8. 검증 결과
