# Hướng Dẫn DuyGPT — Build, Chạy, Sử Dụng

Tài liệu này là hướng dẫn nhanh, thực tế cho chính máy đang chạy DuyGPT. Muốn tra cứu chi tiết từng phần thì xem thư mục [`docs/`](docs/) (liệt kê ở cuối file).

## 1. DuyGPT là gì

Một server AI chạy hoàn toàn on-prem (LLM + database + web đều trên máy này), gồm 3 khu vực:

| Trang | Địa chỉ | Dùng để |
| --- | --- | --- |
| Chat chính | `/` | Chat với AI, tài khoản, persona, RAG tài liệu, tạo ảnh, API giọng nói cho loa/Raspberry Pi |
| Trợ lý gia đình | `/home` | Nhắc việc, ghi chú, danh sách mua sắm — chat có tool-calling |
| Quản lý yêu cầu khách hàng (CRM) | `/crm` | Chỉ admin — khách hàng, sản phẩm, hiện trạng/yêu cầu, tài liệu, đề xuất, tư vấn AI, lịch làm việc |

Cả 3 trang dùng chung một server, một port, một database, một model LLM.

## 2. Yêu cầu hệ thống

- Python 3.10+ (máy này đang chạy Python 3.14 trong `.venv`)
- [Ollama](https://ollama.com) đã cài, đang chạy (`ollama serve`) — hoặc một backend OpenAI-compatible khác (vLLM, LM Studio...)
- PostgreSQL + extension `pgvector`
- GPU khuyến nghị cho tốc độ (máy này: RTX 5060 Ti 16GB)

## 3. Build (cài đặt lần đầu)

### 3.1. Model LLM + embedding

```bash
ollama serve
ollama pull qwen3:14b            # hoặc model chat khác bạn muốn dùng
ollama pull nomic-embed-text     # bắt buộc — dùng cho RAG/tìm kiếm tài liệu ở cả 3 trang
```

### 3.2. PostgreSQL (một lần)

```bash
sudo apt update && sudo apt install -y postgresql postgresql-contrib postgresql-18-pgvector
sudo -u postgres psql -c "CREATE ROLE duygpt LOGIN PASSWORD '<chọn-mật-khẩu>';"
sudo -u postgres createdb -O duygpt duygpt
sudo -u postgres psql -d duygpt -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

Đổi `postgresql-18-pgvector` nếu bản PostgreSQL trên máy khác 18.

### 3.3. Cấu hình

```bash
cp .env.example .env   # bỏ qua nếu .env đã có sẵn
```

Sửa `.env`, tối thiểu cần:

- `PGPASSWORD` — khớp mật khẩu đã tạo ở bước 3.2
- `MODEL` — model đã `ollama pull`, hiện đang đặt `qwen3:14b`
- `REQUIRE_LOGIN=1` — bắt buộc bật trước khi expose ra Internet
- `DEVICE_API_KEY` — nếu dùng API cho loa/thiết bị (`/api/voice/chat`, `/api/schedule/location`)

Toàn bộ danh sách biến: [`docs/configuration.md`](docs/configuration.md).

### 3.4. Cài Python dependencies

Không cần làm thủ công — bước "Chạy" ở dưới tự tạo `.venv` và cài `requirements.txt` (gồm `psycopg`, `pypdf`, `python-docx`, `python-pptx`, `openpyxl`, `faster-whisper`...). Chỉ cần chạy tay nếu muốn build trước:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

> Lưu ý: nếu bạn từng di chuyển thư mục dự án sang đường dẫn khác, `.venv/bin/pip` có thể trỏ sai đường dẫn cũ (bad interpreter). Cách sửa nhanh nhất: xóa `.venv` rồi chạy lại `./scripts/start.sh` để nó tự tạo venv mới.

## 4. Chạy

```bash
./scripts/start.sh
```

Script này tự động: tạo `.env` nếu chưa có, tạo `.venv` nếu chưa có, cài `requirements.txt`, rồi chạy `app.py` — chạy ở foreground (chiếm terminal, Ctrl+C để dừng).

Mở trình duyệt:

```text
http://127.0.0.1:8383          (trên chính máy này)
http://<IP-LAN-máy-này>:8383   (từ máy khác trong mạng nội bộ)
```

### Chạy nền lâu dài (khuyến nghị cho máy chủ)

`start.sh` chạy foreground nên tắt terminal là service tắt theo. Muốn chạy nền, dùng một trong hai cách:

```bash
# Cách nhanh: tmux/screen
tmux new -s duygpt './scripts/start.sh'
# Ctrl+B rồi D để detach, tmux attach -t duygpt để quay lại

# Cách bền vững hơn: systemd (tạo /etc/systemd/system/duygpt.service)
```

```ini
[Unit]
Description=DuyGPT
After=network.target postgresql.service

[Service]
WorkingDirectory=/home/duy/Projects/ai-projects/duygpt
ExecStart=/home/duy/Projects/ai-projects/duygpt/.venv/bin/python3 app.py
Restart=on-failure
User=duy

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now duygpt
```

### Tài khoản admin

Được tạo tự động lần chạy đầu tiên, từ `.env`:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=abcd@123
```

**Đổi mật khẩu admin trước khi expose ra Internet.**

### Truy cập từ Internet (đã port-forward)

Nếu bạn đã port-forward cổng `8383` ra IP public (như hiện tại) thì không cần làm gì thêm — cả 3 trang (`/`, `/home`, `/crm`) đều dùng chung cổng đó. Chi tiết mô hình VPN/port-forward đang dùng: [`docs/public-access.md`](docs/public-access.md).

## 5. Sử dụng

### 5.1. Trang chat chính (`/`)

- Đăng nhập/đăng ký ở sidebar trái (bắt buộc nếu `REQUIRE_LOGIN=1`).
- Chọn provider/model, chỉnh temperature.
- Chat bình thường; lịch sử được lưu theo tài khoản, xem lại ở panel "History".
- Gõ `/image <mô tả>` để tạo ảnh (cần cấu hình `IMAGE_PROVIDER`, xem [`docs/image-generation.md`](docs/image-generation.md)).
- Admin thấy thêm panel Persona (tính cách AI, có thể có nhiều persona, chọn persona nào dùng cho web/voice) và panel Documents (upload tài liệu cho RAG — AI sẽ tham khảo khi trả lời). Xem [`docs/persona-memory.md`](docs/persona-memory.md).
- Ghi âm giọng nói (icon micro) trên web, hoặc cho loa/Raspberry Pi dùng API `/api/voice/assistant` — thiết bị chỉ cần gửi file âm thanh (thu theo hot word hoặc ngắt khi im lặng), server tự nhận diện giọng nói, tự chọn Trợ Lý Gia Đình / Trợ Lý Công Việc / ChatGPT phù hợp, trả lại text để thiết bị đọc ra loa. Thiết bị không tự đọc được thì thêm `"want_audio": true` vào request, hoặc gọi riêng `/api/voice/speak` để lấy file mp3 (cần Internet, dùng `edge-tts`). Module `ai-voice-server` cũ giờ không cần chạy song song nữa — `/api/voice/assistant` đã thay thế đầy đủ. Xem [`docs/speaker-api.md`](docs/speaker-api.md) và [`docs/raspberry-pi-speaker.md`](docs/raspberry-pi-speaker.md).

### 5.2. Trợ lý gia đình (`/home`)

Cần đăng nhập (tài khoản bất kỳ, không cần admin). Đây là agent có thể tự gọi tool để thao tác dữ liệu qua chat, hoặc bạn thao tác trực tiếp trên sidebar:

- **Nhắc việc**: thêm/đánh dấu xong/xóa. Hỏi AI kiểu "Nhắc tôi đổ rác lúc 8 giờ tối nay" — AI tự tính giờ và lưu.
- **Mua sắm**: danh sách mua sắm, tick khi đã mua.
- **Ghi chú**: ghi chú nhanh.
- Mỗi tài khoản có dữ liệu riêng (nhắc việc/ghi chú/mua sắm của ai người đó thấy).

Chi tiết: [`docs/home-assistant.md`](docs/home-assistant.md).

### 5.3. Quản lý yêu cầu khách hàng (`/crm`) — chỉ admin

1. **Chọn/tạo khách hàng** và **chọn/tạo sản phẩm** ở sidebar (2 dropdown độc lập — một khách hàng có thể dùng nhiều sản phẩm khác nhau, ví dụ Production Auto Planning, Smart Warehouse Management System, MES).
2. Sau khi chọn đủ cả hai, khu vực làm việc chính hiện ra với 4 phần:
   - **Hiện trạng & Yêu cầu**: nhật ký ghi nhận hiện trạng nghiệp vụ và yêu cầu của khách hàng theo thời gian.
   - **Tài liệu (Memo/Đề án)**: upload file tham khảo (txt/md/pdf/docx/pptx/xlsx). Upload file mới cùng tiêu đề = tạo phiên bản mới (bản cũ không mất, bật "Hiện tất cả phiên bản" để xem lại).
   - **Đề xuất**: viết/lưu đề xuất dạng nháp, đính kèm nhiều file **.docx/.pptx/.xlsx/.pdf** (nội dung được đọc vào database để tìm kiếm được). Bấm **"Chốt"** khi đề xuất là bản chính thức để triển khai — chốt đề xuất mới sẽ tự chuyển đề xuất chốt trước đó sang "đã thay thế". Đề xuất cũ không dùng nữa thì bấm **"Inactive hóa"** — nó sẽ bị loại khỏi kết quả tìm kiếm/tư vấn nhưng vẫn còn trong lịch sử.
   - **Tư vấn AI**: chat hỏi đáp/xin tư vấn, chỉ dựa trên hiện trạng/yêu cầu đã ghi và nội dung các file đã upload (không bịa). Có thể nhờ AI lưu gợi ý thành đề xuất nháp — vẫn phải tự tay bấm "Chốt" mới chính thức.
3. **Lịch làm việc** (panel trên cùng, luôn hiện, không cần chọn khách hàng trước): ghi lịch làm việc — nội dung, khách hàng liên quan (tùy chọn), địa điểm, giờ bắt đầu/kết thúc. API `/api/schedule/location?at=...` dùng để tra "đang ở đâu tại thời điểm nào" — dành cho voice assistant/màn hình Raspberry Pi tích hợp sau này.

Chi tiết đầy đủ (API, cấu hình `CRM_MODEL`...): [`docs/crm.md`](docs/crm.md).

## 6. Cấu hình hay dùng nhất

```env
PORT=8383
PROVIDER=ollama
MODEL=qwen3:14b
REQUIRE_LOGIN=1
HOME_ASSISTANT_MODEL=       # để trống = dùng chung MODEL
CRM_MODEL=                  # để trống = dùng chung MODEL
EMBEDDING_MODEL=nomic-embed-text
```

Danh sách đầy đủ: [`docs/configuration.md`](docs/configuration.md).

## 7. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Lỗi khi upload tài liệu / hỏi RAG không ra kết quả | Chưa `ollama pull nomic-embed-text` | Pull model embedding rồi thử lại |
| `/crm/*` trả về 403 | Tài khoản không phải admin | Đăng nhập bằng tài khoản `admin_user` |
| `./scripts/start.sh` báo lỗi ngay bước cài đặt | `.venv` hỏng (thường do đổi đường dẫn thư mục dự án) | `rm -rf .venv` rồi chạy lại `./scripts/start.sh` |
| Không upload được attachment cho đề xuất | File không phải `.docx`/`.pptx`/`.xlsx`/`.pdf` | Module CRM chỉ chấp nhận 4 định dạng này |
| Chat không trả lời / lỗi 502 | Ollama chưa chạy, hoặc model trong `MODEL`/`HOME_ASSISTANT_MODEL`/`CRM_MODEL` chưa được `ollama pull` | `ollama serve` + `ollama pull <model>` |
| Trợ lý gia đình/CRM không tự gọi tool đúng | Model không hỗ trợ tool-calling | Dùng model họ Qwen2.5/Qwen3-Instruct qua Ollama |

## 8. Tài liệu chi tiết

- [Setup gốc](docs/setup.md)
- [Cấu hình đầy đủ (.env)](docs/configuration.md)
- [Truy cập public / port-forward](docs/public-access.md)
- [API cho loa/thiết bị](docs/speaker-api.md)
- [Raspberry Pi speaker](docs/raspberry-pi-speaker.md)
- [Persona, ký ức, quan hệ gia đình](docs/persona-memory.md)
- [Tạo ảnh](docs/image-generation.md)
- [Trợ lý gia đình](docs/home-assistant.md)
- [CRM — Quản lý yêu cầu khách hàng](docs/crm.md)
