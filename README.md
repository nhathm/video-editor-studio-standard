# nve-studio (Standard)

**nve** is an AI video editor that lives inside Claude. Drop in raw clips or photos, type `/nve`, and Claude
edits them like a short-form editor would: it plans the video as a storyboard, shows you the plan and a preview,
and renders a finished vertical video ready for TikTok, Reels or Shorts. No timeline, no editing app, no API
key needed.

## What it does

- **Cuts for you**: removes fillers ("ờ", "ừm", "um"), long pauses, false starts and retakes; or cuts product
  footage on its strongest shots.
- **Captions that read well**: word-by-word highlight on bold outlined text (or a colour box, big pop-in words, a
  karaoke pill), broken into whole ideas, Vietnamese-ready fonts, keywords in your accent colour.
- **A hook in the first seconds**: the video's promise in big text with a marker highlight.
- **Motion graphics**: highlight stamps with animated emoji, product cards, full-screen pictures, B-roll in a
  rounded frame, one word in its own colour.
- **Transitions**: zoom punch, flash, whip, glitch, shake at a cut; crossfades and slides between photos.
- **Look and sound**: a clean bright colour look with optional skin retouch, sound effects on every graphic,
  background music mixed under the voice, loudness set for social apps.
- **Colours from you**: a reference picture, a colour you name, or an automatic pick that stands out.
- **Learns your taste**: every correction you make becomes a rule for the next videos.
- **Green screen**: keys the background out and puts you on a new one.

## How it works

1. **Ingest**: nve probes your files, transcribes the speech and measures the pauses.
2. **Plan**: Claude writes a storyboard (cuts, captions, hook, stamps, music) and asks a few style questions once.
   You approve it.
3. **Preview**: stills with the look and text applied. You approve them.
4. **Render + check**: one finished video plus a cover image, checked for length, loudness and frames.

The storyboard is the single source of truth: ask for a change in plain words and Claude edits it.

**Install:** see [INSTALL.md](INSTALL.md) (claude.ai on the web or iPhone, or Claude Code on Mac, Linux, Windows).
Changes: [CHANGELOG.md](CHANGELOG.md).

## Layout

```
core/nve/          engine (Python): doctor, storyboard, timeline, stages, engines/
skills/nve/        the Claude skill + bin/nve launcher
shells/nve/        small skill for claude.ai that loads skills/nve from the `stable` branch
templates/core/    talking-head, product-ad
blocks/core/       captions (bold-outline, word-box, pop-word, karaoke-pill), hook.title, stamp.slam,
                   card.image, media.wall, media.frame
packs/             fonts (OFL), sfx (Pixabay licence), emoji (Noto, CC BY 4.0), music (Kevin MacLeod, CC BY 4.0)
hooks/             Claude Code hook that blocks writes into the install folder
engines.json       capability -> engine preference chain (fallback order)
```

## Tests

```bash
python3 -m venv .venv && .venv/bin/pip install numpy pillow jsonschema pytest
cd core && ../.venv/bin/python -m pytest -q
```

## Licences

Code: MIT ([LICENSE](LICENSE)). Bundled assets: [`packs/LICENSES.json`](packs/LICENSES.json). Music and
Noto emoji need a credit line in the post description: nve writes it next to each render
(`final_vN.credits.txt`). Third-party: HyperFrames (Apache-2.0, used through its CLI).

## Author

Made by **nhathm**: [nhathm.com](https://nhathm.com) · [Facebook](https://web.facebook.com/nhathm.official/)
