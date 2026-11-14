# Connections (third parties)

nve works with **no account at all** (level L0). Keys only add features. `nve doctor` shows the level.

| Level | User does | Adds |
|---|---|---|
| L0 | nothing | everything except below: cut, grade, captions (whisper), stamps, cards, bundled SFX/emoji/fonts, render |
| + ElevenLabs | creates an API key | Scribe transcripts (much better Vietnamese, keeps fillers so they can be cut), later TTS/SFX generation |
| + HeyGen | signs in (OAuth) | HeyGen catalog music/images (via HyperFrames media-use) |

`nve connect elevenlabs` / `nve connect heygen` print the steps for the current runtime.

## Local (Claude Code)

- ElevenLabs: the user pastes `ELEVENLABS_API_KEY=...` into `<workspace>/.env` **themselves**. Never ask
  for the key in chat, never print `.env`. Then `nve doctor --refresh`.
- HeyGen: the user runs `npx hyperframes@0.9.23 auth login` (browser). Check with `nve doctor --deep`.

## Cloud (claude.ai) only: a key pasted in chat

Prefer a claude.ai connector if one exists. Otherwise, if the user wants to paste a key, first say once (in the user's language):

> Key bạn dán sẽ nằm trong lịch sử cuộc trò chuyện này; ai xem được thread (hoặc nếu bạn chia sẻ nó) đều
> thấy key. Nên tạo một key riêng cho nve, đặt hạn mức credit thấp, và xoá/tạo lại key khi xong. Bạn
> vẫn muốn dán chứ?

If they agree: write it only to the sandbox's `<workspace>/.env` (never into a project file, zip, log or
output), never repeat it, and at the end remind them in one line to revoke it.

## Without keys: what changes

- Transcripts come from whisper (offline): Vietnamese fillers like "ừ/ờ" may be missed; check suspicious
  spots and tell the user it's a lower-precision transcript.
- On a cloud sandbox where whisper cannot download its model: no captions and cut by silence only;
  offer captions from a script the user pastes.
- Music: the 6 bundled tracks (Kevin MacLeod, CC BY: credit line required) and the user's library
  (`nve assets list bgm`); HeyGen search needs the HeyGen login.
