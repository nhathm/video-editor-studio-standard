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
    "caption": {"block": "core:caption.bold-outline",
                "keywords": ["unimate", "chanh", "gừng", "inbox", "thắm"],   // "block": "none" = no captions
                "phrases": ["Nghiện trà sữa", "mà sợ tăng cân", "sợ vòng hai to"]},  // caption lines = whole ideas
    "transition": "none"               // default for every change of source: a name, "random" or "none"
  },
  "sources": [{"id": "a", "path": "source/IMG_2701.MOV", "kind": "video", "transcript": "analysis/transcripts/a.json"}],
  "tracks": {
    "video": [                          // SOURCE times, in playback order; a source may appear many times
      {"src": "a", "in": 0.98, "out": 6.12, "note": "hook"},
      {"src": "a", "in": 7.12, "out": 16.54, "transition": "zoom-punch"}  // INTO this range; or {"type", "duration"}
    ],
    "overlay": [                        // OUTPUT times
      {"block": "core:hook.title", "start": 0.0, "end": 2.4,
       "props": {"text": "BẠN ĐANG *UỐNG SAI*|TRÀ SỮA?"}},          // *stars* = highlighted
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
| `core:caption.bold-outline` | **default** captions: no background, white heavy text with a dark outline, 2–4 words on ≤ 2 lines, the spoken word turns accent, keywords stay accent + pop | group_min, group_max, keywords, top (fraction of height, ≤ 0.75 on vertical), size (fraction of width), uppercase |
| `core:caption.word-box` | same, the spoken word sits in a rounded accent box | same |
| `core:caption.pop-word` | very big, 1–3 words at a time, each group pops in | same (uppercase default true) |
| `core:caption.karaoke-pill` | 3–5 words on a dark pill, spoken words light up, keywords accent + pop | same |
| `core:hook.title` | the opening promise, 2–6 words in the first 2–3 s; words fade up, then an accent marker sweeps behind the `*starred*` words; whoosh + pop automatic | text (`\|` = new line, `*word*` = highlight), top, size, marker (colour; empty = accent) |
| `core:media.frame` | B-roll video or photo in a rounded frame with a white border and shadow over the talking video (voice keeps going; the clip is muted); pops in; whoosh automatic | src (project path), in (start inside the clip), top, width, aspect (4:3, 1:1, 16:9, 4:5), radius, border, anim (pop / slide-up / fade) |
| `core:stamp.slam` | big outlined text slammed in, Noto animated emoji above; SFX whoosh + impact (+ pop with emoji) added automatically | text (`\|` = new line, `*word*` = one word in its own colour), emoji [codepoints], alt, top |
| `core:card.image` | white card with an image + label, pops in; SFX pop + sparkle automatic | img (project path or `lib:img/<name>`), label, top |
| `core:media.wall` | a picture over the whole frame while the voice goes on (e.g. a wall of the creator's past videos), zooming towards `focus` (brought to the centre as far as the edges allow); optional colour tint and a badge in the middle (view count with an eye icon); stamps and captions stay on top; SFX whoosh automatic | img, focus [x, y], zoom [from, to], tint, tint_opacity, badge, badge_icon (eye / play / none), badge_color |

## Transitions (`nve transitions`)

Cut effects (any cut, length unchanged): `zoom-punch`, `flash`, `whip`, `glitch`, `shake`. Photo crossings (only
between two photos; elsewhere the closest cut effect is used and `lint` says so): `crossfade`, `slide-left`,
`slide-up`, `zoom-in`, `wipe`, `circle`. Each brings its own short SFX. `style.transition` applies to every change of
source (never to jump cuts inside one clip); `tracks.video[i].transition` sets or cancels (`"none"`) one cut.
Use few: at a change of scene, topic or product, not on every cut.

## Colours

`style.palette`: `ink` (outline / box, dark), `accent` (spoken word, keywords, hook marker), `text`, `spoken`
(karaoke pill only). `nve palette --image <file>` / `--accent <#hex>` / `<project>` (automatic) returns one.

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
- Caption phrases (`style.caption.phrases`): the spoken words in order, one entry per caption, each a
  whole idea (2–7 words); `|` inside a phrase = where its second line starts (otherwise nve picks an even split). nve aligns them on the words, so cut-away words are just skipped; a silence over 1 s
  still breaks a line. Without phrases nve breaks at punctuation and pauses, which cannot see Vietnamese compound
  words: always write them. Check `caption_lines` in the `nve plan refresh` output.
- Hook title: start at 0.0, keep it ≥ 0.6 s + 0.3 s per word (`lint` checks), end before the first stamp.
- B-roll frame: while the thing it shows is being said, 1.2–3 s; keep it above the captions and off the face.
