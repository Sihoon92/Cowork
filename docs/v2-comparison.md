# v1 vs v2 — what to look for

| What | v1 (recipe) | v2 (freeform codegen) |
|---|---|---|
| Layout source | `src/pipeline/recipes_*.py` registry | LLM coins per slide |
| Render | deterministic compile | subprocess-executed Python |
| Plan | one LLM pass | two LLM passes (1a + 1b) |
| Revision | recipe data patch | code patch from PNG critique |
| Learning | none | `references/index.json` gallery |
| Free-form shapes | no (primitives only) | yes (raw `add_connector` etc.) |

Run both on the same input and compare:

- `output/<stem>.pptx` vs `output/<stem>_v2.pptx`
- `output/work_<stem>/plan.json` vs `output/work_v2_<stem>/plan.json`
- v2 only: `output/work_v2_<stem>/slide_codes/` and `captures/` and `critiques/`

Re-run v2 several times on a small set of decks to seed the gallery, then
re-run a fresh deck — Phase 1b should now pull in similar high-scoring
approaches.
