# Style questions (S3, ask once, before the preview)

Read `nve taste prompt` first and skip the questions the user's taste already answers. Ask in ONE message, in the user's language, each with the default first, as choices (buttons / radio: AskUserQuestion in Claude Code, the options widget on claude.ai); a numbered list only when the host has no choice UI. If the user answers
"default" / "mặc định" / "như cũ", use the template defaults and skip the rest.

1. **Frame / platform**: 9:16 TikTok/Reels (default) · 1:1 · 16:9 YouTube.
2. **Font** (pairs from `packs/fonts/fonts.json`): Bold modern (Montserrat, default) · Clean, good diacritics
   (Be Vietnam Pro + Inter) · Fun, rounded (Baloo 2 + Nunito) · Elegant (Playfair Display + Lora).
3. **Colour / filter**: "Trong trẻo" / clean & bright (default) · Original colours.
4. **Skin retouch** (smoothing): Yes (default for talking head) · No.
5. **Captions** (`style.caption.block`): bold white words with a dark outline, the spoken word in the accent
   colour (`core:caption.bold-outline`, default) · the spoken word in a colour box (`core:caption.word-box`) ·
   big pop-in, 1–3 words at a time (`core:caption.pop-word`, high energy) · karaoke on a dark pill
   (`core:caption.karaoke-pill`) · no captions (`"none"`). Keywords (product, numbers, CTA name) in `keywords`.
6. **Speed**: 1.15× (suggested, keeps the voice) · 1.0×.
7. **Background music**: suggest 2–3 tracks that fit the mood from `nve assets list bgm` (with title + mood) ·
   no music. With HeyGen, search more: `nve assets fetch-bgm --intent "..."`.
8. **Original sound** of clips without speech: keep · mute (let the music replace it). Ask only when such
   clips exist.
9. **Cover image**: propose a frame + hook text (2–6 words); also put the cover at the start of the video
   (1 second)?
10. **Colours** (choices): send a picture to take the colours from · say the colour you want · default (I choose).
   Picture: save it in the project and run `nve palette --image <file>`. A named colour: convert it to #RRGGBB
   and run `nve palette --accent <hex>`. Default / no answer: `nve palette <p>` picks an accent that stands out
   from the footage. Write the returned `palette` to `style.palette`.
11. **Transitions**: only when the user mentions them, or when every source is a photo (then always ask). Choices
   from `nve transitions` with their Vietnamese labels, "you choose" first; no answer = `style.transition: "random"`.

Map answers to `output` and `style` in the storyboard. Font pairs set `style.font.title` and
`style.font.caption`. Other Vietnamese-capable fonts in the pack: Anton, Lexend, Lora, Dancing Script,
Pacifico. A user font goes in `custom/fonts/` (then check the diacritics in the preview).

## House style ("làm như cũ") = `core:talking-head` defaults

Bold outlined captions (2–4 words, the spoken word yellow, keywords stay yellow with a pop) + a hook title with a
marker highlight in the first 2–3 s + a highlight stamp on every key idea
(white/yellow text, navy stroke, Noto animated emoji above) + SFX on every stamp/card + soft bgm (≈ 0.1)
+ look "Trong trẻo" with skin retouch + suggest 1.15× + a CTA naming the person ("INBOX THẮM").
Captions-only versions felt too plain to the owner.
