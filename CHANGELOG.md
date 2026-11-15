# Changelog

Versions go up by 0.1 per release (0.3 → 0.4 → 0.5…) unless a number is chosen. (0.2 was skipped.) `stable` always points at the latest release tag.

## 1.0.0 — 2026-11-16 · first official release

nve 1.0 is the first release we call finished: an AI editor inside Claude that takes raw clips to a ready-to-post
short video, with captions, a hook, motion graphics, transitions, music and a quality check, and that learns
your taste as you correct it.

### Captions
- **New default look** `core:caption.bold-outline`: no background, white heavy words with a dark outline, the
  word being spoken lights up in your accent colour, keywords stay coloured with a small pop.
- Two more looks: `core:caption.word-box` (the spoken word sits in a colour box) and `core:caption.pop-word`
  (very big, 1–3 words at a time, popping in). The dark karaoke pill stays as a choice.
- **Whole ideas, never cut mid-phrase.** Claude writes the caption lines as complete ideas
  (`style.caption.phrases`); nve aligns them on the speech, so they survive later cut changes, and lists them in
  the storyboard for review. Without them, nve breaks at sentence ends, commas and pauses, before words like
  "và / nhưng / để", and never after a word that leans on the next.
- A word cut at the edge of a range is shown once, in the range that holds most of it.

### Hook and graphics
- **Hook title** `core:hook.title`: Claude looks for the hook sentence in the first 3 seconds and puts its
  2–6 word essence on screen; words rise one by one, then a marker sweeps in behind the key words.
- **One word in its own colour**: `*word*` in stamp, hook and cover text.
- **B-roll in a rounded frame** `core:media.frame`: a video clip (muted) or photo with a border and shadow over
  the talking video, popping or sliding in.

### Transitions
- Cut effects that keep the video length: zoom punch, white flash, whip pan, glitch, shake. Between two photos:
  crossfade, slide left / up, zoom in, wipe, circle. Each comes with its own short sound.
- Off unless you ask. For a photo slideshow Claude asks which one; no answer means a random pick that stays the
  same if you render again. Jump cuts inside one clip stay clean cuts.

### Colours and choices
- `nve palette`: text colours from a reference picture, from a colour you name (made readable on video), or an
  automatic accent that stands out from your footage.
- Style questions come as buttons where the app has them.
- `nve plan refresh` now warns (`lint`) when a hook is too long to read in its time, when captions sit under the
  app's buttons, or when a transition cannot be done as asked.

### Quality
- The fallback renderer (ffmpeg/ASS) sizes caption and hook text from the font's own metrics, so it matches the
  main renderer (its captions were about 25% smaller before).
- Fixed: photos were not read at ingest with ffmpeg 7.

### Editions
- New **Free** edition (same as Standard, its own repo).
- **Newbie** now also learns the style of a sample video (`nve ref`, `nve style`), and is the only edition that
  carries the whisper model mirror on GitHub.

## 0.9.0 — 2026-11-14
- Taste log (`nve taste`, `references/taste.md`): every correction the user makes is kept in `<workspace>/taste.json` in their words, with optional defaults (`--set style.*/output.*`), limits on storyboard metrics (`--max stamps_per_min=5`, …) and banned SFX/music. `nve plan draft` applies the defaults and bans, `nve plan refresh` / `nve preview` return `taste_warnings`, banned SFX are skipped in the mix (`style.ban_sfx`). Cloud: `nve taste export` / `import` carry it between chats. Idea from kurbaitaev/ghost-editor (MIT).
- Sample style by hand (`references/analyze.md`): when the user shows a sample video, Claude takes its design language (fonts, colours, text treatments, pace, music feel) and applies it to the user's own footage and words; the sample's content is never copied and the scratch project is deleted afterwards.
- Better shot detection for `nve shots` and the visual cut strategy: same-camera jump cuts, flashes no longer counted as cuts, fades through black or white, short inserts kept, fade-in openings joined to the first shot. Adapted from rea-video (Apache-2.0, `core/nve/analyze/NOTICE`), numpy only; ffmpeg scene detection stays as the fallback.
- Soundtrack analysis (`nve.analyze.beat`, adapted from rea-video): voice / music presence, tempo with half / double alternatives, beat grid, music sections, a no-drums guard, whether cuts land on the beat, and the music's character (brightness, drums, energy, mood hint; tempo and drums only count with a clear beat, so speech is not mistaken for drums). Groundwork for the beat cut strategy.
- New block `core:media.wall`: a full-screen picture over the talking video while the voice keeps going (e.g. a wall of the creator's past videos), zooming towards a focus point brought to the centre as far as the edges allow, with an optional tint and a centre badge (view count with an eye icon). Back-to-back walls join with a hard cut. Both compose engines (HyperFrames; ffmpeg zoompan in the ASS fallback).
- `nve new --name <name>` without files makes an empty project.

## 0.8.0 — 2026-11-14
- Shell skill (`shells/nve/SKILL.md`) is now written in English like every other skill file; behaviour unchanged (git clone first, `add_repo` as fallback, short non-technical replies in the user's language).
- Style questions (`references/style.md`) are written in English and asked in the user's language; the key warning in `references/connections.md` is said in the user's language.
- `INSTALL.md`: install prompt is silent, clones with git, and replies with one fixed sentence telling the user to send a video and type `/nve`.

## 0.7.1 — 2026-11-14
- Install prompt (claude.ai): fetch the shell skill with `git clone` first, `add_repo` only as a fallback.

## 0.7.0 — 2026-11-14
- claude.ai Free: shell skill clones the repo with plain `git clone` first (no `add_repo` on Free), `add_repo` only after two failed clones; claude.ai is recognised by `/mnt/user-data` or `/home/claude`.
- `nve doctor` knows when captions are impossible (Free: no domain can be added): one line "paste the spoken words to make captions" instead of the allowlist steps; Standard adds a gentle hint that Claude Pro gets automatic captions. Install docs: nve needs a paid Claude plan (Pro or higher).
- Whisper (Node) is skipped when huggingface.co is blocked; every `npx` runs from a neutral folder with `npm_config_prefix` from `~/.npmrc` (fixes "prefix cannot be changed from project config").
- faster-whisper gets a float32 16 kHz array decoded by nve (newer PyAV broke `decode_audio`).
- Resources catalog `resources.json` + `nve.resources`: large files (models first) pinned by repo folder, version and SHA-256 of every file, fetched with a sparse partial git clone of `nhathm/nve-resources` (only github.com needed; ~8 s for whisper-small on a claude.ai sandbox), parts joined and cached in `~/.cache/nve/<id>/<version>`.
- New **newbie** edition (`build/export_newbie.py`, `EDITION.json` `"resources": ["whisper-small"]`): when Hugging Face is blocked, whisper-small (CTranslate2 int8) comes from nve-resources.
- Exports keep each public repo's own README / LICENSE.

## 0.6.0 — 2026-11-13
- Claude Code: the folder Claude Code is opened in becomes the workspace. Install = open Claude Code in an empty folder, `/plugin marketplace add` + `/plugin install`, new session, `/nve`: the skill runs `nve-setup` on first use (home folder → `~/nve-studio`; inside an existing workspace → that one).
- `nve init` remembers the workspace (`~/.nve/workspace`), so `/nve` still finds it from another folder.

## 0.5.0 — 2026-11-13
- Retry once: nve retries a failed install/download/network step exactly once (`pip install faster-whisper`, whisper model download, `npx` whisper, Scribe network/5xx errors), then reports the error. Same rule in the skill for commands Claude runs (hard rule 13) and in the shell skill for clone/fetch.
- Network allowlist on claude.ai: `nve doctor` on cloud checks `api.elevenlabs.io` and `huggingface.co` and marks blocked hosts; `nve connect network` and `INSTALL.md` explain adding `api.elevenlabs.io`, `huggingface.co`, `*.huggingface.co`, `*.hf.co` in Settings → Capabilities on the web or desktop app (account-wide, so iPhone chats use it too).

- Claude Code plugin installs the `stable` branch (marketplace source `ref: stable`), not whatever is on `main`.
- `nve engines` / doctor no longer pip-install faster-whisper as a side effect; it is installed on first transcription.
- Plain, short replies: the skill and shell skill tell Claude not to mention commits, branches, paths or engine names unless asked; the install prompt asks for one sentence and the file unchanged.

## 0.4.0 — 2026-11-13
- One deliverable: `final_vN.mp4` only (`--phone` for a smaller copy on request).
- Cover image: `storyboard.cover` (frame time + hook title + emoji) renders `final_vN_cover.jpg` with the same engine; shown first on the preview sheet.
- Option to prepend the cover to the video (`cover.prepend`, default 1 s).

## 0.3.0 — 2026-11-13
- Clips without speech: ingest measures loudness and asks whether to drop the clip's own sound (`sources[].audio: "mute"`, or `mute` on one range).
- Background music: 6 bundled tracks (Kevin MacLeod, CC BY 4.0, normalised to −14 LUFS) with mood tags (`nve assets list bgm`); HeyGen catalog search into the library (`nve assets fetch-bgm --intent …`).
- Credits: renders write `final_vN.credits.txt` with the attribution lines the licences require (music, Noto emoji).
- Green screen (Standard): detection, keyfill → greenkey, flip, gradient/section/image backgrounds.
- Transcript review for whisper transcripts; pause detection repairs whisper word timings; faster-whisper fallback; speech estimated from audio when nothing can transcribe.
- Cloud: shell skill (`shells/nve`) loads `stable` on claude.ai; Claude Code uses the plugin; cross-OS launcher + `nve-setup`.
- Short `INSTALL.md`.

## 0.1.0 — 2026-11-13
- First release: storyboard engine, `/nve` skill, talking-head and product-ad templates, HyperFrames + ffmpeg/ASS engines.
