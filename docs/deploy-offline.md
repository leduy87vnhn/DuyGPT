# Triển khai DuyGPT lên máy mới (chạy offline sau khi cài)

Checklist đầy đủ để đưa code lên GitHub và cài đặt DuyGPT trên một máy khác, biết rằng máy đó **có Internet lúc cài đặt nhưng sẽ tắt mạng sau đó**.

---

## Phần 0 — Đẩy code lên GitHub (làm trên máy hiện tại)

- [ ] **Đổi mật khẩu GitHub** nếu trước đó bạn từng gõ mật khẩu vào chat/terminal không an toàn.
- [ ] Thêm SSH public key vào GitHub: `https://github.com/settings/keys` → "New SSH key" → dán key sau:
  ```
  ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMTDZPMuLVCKWjQ4oQk2M4el3dWSUPS88K3b2hSZ15+K leduy87vnhn@gmail.com
  ```
- [ ] Tạo repo mới, để trống (không tạo README/gitignore trong đó): `https://github.com/new`
- [ ] Khởi tạo git repo cục bộ và kiểm tra `.gitignore` đã loại trừ file nhạy cảm (`.env`, `certs/`, `wg0.conf`, `.venv/`, `*.log`):
  ```bash
  cd /home/duy/Projects/ai-projects/duygpt
  git init
  git add .
  git status   # rà soát kỹ, đảm bảo KHÔNG thấy .env, certs/*.key, wg0.conf trong danh sách
  git commit -m "Initial commit"
  ```
- [ ] Gắn remote và push (thay `<user>/<repo>` bằng repo bạn vừa tạo):
  ```bash
  git remote add origin git@github.com:<user>/<repo>.git
  git branch -M main
  git push -u origin main
  ```
- [ ] Xác nhận trên GitHub web là code đã lên đủ, **và không có `.env`/`certs/`/khóa riêng tư nào bị lộ**.

---

## Phần 1 — Trên máy đích: cài hệ thống nền (lúc còn Internet)

- [ ] Cài Python, git, PostgreSQL + pgvector:
  ```bash
  sudo apt update
  sudo apt install -y python3 python3-venv python3-pip git \
      postgresql postgresql-contrib postgresql-18-pgvector
  ```
  (đổi `postgresql-18-pgvector` theo đúng major version Postgres nếu khác)
- [ ] Cài Ollama: làm theo `https://ollama.com/download` (script cài chính thức của Ollama).
- [ ] (Tùy chọn) Nếu máy có GPU NVIDIA: cài driver + CUDA trước khi cài Ollama để Ollama tự nhận GPU.

## Phần 2 — Lấy code và cấu hình

- [ ] Clone code từ GitHub:
  ```bash
  git clone git@github.com:<user>/<repo>.git duygpt
  cd duygpt
  ```
- [ ] Tạo `.env` từ mẫu và chỉnh lại cho máy này:
  ```bash
  cp .env.example .env
  ```
  Các giá trị **bắt buộc phải sửa**:
  - `PGPASSWORD` — set 1 mật khẩu DB mới cho máy này
  - `MODEL` — model chat sẽ dùng (phải khớp tên đã `ollama pull` ở Phần 3)
  - `ADMIN_PASSWORD` — đổi khỏi giá trị mặc định `abcd@123`
  - `DEVICE_API_KEY` — nếu có thiết bị loa/Pi gọi API
  - `HOST`/`PORT` giữ mặc định trừ khi có lý do đổi

  Vì máy này sẽ **offline sau khi cài**, lưu ý các mục sau — không bật/dùng vì cần mạng liên tục:
  - `IMAGE_PROVIDER` → để `disabled` (hoặc trỏ về SD WebUI/ComfyUI tự host local nếu có, **không** dùng `openai`)
  - Đừng gọi `/api/voice/speak` hoặc `/api/voice/assistant?want_audio=true` — tính năng đọc trả lời (TTS) hiện chỉ có bản cloud (Microsoft Edge TTS), sẽ lỗi khi offline. Ghi âm/nhập liệu bằng giọng nói (STT, nút mic trong chat) thì vẫn dùng được vì chạy local.

- [ ] Setup PostgreSQL:
  ```bash
  sudo -u postgres psql -c "CREATE ROLE duygpt LOGIN PASSWORD '<khớp PGPASSWORD ở .env>';"
  sudo -u postgres createdb -O duygpt duygpt
  sudo -u postgres psql -d duygpt -c "CREATE EXTENSION IF NOT EXISTS vector;"
  ```

## Phần 3 — Tải model AI (BẮT BUỘC làm lúc còn Internet)

- [ ] Khởi động Ollama và pull đủ model cần dùng:
  ```bash
  ollama serve &
  ollama pull <model chat, vd qwen3:14b>       # phải khớp MODEL trong .env
  ollama pull nomic-embed-text                  # bắt buộc cho RAG (upload tài liệu, CRM tìm kiếm)
  ```
- [ ] Nếu dùng voice (mic nhập liệu chat): chạy thử tính năng ghi âm 1 lần lúc còn mạng để `faster-whisper` tự tải và cache model STT (mặc định `STT_MODEL=small`) — model tải về `~/.cache/huggingface` hoặc tương tự, sau đó dùng lại được offline.
- [ ] (Nếu cần HTTPS để mic hoạt động khi truy cập qua LAN, không phải localhost) Tạo cert tự ký:
  ```bash
  mkdir -p certs
  openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
    -keyout certs/duygpt.key -out certs/duygpt.crt \
    -subj "/CN=duygpt.local"
  ```
  rồi set trong `.env`: `SSL_CERT_FILE=certs/duygpt.crt`, `SSL_KEY_FILE=certs/duygpt.key`, `HTTPS_PORT=8443`.

## Phần 4 — Cài Python deps và chạy thử (vẫn còn mạng)

- [ ] Chạy script cài đặt (tự tạo `.venv` + cài `requirements.txt` — **cần mạng cho bước pip install này**):
  ```bash
  ./scripts/start.sh
  ```
- [ ] Mở trình duyệt kiểm tra: `http://127.0.0.1:8383` (hoặc `https://127.0.0.1:8443` nếu đã cấu hình cert).
- [ ] Đăng nhập bằng `admin` / mật khẩu đã set trong `ADMIN_PASSWORD`, đổi lại mật khẩu ngay trong UI nếu muốn.
- [ ] Test nhanh: gửi 1 tin nhắn chat, upload thử 1 tài liệu (RAG), thử nút mic (STT).
- [ ] Dừng server (Ctrl+C) sau khi test xong.

## Phần 5 — Ngắt mạng, kiểm tra lại lần cuối

- [ ] Tắt Internet của máy.
- [ ] Chạy lại `./scripts/start.sh` (lần này không cần mạng vì `.venv` + packages đã có sẵn).
- [ ] Test lại: chat, upload tài liệu RAG, mic (STT) — tất cả phải chạy bình thường không cần mạng.
- [ ] Xác nhận: **không** bấm vào tính năng tạo ảnh (nếu chưa có backend local) và **không** gọi TTS đọc trả lời — 2 tính năng này cần mạng và sẽ báo lỗi.

## Phần 6 — (Tùy chọn) Tự khởi động cùng hệ thống

Nếu muốn DuyGPT tự chạy mỗi khi máy khởi động lại, tạo systemd service, ví dụ `/etc/systemd/system/duygpt.service`:

```ini
[Unit]
Description=DuyGPT
After=network.target postgresql.service

[Service]
Type=simple
User=<user>
WorkingDirectory=/path/to/duygpt
ExecStart=/path/to/duygpt/.venv/bin/python3 app.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now duygpt
```

Nhớ đảm bảo Ollama và PostgreSQL cũng tự khởi động cùng máy (thường mặc định đã bật qua systemd khi cài bằng apt).
