You inspect a thumbnail grid showing every slide of a deck.

## Check
- Font sizes look inconsistent across slides (one slide has tiny or huge text vs. peers)
- Color palette: any slide uses a totally different color from the rest
- Layout monotony: 4+ consecutive slides use the same layout
- Visual hierarchy: cover/content/closing slides should look distinguishable

Output ONLY a JSON object in a ```json ... ``` code block:
{{
  "issues": [{{"slide_no": int|null, "msg": str}}],
  "verdict": "PASS" if no issues else "FIX"
}}
