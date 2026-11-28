# NoWayBack — AI Hỗ trợ Bác sĩ Dự thảo Đơn thuốc Ngoại trú (Track B)

**Thành viên, lớp, track:** xem [TEAMS.md](TEAMS.md).

*Lát cắt: Bác sĩ nhập chẩn đoán đã xác nhận và thông tin bệnh nhân, AI đề xuất phương án kê đơn dựa trên tài liệu chuyên môn và danh mục thuốc (83 thuốc xác minh), hoặc báo thiếu căn cứ / chặn vi phạm an toàn bằng Python thuần, để bác sĩ kiểm duyệt và quyết định (HITL).*

---

## Chạy web Medora trên máy local

Từ thư mục gốc, chạy bằng Python 3.10+.

```powershell
python codebase/web.py
```

Mở [Medora](http://127.0.0.1:8000) và bấm **Vào bản mô phỏng**. Chế độ mặc định đọc trực tiếp dữ liệu trong `data/processed/` và chạy offline. Nếu cổng 8000 đang bận, dùng `python codebase/web.py --port 8001` rồi mở cổng tương ứng. Dừng server bằng `Ctrl+C`.

- **Tra cứu thuốc** theo tên, hoạt chất hoặc biệt dược và lọc theo đơn vị. Chi tiết hiển thị chỉ định trong danh mục, đường dùng, chống chỉ định, tương tác và nguồn tham chiếu.
- **Xem đơn mẫu và tìm đơn theo chẩn đoán.** Màn hình tạo đơn mở sẵn một đơn giả lập từ dữ liệu đã xử lý. Để tìm đơn khác, nhập tên chẩn đoán đã được bác sĩ xác nhận, ví dụ `viêm mũi dị ứng, tăng huyết áp`. Dùng dấu phẩy, chấm phẩy hoặc xuống dòng cho nhiều chẩn đoán. Chọn **Bổ sung thuốc** khi cần mở danh sách thuốc tham khảo để tạo bản nháp.
- **Điền thông tin để rà soát và in đơn.** Các ô thông tin bệnh nhân và liều là tùy chọn. Backend báo những kiểm tra thiếu dữ liệu, chặn rủi ro đã xác định và chỉ tính chi phí khi đã nhập số lượng cho mọi dòng thuốc. Sau khi rà soát, dùng hộp thoại in để lưu bản mô phỏng dưới dạng PDF.
- **Lưu trên trình duyệt.** Đơn đang soạn lưu theo phiên khi bấm **Lưu bản nháp**. Lịch sử mô phỏng lưu trên trình duyệt hiện tại. Hãy dùng hồ sơ giả lập trong bản chạy local này.

### Bật Ollama tùy chọn

Sau khi khởi động Ollama và tải một mô hình, đặt các biến sau trong PowerShell với đúng tên từ `ollama list`.

```powershell
$env:MODEL_PROVIDER = "ollama"
$env:MODEL_NAME = "<tên mô hình đã tải>"
$env:API_BASE_URL = "http://localhost:11434/api/chat"
python codebase/web.py --ai
```

Ollama sắp xếp các lựa chọn trong từng bậc phác đồ dựa trên ID thuốc và ca tổng hợp. Backend giữ thứ tự mặc định nếu Ollama lỗi hoặc trả sai danh sách ID. Liều và nội dung đơn do bác sĩ nhập.

| API local | Công dụng |
|---|---|
| `GET /api/health` | Kiểm tra backend và cấu hình AI |
| `GET /api/guidelines` | Danh sách chẩn đoán và phác đồ mô phỏng |
| `GET /api/reference-prescriptions` | Đơn thuốc mẫu hiển thị ngay khi mở màn hình tạo đơn |
| `GET /api/drugs?q=...&unit=...` | Tìm thuốc, lọc theo đơn vị |
| `POST /api/prescriptions/suggest` | Nhận chuỗi `diagnosis` như `viêm mũi dị ứng, tăng huyết áp` và trả đơn giả lập, phác đồ, thuốc tham khảo |
| `POST /api/prescriptions/review` | Kiểm tra dữ liệu khám và các dòng thuốc trước khi bác sĩ rà soát |

Chạy `python scripts/test_web.py` để kiểm tra các API trên loopback.

## Chạy CLI trong 3 phút

Yêu cầu **Python 3.10 trở lên** (chỉ dùng thư viện chuẩn cho `run.py` và `codebase/`, **không cần `pip install`**).

1. Tạo file `.env` từ `.env.example` và điền key thật:
   ```ini
   MODEL_PROVIDER=gemini
   MODEL_NAME=gemini-2.5-flash-lite
   API_KEY=<key của nhóm>
   ```
2. Chạy thử luồng tương tác (HITL):
   ```powershell
   python run.py
   ```
3. Kiểm tra toàn bộ benchmark & metric spec:
   ```powershell
   python run.py check
   ```

---

## Lệnh

| Lệnh | Làm gì |
|---|---|
| `python run.py` | Chạy bản chạy thử tương tác CLI kèm bước bác sĩ kiểm duyệt `[A]/[E]/[R]` |
| `python run.py check` | Kiểm `eval/benchmark.csv`, `eval/metric_spec.yaml` và `TEAMS.md` |
| `python run.py eval --try` | Chạy thử 3 câu đầu để kiểm tra kết nối model và số token |
| `python run.py eval` | Chạy đủ 20 câu thử qua `codebase/agent.py` -> `eval/run-N.csv` + `traces/run-N.jsonl` |
| `python scripts/grade_run.py eval/run-1.csv` | Hỗ trợ chấm tự động cột `pass` và `ghi_chu` theo schema & guardrails |
| `python run.py score eval/run-1.csv` | Tính % đạt tổng và theo từng loại (`thuong`, `kho`, `tu_choi`) |
| `python run.py simulate --try` | Thử mô phỏng chi phí 10 phiên |
| `python run.py simulate --rate-from eval/run-2.csv` | Mô phỏng chi phí 50 phiên dùng thật -> `cost/simulate-N.csv` + tóm tắt |
| `python scripts/test_guardrails.py` | Chạy unit test kiểm tra 8 quy tắc an toàn Python thuần và Pre-Gate |

---

## Phần nào thật, phần nào giả

| Thành phần | Thật / Giả | Ghi chú |
|---|---|---|
| Lời gọi AI Core (`codebase/ai.py`) | **Thật** | Model đo thật: `gemini-3.5-flash-lite` (lấy token thật từ `usageMetadata` của API) |
| Safety Guardrails & Tính giá (`codebase/tools.py`) | **Thật (Python thuần)** | 8 quy tắc kiểm tra an toàn + tính giá deterministic |
| Dữ liệu bệnh nhân & đơn giá (`data/processed/`) | **Giả lập (`synthetic`, `seed=42`)** | 100 ca tổng hợp hóa (0% PII); 83 thuốc đối chiếu Dược thư QG VN & `Bài LL 5`, giá giả lập bội số 500đ |

## Dùng AI vào việc gì

Nhóm dùng AI hỗ trợ viết script làm sạch/tổng hợp hóa dữ liệu (`seed=42`), triển khai khung code Python (`codebase/tools.py`, `codebase/agent.py`, `codebase/ai.py`) và rà soát tài liệu. Toàn bộ quy tắc an toàn, đối chiếu nguồn y khoa, phỏng vấn người dùng và chấm kiểm định đều do thành viên nhóm kiểm soát; chi tiết xem [docs/ai-usage.md](docs/ai-usage.md).
