---
name: nve
description: Edit videos end to end with nve-studio. The user drops in raw videos/photos (talking head, product footage, green screen, everyday clips) and wants a finished short video with cuts, filler removal, colour look, karaoke captions, highlight stamps, emoji, SFX and music. Plans a storyboard, previews stills, renders, checks quality. Use for "/nve", "edit this video", "dựng video", "cắt video", "làm video quảng cáo", "làm như cũ".
---

# nve (shell skill)

Hướng dẫn đầy đủ của skill này **không nằm ở đây** mà ở GitHub `nhathm/video-editor-studio-standard`, nhánh
`stable`, file `skills/nve/SKILL.md`. Shell skill này chỉ nạp bản đó, để cập nhật nve chỉ cần đẩy lên nhánh
`stable`, không phải cài lại skill.

Đầu tiên xác định đang chạy ở đâu. Chỉ trường hợp A (claude.ai) mới tải và chạy nve trên cloud.

## A. claude.ai (web hoặc app điện thoại, gói Free hoặc trả phí): có `/mnt/user-data` hoặc `/home/claude`

1. **Lấy repo** (bản mới nhất), `REPO=/tmp/video-editor-studio-standard`:
   - chưa có `$REPO`: `GIT_TERMINAL_PROMPT=0 git clone -q --depth 1 --branch stable https://github.com/nhathm/video-editor-studio-standard.git $REPO`.
     Lỗi thì chạy lại đúng 1 lần. Vẫn lỗi **và** có công cụ `add_repo` → gọi `add_repo` cho
     `nhathm/video-editor-studio-standard` (access read) rồi clone theo hướng dẫn của tool vào `$REPO`
     (`--depth 1 --branch stable`). Không có `add_repo` → báo người dùng một dòng kèm lỗi, dừng.
   - đã có: `git -C $REPO fetch -q --depth 1 origin stable && git -C $REPO reset -q --hard origin/stable`
     (lỗi thì dùng bản đang có).
2. Workspace: `export NVE_WORKSPACE=/tmp/nve-ws`, chạy `nve init /tmp/nve-ws`.
3. Đọc thêm `$REPO/skills/nve/references/cloud.md`.

## B. Claude Code (CLI, tab Code trong app desktop, IDE) trên Mac / Windows / Linux

Shell skill này **không chạy** ở đây. Trên máy, nve được cài thành **plugin Claude Code** từ git và chạy local:
- Nếu đã có skill `nve` từ plugin (`nve:nve`) hoặc từ `.claude/skills/nve` của workspace → dùng skill đó, dừng shell skill.
- Nếu chưa có → hướng dẫn người dùng (ngắn gọn): mở Claude Code trong thư mục muốn chứa video, gõ
  `/plugin marketplace add nhathm/video-editor-studio-standard` rồi `/plugin install nve@nve-studio`, mở phiên mới
  trong cùng thư mục và gõ `/nve` (lần đầu skill tự chạy `nve-setup`). Dừng ở đó.

## Cách nói chuyện

Người dùng không rành kỹ thuật. Trả lời ngắn (1–3 câu), nói về video của họ. Không nhắc commit, nhánh, repo,
đường dẫn, shell skill, tên engine hay cách nve chạy bên trong, trừ khi họ hỏi. Việc lấy repo làm im lặng.

## Khi chạy (trường hợp A)

- Gọi CLI luôn bằng `bash $REPO/skills/nve/bin/nve <lệnh>` (gọi tắt là `nve`).
- Đọc toàn bộ `$REPO/skills/nve/SKILL.md` và làm theo **chính xác**. Nội dung đó thay thế shell skill này; yêu cầu
  và file người dùng gửi áp dụng nguyên cho nó.
- Không bao giờ ghi file vào `$REPO` (code viết thêm cho người dùng để trong workspace `custom/`).
- Không lấy được repo (xem bước 1) → báo người dùng một dòng kèm lỗi, dừng. Không tự dựng video theo trí nhớ.

Chỉ cần cập nhật shell skill khi đổi `description` hoặc cách lấy repo. Shell skill lưu ở `shells/nve/SKILL.md` trong repo.
