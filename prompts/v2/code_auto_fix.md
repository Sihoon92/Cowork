Your previous slide code raised an error during execution.

## Previous code

```python
{prev_code}
```

## Traceback (current attempt)

```
{traceback}
```

## Prior failed attempts on this same slide

{history_block}

## Design guide (full — pay special attention to the "Forbidden" section)

{design_guide_excerpt}

## Fix instructions

1. Identify the ROOT CAUSE, not just the failing line.
2. Cross-check the cause against the "Forbidden" rules in the design guide.
   If you violated one, do not retry the same idiom with different
   strings/indices — choose a different approach entirely.
3. If a feature you wanted (e.g. a diagram image) cannot be supported
   in this environment, drop it and replace its visual purpose with
   shapes + text.
4. Do NOT add new imports. Do NOT call `prs.save`.

Reply with ONLY the corrected `def build_slide(prs):` body and helpers.
No fences, no prose.
