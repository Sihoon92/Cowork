# CoWork — Gemma → PPTX

Local-LLM-driven PowerPoint generator. Takes a `content.json`, plans the deck with
Ollama (gemma4:e4b), generates python-pptx code per slide, executes each in an
isolated subprocess, and merges into a single `.pptx`.

See `docs/superpowers/specs/2026-05-02-gemma-pptx-pipeline-design.md` for the design.

## Setup

```bash
pip install -r requirements.txt
ollama pull gemma4:e4b   # one-time
ollama serve             # in another terminal
```

## Run

```bash
PYTHONIOENCODING=utf-8 python scripts/run_pipeline.py
# -> output/demo.pptx
```

## Tests

```bash
# unit only (fast, no LLM)
PYTHONIOENCODING=utf-8 pytest -m "not live"

# end-to-end with Ollama (slow)
PYTHONIOENCODING=utf-8 pytest -m live
```

## Layout

```
src/
  llm/ollama_client.py
  pptx/
    primitives.py     # Layer 1 — add_text/add_rect/add_line/add_arrow/add_image/set_bg
    code_runner.py    # subprocess execution + retry
    merger.py         # XML-level slide copy
  pipeline/
    planner.py        # content.json -> plan.json (Phase 2-1, 2-2)
    code_generator.py # plan -> python-pptx code via LLM
    guideline_loader.py
    builder.py        # orchestrator
guidelines/
  primitives_api.md   # API reference (LLM-readable)
  design_guideline.md # 33 patterns across 8 categories
prompts/
  story_outline.txt
  slide_detail.txt
  code_generation.txt
data/
  sample_content.json
```

## Troubleshooting

- **UnicodeEncodeError on Windows**: always set `PYTHONIOENCODING=utf-8`.
- **Slide rendering fails after 3 retries**: inspect `output/work/slides/` and stderr; the LLM may need a smaller layout hint or simpler content. Reduce slide count or use a richer model.
- **Pretendard font missing**: change `_DEFAULT_FONTS` in `src/pipeline/planner.py` to `Malgun Gothic` (Windows) or another installed Korean font.

## v2 — Freeform Codegen Pipeline

A second pipeline that lives alongside the v1 recipe pipeline. v2 generates
python-pptx code per slide via LLM, executes each in a subprocess, and
refines via vision-LLM critique. See
`docs/superpowers/specs/2026-05-06-v2-freeform-codegen-design.md`.

```bash
# Side-by-side run on the same input:
PYTHONIOENCODING=utf-8 python scripts/run_pipeline.py    data/sample_content.json
PYTHONIOENCODING=utf-8 python scripts/run_pipeline_v2.py data/sample_content.json

# Outputs:
# output/sample_content.pptx       (v1)
# output/sample_content_v2.pptx    (v2)

# v2 flags:
python scripts/run_pipeline_v2.py data/foo.json --no-revision   # baseline
python scripts/run_pipeline_v2.py data/foo.json --no-gallery    # no learning
python scripts/run_pipeline_v2.py data/foo.json --max-iter 1    # cheap revision
```
