---
name: nve
description: Edit videos end to end with nve-studio. The user drops in raw videos/photos (talking head, product footage, green screen, everyday clips) and wants a finished short video with cuts, filler removal, colour look, karaoke captions, highlight stamps, emoji, SFX and music. Plans a storyboard, previews stills, renders, checks quality. Use for "/nve", "edit this video", "dựng video", "cắt video", "làm video quảng cáo", "làm như cũ".
---

# nve (shell skill)

Hướng dẫn đầy đủ của skill này **không nằm ở đây** mà ở GitHub `nhathm/video-editor-studio-standard`, nhánh
`stable`, file `skills/nve/SKILL.md`. Shell skill này chỉ nạp bản đó, để cập nhật nve chỉ cần đẩy lên nhánh
`stable`, không phải cài lại skill.

Đầu tiên xác định đang chạy ở đâu. Chỉ trường hợp A (claude.ai) mới tải và chạy nve trên cloud.

## A. claude.ai (web hoặc app điện thoại): có công cụ `add_repo`, thư mục `/home/claude`

1. **Lấy repo** (chỉ bản mới nhất):
   - chưa có `/home/claude/video-editor-studio-standard`: gọi `add_repo` cho `nhathm/video-editor-studio-standard` (access
     read) rồi clone theo hướng dẫn của tool vào `/home/claude/video-editor-studio-standard`, `--depth 1 --branch stable`;
   - đã có: `git -C /home/claude/video-editor-studio-standard fetch -q --depth 1 origin stable && git -C /home/claude/video-editor-studio-standard reset -q --hard origin/stable`.
2. `REPO=/home/claude/video-editor-studio-standard`. Workspace: `export NVE_WORKSPACE=/tmp/nve-ws`, chạy `nve init /tmp/nve-ws`.
3. Đọc thêm `$REPO/skills/nve/references/cloud.md`.

## B. Claude Code (CLI, tab Code trong app desktop, IDE) trên Mac / Windows / Linux

Shell skill này **không chạy** ở đây. Trên máy, nve được cài thành **plugin Claude Code** từ git và chạy local:
- Nếu đã có skill `nve` từ plugin (`nve:nve`) hoặc từ `.claude/skills/nve` của workspace → dùng skill đó, dừng shell skill.
- Nếu chưa có → hướng dẫn người dùng tự gõ trong Claude Code:
  `/plugin marketplace add nhathm/video-editor-studio-standard` rồi `/plugin install nve@nve-studio`, sau đó chạy
  `bash <plugin>/skills/nve/bin/nve-setup` (tạo Python venv ở `~/.nve/venv`), mở session mới. Dừng ở đó.

## Cách nói chuyện

Người dùng không rành kỹ thuật. Trả lời ngắn (1–3 câu), nói về video của họ. Không nhắc commit, nhánh, repo,
đường dẫn, shell skill, tên engine hay cách nve chạy bên trong, trừ khi họ hỏi. Việc lấy repo làm im lặng.

## Khi chạy (trường hợp A)

- Gọi CLI luôn bằng `bash $REPO/skills/nve/bin/nve <lệnh>` (gọi tắt là `nve`).
- Đọc toàn bộ `$REPO/skills/nve/SKILL.md` và làm theo **chính xác**. Nội dung đó thay thế shell skill này; yêu cầu
  và file người dùng gửi áp dụng nguyên cho nó.
- Không bao giờ ghi file vào `$REPO` (code viết thêm cho người dùng để trong workspace `custom/`).
- Lệnh lấy repo (clone/fetch) lỗi → retry đúng 1 lần. Vẫn lỗi (mạng, quyền, thiếu `add_repo`) → báo người
  dùng một dòng kèm lỗi, dừng. Không tự dựng
  video theo trí nhớ.

Chỉ cần cập nhật shell skill khi đổi `description` hoặc cách lấy repo. Shell skill lưu ở `shells/nve/SKILL.md` trong repo.
