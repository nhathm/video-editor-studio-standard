# Transcript review (S1b)

Users without an ElevenLabs key get whisper transcripts. Whisper's Vietnamese is phonetically close but
often misspelled (seen on a real clip: "khá insulin" → kháng, "bỡ bụng" → mỡ, "chất sơ" → xơ, "đậu bóc" →
bắp, "chứng" → trứng, "thịt nạt" → nạc, "tinh bộ" → bột, "ngu cốc" → ngũ, "ăn qua học" → khoa học,
"truyền hóa" → chuyển hóa). Captions would show every one of them, so you proof-read before planning.

nve also measures real pauses on the audio at ingest (`<src>.silences.json`) and pushes whisper's word
edges out of them, so cuts and caption timing stay right. You only fix the text.

## Steps

1. `nve transcript show <p>` prints, per source, numbered words grouped by phrase:
   `[5.7s] 14:chất 15:sơ 16:tốt, 17:rau 18:xanh, 19:đậu 20:bóc, …`
2. Read it as a whole: what is the video about (product, topic)? Fix words that are wrong **in that
   context**. Also add sentence punctuation where it helps captions (a word may become "đúng." or "insulin,").
3. Write `analysis/transcripts/<src>.corrections.json` (in the workspace project, never in the install folder):
   ```json
   {"source": "a", "reviewer": "claude", "fixes": [
     {"i": 3, "from": "khá", "to": "kháng"},
     {"i": 15, "from": "sơ", "to": "xơ"},
     {"i": 40, "from": "ừm", "to": ""}
   ]}
   ```
   `i` = the number shown, `from` = the word as shown (a safety check), `to` = the corrected text;
   `""` deletes the word. One word in, one word out: never merge or split words (timings stay as they are).
4. `nve transcript check <p>` applies them, reports any fix that did not match, and refreshes the
   storyboard if there is one. `storyboard.md` lists every correction so the user sees them at G1.

Unsure about a word (a name, a brand)? Keep it and ask the user at G1 instead of guessing. Brand names that
recur go into the storyboard's `text_fixes` instead.
