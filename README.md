# nve-studio (Standard)

Storyboard-driven video editing for Claude. Drop raw videos/photos in, type `/nve`, approve a plan and a
preview, get a finished short video: cuts, filler removal, colour look, karaoke captions, highlight
stamps with animated emoji, SFX and music. Free, works with no API key at all.

**Install:** see [INSTALL.md](INSTALL.md) (claude.ai / iPhone, or Claude Code on Mac, Linux, Windows).

## Layout

```
core/nve/          engine (Python): doctor, storyboard, timeline, stages, engines/
skills/nve/        the Claude skill + bin/nve launcher
shells/nve/        small skill for claude.ai that loads skills/nve from the `stable` branch
templates/core/    talking-head, product-ad
blocks/core/       caption.karaoke-pill, stamp.slam, card.image
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
