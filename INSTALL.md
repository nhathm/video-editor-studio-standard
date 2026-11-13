# Cài nve

## Trên điện thoại hoặc claude.ai

**0. Mở mạng cho nve** (chỉ một lần, làm trên **claude.ai bản web hoặc app desktop**: app iPhone không có
mục này). Vào Settings → Capabilities, bật "Code execution and file creation", rồi thêm vào
"Additional allowed domains":

```
api.elevenlabs.io
huggingface.co
*.huggingface.co
*.hf.co
```

Danh sách này lưu theo tài khoản, nên chat mở trên iPhone cũng dùng được. Thiếu nó thì nve không tải được
model whisper (không có caption) và không gọi được ElevenLabs.

**1. Cài** (chỉ một lần). Mở một đoạn chat mới, dán:

```
Cài skill nve cho tôi: dùng add_repo cho nhathm/video-editor-studio-standard, lấy nguyên file shells/nve/SKILL.md (không sửa gì) và đưa tôi nút lưu skill. Chỉ trả lời một câu.
```

Bấm **lưu** trên thẻ skill Claude đưa ra.

**2. Dùng.** Mở đoạn chat mới, gửi video kèm câu:

```
Dùng skill nve dựng video này.
```

Mỗi video một đoạn chat mới.

## Trên máy tính (Claude Code)

**1. Tạo thư mục làm việc.** Tạo một thư mục trống (ví dụ `Video Editor`), rồi mở Claude Code trong thư
mục đó (app desktop: chọn thư mục khi tạo phiên; terminal: `cd` vào thư mục rồi gõ `claude`). Video, dự
án và key của bạn sẽ nằm ở đây.

**2. Cài nve.** Gõ lần lượt:

```
/plugin marketplace add nhathm/video-editor-studio-standard
```

```
/plugin install nve@nve-studio
```

**3. Dùng.** Mở phiên mới trong cùng thư mục, gõ `/nve`. Lần đầu nve tự cài phần còn thiếu (khoảng
1 phút) rồi báo nếu máy thiếu gì (ví dụ ffmpeg). Sau đó kéo video vào và nói cần dựng gì.
