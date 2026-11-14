# storyboard.json (schema `nve.storyboard/1`)

`nve plan draft` writes a first version; you then edit it. `nve plan refresh <p>` validates it, writes
`storyboard.md` (what the user reads at G1) and `analysis/words_out.json` (every spoken word with its
OUTPUT time, after cuts, filler removal, speed and `text_fixes`).

```jsonc
{
  "schema": "nve.storyboard/1",
  "project": "mate thắm",
  "template": "core:talking-head",
  "cut_strategy": "speech",            // speech | visual | beat | hybrid
  "brief": "Unimate Chanh Gừng ad, Thắm talking to camera",
  "output": {"aspect": "9:16", "width": 1080, "height": 1920, "fps": 30, "speed": 1.15, "platform": "tiktok"},
  "style": {
    "look": "trong-tro",               // none | trong-tro
    "skin": true,                      // skin retouch
    "font": {"title": "Montserrat", "caption": "Montserrat"},
    "palette": {"ink": "#1F2A44", "accent": "#FFD84D", "text": "#FFFFFF", "spoken": "#9EE6FF"},
    "caption": {"block": "core:caption.karaoke-pill", "group_min": 3, "group_max": 5, "top": 0.77,
                "keywords": ["unimate", "chanh", "gừng", "inbox", "thắm"]}   // "block": "none" = no captions
  },
  "sources": [{"id": "a", "path": "source/IMG_2701.MOV", "kind": "video", "transcript": "analysis/transcripts/a.json"}],
  "tracks": {
    "video": [                          // SOURCE times, in playback order; a source may appear many times
      {"src": "a", "in": 0.98, "out": 6.12, "note": "hook"},
      {"src": "a", "in": 7.12, "out": 16.54}
    ],
    "overlay": [                        // OUTPUT times
      {"block": "core:stamp.slam", "start": 0.08, "end": 1.30,
       "props": {"text": "NGHIỆN TRÀ SỮA", "emoji": ["1f9cb"]}},
      {"block": "core:stamp.slam", "start": 1.32, "end": 3.75,
       "props": {"text": "SỢ TĂNG CÂN|SỢ VÒNG 2 TO", "emoji": ["1f631", "1f62b"], "alt": true},
       "sfx": [["buzz", 0.35, 0.25]]},  // extra SFX: [name, seconds after start, volume]
      {"block": "core:card.image", "start": 3.82, "end": 5.15,
       "props": {"img": "assets/unimate.png", "label": "UNIMATE"}}
    ],
    "audio": [
      {"kind": "bgm", "asset": "lib:bgm/acoustic-01", "volume": 0.1},
      {"kind": "sfx", "asset": "lib:sfx/notification", "at": 19.2, "volume": 0.45}
    ]
  },
  "cover": {"text": "UNIMATE|TRÀ CHANH GỪNG", "at": 3.0, "emoji": ["1f34b"],  // output time of the frame
            "prepend": true, "seconds": 1.0},     // also show it as the first second of the video
  "text_fixes": {"Tranh": "Chanh", "Inbốc": "Inbox"},   // regex -> replacement, captions only
  "engines": {},                        // pin one, e.g. {"compose": "ass"}; empty = default chain
  "gates": {"plan": null, "preview": null, "final": null}  // set only via `nve approve`
}
```

## Blocks (`nve block` lists them with props)

| id | what | props |
|---|---|---|
| `core:caption.karaoke-pill` | captions, 3–5 words on a dark pill, spoken words light up, keywords accent + pop | group_min, group_max, keywords, top (fraction of height), size (fraction of width) |
| `core:stamp.slam` | big outlined text slammed in, Noto animated emoji above; SFX whoosh + impact (+ pop with emoji) added automatically | text (`\|` = new line), emoji [codepoints], alt, top |
| `core:card.image` | white card with an image + label, pops in; SFX pop + sparkle automatic | img (project path or `lib:img/<name>`), label, top |
| `core:media.wall` | a picture over the whole frame while the voice goes on (e.g. a wall of the creator's past videos), zooming towards `focus` (brought to the centre as far as the edges allow); optional colour tint and a badge in the middle (view count with an eye icon); stamps and captions stay on top; SFX whoosh automatic | img, focus [x, y], zoom [from, to], tint, tint_opacity, badge, badge_icon (eye / play / none), badge_color |

## Assets

- `lib:sfx/<name>`: `nve assets list sfx`. `lib:bgm/<name>`: `nve assets list bgm`.
- Emoji: Noto codepoints (`1f604` = 😄). Missing ones are downloaded once into the workspace library; if a
  codepoint has no animated version, nve warns: pick another.
- Images the user gives for cards: copy them into `projects/<p>/assets/` and reference `assets/<file>`.

## Timing tips

- Take times from `analysis/words_out.json`: a stamp starts ~0.05 s before its first word, ends at the
  next stamp or when the idea is over (min 0.8 s, ideal 1.2–3 s). Leave ≥ 0.02 s between stamps.
- A card shows only while the thing is named (start at the word, 1.2–2.5 s).
- After changing `output.speed` or `tracks.video`, re-read `words_out.json` and re-time every overlay.
