# Style questions (S3, ask once, before the preview)

Ask in ONE message, numbered, each with the default first. If the user answers "mặc định" / "như cũ" /
"default", use the template defaults and skip the rest.

1. **Khung hình / nền tảng**: 9:16 TikTok/Reels (mặc định) · 1:1 · 16:9 YouTube.
2. **Font** (pairs from `packs/fonts/fonts.json`): Đậm hiện đại (Montserrat, mặc định) · Gọn, dấu đẹp
   (Be Vietnam Pro + Inter) · Vui, tròn (Baloo 2 + Nunito) · Sang (Playfair Display + Lora).
3. **Màu / filter**: Trong trẻo (mặc định) · Giữ màu gốc.
4. **Cà da (làm mịn da)**: Có (mặc định cho talking head) · Không.
5. **Phụ đề**: karaoke nền tối, từ khoá vàng (mặc định) · không phụ đề.
6. **Tốc độ**: 1.15× (gợi ý, giữ giọng) · 1.0×.
7. **Nhạc nền**: gợi ý 2–3 bài hợp mood từ `nve assets list bgm` (kèm tên bài + mood) · không nhạc.
   Có HeyGen thì tìm thêm: `nve assets fetch-bgm --intent "..."`.
8. **Tiếng gốc** của các clip không có lời: giữ · tắt (để nhạc nền thay) — chỉ hỏi khi có clip như vậy.
9. **Ảnh bìa**: mình đề xuất khung hình + chữ hook (2–6 từ); có gắn ảnh bìa vào đầu video (1 giây) không?
10. Brand colours? (default ink #1F2A44, accent #FFD84D).

Map answers to `output` and `style` in the storyboard. Font pairs set `style.font.title` and
`style.font.caption`. Other Vietnamese-capable fonts in the pack: Anton, Lexend, Lora, Dancing Script,
Pacifico. A user font goes in `custom/fonts/` (then check the diacritics in the preview).

## House style ("làm như cũ") = `core:talking-head` defaults

Karaoke captions (3–5 words, dark pill, keywords yellow with a pop) + a highlight stamp on every key idea
(white/yellow text, navy stroke, Noto animated emoji above) + SFX on every stamp/card + soft bgm (≈ 0.1)
+ look "Trong trẻo" with skin retouch + suggest 1.15× + a CTA naming the person ("INBOX THẮM").
Captions-only versions felt too plain to the owner.
