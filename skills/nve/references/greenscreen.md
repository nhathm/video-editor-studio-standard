# Green screen

`nve ingest` measures how green the frame border is (`ingest.json` → `sources[].greenscreen`:
`border_green`, `likely`, sampled `screen` colour) and says so in `hint_greenscreen`. When it is likely,
`nve plan draft` turns on:

```jsonc
"output": {"flip": false},                       // set true when the front camera mirrored the picture
"style": {
  "key": {"enabled": true, "screen": "#4DAE3A"},  // sampled screen colour
  "background": {"type": "gradient", "colors": ["#E7EEFF", "#9FB6FF"], "angle": 160, "glow": true, "dots": true},
  "person": {"scale": 0.9, "y": 0.0}              // size of the person (1 = full frame), lift from the bottom (fraction of height)
}
```

## What you decide at S3

1. **Mirror?** Look at a frame (`work/gs/*.png` or `nve shots`). If text on a product/shirt reads backwards,
   set `output.flip: true`. If unsure, ask the user.
2. **Background**, one of:
   - `{"type": "color", "color": "#F4F1EA"}`
   - `{"type": "gradient", "colors": [a, b], "glow": true, "dots": true}`
   - `{"type": "sections", "dots": true, "sections": [{"start": 0, "colors": [a, b], "scale": 0.86}, ...]}`:
     one look per part of the video (output times). Alternating `scale` 0.86/0.92 per section gives the
     "punch-in" rhythm of the old studio's food video. Pick colours that match each topic.
   - `{"type": "image", "asset": "assets/bg.jpg"}` (the user's own photo, or a library image).
3. Captions and stamps sit above the person; keep stamps in the top area, clear of the face.

## Engines (socket `key`)

| engine | needs | quality |
|---|---|---|
| `keyfill` (default) | opencv + Node ≥ 22 (HyperFrames `remove-background`, a local AI model downloaded on first use) | AI matte as garbage mask, fine hair edges, holes in dark clothes filled, phone screens kept solid |
| `greenkey` (fallback) | numpy only | hard green key + despill; everything above the screen is cut away, but other non-green set pieces at the sides can remain; may show small holes in green-reflecting dark clothes |

The key runs on the cut (after grade and flip), so the preview is slower for green-screen projects (the AI
matte runs at half resolution for the preview, full resolution for the final). Tell the user. If the
fallback was used, the render `notes` say so: pass it on in one line.
