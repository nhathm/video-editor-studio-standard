# Style questions (S3, ask once, before the preview)

Read `nve taste prompt` first and skip the questions the user's taste already answers. Ask in ONE message, in the user's language, numbered, each with the default first. If the user answers
"default" / "mặc định" / "như cũ", use the template defaults and skip the rest.

1. **Frame / platform**: 9:16 TikTok/Reels (default) · 1:1 · 16:9 YouTube.
2. **Font** (pairs from `packs/fonts/fonts.json`): Bold modern (Montserrat, default) · Clean, good diacritics
   (Be Vietnam Pro + Inter) · Fun, rounded (Baloo 2 + Nunito) · Elegant (Playfair Display + Lora).
3. **Colour / filter**: "Trong trẻo" / clean & bright (default) · Original colours.
4. **Skin retouch** (smoothing): Yes (default for talking head) · No.
5. **Captions**: karaoke on a dark pill, keywords yellow (default) · no captions.
6. **Speed**: 1.15× (suggested, keeps the voice) · 1.0×.
7. **Background music**: suggest 2–3 tracks that fit the mood from `nve assets list bgm` (with title + mood) ·
   no music. With HeyGen, search more: `nve assets fetch-bgm --intent "..."`.
8. **Original sound** of clips without speech: keep · mute (let the music replace it). Ask only when such
   clips exist.
9. **Cover image**: propose a frame + hook text (2–6 words); also put the cover at the start of the video
   (1 second)?
10. Brand colours? (default ink #1F2A44, accent #FFD84D).

Map answers to `output` and `style` in the storyboard. Font pairs set `style.font.title` and
`style.font.caption`. Other Vietnamese-capable fonts in the pack: Anton, Lexend, Lora, Dancing Script,
Pacifico. A user font goes in `custom/fonts/` (then check the diacritics in the preview).

## House style ("làm như cũ") = `core:talking-head` defaults

Karaoke captions (3–5 words, dark pill, keywords yellow with a pop) + a highlight stamp on every key idea
(white/yellow text, navy stroke, Noto animated emoji above) + SFX on every stamp/card + soft bgm (≈ 0.1)
+ look "Trong trẻo" with skin retouch + suggest 1.15× + a CTA naming the person ("INBOX THẮM").
Captions-only versions felt too plain to the owner.
