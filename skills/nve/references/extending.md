# Extending nve without overriding it

Layers, lowest to highest: `core:` (shipped) < `pro:` (shipped, private edition) < `user:` (workspace
`custom/`) < the project's own storyboard. Shipped files are never edited; updates replace them wholesale
and never touch `custom/`.

## A user template

```bash
nve template fork core:talking-head my-shop     # creates custom/templates/my-shop/template.json
```
```json
{"id": "user:my-shop", "extends": "core:talking-head@^1",
 "patch": {"defaults.style.font.title": "Be Vietnam Pro", "defaults.style.palette.accent": "#FF7A00"}}
```
`patch` keys are dotted paths. Any other top-level key deep-merges over the parent. Add a `rules.md`
next to it for extra editorial rules. A user id can never be `core:…` or `pro:…` (nve refuses).

## A user block

`custom/blocks/<name>/block.json` with `"id": "user:<name>"` and the same fields as a core block. A block
needs a renderer in each compose engine to show up; until nve supports user renderers, implement the
effect as a reusable script (below) that writes an overlay video/PNG into the project and reference it
from the storyboard.

## Code you write for the user

- Reusable ("lần sau làm vậy nữa"): `custom/scripts/<name>/script.py` + `script.json`
  (`{"name", "description", "inputs", "outputs", "stage": "before_render" | "after_cut" | …}`).
  Mention it in the project log line you give the user.
- One-off: `projects/<p>/work/scripts/`.
- Never in the install folder. In Claude Code a hook blocks such writes; on cloud this rule is on you.

## Brand kits

`custom/brands/<brand>/brand.json`: `{"palette": {...}, "font": {...}, "cta": "INBOX …", "logo": "logo.png"}`.
Copy its values into the storyboard `style` when the user names the brand.
