# Cài nve trên Windows

nve chạy trong **Claude Code**: tab **Code** của app Claude desktop. Cần tài khoản Claude trả phí (Pro trở
lên).

## 1. Cài phần máy cần (một lần, làm trước)

Mở **PowerShell** (bấm Start, gõ `PowerShell`) và chạy lần lượt:

```
winget install --id Git.Git -e
```

```
winget install Python.Python.3.12
```

```
winget install Gyan.FFmpeg
```

Xong thì **thoát hẳn app Claude** (cả biểu tượng ở khay hệ thống, góc phải thanh taskbar) rồi mở lại.
Thiếu Git thì bước 3 sẽ báo "Cần có Git để thêm marketplace".

Không có `winget`: tải bản cài ở git-scm.com, python.org và gyan.dev/ffmpeg, cài với lựa chọn mặc định.

## 2. Mở thư mục làm việc

Tạo một thư mục trống (ví dụ `Video Editor`). Mở app Claude → tab **Code** → tạo phiên mới và chọn thư mục
đó. Video, dự án và cài đặt của bạn sẽ nằm trong thư mục này.

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

nve trên Windows chưa được thử trên máy thật; gặp lỗi thì chụp màn hình gửi người hướng dẫn.
