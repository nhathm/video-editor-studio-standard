# Running on claude.ai (cloud sandbox, also the Claude iPhone/Android app)

## Install (once per account)

Install the **shell skill** (`shells/nve/SKILL.md`, steps in `INSTALL.md`). It loads the `stable` branch of the
repo in each conversation. Fallback: upload `nve-cloud-<edition>-<version>.zip` (`build/pack.py`) in
Settings → Capabilities → Skills.

## Network allowlist (once per account)

The sandbox may only reach allowed domains. nve needs:

| Domain | For |
|---|---|
| `api.elevenlabs.io` | Scribe transcripts (with an ElevenLabs key) |
| `huggingface.co`, `*.huggingface.co`, `*.hf.co` | whisper model files (transcripts without a key) |

`nve doctor` on cloud checks these and marks a blocked host `BLOCKED`. Then tell the user (in their language):

1. Open **claude.ai in a web browser or the desktop app**. The iOS app's Settings → Capabilities has no
   "Additional allowed domains" field.
2. Settings → Capabilities: "Code execution and file creation" on; add the four domains above to
   "Additional allowed domains".
3. The list is stored on the account, and the code runs in Anthropic's cloud sandbox, not on the phone, so
   chats opened on iPhone use it too. Adding it once on the web is enough. Start a new chat afterwards.

`nve connect network` prints the same steps.

## Per conversation

`nve doctor` reports `runtime=cloud` when `/mnt/user-data` or `/mnt/skills` exists.

- **One thread per video.** Nothing persists between threads. Start with:
  `export NVE_WORKSPACE=/tmp/nve-ws && bash <skill dir>/bin/nve init /tmp/nve-ws`
  (always call the CLI as `bash <skill dir>/bin/nve ...`: the executable bit may be lost on upload).
- Uploaded files are in `/mnt/user-data/uploads/`. Pass them to `nve new`.
- Deliver to `/mnt/user-data/outputs/`: the final video, the cover image, the credits text and `project.zip`
  (`storyboard.json`, `storyboard.md`, `analysis/`, `project.md`, without `work/`) so the user can continue later.
- Engines: without Node/Chrome, compose falls back to ffmpeg/ASS automatically (no animated emoji).
  Transcripts: Scribe (key) → whisper (Node) → faster-whisper (pip + model download) → none. With none,
  nve measures speech on the audio and cuts on pauses, but there are **no captions**: tell the user and
  offer captions from a script they paste.
- Python: nve needs numpy + Pillow (usually present). Skin retouch needs opencv
  (`pip install opencv-python-headless` if PyPI is reachable); without it the look is approximated.
- Keep videos short (≤ 1–3 min): CPU and time are limited. Measure on the first run and tell the user.
- Keys: see `connections.md` (cloud-only consent rule).
