# Cài nve trên Mac

nve chạy trong **Claude Code**: tab **Code** của app Claude desktop, hoặc lệnh `claude` trong Terminal.
Cần tài khoản Claude trả phí (Pro trở lên).

## 1. Mở thư mục làm việc

Tạo một thư mục trống (ví dụ `Video Editor`). Mở app Claude → tab **Code** → tạo phiên mới và chọn thư mục
đó. Video, dự án và cài đặt của bạn sẽ nằm trong thư mục này.

## 2. Cài phần máy cần (một lần)

Dán vào phiên vừa mở:

```
Kiểm tra máy Mac này đã có Git, Python 3.10+ và ffmpeg (bản có libass) chưa. Thiếu cái nào thì cài bằng Homebrew (chưa có Homebrew thì hướng dẫn tôi cài, không tự chạy lệnh cần mật khẩu). Trả lời ngắn: đã có gì, vừa cài gì, còn thiếu gì.
```

## 3. Cài nve

Tự gõ lần lượt vào ô chat (Claude không tự chạy được lệnh `/plugin`):

```
/plugin marketplace add nhathm/video-editor-studio-standard
```

```
/plugin install nve@nve-studio
```

## 4. Dùng

Mở **phiên mới** trong cùng thư mục, kéo video vào và gõ:

```
/nve
```

Lần đầu nve tự cài phần còn lại (khoảng 1 phút) rồi bắt đầu dựng. Từ lần sau chỉ cần mở thư mục đó và
gõ `/nve`.
