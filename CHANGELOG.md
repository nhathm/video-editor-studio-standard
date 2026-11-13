# Changelog

Versions go up by 0.1 per release (0.3 → 0.4 → 0.5…) unless a number is chosen. (0.2 was skipped.) `stable` always points at the latest release tag.

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
