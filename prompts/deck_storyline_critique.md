You review whether a slide deck's narrative flows when reading only the head messages.

Head messages in order:
{head_messages}

## Check
- Does the sequence read like a coherent argument?
- Is any slide's message a non-sequitur — disconnected from the slides before/after?
- Is any slide redundant (says the same thing as a neighbor)?

Output ONLY a JSON object in a ```json ... ``` code block:
{{
  "issues": [{{"slide_no": int, "msg": str}}],
  "verdict": "PASS" if no issues else "FIX"
}}
