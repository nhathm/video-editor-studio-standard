# talking-head: editorial rules

- Cut strategy `speech`: drop fillers (ờ, ừ, ừm, ừa, ơ, ầm, ờm; um, uh), long pauses, false starts (Scribe marks them `--`) and retakes (keep the last good take). Ask before removing verbal tics such as "thì là", "kiểu như", "nói chung là".
- First 1–3 s must hook: start on the strongest sentence; if the real hook is later, consider moving it first.
- Stamps (`core:stamp.slam`) on every key idea, 1.2–3 s each, text ≤ 2 short lines in CAPITALS, one Noto emoji that fits the idea. Alternate `alt: true` for rhythm. Keep stamps in the top area; never over the face.
- Image cards (`core:card.image`) only while the product/thing is being named; one item per card.
- Captions: 3–5 words, keywords (product names, numbers, the CTA name) in `style.caption.keywords`.
- Suggest speed 1.15× to the user (pitch is kept).
- CTA at the end names the person in the clip ("INBOX THẮM"), from the transcript.
- Fix brand mishearings via `text_fixes` (e.g. "Tranh" -> "Chanh", "Inbốc" -> "Inbox").
- Soft bgm at volume ≈ 0.1 under the voice if a suitable track exists (`nve assets list bgm`).
